from __future__ import annotations

import json
from typing import Any

from .common import clean_text
from .evidence_aligner import align_quote_to_text
from .openai_compat import JsonChatClient
from .prompt_views import format_chunks_for_prompt, format_summaries_for_prompt, knowledge_prompt_view


ANSWER_PREBUILD_SYSTEM_PROMPT = """你是企业知识库 RAG-Doc 的预设答案生成模型。
你的任务是基于原文 chunk、层级摘要、Anchor、Knowledge Unit 和 Relation，生成可进入 kb_qa_pair 的高质量预设答案候选。

必须遵守：
1. 只输出 JSON object。
2. 每条答案必须能被原文 evidence_quotes 证明，不能编造。
3. 每条答案必须给 source_chunk_keys，且 evidence_quotes 必须来自这些 chunk。
4. evidence_quotes 必须逐字复制原文，禁止改写、缩写、合并或润色。对齐失败会导致整条 QA 被丢弃。
5. 优先生成用户高频会问的问题，不要机械地给每个 chunk 生成问题。
6. 自动答案不能替代原文证据；答案要短、准、完整。
7. 如果证据不足，不要生成该问题。
8. answer_type 只能从 auto_qa、field_answer、summary_answer、conditional_answer、reference_answer、card_answer、hybrid_answer 中选择。
"""


def _int_option(options: dict[str, Any] | None, path: str, default: int) -> int:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    try:
        return int(current)
    except Exception:
        return default


def _bool_option(options: dict[str, Any] | None, path: str, default: bool) -> bool:
    current: Any = options or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    if isinstance(current, bool):
        return current
    if isinstance(current, str):
        return current.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(current)


def _quote_alignment(quote: str, chunk: dict[str, Any]) -> dict[str, Any]:
    return align_quote_to_text(quote, chunk.get("content") or "").to_dict()


def _evidence_quality(alignments: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "") for item in alignments}
    if not alignments:
        return "no_evidence"
    if statuses <= {"exact"}:
        return "exact_evidence"
    if statuses <= {"exact", "normalized_exact"}:
        return "exact_evidence"
    if "failed" not in statuses:
        return "fuzzy_evidence"
    return "chunk_only"


def _chunk_context(chunks: list[dict[str, Any]], max_chars: int) -> str:
    return format_chunks_for_prompt(chunks, max_chars=max_chars, chunk_type="small_chunk", max_text_chars=4000)


def _summary_context(section_summaries: list[dict[str, Any]], max_items: int = 30) -> str:
    return format_summaries_for_prompt(section_summaries, max_items=max_items, max_chars=10000, max_summary_chars=600)


def _is_main_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    return metadata.get("content_role") != "appendix" and chunk.get("section_type") != "appendix"


def normalize_prebuilt_answers(payload: dict[str, Any], chunks: list[dict[str, Any]], *, max_pairs: int) -> dict[str, Any]:
    chunk_by_key = {str(chunk.get("chunk_key")): chunk for chunk in chunks if chunk.get("chunk_key")}
    qa_pairs: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_questions: set[str] = set()
    for index, raw in enumerate(payload.get("qa_pairs") or [], 1):
        if not isinstance(raw, dict):
            continue
        question = clean_text(raw.get("question"))
        answer = clean_text(raw.get("answer"))
        if not question or not answer:
            warnings.append(f"qa_prebuild_missing_question_or_answer:{index}")
            continue
        question_key = "".join(question.split()).lower()
        if question_key in seen_questions:
            warnings.append(f"qa_prebuild_duplicate_question:{index}")
            continue
        source_chunk_keys = [clean_text(item) for item in (raw.get("source_chunk_keys") or []) if clean_text(item)]
        evidence_quotes = [clean_text(item) for item in (raw.get("evidence_quotes") or []) if clean_text(item)]
        source_chunks = [chunk_by_key[key] for key in source_chunk_keys if key in chunk_by_key]
        if not source_chunks or not evidence_quotes:
            warnings.append(f"qa_prebuild_missing_evidence:{question[:40]}")
            continue
        quote_alignments: list[dict[str, Any]] = []
        aligned = True
        for quote in evidence_quotes:
            alignments = [_quote_alignment(quote, chunk) for chunk in source_chunks]
            best = sorted(
                alignments,
                key=lambda item: (
                    0 if item.get("status") == "exact" else 1 if item.get("status") == "normalized_exact" else 2 if item.get("status") == "fuzzy_aligned" else 3,
                    -float(item.get("coverage") or 0.0),
                ),
            )[0]
            quote_alignments.append({"quote": quote, **best})
            if best.get("status") == "failed":
                aligned = False
        if not aligned:
            warnings.append(f"qa_prebuild_evidence_unaligned:{question[:40]}")
            continue
        evidence_quality = _evidence_quality(quote_alignments)
        try:
            base_confidence = float(raw.get("confidence")) if raw.get("confidence") is not None else 0.75
        except Exception:
            base_confidence = 0.75
        if evidence_quality == "exact_evidence":
            confidence = max(base_confidence, 0.9)
            priority = int(raw.get("priority") or 0) + 20
        elif evidence_quality == "fuzzy_evidence":
            confidence = min(max(base_confidence, 0.72), 0.86)
            priority = int(raw.get("priority") or 0) + 10
        else:
            confidence = min(base_confidence, 0.45)
            priority = int(raw.get("priority") or 0) - 20
        seen_questions.add(question_key)
        qa_pairs.append(
            {
                "question": question,
                "answer": answer,
                "extended_questions": [clean_text(item) for item in (raw.get("extended_questions") or []) if clean_text(item)][:5],
                "answer_type": clean_text(raw.get("answer_type")) or "auto_qa",
                "generation_source": "auto_pregenerated",
                "source_type": clean_text(raw.get("source_type")) or "parse_answer_prebuild",
                "source_chunk_keys": source_chunk_keys,
                "evidence_quotes": evidence_quotes,
                "evidence_quality": evidence_quality,
                "confidence": round(confidence, 4),
                "priority": priority,
                "manual_override": False,
                "metadata": {
                    "generator": "answer_prebuilder",
                    "raw_index": index,
                    "reason": clean_text(raw.get("reason")),
                    "evidence_quality": evidence_quality,
                    "evidence_alignments": quote_alignments,
                },
            }
        )
        if len(qa_pairs) >= max_pairs:
            break
    return {
        "qa_pairs": qa_pairs,
        "warnings": warnings + [clean_text(item) for item in (payload.get("warnings") or []) if clean_text(item)],
    }


def prebuild_answers(
    *,
    chunks: list[dict[str, Any]],
    section_summaries: list[dict[str, Any]],
    knowledge_structure: dict[str, Any],
    profile: str,
    parse_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enabled = _bool_option(parse_options, "answer_prebuild.enabled", True)
    if not enabled:
        return {"qa_pairs": [], "warnings": ["answer_prebuild_disabled"]}
    small_chunks = [chunk for chunk in chunks if chunk.get("chunk_type") == "small_chunk"]
    primary_chunks = [chunk for chunk in small_chunks if _is_main_chunk(chunk)] or small_chunks or chunks
    max_pairs = max(1, _int_option(parse_options, "answer_prebuild.max_pairs", 30))
    max_chars = max(3000, _int_option(parse_options, "answer_prebuild.max_input_chars", 18000))
    user_prompt = f"""## Profile
{profile}

## Section Summaries
{_summary_context(section_summaries)}

## Knowledge Structure
{json.dumps(knowledge_prompt_view(knowledge_structure, max_anchors=80, max_units=120, max_relations=80), ensure_ascii=False, indent=2)}

## 输出 JSON Schema
{{
  "qa_pairs": [
    {{
      "question": "用户可能会问的问题",
      "extended_questions": ["同义问法1", "同义问法2"],
      "answer": "基于证据的简洁答案",
      "answer_type": "auto_qa|field_answer|summary_answer|conditional_answer|reference_answer|card_answer|hybrid_answer",
      "source_type": "parse_answer_prebuild",
      "source_chunk_keys": ["small_001_01"],
      "evidence_quotes": ["必须来自 source_chunk_keys 对应原文 chunk 的原文短句"],
      "confidence": 0.9,
      "priority": 0,
      "reason": "为什么这个问题值得预生成"
    }}
  ],
  "warnings": []
}}

## 原文 chunks
{_chunk_context(primary_chunks, max_chars)}
"""
    try:
        client = JsonChatClient("ANSWER_PREBUILD", default_model=True)
        payload = client.complete_json(ANSWER_PREBUILD_SYSTEM_PROMPT, user_prompt, temperature=0)
    except Exception as exc:
        return {"qa_pairs": [], "warnings": [f"answer_prebuild_llm_failed:{exc}"]}
    return normalize_prebuilt_answers(payload, primary_chunks, max_pairs=max_pairs)
