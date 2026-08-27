from __future__ import annotations

import json
import mimetypes
import os
import re
import csv
from io import BytesIO
from pathlib import Path
from typing import Any

from .common import clean_text, normalize_html_text
from .ocr_client import call_mineru_parse, call_ocr_web_v2, call_paddle_ocr_predict, call_qianfan_vlm_ocr
from .paddle_normalizer import normalize_etl4lm_response, normalize_paddle_layout_json

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
TEXT_SUFFIXES = {".txt", ".md"}
SPREADSHEET_SUFFIXES = {".xlsx", ".xlsm", ".csv", ".tsv"}
HEADING_LINE_RE = re.compile(r"^(#{1,6}\s+.+|第[一二三四五六七八九十百千万0-9]+[章节条款].*|[一二三四五六七八九十]+[、.．].*|[0-9]+[、.．].*)$")


def _union_bbox(boxes: list[list[Any]]) -> list[float]:
    numeric_boxes: list[list[float]] = []
    for box in boxes:
        if not isinstance(box, list) or len(box) < 4:
            continue
        try:
            numeric_boxes.append([float(box[0]), float(box[1]), float(box[2]), float(box[3])])
        except (TypeError, ValueError):
            continue
    if not numeric_boxes:
        return []
    return [
        min(box[0] for box in numeric_boxes),
        min(box[1] for box in numeric_boxes),
        max(box[2] for box in numeric_boxes),
        max(box[3] for box in numeric_boxes),
    ]


def _estimate_line_bbox(block_bbox: list[Any], line_index: int, line_count: int) -> list[float]:
    if not isinstance(block_bbox, list) or len(block_bbox) < 4 or line_count <= 0:
        return []
    try:
        left, top, right, bottom = [float(item) for item in block_bbox[:4]]
    except (TypeError, ValueError):
        return []
    height = max((bottom - top) / max(line_count, 1), 0.0)
    line_top = top + height * line_index
    line_bottom = bottom if line_index == line_count - 1 else line_top + height
    return [left, line_top, right, line_bottom]


def _positions_from_bbox(page_no: int, bbox: list[Any]) -> list[list[Any]]:
    if not isinstance(bbox, list) or len(bbox) < 4:
        return []
    return [[page_no, bbox[0], bbox[2], bbox[1], bbox[3]]]


def _line_items_for_block(text: str, block: dict[str, Any]) -> list[dict[str, Any]]:
    lines = block.get("lines") if isinstance(block.get("lines"), list) else []
    result: list[dict[str, Any]] = []
    if lines:
        for index, line in enumerate(lines):
            line_text = clean_text(line.get("text") if isinstance(line, dict) else line)
            if not line_text:
                continue
            line_bbox = line.get("bbox") if isinstance(line, dict) else None
            result.append({"text": line_text, "bbox": line_bbox or [], "line_no": index + 1})
        if result:
            return result
    split_lines = [clean_text(part) for part in str(text or "").splitlines()]
    split_lines = [part for part in split_lines if part]
    if not split_lines:
        split_lines = [clean_text(text)]
    line_count = len(split_lines)
    block_bbox = block.get("bbox") or []
    return [
        {
            "text": line,
            "bbox": _estimate_line_bbox(block_bbox, index, line_count),
            "line_no": index + 1,
        }
        for index, line in enumerate(split_lines)
        if line
    ]


def _normalize_native_pages(
    *,
    document_id: str,
    file_name: str,
    profile: str,
    parser: str,
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    plain_parts: list[str] = []
    normalized_text_parts: list[str] = []
    char_spans: list[dict[str, Any]] = []
    markdown_parts: list[str] = []
    normalized_pages: list[dict[str, Any]] = []
    first_title = Path(file_name).stem

    for page_no, page in enumerate(pages, 1):
        blocks = page.get("blocks") or []
        normalized_blocks: list[dict[str, Any]] = []
        for idx, block in enumerate(blocks, 1):
            text = clean_text(block.get("text"))
            if not text:
                continue
            label = block.get("label") or ("doc_title" if page_no == 1 and idx == 1 else "text")
            block_type = block.get("type") or ("title" if label in {"doc_title", "paragraph_title", "title"} else "text")
            normalized_blocks.append(
                {
                    "block_id": f"p{page_no}_b{idx:03d}",
                    "raw_block_id": block.get("raw_block_id") or idx,
                    "type": block_type,
                    "label": label,
                    "text": text,
                    "markdown": block.get("markdown") or text,
                    "bbox": block.get("bbox") or [],
                    "polygon": block.get("polygon") or [],
                    "order": idx,
                    "group_id": None,
                    "quality": {"ocr_confidence": None},
                }
            )
            plain_parts.append(text)
            if normalized_text_parts:
                normalized_text_parts.append("\n")
            start = sum(len(part) for part in normalized_text_parts)
            normalized_text_parts.append(text)
            end = start + len(text)
            line_search_offset = 0
            line_items = _line_items_for_block(text, block)
            for line_index, line in enumerate(line_items, 1):
                line_text = clean_text(line.get("text"))
                if not line_text:
                    continue
                relative_start = text.find(line_text, line_search_offset)
                if relative_start < 0:
                    relative_start = line_search_offset
                relative_end = min(relative_start + len(line_text), len(text))
                line_search_offset = relative_end
                line_bbox = line.get("bbox") or _estimate_line_bbox(block.get("bbox") or [], line_index - 1, len(line_items))
                span_start = start + relative_start
                span_end = start + relative_end
                char_spans.append(
                    {
                        "span_id": f"span_p{page_no}_b{idx:03d}_l{int(line.get('line_no') or line_index):03d}",
                        "global_char_start": span_start,
                        "global_char_end": span_end,
                        "normalized_start": span_start,
                        "normalized_end": span_end,
                        "raw_text_start": relative_start,
                        "raw_text_end": relative_end,
                        "page_no": page_no,
                        "block_id": f"p{page_no}_b{idx:03d}",
                        "line_no": int(line.get("line_no") or line_index),
                        "bbox": line_bbox,
                        "raw_bbox": line_bbox or block.get("bbox") or [],
                        "positions": _positions_from_bbox(page_no, line_bbox),
                        "source_type": "line",
                        "block_type": block_type,
                        "block_label": label,
                        "text": text[relative_start:relative_end],
                    }
                )
        if normalized_blocks and normalized_blocks[0]["label"] == "doc_title":
            first_title = normalized_blocks[0]["text"]
        page_markdown = clean_text(page.get("markdown") or "\n\n".join(item["markdown"] for item in normalized_blocks))
        if page_markdown:
            markdown_parts.append(page_markdown)
        normalized_pages.append(
            {
                "page_no": page_no,
                "width": page.get("width"),
                "height": page.get("height"),
                "blocks": normalized_blocks,
            }
        )

    if normalized_pages and (
        not normalized_pages[0]["blocks"] or normalized_pages[0]["blocks"][0]["label"] != "doc_title"
    ):
        normalized_pages[0]["blocks"].insert(
            0,
            {
                "block_id": "p1_b000",
                "raw_block_id": "doc_title",
                "type": "title",
                "label": "doc_title",
                "text": first_title,
                "markdown": first_title,
                "bbox": [],
                "polygon": [],
                "order": 0,
                "group_id": None,
                "quality": {"ocr_confidence": None},
            },
        )

    normalized_text = "".join(normalized_text_parts)
    return {
        "document_id": document_id,
        "file_name": file_name,
        "file_type": Path(file_name).suffix.lstrip(".").lower() or "unknown",
        "profile": profile,
        "parser": parser,
        "plain_text": clean_text("\n".join(plain_parts)),
        "normalized_text": normalized_text,
        "char_map": {"text_version": "norm_v1", "spans": char_spans},
        "markdown": clean_text("\n\n".join(markdown_parts)),
        "pages": normalized_pages,
        "tables": [],
        "images": [],
        "coordinate_map": {},
        "quality": {
            "quality_level": "high" if plain_parts else "low",
            "warnings": [] if plain_parts else ["no_text_extracted"],
        },
    }


def _decode_text_bytes(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def _parse_txt_or_md(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    text = clean_text(_decode_text_bytes(file_bytes))
    title = Path(file_name).stem
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blocks = [{"label": "doc_title", "type": "title", "text": title}]
    blocks.extend({"label": "text", "type": "text", "text": line} for line in lines)
    middle = _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser="plain_text",
        pages=[{"blocks": blocks, "markdown": text}],
    )
    return middle, {"raw_text": text}


def _parse_docx(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from danbao_poc.docx_image_extractor import extract_docx_flow

    flow = extract_docx_flow(file_bytes)
    paragraphs = [item["text"] for item in flow if item["kind"] == "text" and clean_text(item.get("text"))]
    title = paragraphs[0] if paragraphs else Path(file_name).stem
    blocks = [{"label": "doc_title", "type": "title", "text": title}]
    blocks.extend({"label": "text", "type": "text", "text": text} for text in paragraphs[1:] if text)
    middle = _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser="docx",
        pages=[{"blocks": blocks, "markdown": "\n\n".join(paragraphs)}],
    )
    # 内嵌图片：按文档流顺序收集，图片字节只在内存中（供 multimodal.py 做 VLM 描述），
    # 分析后由 analyze_images 就地剥离，避免随 middle_document 持久化出大 JSON。
    images: list[dict[str, Any]] = []
    text_block_no = 0
    image_seq = 0
    for flow_index, item in enumerate(flow):
        if item["kind"] == "text":
            if clean_text(item.get("text")):
                text_block_no += 1
            continue
        image_seq += 1
        images.append(
            {
                "image_id": f"IMG_{image_seq:04d}",
                "flow_index": flow_index,
                "page_no": 1,
                "block_id": f"p1_b{text_block_no + 1:03d}" if text_block_no else None,
                "bbox": [],
                "format": item.get("format"),
                "name": item.get("name"),
                "docpr_name": item.get("docpr_name"),
                "bytes": item.get("bytes"),
                "file_center_file_id": None,
            }
        )
    middle["images"] = images
    # _docx_flow 只保留「文字 + 图片占位」的顺序（不含字节），供 surrounding 定位；
    # 图片字节只在 images[] 里，analyze_images 分析后就地剥离。
    middle["_docx_flow"] = [item if item["kind"] == "text" else {"kind": "image"} for item in flow]
    return middle, {"paragraph_count": len(paragraphs), "image_count": len(images)}


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return clean_text(str(value))


def _infer_column_type(values: list[Any]) -> str:
    non_empty = [_cell_text(value) for value in values if _cell_text(value)]
    if not non_empty:
        return "string"
    numeric_count = 0
    date_count = 0
    for value in non_empty:
        if re.fullmatch(r"[-+]?\d+(\.\d+)?", value.replace(",", "")):
            numeric_count += 1
        elif re.fullmatch(r"\d{4}[-/年]\d{1,2}([-/月]\d{1,2}日?)?", value):
            date_count += 1
    if numeric_count >= max(1, int(len(non_empty) * 0.8)):
        return "number"
    if date_count >= max(1, int(len(non_empty) * 0.8)):
        return "date"
    return "string"


def _dedupe_columns(headers: list[str], width: int) -> list[str]:
    result: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        name = clean_text(headers[index] if index < len(headers) else "") or f"column_{index + 1}"
        count = seen.get(name, 0) + 1
        seen[name] = count
        result.append(name if count == 1 else f"{name}_{count}")
    return result


def _table_markdown(columns: list[str], rows: list[dict[str, Any]], max_rows: int = 50) -> str:
    safe_columns = [column.replace("|", "\\|") for column in columns]
    lines = ["| " + " | ".join(safe_columns) + " |", "| " + " | ".join(["---"] * len(safe_columns)) + " |"]
    for row in rows[:max_rows]:
        lines.append("| " + " | ".join(_cell_text(row.get(column)).replace("|", "\\|") for column in columns) + " |")
    return "\n".join(lines)


def _build_table(
    *,
    table_key: str,
    title: str,
    page_no: int,
    raw_rows: list[list[Any]],
    source_type: str,
) -> dict[str, Any] | None:
    trimmed = [[_cell_text(value) for value in row] for row in raw_rows]
    trimmed = [row for row in trimmed if any(cell for cell in row)]
    if not trimmed:
        return None
    width = max(len(row) for row in trimmed)
    normalized_rows = [row + [""] * (width - len(row)) for row in trimmed]
    header_row = normalized_rows[0]
    has_header = any(cell and not re.fullmatch(r"[-+]?\d+(\.\d+)?", cell.replace(",", "")) for cell in header_row)
    columns = _dedupe_columns(header_row if has_header else [], width)
    data_rows = normalized_rows[1:] if has_header else normalized_rows
    row_objects = [{columns[index]: row[index] for index in range(width)} for row in data_rows]
    column_defs = [
        {
            "name": column,
            "data_type": _infer_column_type([row.get(column) for row in row_objects]),
        }
        for column in columns
    ]
    markdown = _table_markdown(columns, row_objects)
    return {
        "table_key": table_key,
        "page_no": page_no,
        "title": title,
        "markdown": markdown,
        "columns": column_defs,
        "rows": row_objects,
        "metadata": {
            "source_type": source_type,
            "row_count": len(row_objects),
            "column_count": len(columns),
            "has_header": has_header,
        },
    }


def _parse_csv_or_tsv(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    text = _decode_text_bytes(file_bytes)
    suffix = Path(file_name).suffix.lower()
    delimiter = "\t" if suffix == ".tsv" else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
    title = Path(file_name).stem
    table = _build_table(table_key="table_001", title=title, page_no=1, raw_rows=rows, source_type=suffix.lstrip("."))
    tables = [table] if table else []
    markdown = table["markdown"] if table else text
    middle = _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser=suffix.lstrip(".") or "csv",
        pages=[{"blocks": [{"label": "doc_title", "type": "title", "text": title}, {"label": "table", "type": "table", "text": markdown, "markdown": markdown}], "markdown": markdown}],
    )
    middle["tables"] = tables
    return middle, {"table_count": len(tables)}


def _parse_xlsx(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        tables: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        for sheet_index, sheet in enumerate(workbook.worksheets, 1):
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            table = _build_table(
                table_key=f"sheet_{sheet_index:03d}",
                title=sheet.title,
                page_no=sheet_index,
                raw_rows=rows,
                source_type="xlsx",
            )
            markdown = table["markdown"] if table else ""
            if table:
                tables.append(table)
            pages.append(
                {
                    "blocks": [
                        {"label": "paragraph_title", "type": "title", "text": sheet.title},
                        {"label": "table", "type": "table", "text": markdown, "markdown": markdown},
                    ],
                    "markdown": f"{sheet.title}\n\n{markdown}" if markdown else sheet.title,
                }
            )
        middle = _normalize_native_pages(
            document_id=document_id,
            file_name=file_name,
            profile=profile,
            parser="xlsx",
            pages=pages or [{"blocks": [{"label": "doc_title", "type": "title", "text": Path(file_name).stem}], "markdown": Path(file_name).stem}],
        )
        middle["tables"] = tables
        return middle, {"sheet_count": len(workbook.worksheets), "table_count": len(tables)}
    finally:
        workbook.close()


def _ocr_backend() -> str:
    return os.getenv("OCR_BACKEND", "mineru").strip().lower() or "mineru"


def _ocr_model_prefix(backend: str | None = None) -> str:
    backend = (backend or _ocr_backend()).strip().lower()
    if backend in {"glm_ocr", "glm-vlm", "glm_vlm"}:
        return "GLM_OCR"
    return "QIANFAN_OCR"


def _vlm_ocr_base_url(prefix: str) -> str:
    base_url = os.getenv(f"{prefix}_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError(f"{prefix}_BASE_URL must be configured when OCR_BACKEND uses a VLM OCR backend")
    if base_url.endswith("/chat/completions"):
        return base_url[: -len("/chat/completions")]
    if base_url.rstrip("/").endswith("/v1"):
        return base_url.rstrip("/")
    return base_url.rstrip("/") + "/v1"


def _build_vlm_markdown_blocks(page_markdown: str, page_no: int) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    parts = re.split(r"\n\s*\n", page_markdown)
    for part in parts:
        text = normalize_html_text(part)
        if not text:
            continue
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        first_line = clean_text(lines[0].lstrip("#").strip())
        is_table = len(lines) >= 2 and any("|" in line for line in lines)
        is_heading = bool(HEADING_LINE_RE.match(lines[0])) or lines[0].startswith("#")
        label = "table" if is_table else ("paragraph_title" if is_heading else "text")
        block_type = "table" if is_table else ("title" if is_heading else "text")
        if page_no == 1 and not blocks and block_type == "title":
            label = "doc_title"
        blocks.append(
            {
                "label": label,
                "type": block_type,
                "text": text if block_type != "title" else first_line,
                "markdown": text,
                "bbox": [],
                "polygon": [],
            }
        )
    return blocks


def _normalize_vlm_pages(
    *,
    document_id: str,
    file_name: str,
    profile: str,
    page_markdowns: list[str],
) -> dict[str, Any]:
    pages = []
    for page_no, markdown in enumerate(page_markdowns, 1):
        pages.append(
            {
                "blocks": _build_vlm_markdown_blocks(markdown, page_no),
                "markdown": markdown,
                "width": None,
                "height": None,
            }
        )
    return _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser="qianfan_vlm",
        pages=pages,
    )


def _extract_mineru_markdown(result: dict[str, Any]) -> str:
    results = result.get("results")
    if not isinstance(results, dict):
        return ""
    markdowns: list[str] = []
    for file_result in results.values():
        if not isinstance(file_result, dict):
            continue
        markdown = clean_text(file_result.get("md_content") or file_result.get("markdown") or "")
        if markdown:
            markdowns.append(markdown)
    return clean_text("\n\n".join(markdowns))


def _extract_mineru_middle_json(result: dict[str, Any]) -> dict[str, Any] | None:
    results = result.get("results")
    if not isinstance(results, dict):
        return None
    for file_result in results.values():
        if not isinstance(file_result, dict):
            continue
        middle_json = file_result.get("middle_json")
        if middle_json:
            if isinstance(middle_json, str):
                try:
                    return json.loads(middle_json)
                except (json.JSONDecodeError, TypeError):
                    return None
            if isinstance(middle_json, dict):
                return middle_json
    return None


def _normalize_mineru_markdown(
    *,
    document_id: str,
    file_name: str,
    profile: str,
    markdown: str,
) -> dict[str, Any]:
    markdown = normalize_html_text(markdown)
    pages = [{"blocks": _build_vlm_markdown_blocks(markdown, 1), "markdown": markdown, "width": None, "height": None}]
    middle = _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser="mineru",
        pages=pages,
    )
    middle["parser"] = "mineru"
    return middle


def _extract_block_text_from_lines(block: dict[str, Any]) -> str:
    """Extract text from a MinerU block's lines/spans structure.

    Handles nested structures: list blocks have content in block["blocks"],
    table blocks have sub-blocks with table_body, etc.
    """
    parts = []

    # For list-type blocks, content is in block["blocks"] sub-array
    if block.get("type") == "list" and "blocks" in block:
        for sub_block in block["blocks"]:
            sub_text = _extract_block_text_from_lines(sub_block)
            if sub_text:
                parts.append(sub_text)
        return "\n".join(parts)

    # Standard lines/spans extraction
    if "lines" in block:
        for line in block["lines"]:
            if "spans" in line:
                for span in line["spans"]:
                    content = span.get("content", "")
                    if content:
                        parts.append(content)
            elif "text" in line:
                parts.append(line["text"])
        return "".join(parts)

    return block.get("text", "")


def _extract_line_items_from_mineru_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    if block.get("type") == "list" and "blocks" in block:
        result: list[dict[str, Any]] = []
        for sub_block in block["blocks"]:
            result.extend(_extract_line_items_from_mineru_block(sub_block))
        return result
    result: list[dict[str, Any]] = []
    for line in block.get("lines") or []:
        line_parts: list[str] = []
        span_boxes: list[list[Any]] = []
        for span in line.get("spans", []):
            content = span.get("content") or span.get("text") or ""
            if content:
                line_parts.append(str(content))
            if span.get("bbox"):
                span_boxes.append(span.get("bbox"))
        if not line_parts and line.get("text"):
            line_parts.append(str(line.get("text")))
        line_text = clean_text("".join(line_parts))
        if not line_text:
            continue
        result.append(
            {
                "text": line_text,
                "bbox": line.get("bbox") or _union_bbox(span_boxes),
            }
        )
    return result


def _normalize_mineru_middle_json(
    *,
    document_id: str,
    file_name: str,
    profile: str,
    middle_json: dict[str, Any],
) -> dict[str, Any]:
    """Normalize MinerU middle_json into danbao-poc middle_document format.

    middle_json.pdf_info[] has per-page data with para_blocks/preproc_blocks.
    Each page has page_idx, page_size, and block arrays.
    """
    pdf_info = middle_json.get("pdf_info", [])
    pages: list[dict[str, Any]] = []

    for page in pdf_info:
        page_idx = page.get("page_idx", 0)
        page_size = page.get("page_size") or [0, 0]
        blocks_raw = page.get("para_blocks") or page.get("preproc_blocks") or []
        page_markdown_parts: list[str] = []

        blocks: list[dict[str, Any]] = []
        for block in blocks_raw:
            block_type = block.get("type", "text")
            text = _extract_block_text_from_lines(block)
            if not text and block_type not in ("image", "interline_equation"):
                continue

            # Determine label
            if block_type == "title":
                label = "paragraph_title"
            elif block_type == "table":
                label = "table"
            elif block_type == "image":
                label = "image"
            else:
                label = "text"

            # Extract heading level for titles
            level = block.get("level")
            if level is not None:
                try:
                    level = int(level)
                except (TypeError, ValueError):
                    level = None

            # Build markdown representation
            if block_type == "title" and level:
                markdown = f"{'#' * min(max(level, 1), 6)} {text}"
            elif block_type == "table":
                # Try to get HTML from sub-blocks
                html = ""
                for sub in block.get("blocks", []):
                    if sub.get("type") == "table_body":
                        for line in sub.get("lines", []):
                            for span in line.get("spans", []):
                                if "html" in span:
                                    html = span["html"]
                                    break
                markdown = html or text
            else:
                markdown = text

            page_markdown_parts.append(markdown)

            blocks.append({
                "label": label,
                "type": "title" if block_type == "title" else "text",
                "text": text,
                "markdown": markdown,
                "bbox": block.get("bbox") or [],
                "lines": _extract_line_items_from_mineru_block(block),
                "polygon": [],
                "order": len(blocks) + 1,
                "group_id": None,
                "quality": {"ocr_confidence": block.get("score")},
            })

        page_markdown = "\n\n".join(page_markdown_parts)
        pages.append({
            "blocks": blocks,
            "markdown": page_markdown,
            "width": page_size[0] if len(page_size) > 0 else None,
            "height": page_size[1] if len(page_size) > 1 else None,
        })

    middle = _normalize_native_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        parser="mineru",
        pages=pages,
    )
    middle["parser"] = "mineru"
    return middle


def _render_pdf_pages(file_bytes: bytes, prefix: str = "QIANFAN_OCR") -> list[bytes]:
    import fitz

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        scale = float(os.getenv(f"{prefix}_RENDER_SCALE", os.getenv("QIANFAN_OCR_RENDER_SCALE", "2.0")))
        matrix = fitz.Matrix(scale, scale)
        images: list[bytes] = []
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
        return images
    finally:
        doc.close()


def _parse_via_vlm_ocr(
    file_name: str,
    file_bytes: bytes,
    document_id: str,
    profile: str,
    *,
    backend: str,
    prefix: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    suffix = Path(file_name or "").suffix.lower()
    if suffix == ".pdf":
        page_images = _render_pdf_pages(file_bytes, prefix)
    else:
        page_images = [file_bytes]
    base_url = _vlm_ocr_base_url(prefix)
    model = os.getenv(f"{prefix}_MODEL", "").strip()
    api_key = os.getenv(f"{prefix}_API_KEY", os.getenv("DEFAULT_MODEL_API_KEY", "EMPTY")).strip()
    prompt = os.getenv(f"{prefix}_PROMPT", os.getenv("QIANFAN_OCR_PROMPT", "")).strip() or None
    timeout = int(os.getenv(f"{prefix}_TIMEOUT", os.getenv("QIANFAN_OCR_TIMEOUT", "600")))

    page_markdowns: list[str] = []
    raw_pages: list[dict[str, Any]] = []
    for page_no, image_bytes in enumerate(page_images, 1):
        result = call_qianfan_vlm_ocr(
            base_url=base_url,
            model=model,
            api_key=api_key,
            image_bytes=image_bytes,
            image_mime_type="image/png",
            prompt=prompt,
            timeout=timeout,
        )
        page_markdown = clean_text(result["markdown"])
        page_markdowns.append(page_markdown)
        raw_pages.append({"page_no": page_no, "markdown": page_markdown, "raw_response": result["raw_response"]})

    middle = _normalize_vlm_pages(
        document_id=document_id,
        file_name=file_name,
        profile=profile,
        page_markdowns=page_markdowns,
    )
    middle["parser"] = backend
    return middle, {"raw_ocr": {"backend": backend, "model": model, "pages": raw_pages}}


def _parse_via_qianfan_vlm(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return _parse_via_vlm_ocr(file_name, file_bytes, document_id, profile, backend="qianfan_vlm", prefix="QIANFAN_OCR")


def _parse_via_glm_ocr(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return _parse_via_vlm_ocr(file_name, file_bytes, document_id, profile, backend="glm_ocr", prefix="GLM_OCR")


def _parse_via_paddle(file_name: str, file_bytes: bytes, document_id: str, profile: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ocr_web_url = os.getenv("PADDLE_OCR_WEB_URL", "")
    predict_url = os.getenv("PADDLE_OCR_PREDICT_URL", "")
    if ocr_web_url:
        ocr_result = call_ocr_web_v2(ocr_web_url, file_name, file_bytes)
        middle = normalize_paddle_layout_json(ocr_result["raw_layout"], document_id, file_name, profile)
        return middle, {"raw_ocr": ocr_result}
    if predict_url:
        ocr_result = call_paddle_ocr_predict(predict_url, file_name, file_bytes)
        middle = normalize_etl4lm_response(ocr_result, document_id, file_name, profile)
        return middle, {"raw_ocr": ocr_result}
    raise RuntimeError("PADDLE_OCR_WEB_URL or PADDLE_OCR_PREDICT_URL must be configured when OCR_BACKEND=paddle_layout")


def _parse_via_mineru(file_name: str, file_bytes: bytes, document_id: str, profile: str, *, file_id: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    base_url = os.getenv("MINERU_BASE_URL", "http://124.128.251.51:21189").strip()
    ocr_result = call_mineru_parse(base_url, file_name, file_bytes, file_id=file_id)
    markdown = _extract_mineru_markdown(ocr_result)

    # Try to use middle_json for proper page-level structure
    middle_json = _extract_mineru_middle_json(ocr_result)
    if middle_json and middle_json.get("pdf_info"):
        middle = _normalize_mineru_middle_json(
            document_id=document_id,
            file_name=file_name,
            profile=profile,
            middle_json=middle_json,
        )
        return middle, {"raw_ocr": {"backend": "mineru", "markdown": markdown, "middle_json": middle_json}}

    # Fallback to markdown-only mode
    if not markdown:
        raise RuntimeError(f"MinerU returned empty markdown: {ocr_result}")
    middle = _normalize_mineru_markdown(document_id=document_id, file_name=file_name, profile=profile, markdown=markdown)
    return middle, {"raw_ocr": {"backend": "mineru", "markdown": markdown, "response": ocr_result}}


def _parse_via_ocr(file_name: str, file_bytes: bytes, document_id: str, profile: str, *, file_id: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    backend = _ocr_backend()
    if backend in {"mineru", "mineru_api"}:
        return _parse_via_mineru(file_name, file_bytes, document_id, profile, file_id=file_id)
    if backend == "paddle_layout":
        return _parse_via_paddle(file_name, file_bytes, document_id, profile)
    if backend == "qianfan_vlm":
        return _parse_via_qianfan_vlm(file_name, file_bytes, document_id, profile)
    if backend in {"glm_ocr", "glm-vlm", "glm_vlm"}:
        return _parse_via_glm_ocr(file_name, file_bytes, document_id, profile)
    raise RuntimeError(f"unsupported OCR_BACKEND: {backend}")


def _parse_pdf_native(file_name: str, file_bytes: bytes, document_id: str, profile: str, error: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    import fitz

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        pages = []
        for page_no, page in enumerate(doc, 1):
            page_text = page.get_text("text") or ""
            lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            blocks = [{"label": "text", "type": "text", "text": line} for line in lines]
            pages.append({"blocks": blocks, "markdown": page_text, "width": page.rect.width, "height": page.rect.height})
        middle = _normalize_native_pages(document_id=document_id, file_name=file_name, profile=profile, parser="pdf_native", pages=pages)
        payload: dict[str, Any] = {"fallback": "pdf_native"} if error else {"parser": "pdf_native"}
        if error:
            payload["error"] = error
        return middle, payload
    finally:
        doc.close()


def parse_document(
    file_name: str,
    file_bytes: bytes,
    document_id: str,
    profile: str,
    parser_hint: str | None = None,
    *,
    file_id: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    suffix = Path(file_name or "").suffix.lower()
    mime_type = mimetypes.guess_type(file_name or "")[0] or ""
    hint = (parser_hint or "").strip().lower()

    if suffix in TEXT_SUFFIXES:
        return _parse_txt_or_md(file_name, file_bytes, document_id, profile)
    if suffix == ".docx":
        return _parse_docx(file_name, file_bytes, document_id, profile)
    if suffix in {".csv", ".tsv"}:
        return _parse_csv_or_tsv(file_name, file_bytes, document_id, profile)
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_xlsx(file_name, file_bytes, document_id, profile)
    if suffix == ".pdf" or mime_type == "application/pdf":
        if hint in {"native", "native_only", "pdf_native"}:
            return _parse_pdf_native(file_name, file_bytes, document_id, profile)
        try:
            return _parse_via_ocr(file_name, file_bytes, document_id, profile, file_id=file_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("OCR failed for pdf: %s, falling back to basic extraction", e)
            return _parse_pdf_native(file_name, file_bytes, document_id, profile, error=str(e))
    if suffix in IMAGE_SUFFIXES or mime_type.startswith("image/"):
        return _parse_via_ocr(file_name, file_bytes, document_id, profile, file_id=file_id)

    raise RuntimeError(f"unsupported file type for P0: {file_name}")
