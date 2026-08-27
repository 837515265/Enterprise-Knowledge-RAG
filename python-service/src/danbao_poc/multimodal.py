from __future__ import annotations

"""多模态 VLM 描述（参考 LightRAG ``analyze_multimodal`` + ``multimodal_context.py``）。

对 ``middle_document["images"]`` 里的每张 docx 内嵌截图做「上下文感知 VLM 描述」，
产出与现有文字 chunk 完全同构的 ``visual_chunk``。图片不是被「看图」检索，
而是被 VLM 先翻译成文字，文字再进现有的 chunk → 抽取 → MySQL/ES 全链路。

复用现有后端（``call_qianfan_vlm_ocr`` + ``ModelRouter``），不引入 LightRAG 存储/检索。
"""

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from danbao_poc.common import clean_text
from danbao_poc.model_router import ModelRoute, ModelRouter
from danbao_poc.ocr_client import call_qianfan_vlm_ocr

VISUAL_TYPE_ENUM = ("Screenshot", "Chart", "Flowchart", "Architecture", "GeneralImage", "Other")

_CAPTION_PROMPT = (
    "你是担保业务操作手册的截图理解助手。下面是一张操作界面截图。\n"
    "这是操作手册里的【第 {step} 步 / 共 {total} 步】截图，按操作顺序排列。\n"
    "请结合上一步截图和前后文操作步骤，把截图里所有对用户办理业务有用的信息都忠实写出来，"
    "输出严格 JSON（不要 markdown 代码块包裹，不要输出解释）：\n"
    '{"name": "截图的简短标题（如「缴费-选择支付方式」）", '
    '"type": "Screenshot|Chart|Flowchart|Architecture|GeneralImage|Other", '
    '"description": "详细描述截图可见内容：界面标题、按钮、输入框、菜单、金额、账户、卡号、'
    '提示文字、操作含义、当前处于哪一步。数字和名称（银行、公司、账号）务必照抄不要遗漏。"}\n\n'
    "【上一步截图描述】\n{prev}\n\n"
    "【图前文字】\n{leading}\n\n【图后文字】\n{trailing}\n"
)

_CHUNK_TYPE_BY_VISUAL = {
    "Screenshot": "image",
    "Chart": "chart",
    "Flowchart": "diagram",
    "Architecture": "diagram",
    "GeneralImage": "image",
    "Other": "image",
}


def _chunk_type_for(visual_type: str) -> str:
    return _CHUNK_TYPE_BY_VISUAL.get(visual_type or "", "image")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _resolve_vision_route() -> Any:
    """VISION 前缀优先；未配置则回退 DEFAULT_MODEL。

    注意两点：
    1. VLM/OCR 后端走 ``{prefix}_MODEL`` 键（见 ``document_parser._parse_via_vlm_ocr``），
       不是 ModelRouter 的 ``{prefix}_MODEL_NAME`` 键。
    2. 有的环境 DEFAULT 本身就是视觉模型（dev 的 ``qwen3.5-27b-zf`` 支持读图），
       这时即使不配 VISION 也能直接复用 DEFAULT。
    """
    model = os.getenv("VISION_MODEL", "").strip()
    base_url = os.getenv("VISION_BASE_URL", "").strip()
    if model and base_url:
        api_key = os.getenv("VISION_API_KEY", os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")).strip()
        timeout = int(os.getenv("VISION_TIMEOUT", os.getenv("DEFAULT_MODEL_TIMEOUT", "600")))
        return ModelRoute(prefix="VISION", tier="primary", model_name=model, base_url=base_url, api_key=api_key, timeout=timeout)
    return ModelRouter().select("DEFAULT")


def _parse_caption_json(raw: str) -> dict[str, Any] | None:
    text = raw or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _caption_one(
    *,
    image: dict[str, Any],
    leading: str,
    trailing: str,
    route: Any,
    request_id: str | None,
    step: int,
    total: int,
    prev: str,
) -> dict[str, Any] | None:
    image_bytes = image.get("bytes")
    if not image_bytes:
        return None
    fmt = image.get("format") or "png"
    prompt = (
        _CAPTION_PROMPT
        .replace("{step}", str(step))
        .replace("{total}", str(total))
        .replace("{prev}", clean_text(prev) or "（无）")
        .replace("{leading}", clean_text(leading) or "（无）")
        .replace("{trailing}", clean_text(trailing) or "（无）")
    )
    try:
        result = call_qianfan_vlm_ocr(
            base_url=route.base_url,
            model=route.model_name,
            api_key=route.api_key,
            image_bytes=image_bytes,
            image_mime_type=f"image/{fmt}",
            prompt=prompt,
            timeout=route.timeout,
            append_think=False,
        )
    except Exception:
        return None
    parsed = _parse_caption_json(result.get("markdown") or "")
    if not parsed or not parsed.get("description"):
        return None
    name = clean_text(parsed.get("name")) or clean_text(image.get("docpr_name")) or "操作截图"
    visual_type = clean_text(parsed.get("type"))
    if visual_type not in VISUAL_TYPE_ENUM:
        visual_type = "Other"
    return {
        "name": name,
        "type": visual_type,
        "description": clean_text(parsed.get("description")),
        "vlm_model": route.model_name,
    }


def analyze_images(
    middle_document: dict[str, Any],
    *,
    parse_options: dict[str, Any] | None,
    profile: str,
    file_center: Any | None = None,
    request_id: str | None = None,
    surrounding_window: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """对每张图做上下文感知 VLM 描述，返回 (visual_chunks, visual_assets)。

    - visual_chunks: 每张图一个 chunk，字段与 ``chunk_generation._make_chunk`` 完全同构，
      可直接并入 ``chunks`` 走 catalog/extract/storage。
    - visual_assets:  每张图的原始元信息（原图资源 / VLM 结果，供 file_visual_asset 落库）。

    图片字节在分析完会被就地剥离（``image["bytes"] = None``），避免随 middle_document
    持久化出几十 MB 的 JSON。
    """
    from danbao_poc.chunk_generation import _make_chunk

    images = middle_document.get("images") or []
    if not images:
        return [], []

    max_images = _int_env("MULTIMODAL_MAX_IMAGES_PER_DOC", 0)
    if max_images > 0:
        images = images[:max_images]

    # 收集 surrounding：用提图阶段产出的文档流顺序（若调用方已注入 surrounding 则复用）
    document_title = clean_text(middle_document.get("file_name") or "") or "document"
    for stem in (".docx", ".doc", ".DOCX"):
        if document_title.endswith(stem):
            document_title = document_title[: -len(stem)]
            break

    def _surrounding_for(image: dict[str, Any], index: int) -> tuple[str, str]:
        flow = middle_document.get("_docx_flow") or []
        if flow:
            from danbao_poc.docx_image_extractor import surrounding_texts

            flow_index = image.get("flow_index")
            if flow_index is None:
                flow_index = index
            return surrounding_texts(flow, int(flow_index), window=surrounding_window)
        leading = clean_text(image.get("surrounding_leading")) or ""
        trailing = clean_text(image.get("surrounding_trailing")) or ""
        return leading, trailing

    route = _resolve_vision_route()
    concurrency = max(1, _int_env("MULTIMODAL_VLM_CONCURRENCY", 8))
    chain_steps = os.getenv("MULTIMODAL_CHAIN_STEPS", "false").strip().lower() in {"1", "true", "yes", "on"}
    upload_images = os.getenv("MULTIMODAL_UPLOAD_IMAGES", "false").strip().lower() in {"1", "true", "yes", "on"}

    visual_assets: list[dict[str, Any]] = []
    captions: dict[int, dict[str, Any]] = {}
    total = len(images)

    def _caption_at(index: int, prev: str) -> dict[str, Any] | None:
        image = images[index]
        leading, trailing = _surrounding_for(image, index)
        return _caption_one(
            image=image,
            leading=leading,
            trailing=trailing,
            route=route,
            request_id=request_id,
            step=index + 1,
            total=total,
            prev=prev,
        )

    if chain_steps:
        # 串行 + 步骤链：把上一步截图描述喂给当前步骤，VLM 能说出跨图顺序关联
        prev_text = "（无）"
        for index in range(total):
            caption = _caption_at(index, prev_text)
            if caption:
                captions[index] = caption
                prev_text = f"[{caption['name']}] {caption['description'][:200]}"
    else:
        # 全并发（不链步骤，只带步序号）
        def _run(index: int) -> tuple[int, dict[str, Any] | None]:
            return index, _caption_at(index, "（无）")

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_run, i) for i in range(total)]
            for future in as_completed(futures):
                try:
                    index, caption = future.result()
                except Exception:
                    continue
                if caption:
                    captions[index] = caption

    visual_chunks: list[dict[str, Any]] = []
    seq = 100000
    for index, image in enumerate(images):
        image_id = image.get("image_id") or f"img_p{image.get('page_no') or 0}_{index + 1:04d}"
        caption = captions.get(index)
        file_center_file_id = image.get("file_center_file_id")
        # 可选：图字节上传文件中心（回看原图用）
        if upload_images and file_center is not None and image.get("bytes"):
            try:
                upload = file_center.upload_file(
                    file_name=f"{document_title}.img{index + 1:03d}.{image.get('format') or 'png'}",
                    file_bytes=image["bytes"],
                    request_id=request_id,
                )
                file_center_file_id = str(upload.get("fileId") or upload.get("file_id") or upload.get("id") or "")
            except Exception:
                file_center_file_id = file_center_file_id or ""

        asset = {
            "image_id": image_id,
            "page_no": image.get("page_no"),
            "block_id": image.get("block_id"),
            "step_no": index + 1,
            "step_total": total,
            "bbox": image.get("bbox") or [],
            "format": image.get("format"),
            "file_center_file_id": file_center_file_id or None,
            "name": caption.get("name") if caption else (image.get("docpr_name") or "操作截图"),
            "visual_type": caption.get("type") if caption else "Other",
            "description": caption.get("description") if caption else "",
            "vlm_model": caption.get("vlm_model") if caption else None,
            "status": "success" if caption else "failed",
        }
        visual_assets.append(asset)
        # 就地剥离字节，避免持久化爆炸
        image["bytes"] = None
        image["file_center_file_id"] = file_center_file_id or None

        if not caption:
            continue
        chunk = _make_chunk(
            chunk_key=f"img_{image_id}",
            seq_no=seq + index,
            chunk_type=_chunk_type_for(caption["type"]),
            section_type="image",
            section_id=f"img:{image_id}",
            chunk_group_id=f"img:{image_id}",
            title=caption["name"],
            title_path=[document_title, caption["name"]],
            content=caption["description"],
            document_title=document_title,
            page_start=image.get("page_no"),
            page_end=image.get("page_no"),
            block_ids=[image.get("block_id")] if image.get("block_id") else [],
            metadata={
                "visual_type": caption["type"],
                "file_center_file_id": file_center_file_id or None,
                "visual_asset_id": image_id,
                "step_no": index + 1,
                "step_total": total,
                "profile": profile,
                "vlm_model": caption["vlm_model"],
                "confidence": "HIGH",
                "source_kind": "image",
            },
            bbox=image.get("bbox") or [],
        )
        visual_chunks.append(chunk)

    return visual_chunks, visual_assets


# ==========================================================================================
# 多图联合解析（整文件 / 整批图片一次 VLM 调用）
# 参考 LightRAG 多模态能力，扩展为「全量多图理解全局 + 单图高精复核细节」分层体系。
# 当前先落地多图 Global Pass：一次调用同时产出 每图事实(images) + 跨图关系(relations) + 文档级分组(groups)。
# ==========================================================================================

_MULTI_IMAGE_PROMPT = """你是一名企业级多模态文档知识抽取模型。下面是一个文档的全部截图（按文档出现顺序排列），每张截图前有它的 image_id、所在章节、前文、后文。

你的任务：
1. 对每张截图独立抽取事实；
2. 识别截图之间的语义关系（重复、前后步骤、总览-详情、同系列等）；
3. 把多张截图组合成流程/系列（group）。

【关系类型】只能用这些：
DUPLICATE / NEAR_DUPLICATE / NEXT_STEP / CONTINUATION / BEFORE_AFTER / OVERVIEW_DETAIL / SAME_SERIES

【image_type】只能用这些：
ui_screenshot / chart / map / table / diagram / photo / document_scan / other

只输出一个合法 JSON 对象（不要 markdown 代码块包裹，不要输出分析过程），结构：

{
  "images": [
    {
      "image_id": "IMG_0001",
      "image_type": "ui_screenshot",
      "title": "简短标题",
      "description": "详细描述：页面/模块、按钮、输入框、金额、账号、订单号、状态、操作含义",
      "entities": ["实体名"],
      "key_facts": ["关键事实"],
      "keywords": ["关键词"]
    }
  ],
  "relations": [
    {"source_image_id": "IMG_0001", "target_image_id": "IMG_0002", "relation_type": "NEXT_STEP", "description": "点击立即缴费后进入收银台", "confidence": 0.9}
  ],
  "groups": [
    {
      "group_id": "GROUP_001",
      "group_type": "procedure",
      "topic": "保费缴纳流程",
      "ordered_image_ids": ["IMG_0001", "IMG_0002"],
      "summary": "流程概述",
      "steps": [
        {"step_no": 1, "step_name": "查询账单", "description": "步骤说明", "evidence_images": [{"image_id": "IMG_0001", "role": "primary"}]}
      ]
    }
  ]
}

【硬性要求】
- 必须严格使用给定的 image_id，不得自创、修改或猜测；
- 每张图片必须恰好出现在 images 数组里一次，不得遗漏；
- 数字和名称（账号、金额、订单号、业务编号）务必照抄，无法确定的不要编造；
- relations/groups 里引用的 image_id 必须真实存在于 images 中；
- 不要因为两张图相邻就判 NEXT_STEP，要结合内容判断；
- 相似但状态不同的图（如提交前/提交后）标 NEAR_DUPLICATE，不要标 DUPLICATE。
"""


def build_image_manifest(middle_document: dict[str, Any], *, surrounding_window: int = 3) -> dict[str, Any]:
    """从 middle_document 构建 Image Manifest：稳定 image_id + 前文/后文 + provenance。

    VLM 只负责语义关系，程序负责确定性 ID 映射（image_id → image_file_id 等），
    这一层就是后续 bind_procedure_evidence 的确定性来源。
    """
    from danbao_poc.docx_image_extractor import surrounding_texts

    images = middle_document.get("images") or []
    flow = middle_document.get("_docx_flow") or []
    document_title = clean_text(middle_document.get("file_name") or "") or "document"
    for stem in (".docx", ".doc", ".DOCX"):
        if document_title.endswith(stem):
            document_title = document_title[: -len(stem)]
            break

    items: list[dict[str, Any]] = []
    for idx, img in enumerate(images, 1):
        image_id = img.get("image_id") or f"IMG_{idx:04d}"
        flow_index = img.get("flow_index")
        if flow_index is not None:
            leading, trailing = surrounding_texts(flow, int(flow_index), window=surrounding_window)
        else:
            leading = clean_text(img.get("surrounding_leading")) or ""
            trailing = clean_text(img.get("surrounding_trailing")) or ""
        items.append(
            {
                "image_id": image_id,
                "order": idx,
                "page_no": img.get("page_no"),
                "leading_text": clean_text(leading) or "",
                "trailing_text": clean_text(trailing) or "",
                "image_file_id": img.get("file_center_file_id"),
                "bytes": img.get("bytes"),
                "format": img.get("format") or "png",
            }
        )
    return {
        "document_id": document_title,
        "document_title": document_title,
        "images": items,
    }


def call_multi_image_vlm(
    *,
    base_url: str,
    model: str,
    api_key: str,
    manifest_images: list[dict[str, Any]],
    prompt: str,
    timeout: int = 600,
) -> str:
    """一次调用把多张图（带 image_id + 前后文标签）发给 VLM，返回模型原始文本。

    文本标签紧挨对应图片（交替发送），避免模型对 image_id 与图片的映射出错。
    """
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for item in manifest_images:
        image_bytes = item.get("bytes")
        if not image_bytes:
            continue
        fmt = item.get("format") or "png"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        label = item.get("image_id") or ""
        leading = item.get("leading_text") or ""
        trailing = item.get("trailing_text") or ""
        content.append({"type": "text", "text": f"[{label}]\n前文：{leading}\n后文：{trailing}"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{fmt};base64,{b64}"},
            }
        )
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": content}],
    }
    normalized_base_url = base_url.rstrip("/")
    response = requests.post(
        f"{normalized_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key or 'EMPTY'}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    try:
        content_out = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"multi-image vlm returned invalid response: {data}") from exc
    if isinstance(content_out, list):
        text_parts = []
        for item in content_out:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                text_parts.append(item)
        return "\n".join(part for part in text_parts if part).strip()
    return str(content_out or "").strip()


def analyze_multi_images(
    middle_document: dict[str, Any],
    *,
    parse_options: dict[str, Any] | None = None,
    profile: str = "general_document",
    file_center: Any | None = None,
    request_id: str | None = None,
    surrounding_window: int = 3,
) -> dict[str, Any]:
    """整文件多图联合解析（Global Pass）。

    返回：{"document": manifest, "images": [...], "relations": [...], "groups": [...]}
    其中 VLM 只输出 image_id；image_file_id / source_file_id 由程序在后续
    bind_procedure_evidence 阶段回填。
    """
    # 可选：先上传原图到文件中心（回显原图用），再建 manifest，这样 manifest 带上 file_center_file_id
    upload_images = os.getenv("MULTIMODAL_UPLOAD_IMAGES", "false").strip().lower() in {"1", "true", "yes", "on"}
    if upload_images and file_center is not None:
        doc_title = clean_text(middle_document.get("file_name") or "") or "document"
        for stem in (".docx", ".doc", ".DOCX"):
            if doc_title.endswith(stem):
                doc_title = doc_title[: -len(stem)]
                break
        for idx, image in enumerate(middle_document.get("images") or [], 1):
            if not image.get("bytes"):
                continue
            try:
                upload = file_center.upload_file(
                    file_name=f"{doc_title}.img{idx:03d}.{image.get('format') or 'png'}",
                    file_bytes=image["bytes"],
                    request_id=request_id,
                )
                image["file_center_file_id"] = str(upload.get("fileId") or upload.get("file_id") or upload.get("id") or "")
            except Exception:
                pass

    manifest = build_image_manifest(middle_document, surrounding_window=surrounding_window)
    manifest_images = manifest["images"]
    if not manifest_images:
        return {"document": manifest, "images": [], "relations": [], "groups": []}

    route = _resolve_vision_route()
    prompt = _MULTI_IMAGE_PROMPT
    raw = call_multi_image_vlm(
        base_url=route.base_url,
        model=route.model_name,
        api_key=route.api_key,
        manifest_images=manifest_images,
        prompt=prompt,
        timeout=route.timeout,
    )
    # VLM 调用完成后剥离图片字节：manifest 会随结果写 JSON artifact，
    # middle_document 会进 parse cache（json.dumps），bytes 都会导致序列化失败。
    for item in manifest_images:
        item.pop("bytes", None)
    for image in middle_document.get("images") or []:
        image["bytes"] = None
    parsed = _parse_caption_json(raw)
    if not parsed:
        return {"document": manifest, "images": [], "relations": [], "groups": [], "_raw": raw}
    if isinstance(parsed, dict):
        parsed.setdefault("document", manifest)
        return parsed
    return {"document": manifest, "images": [], "relations": [], "groups": [], "_raw": raw}


_IMAGE_TYPE_TO_CHUNK_TYPE = {
    "ui_screenshot": "image",
    "chart": "chart",
    "map": "image",
    "table": "table",
    "diagram": "diagram",
    "photo": "image",
    "document_scan": "image",
    "other": "image",
}


def _chunk_type_for_image_type(image_type: str | None) -> str:
    return _IMAGE_TYPE_TO_CHUNK_TYPE.get((image_type or "").lower(), "image")


def bind_procedure_evidence(result: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """程序侧校验 + 回填确定性 ID。

    VLM 只输出 image_id，这里：
    1. 校验 images/relations/groups 引用的 image_id 都真实存在于 manifest；
    2. 回填 image_file_id / order / page_no；
    3. 标记 manifest 里没有被任何 image_record 覆盖的 orphan；
    4. evidence_images 缺 role 时兜底（第一个 primary，其余 supporting）。
    """
    manifest_by_id: dict[str, dict[str, Any]] = {img["image_id"]: img for img in manifest.get("images") or []}

    # 1) images 校验 + 回填
    seen_ids: set[str] = set()
    for img in result.get("images") or []:
        img_id = img.get("image_id")
        if not img_id:
            continue
        meta = manifest_by_id.get(img_id)
        if meta is None:
            img["_missing_from_manifest"] = True
            continue
        seen_ids.add(img_id)
        img["image_file_id"] = meta.get("image_file_id")
        img["order"] = meta.get("order")
        img["page_no"] = meta.get("page_no")

    # 2) orphan：manifest 里没被任何 image_record 覆盖的图（漏图）
    orphan_ids = [iid for iid in manifest_by_id if iid not in seen_ids]
    result.setdefault("orphan_image_ids", orphan_ids)

    # 3) relations 校验
    for rel in result.get("relations") or []:
        src = rel.get("source_image_id")
        tgt = rel.get("target_image_id")
        rel["_valid"] = src in manifest_by_id and tgt in manifest_by_id

    # 4) groups 回填 + role 兜底
    for group in result.get("groups") or []:
        group.setdefault("source_file_id", manifest.get("document_id"))
        for step in group.get("steps") or []:
            evidence = step.get("evidence_images") or []
            for i, ev in enumerate(evidence):
                iid = ev.get("image_id")
                if iid and iid in manifest_by_id:
                    ev["image_file_id"] = manifest_by_id[iid].get("image_file_id")
                    ev["source_file_id"] = manifest.get("document_id")
                if not ev.get("role"):
                    ev["role"] = "primary" if i == 0 else "supporting"
    return result


def _group_content_text(group: dict[str, Any]) -> str:
    """Procedure chunk 的可检索文本：步骤语义 + 证据图片 IMG_id 嵌入对应步骤。"""
    lines: list[str] = []
    topic = group.get("topic") or "流程"
    lines.append(f"主题：{topic}")
    if group.get("summary"):
        lines.append(f"概述：{group['summary']}")
    for step in group.get("steps") or []:
        no = step.get("step_no", "")
        name = step.get("step_name") or ""
        desc = step.get("description") or ""
        primary = [e for e in (step.get("evidence_images") or []) if e.get("role") == "primary"]
        supporting = [e for e in (step.get("evidence_images") or []) if e.get("role") != "primary"]
        lines.append("")
        lines.append(f"步骤{no}：{name}")
        if desc:
            lines.append(desc)
        if primary:
            lines.append("主证据图片：" + "、".join(e.get("image_id") for e in primary if e.get("image_id")))
        if supporting:
            lines.append("辅助图片：" + "、".join(e.get("image_id") for e in supporting if e.get("image_id")))
    return "\n".join(lines)


def build_multimodal_chunks(
    result: dict[str, Any],
    manifest: dict[str, Any],
    *,
    profile: str = "general_document",
    source_file_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把多图解析结果转成 chunk 列表 + relations。

    - Image Chunk：每张图一个（chunk_type 由 image_type 映射），可独立检索；
    - Procedure/Group Chunk：每个 group 一个（chunk_type='image_group'），content=步骤语义，
      metadata 存 steps[].evidence_images[].image_file_id（答案阶段精准回图用）；
    - relations：跨图关系（NEXT_STEP/DUPLICATE/...），先随 group chunk metadata 携带，
      后续再进 Neo4j 图。
    """
    from danbao_poc.chunk_generation import _make_chunk

    document_title = manifest.get("document_title") or "document"
    bound = bind_procedure_evidence(result, manifest)
    chunks: list[dict[str, Any]] = []

    # Image Chunks
    seq = 100000
    for idx, img in enumerate(bound.get("images") or []):
        if img.get("_missing_from_manifest"):
            continue
        image_id = img.get("image_id") or f"IMG_{idx + 1:04d}"
        image_type = img.get("image_type") or "other"
        description = img.get("description") or ""
        chunks.append(
            _make_chunk(
                chunk_key=f"img_{image_id}",
                seq_no=seq + idx,
                chunk_type=_chunk_type_for_image_type(image_type),
                section_type="image",
                section_id=f"img:{image_id}",
                chunk_group_id=f"img:{image_id}",
                title=img.get("title") or "截图",
                title_path=[document_title, img.get("title") or "截图"],
                content=description,
                document_title=document_title,
                page_start=img.get("page_no"),
                page_end=img.get("page_no"),
                block_ids=[],
                metadata={
                    "visual_type": image_type,
                    "image_id": image_id,
                    "file_center_file_id": img.get("image_file_id"),
                    "source_file_id": source_file_id,
                    "entities": img.get("entities") or [],
                    "key_facts": img.get("key_facts") or [],
                    "keywords": img.get("keywords") or [],
                    "profile": profile,
                    "source_kind": "image",
                },
                bbox=[],
            )
        )

    # Group Chunks（Procedure 等）
    for gidx, group in enumerate(bound.get("groups") or []):
        group_id = group.get("group_id") or f"GROUP_{gidx + 1:03d}"
        group_content = _group_content_text(group)
        chunks.append(
            _make_chunk(
                chunk_key=f"img_group_{group_id}",
                seq_no=200000 + gidx,
                chunk_type="image_group",
                section_type="image_group",
                section_id=f"group:{group_id}",
                chunk_group_id=f"group:{group_id}",
                title=group.get("topic") or "流程",
                title_path=[document_title, group.get("topic") or "流程"],
                content=group_content,
                document_title=document_title,
                page_start=None,
                page_end=None,
                block_ids=[],
                metadata={
                    "group_id": group_id,
                    "group_type": group.get("group_type"),
                    "topic": group.get("topic"),
                    "source_file_id": source_file_id or manifest.get("document_id"),
                    "steps": group.get("steps") or [],
                    "ordered_image_ids": group.get("ordered_image_ids") or [],
                    "profile": profile,
                    "source_kind": "image_group",
                },
                bbox=[],
            )
        )

    return chunks, bound.get("relations") or []
