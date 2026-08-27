from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
import json
import os
import re
from pathlib import Path
from typing import Any


def ensure_parent(path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_text(text: Any) -> str:
    text = "" if text is None else str(text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(clean_text("".join(self._current_cell)))
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def html_table_to_markdown(table_html: str) -> str:
    parser = _HtmlTableParser()
    try:
        parser.feed(table_html)
    except Exception:
        pass
    rows = [row for row in parser.rows if any(cell for cell in row)]
    if not rows:
        return clean_text(html.unescape(HTML_TAG_RE.sub(" ", table_html)))
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]
    lines = ["| " + " | ".join(cell.replace("|", "\\|") for cell in header) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in body:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return clean_text("\n".join(lines))


def normalize_html_text(text: Any) -> str:
    value = "" if text is None else str(text)
    if "<" not in value or ">" not in value:
        return clean_text(value)
    value = HTML_TABLE_RE.sub(lambda match: "\n" + html_table_to_markdown(match.group(0)) + "\n", value)
    value = HTML_TAG_RE.sub(" ", value)
    return clean_text(html.unescape(value))


def visible_text_length(text: Any) -> int:
    return len(re.sub(r"\s+", "", normalize_html_text(text)))


def stable_hash(text: str, length: int = 40) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:length]


def canonical_text(text: Any) -> str:
    """Normalize entity labels for stable keys and lightweight dedupe."""
    value = clean_text(text).lower()
    value = re.sub(r"[\s,，;；:：|/\\\-_.。、《》<>\"'`]+", "", value)
    return value


def canonical_key(kind: str, *values: Any, length: int = 24) -> str:
    parts = [canonical_text(value) for value in values if canonical_text(value)]
    return stable_hash(f"{canonical_text(kind)}:{'|'.join(parts)}", length) if parts else ""


def safe_filename(text: str, default: str = "item") -> str:
    text = text or default
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    return (text[:120] or default)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_project_path(path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path
    return project_root() / path
