from __future__ import annotations

"""docx 内嵌图片提取（参考 LightRAG ``parser/docx/drawing_image_extractor.py``）。

只做一件事：把一个 docx 按「文档流顺序」摊平成 text / image 条目序列，
图片字节从 ``word/media/`` 关系表解析出来，并保留它在段落流中的位置
（供 VLM 描述时取 surrounding 上下文）。

刻意不引入 LightRAG 的 ``<drawing/>`` 占位符 / sidecar / export_dir 那套，
danbao-poc 只要字节 + 格式 + 位置，图字节随后交给文件中心或直接进内存。
"""

from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

# 命名空间（DrawingML / VML / 关系）
NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_V = "urn:schemas-microsoft-com:vml"

_W_P = f"{{{NS_W}}}p"
_W_TBL = f"{{{NS_W}}}tbl"
_W_T = f"{{{NS_W}}}t"
_W_DRAWING = f"{{{NS_W}}}drawing"
_W_PICT = f"{{{NS_W}}}pict"
_W_OBJECT = f"{{{NS_W}}}object"
_A_BLIP = f"{{{NS_A}}}blip"
_R_EMBED = f"{{{NS_R}}}embed"
_R_LINK = f"{{{NS_R}}}link"
_R_ID = f"{{{NS_R}}}id"
_V_IMAGEDATA = f"{{{NS_V}}}imagedata"

# VLM 能直接消费的位图格式；EMF/WMF/SVG 是矢量占位图，跳过（LightRAG 同款过滤）
SUPPORTED_IMAGE_FORMATS = {"png", "jpeg", "jpg", "gif", "bmp", "tiff", "tif", "webp"}


def _normalize_image_format(ext_or_type: str | None) -> str | None:
    if not ext_or_type:
        return None
    value = ext_or_type.strip().lower()
    if value.startswith("image/"):
        value = value.split("/", 1)[1]
        if "+" in value:
            value = value.split("+", 1)[0]
        if value.startswith("x-"):
            value = value[2:]
    value = value.lstrip(".")
    if value == "jpg":
        return "jpeg"
    if value in {"jpeg", "png", "gif", "bmp", "tiff", "webp"}:
        return value
    return value or None


def _image_format_from_part(part: Any) -> str | None:
    content_type = getattr(part, "content_type", "") or ""
    fmt = _normalize_image_format(content_type)
    if fmt:
        return fmt
    part_name = str(getattr(part, "partname", "") or "")
    return _normalize_image_format(PurePosixPath(part_name).suffix.lstrip("."))


def _paragraph_text(p_element: Any) -> str:
    texts = [node.text or "" for node in p_element.iter(_W_T)]
    return "".join(texts).strip()


def _table_text(tbl_element: Any) -> str:
    lines: list[str] = []
    for row in tbl_element.iter(f"{{{NS_W}}}tr"):
        cells: list[str] = []
        for tc in row.iter(f"{{{NS_W}}}tc"):
            cell_text = "".join(node.text or "" for node in tc.iter(_W_T)).strip()
            cells.append(cell_text)
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def _blip_relationships(container_element: Any) -> list[tuple[str, str]]:
    """返回 [(kind, rel_id)]，kind ∈ {"embed", "link"}。

    优先取 ``a:blip@r:embed``（内嵌）；``r:link`` 只记远程 URL。
    兼容 ``w:pict``/``w:object`` 里 VML 的 ``v:imagedata@r:id``。
    """
    refs: list[tuple[str, str]] = []
    for blip in container_element.iter(_A_BLIP):
        link = blip.get(_R_LINK)
        if link:
            refs.append(("link", link))
            continue
        embed = blip.get(_R_EMBED)
        if embed:
            refs.append(("embed", embed))
    for imagedata in container_element.iter(_V_IMAGEDATA):
        rel_id = imagedata.get(_R_ID)
        if rel_id:
            refs.append(("embed", rel_id))
    return refs


def iter_docx_flow(document: Any):
    """按文档流顺序产出 (kind, payload)：

    - ``("text", str)``           段落 / 表格文字（表格按 ``cell | cell`` 拼行）
    - ``("image", dict)``         图片，payload 见下

    图片 payload::

        {
            "bytes": b"...",          # 内嵌图片字节（link 图无此字段）
            "format": "png",          # 归一化位图格式（非位图已过滤）
            "name": "image1.png",     # 原始 part 文件名
            "docpr_name": "Picture 1" # wp:docPr 名称（可能为空）
        }
    """
    from docx import Document

    if isinstance(document, (bytes, bytearray)):
        document = Document(BytesIO(bytes(document)))

    body = document.element.body
    rels = getattr(document.part, "rels", {}) or {}

    for child in body.iterchildren():
        tag = child.tag
        if tag == _W_P:
            # 段落：先看是否含图，图文混排时「先文字后图片」
            text = _paragraph_text(child)
            if text:
                yield ("text", text)
            for container in (child,):
                if container.find(f".//{_W_DRAWING}") is None and container.find(f".//{_W_PICT}") is None and container.find(f".//{_W_OBJECT}") is None:
                    continue
                for kind, rel_id in _blip_relationships(container):
                    if kind == "link":
                        yield ("image", {"format": None, "name": rel_id, "docpr_name": ""})
                        continue
                    part = rels.get(rel_id)
                    if part is None:
                        continue
                    target = part.target_part if hasattr(part, "target_part") else part
                    fmt = _image_format_from_part(target)
                    if fmt not in SUPPORTED_IMAGE_FORMATS:
                        continue
                    payload = {
                        "bytes": getattr(target, "blob", b""),
                        "format": fmt,
                        "name": str(getattr(target, "partname", "") or "").split("/")[-1] or f"image.{fmt}",
                        "docpr_name": "",
                    }
                    # 尽力取 wp:docPr 名称
                    for docpr in container.iter(f"{{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}}docPr"):
                        payload["docpr_name"] = docpr.get("name", "") or docpr.get("id", "") or ""
                        break
                    if payload["bytes"]:
                        yield ("image", payload)
        elif tag == _W_TBL:
            table_text = _table_text(child)
            if table_text:
                yield ("text", table_text)
            # 表格内图片（较少见，尽力提取）
            for kind, rel_id in _blip_relationships(child):
                if kind != "embed":
                    continue
                part = rels.get(rel_id)
                if part is None:
                    continue
                target = part.target_part if hasattr(part, "target_part") else part
                fmt = _image_format_from_part(target)
                if fmt not in SUPPORTED_IMAGE_FORMATS:
                    continue
                blob = getattr(target, "blob", b"")
                if blob:
                    yield (
                        "image",
                        {
                            "bytes": blob,
                            "format": fmt,
                            "name": str(getattr(target, "partname", "") or "").split("/")[-1] or f"image.{fmt}",
                            "docpr_name": "",
                        },
                    )


def extract_docx_flow(file_bytes: bytes) -> list[dict[str, Any]]:
    """把 ``iter_docx_flow`` 收集成结构化列表，供无生成器场景使用。"""
    from docx import Document

    document = Document(BytesIO(file_bytes))
    flow: list[dict[str, Any]] = []
    for kind, payload in iter_docx_flow(document):
        if kind == "text":
            flow.append({"kind": "text", "text": payload})
        else:
            flow.append({"kind": "image", **payload})
    return flow


def surrounding_texts(flow: list[dict[str, Any]], image_index: int, window: int = 3) -> tuple[str, str]:
    """取图片前后各 ``window`` 条文字，拼成 (leading, trailing)。"""
    leading_parts: list[str] = []
    trailing_parts: list[str] = []
    for item in flow[:image_index][::-1]:
        if item.get("kind") == "text":
            leading_parts.append(item["text"])
            if len(leading_parts) >= window:
                break
    for item in flow[image_index + 1 :]:
        if item.get("kind") == "text":
            trailing_parts.append(item["text"])
            if len(trailing_parts) >= window:
                break
    return "\n".join(reversed(leading_parts)), "\n".join(trailing_parts)
