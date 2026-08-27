from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

from .common import clean_text


@dataclass
class EvidenceAlignment:
    status: str
    coverage: float
    density: float
    start_char: int | None = None
    end_char: int | None = None
    matched_text: str | None = None
    method: str | None = None
    matched_units: int | None = None
    source_span_units: int | None = None
    false_positive_suspect: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    compact_chars: list[str] = []
    original_indexes: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        compact_chars.append(char.lower())
        original_indexes.append(index)
    return "".join(compact_chars), original_indexes


def _lcs_alignment(compact_quote: str, compact_text: str, text_map: list[int]) -> EvidenceAlignment:
    quote_len = len(compact_quote)
    text_len = len(compact_text)
    if not quote_len or not text_len:
        return EvidenceAlignment(status="failed", coverage=0.0, density=0.0, method="lcs")

    # Keep memory bounded while still handling normal evidence quote sizes.
    if quote_len * text_len > 1_500_000:
        return EvidenceAlignment(status="failed", coverage=0.0, density=0.0, method="lcs_skipped")

    previous = [0] * (text_len + 1)
    directions: list[bytearray] = [bytearray(text_len + 1) for _ in range(quote_len + 1)]
    for i, q_char in enumerate(compact_quote, 1):
        current = [0] * (text_len + 1)
        for j, t_char in enumerate(compact_text, 1):
            if q_char == t_char:
                current[j] = previous[j - 1] + 1
                directions[i][j] = 1
            elif previous[j] >= current[j - 1]:
                current[j] = previous[j]
                directions[i][j] = 2
            else:
                current[j] = current[j - 1]
                directions[i][j] = 3
        previous = current

    matched_positions: list[int] = []
    i, j = quote_len, text_len
    while i > 0 and j > 0:
        direction = directions[i][j]
        if direction == 1:
            matched_positions.append(j - 1)
            i -= 1
            j -= 1
        elif direction == 2:
            i -= 1
        else:
            j -= 1
    matched_positions.reverse()

    matched = len(matched_positions)
    coverage = matched / quote_len if quote_len else 0.0
    if not matched_positions:
        return EvidenceAlignment(status="failed", coverage=coverage, density=0.0, method="lcs", matched_units=0)
    span_start = matched_positions[0]
    span_end = matched_positions[-1] + 1
    span_units = max(1, span_end - span_start)
    density = matched / span_units
    start_char = text_map[span_start]
    end_char = text_map[span_end - 1] + 1
    return EvidenceAlignment(
        status="lcs_aligned",
        coverage=coverage,
        density=density,
        start_char=start_char,
        end_char=end_char,
        matched_text=None,
        method="lcs",
        matched_units=matched,
        source_span_units=span_units,
        false_positive_suspect=bool(coverage >= 0.75 and density < 0.33),
    )


def align_quote_to_text(
    quote: str,
    text: str,
    *,
    min_coverage: float = 0.85,
    min_density: float = 0.65,
    min_lcs_coverage: float = 0.75,
    min_lcs_density: float = 0.33,
) -> EvidenceAlignment:
    quote = clean_text(quote)
    text = clean_text(text)
    if not quote or not text:
        return EvidenceAlignment(status="failed", coverage=0.0, density=0.0)

    exact_start = text.find(quote)
    if exact_start >= 0:
        exact_end = exact_start + len(quote)
        return EvidenceAlignment(
            status="exact",
            coverage=1.0,
            density=1.0,
            start_char=exact_start,
            end_char=exact_end,
            matched_text=text[exact_start:exact_end],
            method="exact",
        )

    compact_quote, _ = _compact_with_map(quote)
    compact_text, text_map = _compact_with_map(text)
    if not compact_quote or not compact_text:
        return EvidenceAlignment(status="failed", coverage=0.0, density=0.0)

    compact_start = compact_text.find(compact_quote)
    if compact_start >= 0:
        compact_end = compact_start + len(compact_quote) - 1
        start_char = text_map[compact_start]
        end_char = text_map[compact_end] + 1
        return EvidenceAlignment(
            status="normalized_exact",
            coverage=1.0,
            density=1.0,
            start_char=start_char,
            end_char=end_char,
            matched_text=text[start_char:end_char],
            method="normalized_exact",
        )

    lcs = _lcs_alignment(compact_quote, compact_text, text_map)
    if lcs.status == "lcs_aligned" and lcs.coverage >= min_lcs_coverage and lcs.density >= min_lcs_density:
        return EvidenceAlignment(
            status="lcs_aligned",
            coverage=lcs.coverage,
            density=lcs.density,
            start_char=lcs.start_char,
            end_char=lcs.end_char,
            matched_text=text[lcs.start_char:lcs.end_char] if lcs.start_char is not None and lcs.end_char is not None else None,
            method=lcs.method,
            matched_units=lcs.matched_units,
            source_span_units=lcs.source_span_units,
            false_positive_suspect=lcs.false_positive_suspect,
        )

    matcher = SequenceMatcher(None, compact_quote, compact_text, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    matched_chars = sum(block.size for block in blocks)
    coverage = matched_chars / len(compact_quote) if compact_quote else 0.0
    if not blocks or coverage < min_coverage:
        return EvidenceAlignment(status="failed", coverage=coverage, density=lcs.density if lcs.coverage >= coverage else 0.0, method="lcs_then_sequence", false_positive_suspect=lcs.false_positive_suspect)

    content_start = min(block.b for block in blocks)
    content_end = max(block.b + block.size for block in blocks)
    span_len = max(1, content_end - content_start)
    density = matched_chars / span_len
    if density < min_density:
        return EvidenceAlignment(status="failed", coverage=coverage, density=density, method="sequence", false_positive_suspect=bool(coverage >= min_lcs_coverage and density < min_lcs_density))

    start_char = text_map[content_start]
    end_char = text_map[content_end - 1] + 1
    return EvidenceAlignment(
        status="fuzzy_aligned",
        coverage=coverage,
        density=density,
        start_char=start_char,
        end_char=end_char,
        matched_text=text[start_char:end_char],
        method="sequence",
    )


def align_quote_to_chunks(
    quote: str,
    chunks: list[dict[str, Any]],
    *,
    min_coverage: float = 0.85,
    min_density: float = 0.65,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for chunk in chunks:
        alignment = align_quote_to_text(
            quote,
            chunk.get("content") or "",
            min_coverage=min_coverage,
            min_density=min_density,
        )
        if alignment.status == "failed":
            if best is None or alignment.coverage > best["alignment"].coverage:
                best = {"chunk": chunk, "alignment": alignment}
            continue
        return {"chunk": chunk, "alignment": alignment}
    return None if best is None or best["alignment"].status == "failed" else best
