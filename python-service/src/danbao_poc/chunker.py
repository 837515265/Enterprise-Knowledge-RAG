from __future__ import annotations

import json
import os
import re
from typing import Any

from .common import clean_text, stable_hash
from .chunker_common import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    doc_title,
    embedding_text,
    flatten_blocks,
    is_page_number_block,
    split_content,
)


SECTION_ALIASES = {
    "service_object": ["服务对象", "支持对象", "适用客户", "服务主体"],
    "access_condition": ["准入条件", "准入要求", "申请条件", "办理条件"],
    "credit_purpose": ["授信用途", "贷款用途", "资金用途"],
    "credit_limit": ["额度测算", "授信额度", "贷款额度", "担保额度", "授信金额", "最高额度"],
    "credit_term": ["授信期限", "贷款期限", "担保期限", "最长期限", "期限及还款方式", "还款方式"],
    "risk_mitigation": ["风险缓释", "风险控制", "风险管控", "风控措施", "风险分担", "财政分险", "分险比例"],
    "counter_guarantee": ["反担保", "抵押反担保", "保证反担保"],
    "applicable_scope": ["适用范围", "适用地区", "支持区域"],
    "business_process": ["办理流程", "业务流程", "申请流程"],
    "required_materials": ["申请资料", "申报材料", "所需材料", "项目资料清单", "资料清单"],
    "guarantee_rate": ["担保费率", "担保费", "费率"],
    "loan_rate": ["贷款利率", "利率", "年利率"],
    "business_model": ["业务模式", "业务方式", "运营模式"],
    "storage_requirement": ["储存要求", "仓储要求", "质押物储存"],
    "supervision_management": ["监管管理", "监管要求", "监管公司管理", "仓储企业管理"],
    "cross_dept_mechanism": ["协同管理", "协同机制", "跨部门协同"],
    "supervision_fee": ["监管费", "收费管理", "监管费收费"],
    "business_block": ["业务板块", "业务类别", "产品类别"],
}


TOP_LEVEL_BLOCK_RE = r"^[一二三四五六七八九十]+[、.．]\s*.{1,40}(?:类|业务|产品|板块|方案)$"


def classify_section(title: str) -> str:
    normalized_title = clean_text(title)
    if re.match(TOP_LEVEL_BLOCK_RE, normalized_title):
        return "business_block"
    for section_type, aliases in SECTION_ALIASES.items():
        if any(alias in normalized_title for alias in aliases):
            return section_type
    return "other"


def _section_text(section: dict[str, Any]) -> str:
    return clean_text("\n".join(block.get("text") or "" for block in section.get("blocks", [])))


def _is_tiny_section(section: dict[str, Any], min_content_chars: int) -> bool:
    text = _section_text(section)
    if not text:
        return False
    if len(section.get("blocks") or []) >= 2 and section.get("section_type") not in {"other", "business_block"}:
        return False
    if len(text) < 30:
        return True
    if len(section.get("blocks") or []) <= 1 and re.match(r"^\s*(?:[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十0-9]+）|第[一二三四五六七八九十0-9]+[章节条款]).{0,40}$", text):
        return True
    return False


def _merge_section_prefix(prefix: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    merged = dict(target)
    merged["blocks"] = list(prefix.get("blocks", [])) + list(target.get("blocks", []))
    if prefix.get("section_type") and prefix.get("section_type") != "other":
        merged["section_type"] = prefix.get("section_type")
    merged["title"] = prefix.get("title") or target.get("title")
    for key in ["section_id", "hierarchy_level", "parent_section_id", "business_block_id", "business_block_title", "reason"]:
        if prefix.get(key) not in (None, ""):
            merged[key] = prefix.get(key)
    warnings = list(prefix.get("planner_warnings") or []) + list(target.get("planner_warnings") or [])
    warnings.append("merged_tiny_section_forward")
    merged["planner_warnings"] = warnings
    return merged


def _merge_section_suffix(target: dict[str, Any], suffix: dict[str, Any]) -> dict[str, Any]:
    merged = dict(target)
    merged["blocks"] = list(target.get("blocks", [])) + list(suffix.get("blocks", []))
    warnings = list(target.get("planner_warnings") or []) + list(suffix.get("planner_warnings") or [])
    warnings.append("merged_tiny_section_backward")
    merged["planner_warnings"] = warnings
    return merged


# ─── Chunk 摘要 Prompt ────────────────────────────────────────

_SUMMARY_SYSTEM = (
    "你是企业知识库文档摘要器。\n"
    "你的目标是为文档片段生成简洁、信息密度高的检索摘要，帮助检索系统判断这段内容是否与用户问题相关。\n"
    "规则：\n"
    "1. 只返回 JSON，格式为 {\"summary\": \"...\"}。\n"
    "2. 摘要不超过 120 字。\n"
    "3. 摘要必须保留核心事实和关键数值（如金额、比例、期限、条件）。\n"
    "4. 不要使用'本部分介绍了…'这类空泛表述，直接概括内容实质。\n"
    "5. 如果片段只有标题没有正文，摘要应如实说明'仅包含章节标题，正文内容在后续片段中'。"
)


def summarize_chunk(title: str, content: str) -> str:
    backend = os.getenv("CHUNK_SUMMARY_BACKEND", "llm").strip().lower()
    fallback = content[:180]
    if backend != "llm":
        return fallback
    try:
        from .openai_compat import JsonChatClient

        client = JsonChatClient("SUMMARY", default_model=True)
        result = client.complete_json(
            system_prompt=_SUMMARY_SYSTEM,
            user_prompt=(
                "请为以下文档片段生成检索摘要。\n"
                "要求：保留关键数值和核心条件，不超过120字，不要空泛概括。\n"
                "只返回 {\"summary\": \"...\"}。\n\n"
                f"标题：{title}\n正文：{content[:4000]}"
            ),
            temperature=0,
            max_tokens=300,
        )
        summary = clean_text(result.get("summary"))
        return summary[:300] if summary else fallback
    except Exception:
        return fallback


# ─── Chunk Planner 配置 ───────────────────────────────────────

def _chunk_plan_max_chars() -> int:
    """Planner 的最大输入字符数。32K token 模型需降低此值以避免溢出。"""
    try:
        return max(10000, int(os.getenv("BUSINESS_PLAN_CHUNK_PLAN_MAX_CHARS", "32000")))
    except Exception:
        return 32000


# Planner 每个 block 的文本截断长度（只需识别边界，不需完整正文）
_PLANNER_BLOCK_TEXT_LIMIT = int(os.getenv("PLANNER_BLOCK_TEXT_LIMIT", "120"))


def _block_label(block: dict[str, Any], index: int) -> str:
    return clean_text(block.get("block_id")) or f"block_{index:04d}"


def _compact_blocks_for_llm(blocks: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    max_chars = _chunk_plan_max_chars()
    rows: list[str] = []
    block_index: dict[str, int] = {}
    size = 0
    for index, block in enumerate(blocks):
        block_id = _block_label(block, index + 1)
        block_index[block_id] = index
        text = clean_text(block.get("text"))
        # P0 优化：截断每个 block 的文本，Planner 只需识别边界
        if len(text) > _PLANNER_BLOCK_TEXT_LIMIT:
            text = text[:_PLANNER_BLOCK_TEXT_LIMIT] + "…"
        row = f"[id:{block_id}][page:{block.get('page_no') or ''}] {text}\n"
        if rows and size + len(row) > max_chars:
            break
        rows.append(row)
        size += len(row)
    return "".join(rows), block_index


# ─── Chunk Planner Prompt（核心优化） ─────────────────────────

_PLANNER_SYSTEM = (
    "你是担保/授信业务方案分段规划器。你必须严格按 JSON 格式返回分段结果。\n\n"
    "## 你的工作\n"
    "1. 分析全文的 block 列表，识别文档的章节结构。\n"
    "2. 输出每个 section 的 start_block_id、end_block_id、title、section_type。\n"
    "3. 确保每个 section 包含完整的标题+正文内容。\n\n"
    "## 核心规则（必须严格遵守）\n\n"
    "### 规则1：标题必须包含其下全部正文\n"
    "每个 section 从其标题行开始，到下一个同级标题前一行结束。\n"
    "绝对禁止产生只包含标题而不包含正文的 section。\n"
    "如果一个 section 的全部文本加起来不超过 30 个字，说明你切错了。\n\n"
    "### 规则2：编号条款不是独立 section\n"
    "1.、2.、3.、（1）、（2）、①②③ 这类编号条款是上级章节的正文内容，\n"
    "不要把它们单独拆成独立的 section。\n"
    "只有中文数字大标题（如 一、 二、 （一） （二））才可能是 section 边界。\n\n"
    "### 规则3：多业务板块文档\n"
    "如果文档包含多个业务板块（如 一、农产品贸易类 / 二、惠农电商类），\n"
    "每个板块是一个独立的一级结构，板块内的（一）服务对象、（二）准入条件等是二级结构。\n"
    "二级 section 的 section_type 必须与所在板块对应。\n\n"
    "### 规则4：附件和资料清单\n"
    "附件、资料清单、表格模板应归为 required_materials 或 other，\n"
    "绝对不要并入前一个业务章节的末尾。\n\n"
    "### 规则5：页码行\n"
    "形如 — 3 — 或 — 12 — 的行是页码，不是内容，忽略它们。\n\n"
    "### 规则6：section_type 白名单\n"
    "section_type 只能从白名单中选择，不确定时填 other。\n\n"
    "### 规则7：多板块 metadata\n"
    "如果 section 属于某个业务板块，必须输出 business_block_id 和 business_block_title。\n"
    "同一业务板块下的二级 section 使用相同 business_block_id。"
)


def _build_planner_prompt(document_title: str, block_text: str, allowed_section_types: list[str]) -> str:
    schema = {
        "sections": [
            {
                "section_id": "block1_access_condition",
                "business_block_id": "block1",
                "business_block_title": "一、农产品贸易类",
                "title": "（二）准入条件",
                "section_type": "access_condition",
                "hierarchy_level": 2,
                "parent_section_id": "block1",
                "start_block_id": "p2_b014",
                "end_block_id": "p3_b010",
                "reason": "从准入条件标题开始，包含其后全部6条准入条件（1.~6.），到下一个同级标题（三）授信额度前结束",
            }
        ]
    }

    return (
        f"请对以下担保/授信方案文档进行语义分段规划。\n\n"
        f"文档标题：{document_title}\n"
        f"section_type 白名单：{json.dumps(allowed_section_types, ensure_ascii=False)}\n\n"
        "## 正确 vs 错误分段对比\n\n"
        "❌ 错误示例（标题和正文被分离）：\n"
        '{"sections": [\n'
        '  {"title": "（二）准入条件", "start_block_id": "p2_b014", "end_block_id": "p2_b014",\n'
        '   "reason": "准入条件标题"},\n'
        '  {"title": "1.符合…", "start_block_id": "p2_b015", "end_block_id": "p2_b016",\n'
        '   "section_type": "other", "reason": "第一条准入条件"},\n'
        '  {"title": "2.须依法…", "start_block_id": "p2_b017", "end_block_id": "p2_b019",\n'
        '   "section_type": "other", "reason": "第二条准入条件"}\n'
        "]}\n"
        "↑ 这样切是错误的！标题 section 只有7个字，子条款被拆成独立的 other section。\n\n"
        "✅ 正确示例（标题和全部正文在同一个 section）：\n"
        '{"sections": [\n'
        '  {"title": "（二）准入条件", "start_block_id": "p2_b014", "end_block_id": "p3_b010",\n'
        '   "section_type": "access_condition",\n'
        '   "reason": "从准入条件标题开始，包含全部6条准入条件（1.~6.），到下一个同级标题（三）授信额度前结束"}\n'
        "]}\n"
        "↑ 标题+全部子条款正文在同一个 section 中，section_type 正确标记。\n\n"
        "## 自检清单（输出前必须逐条检查）\n"
        "1. 是否有 section 的全部文本不超过 30 个字？如果有，说明标题和正文被分离了，请修正。\n"
        "2. 是否把 1./2./3./(1)/(2) 等编号条款单独切成了 section？如果有，请合并到父级章节。\n"
        "3. 所有 section 的 block 范围是否连续不重叠？\n"
        "4. start_block_id 和 end_block_id 是否都来自输入 block 列表？\n"
        "5. 附件/资料清单是否被错误地并入了前一个业务章节？\n"
        "6. 多业务板块文档的二级 section 是否都填写了 business_block_id/business_block_title？\n\n"
        f"返回结构示例：{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"全文 block 列表（共 {len(block_text.splitlines())} 行）：\n{block_text}"
    )


def _llm_plan_sections(blocks: list[dict[str, Any]], document_title: str) -> tuple[list[dict[str, Any]], str]:
    if not blocks:
        return [], "empty"
    if os.getenv("BUSINESS_PLAN_CHUNK_PLANNER", "llm").strip().lower() != "llm":
        return _single_section(blocks, document_title), "single_fallback_disabled"

    max_chars = _chunk_plan_max_chars()
    # 估算全部 blocks 压缩后的总字符数
    total_chars = sum(min(len(clean_text(b.get("text")) or ""), _PLANNER_BLOCK_TEXT_LIMIT) + 40 for b in blocks)

    if total_chars <= max_chars:
        # 短文档：单次规划
        return _llm_plan_single_pass(blocks, document_title)

    # P2: 长文档 — 两阶段规划
    return _llm_plan_two_stage(blocks, document_title, max_chars)


def _llm_plan_single_pass(blocks: list[dict[str, Any]], document_title: str) -> tuple[list[dict[str, Any]], str]:
    """短文档单次 LLM 规划。"""
    block_text, block_index = _compact_blocks_for_llm(blocks)
    allowed_section_types = sorted(SECTION_ALIASES.keys()) + ["other"]
    prompt = _build_planner_prompt(document_title, block_text, allowed_section_types)

    try:
        from .openai_compat import JsonChatClient
        client = JsonChatClient("CHUNK_PLANNER", default_model=True, enable_fallback=True)
        result = client.complete_json(
            system_prompt=_PLANNER_SYSTEM,
            user_prompt=prompt,
            temperature=0,
            max_tokens=4000,
        )
    except Exception:
        return _single_section(blocks, document_title), "single_fallback_error"
    sections = _normalize_planned_sections(result.get("sections"), blocks, block_index)
    if not sections:
        return _single_section(blocks, document_title), "single_fallback_invalid"

    sections = _merge_tiny_sections(sections, min_content_chars=50)
    return sections, "llm"


def _llm_plan_two_stage(
    blocks: list[dict[str, Any]],
    document_title: str,
    max_chars: int,
) -> tuple[list[dict[str, Any]], str]:
    """P2: 两阶段长文档规划 — 骨架扫描 + 分窗口精细规划。"""
    from .context_budget import skeleton_scan, split_blocks_into_windows

    # 阶段 1: 骨架扫描（极少 token）
    windows = skeleton_scan(blocks, document_title)

    # 阶段 2: 分窗口精细规划
    window_groups = split_blocks_into_windows(blocks, windows, max_chars_per_window=max_chars, overlap_blocks=3)

    all_sections: list[dict[str, Any]] = []
    allowed_section_types = sorted(SECTION_ALIASES.keys()) + ["other"]

    for window_blocks, window_title in window_groups:
        if not window_blocks:
            continue
        block_text, block_index = _compact_blocks_for_llm(window_blocks)
        prompt = _build_planner_prompt(window_title, block_text, allowed_section_types)

        try:
            from .openai_compat import JsonChatClient
            client = JsonChatClient("CHUNK_PLANNER", default_model=True, enable_fallback=True)
            result = client.complete_json(
                system_prompt=_PLANNER_SYSTEM,
                user_prompt=prompt,
                temperature=0,
                max_tokens=4000,
            )
            sections = _normalize_planned_sections(result.get("sections"), window_blocks, block_index)
            if sections:
                all_sections.extend(sections)
            else:
                all_sections.append({"title": window_title, "section_type": "other", "blocks": window_blocks})
        except Exception:
            all_sections.append({"title": window_title, "section_type": "other", "blocks": window_blocks})

    if not all_sections:
        return _single_section(blocks, document_title), "single_fallback_two_stage"

    all_sections = _merge_tiny_sections(all_sections, min_content_chars=50)
    return all_sections, "llm_two_stage"


def _merge_tiny_sections(sections: list[dict[str, Any]], min_content_chars: int = 50) -> list[dict[str, Any]]:
    """将过短的 section（疑似只有标题）优先合并到后续正文。"""
    if not sections:
        return sections

    result: list[dict[str, Any]] = []
    pending_tiny: dict[str, Any] | None = None

    for section in sections:
        if section.get("container_only"):
            continue
        is_tiny = _is_tiny_section(section, min_content_chars)
        if is_tiny:
            section = dict(section)
            section["planner_warnings"] = list(section.get("planner_warnings") or []) + ["heading_only_section"]
            if pending_tiny is None:
                pending_tiny = section
            else:
                pending_tiny = _merge_section_suffix(pending_tiny, section)
            continue

        if pending_tiny is not None:
            result.append(_merge_section_prefix(pending_tiny, section))
            pending_tiny = None
        else:
            result.append(section)

    if pending_tiny is not None:
        if result:
            result[-1] = _merge_section_suffix(result[-1], pending_tiny)
        else:
            result.append(pending_tiny)

    return [section for section in result if section.get("blocks")]


def _normalize_planned_sections(
    planned: Any,
    blocks: list[dict[str, Any]],
    block_index: dict[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(planned, list):
        return []
    allowed = set(SECTION_ALIASES) | {"other"}
    normalized: list[dict[str, Any]] = []
    last_end = -1
    current_block_id = ""
    current_block_title = ""
    for item in planned:
        if not isinstance(item, dict):
            continue
        start_id = clean_text(item.get("start_block_id"))
        end_id = clean_text(item.get("end_block_id"))
        if start_id not in block_index or end_id not in block_index:
            continue
        start = block_index[start_id]
        end = block_index[end_id]
        if start > end:
            start, end = end, start
        if start <= last_end:
            start = last_end + 1
        if start >= len(blocks):
            continue
        end = min(end, len(blocks) - 1)
        title = clean_text(item.get("title")) or clean_text(blocks[start].get("text")) or "未命名章节"
        section_type = clean_text(item.get("section_type")) or classify_section(title)
        if section_type not in allowed:
            section_type = classify_section(title)
        hierarchy_level = item.get("hierarchy_level")
        try:
            hierarchy_level = int(hierarchy_level)
        except Exception:
            hierarchy_level = 1 if section_type == "business_block" else (2 if current_block_id else 1)
        section_id = clean_text(item.get("section_id")) or f"section_{len(normalized) + 1:03d}"
        business_block_id = clean_text(item.get("business_block_id"))
        business_block_title = clean_text(item.get("business_block_title"))
        if section_type == "business_block" or (hierarchy_level == 1 and re.match(TOP_LEVEL_BLOCK_RE, title)):
            current_block_id = business_block_id or section_id
            current_block_title = business_block_title or title
            business_block_id = current_block_id
            business_block_title = current_block_title
            section_type = "business_block"
        elif not business_block_id and current_block_id:
            business_block_id = current_block_id
            business_block_title = current_block_title
        warnings: list[str] = []
        if current_block_id and section_type != "business_block" and not business_block_id:
            warnings.append("business_block_missing")
        section_blocks = blocks[start : end + 1]
        container_only = section_type == "business_block" and len(clean_text("\n".join(block.get("text") or "" for block in section_blocks))) < 50
        normalized.append(
            {
                "section_id": section_id,
                "title": title,
                "section_type": section_type if section_type in allowed else "other",
                "blocks": section_blocks,
                "hierarchy_level": hierarchy_level,
                "parent_section_id": clean_text(item.get("parent_section_id")) or (business_block_id if business_block_id and section_type != "business_block" else ""),
                "business_block_id": business_block_id,
                "business_block_title": business_block_title,
                "reason": clean_text(item.get("reason")),
                "planner_warnings": warnings,
                "container_only": container_only,
            }
        )
        last_end = end
    if last_end + 1 < len(blocks):
        if normalized:
            normalized[-1]["blocks"].extend(blocks[last_end + 1 :])
        else:
            return _single_section(blocks, "全文")
    return [section for section in normalized if section.get("blocks")]


def _single_section(blocks: list[dict[str, Any]], document_title: str) -> list[dict[str, Any]]:
    title = document_title
    first_text = clean_text(blocks[0].get("text")) if blocks else ""
    if first_text and len(first_text) <= 100:
        title = first_text
    section_type = classify_section(title)
    if section_type == "other":
        section_type = classify_section(clean_text("\n".join(block.get("text") or "" for block in blocks))[:200])
    return [{"title": title, "section_type": section_type, "blocks": blocks}]


def chunk_guarantee_plan(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    title = doc_title(middle_document)
    blocks = [
        block
        for block in flatten_blocks(middle_document)
        if clean_text(block.get("text"))
        and block.get("type") not in {"noise", "seal"}
        and block.get("label") != "doc_title"
        and not is_page_number_block(block)  # 过滤页码行
    ]
    sections, plan_source = _llm_plan_sections(blocks, title)

    chunks: list[dict[str, Any]] = []
    seq_no = 0
    for section in sections:
        section_blocks = section["blocks"]
        content = clean_text("\n".join(item.get("text") or "" for item in section_blocks))
        if not content:
            continue
        section_type = section.get("section_type") or "other"
        aliases = SECTION_ALIASES.get(section_type, [])
        page_numbers = [item.get("page_no") for item in section_blocks if item.get("page_no")]
        business_block_id = clean_text(section.get("business_block_id"))
        business_block_title = clean_text(section.get("business_block_title"))
        group_prefix = f"business_block:{business_block_id}:" if business_block_id else ""
        semantic_group = (
            f"{group_prefix}field:{section_type}"
            if section_type != "other"
            else f"{group_prefix}section:{stable_hash(clean_text(section.get('title')), 16)}"
        )
        section_title = clean_text(section.get("title"))
        section_id = clean_text(section.get("section_id")) or f"section_{stable_hash(section_title or content[:80], 16)}"
        for part_index, part in enumerate(split_content(content), 1):
            seq_no += 1
            chunk_key = f"chunk_{seq_no:03d}"
            chunks.append(
                {
                    "chunk_key": chunk_key,
                    "seq_no": seq_no,
                    "chunk_type": "original",
                    "section_type": section_type,
                    "section_id": section_id,
                    "chunk_group_id": semantic_group,
                    "title": section_title,
                    "title_path": [title, section_title],
                    "content": part,
                    "summary": summarize_chunk(section_title, part),
                    "content_hash": stable_hash(part, 40),
                    "content_for_embedding": embedding_text(title, section_title, part),
                    "content_for_bm25": clean_text(f"{' '.join(aliases)} {section_title} {part}"),
                    "page_start": min(page_numbers) if page_numbers else None,
                    "page_end": max(page_numbers) if page_numbers else None,
                    "block_ids": [item.get("block_id") for item in section_blocks if item.get("block_id")],
                    "bbox": [],
                    "metadata": {
                        "document_title": title,
                        "aliases": aliases,
                        "chunk_plan_source": plan_source,
                        "part_index": part_index,
                        "min_chunk_chars": MIN_CHUNK_CHARS,
                        "max_chunk_chars": MAX_CHUNK_CHARS,
                        "confidence": "EXTRACTED",
                        "section_id": section_id,
                        "section_reason": clean_text(section.get("reason")),
                        "hierarchy_level": section.get("hierarchy_level"),
                        "parent_section_id": clean_text(section.get("parent_section_id")),
                        "business_block_id": business_block_id,
                        "business_block_title": business_block_title,
                        "planner_warnings": section.get("planner_warnings") or [],
                    },
                }
            )
    return chunks
