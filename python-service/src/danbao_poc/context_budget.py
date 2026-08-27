"""Context budget management utilities for handling long documents with limited LLM context.

Strategies implemented:
- P1: Grouped extraction with merge (for extractor)
- P1: Priority-based chunk selection (for extractor)
- P2: Two-stage planner (skeleton scan + windowed planning)
- P2: Content pre-compression
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any

from .common import clean_text

logger = logging.getLogger(__name__)


# ─── 全局预算配置 ──────────────────────────────────────────────

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


# 模型总上下文 token 数
MODEL_MAX_TOKENS = _int_env("DEFAULT_MODEL_MAX_TOKENS", 32000)
# 输出预留 token
OUTPUT_RESERVE_TOKENS = _int_env("OUTPUT_RESERVE_TOKENS", 4000)
# 中文 token 与字符的近似比 (1 token ≈ 1.5 字符, 保守)
TOKEN_CHAR_RATIO = float(os.getenv("TOKEN_CHAR_RATIO", "1.5"))


def compute_available_chars(
    system_prompt_chars: int = 0,
    model_max_tokens: int | None = None,
    output_reserve: int | None = None,
) -> int:
    """计算可用于用户 prompt 内容的最大字符数。"""
    max_tokens = model_max_tokens or MODEL_MAX_TOKENS
    reserve = output_reserve or OUTPUT_RESERVE_TOKENS
    available_tokens = max_tokens - reserve
    available_chars = int(available_tokens * TOKEN_CHAR_RATIO)
    return max(4000, available_chars - system_prompt_chars)


# ─── P2: 内容预压缩 ──────────────────────────────────────────

# 页码行模式
_PAGE_NUMBER_RE = re.compile(r"^—\s*\d+\s*—$")
# 纯空白行模式
_BLANK_LINE_RE = re.compile(r"^\s*$")
# 常见无意义前缀
_NOISE_PREFIX_RE = re.compile(r"^(注[：:]|备注[：:]|说明[：:])\s*$")


def compress_text(text: str, max_chars: int = 0) -> str:
    """压缩文本，去除页码、多余空白、无意义前缀。"""
    if not text:
        return ""
    # 去除页码行
    text = _PAGE_NUMBER_RE.sub("", text)
    # 合并连续空白为单个空格
    text = re.sub(r"\s+", " ", text).strip()
    # 截断
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


def compress_block_for_planner(text: str, max_chars: int = 120) -> str:
    """为 Planner 压缩 block 文本 — 只保留开头用于边界识别。"""
    text = compress_text(text)
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


# ─── P2: 两阶段 Planner — 骨架扫描 ──────────────────────────

_SKELETON_SYSTEM = (
    "你是文档结构快速识别器。\n"
    "请根据文档的标题列表，识别出一级章节边界。\n"
    "只返回 JSON，格式为 {\"boundaries\": [{\"block_id\": \"...\", \"title\": \"...\"}]}。\n"
    "只标注一级章节的起始 block_id（如 一、xxx / 二、xxx / 第一章 / 附件 等）。\n"
    "编号条款（1. 2. 3. (1) (2)）不是一级边界，不要返回。\n"
    "如果文档没有明显的一级结构，返回 {\"boundaries\": []}。"
)


def build_skeleton_text(blocks: list[dict[str, Any]], max_chars: int = 8000) -> tuple[str, dict[str, int]]:
    """生成骨架文本：每个 block 只保留前 40 字符，用于粗粒度边界识别。"""
    rows: list[str] = []
    block_index: dict[str, int] = {}
    size = 0
    for i, block in enumerate(blocks):
        block_id = clean_text(block.get("block_id")) or f"block_{i + 1:04d}"
        block_index[block_id] = i
        text = compress_text(clean_text(block.get("text")), max_chars=40)
        row = f"[{block_id}] {text}\n"
        if size + len(row) > max_chars:
            break
        rows.append(row)
        size += len(row)
    return "".join(rows), block_index


def skeleton_scan(blocks: list[dict[str, Any]], document_title: str) -> list[dict[str, Any]]:
    """阶段1：用极少 token 做粗粒度一级边界识别。

    Returns:
        list of {"block_id": str, "title": str, "start_index": int, "end_index": int}
    """
    skeleton_text, block_index = build_skeleton_text(blocks, max_chars=8000)
    if not skeleton_text.strip():
        return [{"block_id": "", "title": document_title, "start_index": 0, "end_index": len(blocks) - 1}]

    try:
        from .openai_compat import JsonChatClient
        client = JsonChatClient("CHUNK_PLANNER", default_model=True, enable_fallback=True)
        result = client.complete_json(
            system_prompt=_SKELETON_SYSTEM,
            user_prompt=(
                f"以下是文档 '{document_title}' 的全部 block 标题列表。\n"
                "请识别一级章节边界（如 一、xxx / 第一章 / 附件 等）。\n"
                "只返回 JSON。\n\n"
                f"{skeleton_text}"
            ),
            temperature=0,
            max_tokens=1000,
        )
    except Exception:
        logger.warning("Skeleton scan failed, treating as single section")
        return [{"block_id": "", "title": document_title, "start_index": 0, "end_index": len(blocks) - 1}]

    boundaries = result.get("boundaries") or []
    if not boundaries:
        return [{"block_id": "", "title": document_title, "start_index": 0, "end_index": len(blocks) - 1}]

    # 把 boundaries 转换为 window 列表
    windows: list[dict[str, Any]] = []
    for i, boundary in enumerate(boundaries):
        bid = clean_text(boundary.get("block_id"))
        if bid not in block_index:
            continue
        start_idx = block_index[bid]
        # end_index = 下一个 boundary 的 start - 1，或者文档末尾
        if i + 1 < len(boundaries):
            next_bid = clean_text(boundaries[i + 1].get("block_id"))
            end_idx = block_index.get(next_bid, len(blocks)) - 1
        else:
            end_idx = len(blocks) - 1
        windows.append({
            "block_id": bid,
            "title": clean_text(boundary.get("title")) or document_title,
            "start_index": start_idx,
            "end_index": end_idx,
        })

    # 处理第一个 boundary 前面的 blocks
    if windows and windows[0]["start_index"] > 0:
        windows.insert(0, {
            "block_id": "",
            "title": document_title,
            "start_index": 0,
            "end_index": windows[0]["start_index"] - 1,
        })

    return windows if windows else [{"block_id": "", "title": document_title, "start_index": 0, "end_index": len(blocks) - 1}]


def split_blocks_into_windows(
    blocks: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    max_chars_per_window: int,
    overlap_blocks: int = 3,
) -> list[tuple[list[dict[str, Any]], str]]:
    """根据骨架扫描结果，将 blocks 切分为多个窗口。

    每个窗口前后加 overlap_blocks 个 block 做上下文重叠。
    如果单个窗口的文本量仍超过 max_chars_per_window，进一步等分。

    Returns:
        list of (window_blocks, window_title)
    """
    result: list[tuple[list[dict[str, Any]], str]] = []
    for window in windows:
        start = max(0, window["start_index"] - overlap_blocks)
        end = min(len(blocks), window["end_index"] + 1 + overlap_blocks)
        window_blocks = blocks[start:end]
        # 估算文本量
        total_chars = sum(len(clean_text(b.get("text")) or "") for b in window_blocks)
        if total_chars <= max_chars_per_window:
            result.append((window_blocks, window["title"]))
        else:
            # 窗口太大，按最大字符数拆分
            chunk_blocks: list[dict[str, Any]] = []
            chunk_chars = 0
            for block in window_blocks:
                block_chars = len(clean_text(block.get("text")) or "")
                if chunk_blocks and chunk_chars + block_chars > max_chars_per_window:
                    result.append((chunk_blocks, window["title"]))
                    chunk_blocks = []
                    chunk_chars = 0
                chunk_blocks.append(block)
                chunk_chars += block_chars
            if chunk_blocks:
                result.append((chunk_blocks, window["title"]))
    return result


# ─── P1: 分组抽取 ─────────────────────────────────────────────

def group_chunks_for_extraction(
    chunks: list[dict[str, Any]],
    max_chars_per_group: int = 20000,
) -> list[list[dict[str, Any]]]:
    """将 chunks 按 business_block + section_type 分组。

    如果所有 chunks 的总文本量在预算内，返回 [全部 chunks]。
    否则按组分批，优先将有明确 section_type 的 chunks 分到同一组。
    """
    total_chars = sum(len(chunk.get("content") or "") + 200 for chunk in chunks)
    if total_chars <= max_chars_per_group:
        return [chunks]

    # 按 business_block_id + section_type 分组
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        block_id = clean_text(metadata.get("business_block_id")) or ""
        section_type = chunk.get("section_type") or "other"
        key = f"{block_id}|{section_type}"
        groups[key].append(chunk)

    # 将小组合并为批次，每批不超过预算
    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_size = 0

    # 排序：有明确 section_type 的优先
    sorted_keys = sorted(groups.keys(), key=lambda k: (0 if k.split("|")[1] != "other" else 1, k))

    for key in sorted_keys:
        group = groups[key]
        group_size = sum(len(c.get("content") or "") + 200 for c in group)

        if group_size > max_chars_per_group:
            # 单组超预算，独立成批，并截断
            if current_batch:
                batches.append(current_batch)
                current_batch = []
                current_size = 0
            # 分割大组
            sub_batch: list[dict[str, Any]] = []
            sub_size = 0
            for chunk in group:
                chunk_size = len(chunk.get("content") or "") + 200
                if sub_batch and sub_size + chunk_size > max_chars_per_group:
                    batches.append(sub_batch)
                    sub_batch = []
                    sub_size = 0
                sub_batch.append(chunk)
                sub_size += chunk_size
            if sub_batch:
                batches.append(sub_batch)
            continue

        if current_size + group_size > max_chars_per_group:
            if current_batch:
                batches.append(current_batch)
            current_batch = list(group)
            current_size = group_size
        else:
            current_batch.extend(group)
            current_size += group_size

    if current_batch:
        batches.append(current_batch)

    return batches if batches else [chunks]


def select_priority_chunks(
    chunks: list[dict[str, Any]],
    max_chars: int = 20000,
) -> list[dict[str, Any]]:
    """优先选择有明确 section_type 的 chunks，截断以适应预算。"""
    priority = [c for c in chunks if c.get("section_type") not in (None, "", "other")]
    other = [c for c in chunks if c.get("section_type") in (None, "", "other")]

    selected: list[dict[str, Any]] = []
    total = 0
    for chunk in priority + other:
        content = chunk.get("content") or ""
        cost = len(content) + 200
        if total + cost > max_chars:
            remaining = max_chars - total - 200
            if remaining > 100 and chunk in priority:
                chunk = dict(chunk)
                chunk["content"] = content[:remaining] + "…（截断）"
                selected.append(chunk)
            break
        selected.append(chunk)
        total += cost
    return selected


# ─── P1: 字段去重与合并 ───────────────────────────────────────

def dedupe_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对来自多批次抽取的 fields 做去重。

    规则：
    - 相同 field_code + 相同 business_block_id 只保留 confidence 最高的
    - confidence 排序：HIGH > MEDIUM > LOW
    """
    confidence_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "": 3}
    best: dict[str, dict[str, Any]] = {}

    for field in fields:
        code = field.get("field_code") or ""
        block_id = field.get("business_block_id") or ""
        key = f"{block_id}:{code}"

        existing = best.get(key)
        if existing is None:
            best[key] = field
            continue

        existing_conf = confidence_order.get(clean_text(existing.get("confidence")).upper(), 3)
        new_conf = confidence_order.get(clean_text(field.get("confidence")).upper(), 3)
        if new_conf < existing_conf:
            best[key] = field
        elif new_conf == existing_conf:
            # 更长的 value_text 优先
            if len(field.get("value_text") or "") > len(existing.get("value_text") or ""):
                best[key] = field

    return list(best.values())


def merge_plan_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """合并两个 plan 字典，overlay 中非空值覆盖 base。"""
    merged = dict(base)
    for key, value in overlay.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        merged[key] = value
    return merged
