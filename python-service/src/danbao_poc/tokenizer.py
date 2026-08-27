"""Application-level Chinese tokenizer using jieba.

Follows RAGFLOW's architecture: pre-tokenize text at the application layer,
store space-separated tokens in ES fields with `whitespace` analyzer,
so BM25 retrieval quality does not depend on ES plugins (IK, etc.).
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENABLED = os.getenv("TOKENIZER_ENABLED", "true").lower() != "false"
_USER_DICT = os.getenv("JIEBA_USER_DICT", "")

# Minimal Chinese stop words set — only high-frequency particles/connectors
# that hurt BM25 precision. Conservative: keep domain-relevant words.
_STOP_WORDS = frozenset(
    [
        "的",
        "了",
        "在",
        "是",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "着",
        "没有",
        "看",
        "好",
        "自己",
        "这",
    ]
)

# Pattern: text that is purely ASCII (English / digits / punctuation)
_PURE_ASCII = re.compile(r"^[\x00-\x7f]+$")

# Pattern: single CJK character (noise for BM25)
_SINGLE_CJK = re.compile(r"^[一-鿿]$")

# Pattern: whitespace / punctuation only
_WHITESPACE_OR_PUNCT = re.compile(r"^[\s\W]+$")

# ---------------------------------------------------------------------------
# Lazy jieba initialization
# ---------------------------------------------------------------------------

_jieba = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        try:
            import jieba as _jieba_mod
        except ModuleNotFoundError:
            logger.warning("jieba is not installed, falling back to regex tokenization")
            _jieba = False
            return None

        _jieba = _jieba_mod
        _jieba.setLogLevel(logging.WARNING)  # suppress jieba's init logs
        if _USER_DICT and os.path.isfile(_USER_DICT):
            _jieba.load_userdict(_USER_DICT)
            logger.info("jieba loaded user dict: %s", _USER_DICT)
    return _jieba


def _regex_tokens(text: str) -> list[str]:
    return [
        item
        for item in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", text or "")
        if item not in _STOP_WORDS and not _SINGLE_CJK.match(item)
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tokenize_text(text: str) -> str:
    """Return space-separated tokens for ES whitespace analyzer indexing.

    Uses jieba.cut_for_search() for maximum recall (search mode produces
    both short and long tokens, e.g. "公司章程" → "公司 章程 公司章程").

    Args:
        text: Raw Chinese (or mixed) text.

    Returns:
        Space-separated token string.  Empty string if no meaningful tokens.
    """
    if not _ENABLED:
        return text or ""

    if not text or not text.strip():
        return ""

    text = text.strip()

    # Pure ASCII — no tokenization needed, whitespace analyzer handles it
    if _PURE_ASCII.match(text):
        return text

    jb = _get_jieba()
    if not jb:
        return " ".join(_regex_tokens(text))
    tokens = jb.cut_for_search(text, HMM=True)

    result: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Drop stop words
        if tok in _STOP_WORDS:
            continue
        # Drop single CJK characters (noise for BM25)
        if _SINGLE_CJK.match(tok):
            continue
        # Drop pure whitespace/punctuation tokens
        if _WHITESPACE_OR_PUNCT.match(tok):
            continue
        result.append(tok)

    return " ".join(result)


def tokenize_list(text: str) -> list[str]:
    """Return token list for IDF aggregation (ES keyword array field).

    Same logic as tokenize_text() but returns a list instead of
    space-joined string, suitable for ES multi-value keyword fields.

    Args:
        text: Raw Chinese (or mixed) text.

    Returns:
        List of tokens. Empty list if no meaningful tokens.
    """
    if not _ENABLED:
        return text.split() if text else []

    if not text or not text.strip():
        return []

    text = text.strip()

    # Pure ASCII — split on whitespace
    if _PURE_ASCII.match(text):
        return text.split()

    jb = _get_jieba()
    if not jb:
        return _regex_tokens(text)
    tokens = jb.cut_for_search(text, HMM=True)

    result: list[str] = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if tok in _STOP_WORDS:
            continue
        if _SINGLE_CJK.match(tok):
            continue
        if _WHITESPACE_OR_PUNCT.match(tok):
            continue
        result.append(tok)

    return result
