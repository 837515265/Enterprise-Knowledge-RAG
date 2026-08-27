from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from .common import clean_text, normalize_html_text, read_json


OCR_TO_PDF_SCALE = 72 / 144
NOISE_LABELS = {"footer", "header", "number", "aside", "aside_text", "header_image"}

LABEL_TYPE_MAP = {
    "doc_title": "title",
    "paragraph_title": "title",
    "title": "title",
    "text": "text",
    "abstract": "text",
    "reference_content": "text",
    "footnote": "text",
    "table": "table",
    "image": "image",
    "chart": "image",
    "chart_box": "image",
    "figure": "image",
    "figure_title": "caption",
    "seal": "seal",
    "list": "list",
}


def _markdown_text(obj: Any) -> str:
    if not obj:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("text") or obj.get("markdown") or ""
    return ""


def _extract_page_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "result" in raw:
        result = raw.get("result") or {}
        if isinstance(result, dict) and "layoutParsingResults" in result:
            return result.get("layoutParsingResults") or []
    if isinstance(raw, dict) and "layoutParsingResults" in raw:
        return raw.get("layoutParsingResults") or []
    if isinstance(raw, dict) and "prunedResult" in raw:
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def _scale_bbox(bbox: Any, scale: float = OCR_TO_PDF_SCALE) -> list[float]:
    if not isinstance(bbox, list):
        return []
    result: list[float] = []
    for value in bbox[:4]:
        try:
            result.append(round(float(value) * scale, 2))
        except (TypeError, ValueError):
            return []
    return result


def _merge_caption_blocks(raw_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    pending_caption = ""
    for block in raw_blocks:
        label = block.get("block_label") or "text"
        text = clean_text(block.get("block_content") or "")
        if label == "figure_title":
            pending_caption = clean_text(f"{pending_caption}\n{text}") if pending_caption else text
            continue
        item = dict(block)
        if pending_caption and label in {"table", "image", "chart", "chart_box", "figure"}:
            content = clean_text(item.get("block_content") or "")
            item["block_content"] = clean_text(f"{pending_caption}\n{content}") if content else pending_caption
            item["caption"] = pending_caption
            pending_caption = ""
        elif pending_caption:
            merged.append({"block_label": "figure_title", "block_content": pending_caption})
            pending_caption = ""
        merged.append(item)
    if pending_caption:
        merged.append({"block_label": "figure_title", "block_content": pending_caption})
    return merged


def _add_text_maps(middle: dict[str, Any]) -> dict[str, Any]:
    plain_parts: list[str] = []
    normalized_text_parts: list[str] = []
    char_spans: list[dict[str, Any]] = []
    offset = 0
    for page in middle.get("pages") or []:
        page_no = page.get("page_no")
        for block in page.get("blocks") or []:
            if block.get("type") in {"noise", "seal"}:
                continue
            text = clean_text(block.get("text") or "")
            if not text:
                continue
            plain_parts.append(text)
            if normalized_text_parts:
                normalized_text_parts.append("\n")
                offset += 1
            start = offset
            normalized_text_parts.append(text)
            end = start + len(text)
            offset = end
            char_spans.append(
                {
                    "span_id": f"span_{block.get('block_id') or len(char_spans) + 1}",
                    "global_char_start": start,
                    "global_char_end": end,
                    "normalized_start": start,
                    "normalized_end": end,
                    "raw_text_start": 0,
                    "raw_text_end": len(str(block.get("raw_text") or block.get("text") or "")),
                    "page_no": page_no,
                    "block_id": block.get("block_id"),
                    "bbox": block.get("raw_bbox") or block.get("bbox") or [],
                    "raw_bbox": block.get("raw_bbox") or block.get("bbox") or [],
                    "block_type": block.get("type"),
                    "block_label": block.get("label"),
                    "text": text,
                }
            )
    middle["plain_text"] = middle.get("plain_text") or clean_text("\n".join(plain_parts))
    middle["normalized_text"] = "".join(normalized_text_parts)
    middle["char_map"] = {"text_version": "norm_v1", "spans": char_spans}
    return middle


def load_paddle_pages(input_path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(input_path)
    if input_path.is_dir():
        page_files = sorted(glob.glob(str(input_path / "page_*.json")))
        if page_files:
            return [read_json(path) for path in page_files]
        pdf_raw = input_path / "pdf_ocr_raw.json"
        if pdf_raw.exists():
            return _extract_page_items(read_json(pdf_raw))
        raise ValueError(f"No page_*.json or pdf_ocr_raw.json found in: {input_path}")

    return _extract_page_items(read_json(input_path))


def normalize_paddle_result(
    input_path: str | Path,
    document_id: str,
    file_name: str,
    profile: str = "guarantee_plan",
) -> dict[str, Any]:
    pages_raw = load_paddle_pages(input_path)
    return normalize_paddle_pages(pages_raw, document_id, file_name, profile, parser="paddleocr")


def normalize_paddle_layout_json(
    layout_json: dict[str, Any],
    document_id: str,
    file_name: str,
    profile: str = "guarantee_plan",
) -> dict[str, Any]:
    pages_raw = _extract_page_items(layout_json)
    return normalize_paddle_pages(pages_raw, document_id, file_name, profile, parser="ocr_web_v2")


def normalize_paddle_pages(
    pages_raw: list[dict[str, Any]],
    document_id: str,
    file_name: str,
    profile: str = "guarantee_plan",
    parser: str = "paddleocr",
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    markdown_parts: list[str] = []
    plain_parts: list[str] = []
    tables: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []

    for page_index, page_raw in enumerate(pages_raw, 1):
        pruned = page_raw.get("prunedResult") if isinstance(page_raw, dict) else None
        if pruned is None:
            pruned = page_raw

        raw_blocks = _merge_caption_blocks(pruned.get("parsing_res_list") or [])
        page_blocks: list[dict[str, Any]] = []

        for idx, block in enumerate(raw_blocks, 1):
            label = block.get("block_label") or "text"
            block_type = LABEL_TYPE_MAP.get(label, "text")
            if label in NOISE_LABELS:
                block_type = "noise"
            block_id = f"p{page_index}_b{idx:03d}"
            raw_text = block.get("block_content") or ""
            text = clean_text(raw_text)
            raw_bbox = block.get("block_bbox") or []
            bbox = _scale_bbox(raw_bbox)
            normalized = {
                "block_id": block_id,
                "raw_block_id": block.get("block_id"),
                "type": block_type,
                "label": label,
                "text": text,
                "raw_text": raw_text,
                "markdown": text,
                "bbox": bbox,
                "raw_bbox": raw_bbox,
                "polygon": block.get("block_polygon_points") or [],
                "order": block.get("block_order") or idx,
                "group_id": block.get("group_id"),
                "quality": {"ocr_confidence": block.get("confidence"), "bbox_scale": OCR_TO_PDF_SCALE},
            }
            page_blocks.append(normalized)

            if block_type not in {"noise", "seal"} and text:
                plain_parts.append(text)
            if block_type == "table":
                tables.append({"table_id": block_id, "page_no": page_index, "text": text, "bbox": normalized["bbox"]})
            if block_type == "image":
                images.append({"image_id": block_id, "page_no": page_index, "caption": block.get("caption") or text, "bbox": normalized["bbox"]})

        page_blocks.sort(key=lambda item: item.get("order") or 0)
        page_markdown = _markdown_text(page_raw.get("markdown") if isinstance(page_raw, dict) else None)
        if not page_markdown:
            page_markdown = "\n\n".join(
                b["text"] for b in page_blocks if b["type"] not in {"noise", "seal"} and b["text"]
            )
        if page_markdown:
            markdown_parts.append(page_markdown)

        pages.append(
            {
                "page_no": page_index,
                "width": pruned.get("width"),
                "height": pruned.get("height"),
                "blocks": page_blocks,
            }
        )

    return _add_text_maps({
        "document_id": document_id,
        "file_name": file_name,
        "file_type": Path(file_name).suffix.lstrip(".").lower() or "unknown",
        "profile": profile,
        "parser": parser,
        "plain_text": clean_text("\n".join(plain_parts)),
        "markdown": clean_text("\n\n".join(markdown_parts)),
        "pages": pages,
        "tables": tables,
        "images": images,
        "coordinate_map": {},
        "quality": {
            "quality_level": "high" if pages else "low",
            "warnings": [] if pages else ["no_pages_loaded"],
        },
    })


def normalize_etl4lm_response(
    response: dict[str, Any],
    document_id: str,
    file_name: str,
    profile: str = "guarantee_plan",
) -> dict[str, Any]:
    """Convert ETL4LM-compatible PaddleOCR response to the same middle structure.

    Expected response shape:
    {
      "status_code": 200,
      "partitions": [
        {
          "type": "Text",
          "text": "...",
          "metadata": {"extra_data": {"bboxes": [[...]], "pages": [0]}}
        }
      ],
      "text": "..."
    }
    """
    partitions = response.get("partitions") or []
    pages_by_no: dict[int, list[dict[str, Any]]] = {}
    plain_parts: list[str] = []

    for idx, part in enumerate(partitions, 1):
        text = normalize_html_text(part.get("text") or "")
        metadata = part.get("metadata") or {}
        extra = metadata.get("extra_data") or {}
        pages = extra.get("pages") or [0]
        bboxes = extra.get("bboxes") or [[]]
        page_no = int(pages[0] or 0) + 1
        bbox = bboxes[0] if bboxes else []
        part_type = str(part.get("type") or "Text").lower()
        block_type = "table" if "table" in part_type else "title" if "title" in part_type else "text"
        label = "table" if block_type == "table" else "paragraph_title" if block_type == "title" else "text"
        block = {
            "block_id": f"p{page_no}_b{len(pages_by_no.get(page_no, [])) + 1:03d}",
            "raw_block_id": part.get("element_id") or idx,
            "type": block_type,
            "label": label,
            "text": text,
            "markdown": text,
            "bbox": bbox,
            "polygon": [],
            "order": idx,
            "group_id": None,
            "quality": {"ocr_confidence": None},
        }
        pages_by_no.setdefault(page_no, []).append(block)
        if text:
            plain_parts.append(text)

    if not pages_by_no and response.get("text"):
        text = clean_text(response.get("text"))
        pages_by_no[1] = [
            {
                "block_id": "p1_b001",
                "raw_block_id": "text",
                "type": "text",
                "label": "text",
                "text": text,
                "markdown": text,
                "bbox": [],
                "polygon": [],
                "order": 1,
                "group_id": None,
                "quality": {"ocr_confidence": None},
            }
        ]
        plain_parts.append(text)

    pages = []
    tables = []
    for page_no in sorted(pages_by_no):
        blocks = pages_by_no[page_no]
        pages.append({"page_no": page_no, "width": None, "height": None, "blocks": blocks})
        for block in blocks:
            if block.get("type") == "table":
                tables.append({"table_id": block["block_id"], "page_no": page_no, "text": block.get("text"), "bbox": block.get("bbox")})

    markdown = clean_text(response.get("markdown") or response.get("text") or "\n\n".join(plain_parts))
    return _add_text_maps({
        "document_id": document_id,
        "file_name": file_name,
        "file_type": Path(file_name).suffix.lstrip(".").lower() or "unknown",
        "profile": profile,
        "parser": "paddleocr_etl4lm",
        "plain_text": clean_text("\n".join(plain_parts)),
        "markdown": markdown,
        "pages": pages,
        "tables": tables,
        "images": [],
        "coordinate_map": {},
        "quality": {
            "quality_level": "high" if pages else "low",
            "warnings": [] if pages else ["no_pages_loaded"],
        },
    })
