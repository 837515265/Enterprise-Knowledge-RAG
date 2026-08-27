"""Three-dimensional term weighting (IDF + NER + POS).

Inspired by RAGFLOW's term_weight.py. Computes per-token weights for BM25
queries so that high-discriminance tokens (rare nouns, entity names) get
higher boost than high-frequency noise words (的, 是, 公司).

Dimensions:
  IDF — document frequency from ES aggregation
  NER — entity type boost from jieba.posseg (nt=机构 3x, ns=地名 2.5x, etc.)
  POS — part-of-speech boost (名词 2x, 动词 1.5x, 代词/连词 0.3x)
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NER boost — derived from jieba.posseg tags
# ---------------------------------------------------------------------------

NER_BOOST: dict[str, float] = {
    "nt": 3.0,   # 机构名（鲁农担、山东省农业发展信贷担保有限责任公司）
    "ns": 2.5,   # 地名（烟台、山东省）
    "nr": 2.0,   # 人名
    "nz": 2.0,   # 其他专名（三重一大）
    "t": 1.5,    # 时间（2025年）
    "m": 1.5,    # 数量（50万元）
}

# ---------------------------------------------------------------------------
# POS boost — base part-of-speech categories
# ---------------------------------------------------------------------------

POS_BOOST: dict[str, float] = {
    "n": 2.0, "nr": 2.0, "ns": 2.0, "nt": 2.0, "nz": 2.0,  # 名词
    "v": 1.5, "vd": 1.5, "vn": 1.5,                          # 动词
    "a": 1.0, "ad": 1.0, "an": 1.0,                          # 形容词
    "r": 0.3, "c": 0.3, "d": 0.3, "p": 0.3, "u": 0.2,      # 代词/连词/副词/介词/助词
}

# Default boost for unknown POS tags
_DEFAULT_POS_BOOST = 1.0

# ---------------------------------------------------------------------------
# IDF computation
# ---------------------------------------------------------------------------


def _compute_idf(df: int, N: int) -> float:
    """BM25-style IDF: log10(1 + (N - df + 0.5) / (df + 0.5))."""
    if N <= 0 or df < 0:
        return 1.0
    return math.log10(1 + (N - df + 0.5) / (df + 0.5))


# ---------------------------------------------------------------------------
# TermWeighter — singleton engine
# ---------------------------------------------------------------------------


class TermWeighter:
    """Three-dimensional term weighting engine."""

    def __init__(self) -> None:
        self._idf: dict[str, float] = {}
        self._N: int = 0
        self._ready: bool = False
        self._scoped_stats: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def corpus_size(self) -> int:
        return self._N

    def build_idf_from_es(
        self,
        es: Any,
        index: str = "knowledge_chunks_v1",
        token_field: str = "content_tks_tokens",
        kb_id: int | None = None,
        max_terms: int = 50000,
    ) -> None:
        """Build IDF dictionary from ES terms aggregation.

        Uses the _tks_tokens keyword field to get per-token document frequency.
        """
        try:
            # Get total document count
            count_query: dict[str, Any] = {"query": {"match_all": {}}}
            if kb_id is not None:
                count_query = {"query": {"term": {"kb_id": kb_id}}}
            count_resp = es.count(index=index, body=count_query)
            self._N = count_resp.get("count", 0)
            if self._N == 0:
                logger.warning("TermWeighter: no documents in %s, IDF disabled", index)
                return

            # Aggregate token frequencies
            agg_query: dict[str, Any] = {
                "size": 0,
                "aggs": {
                    "tokens": {
                        "terms": {
                            "field": token_field,
                            "size": max_terms,
                        }
                    }
                },
            }
            if kb_id is not None:
                agg_query["query"] = {"term": {"kb_id": kb_id}}

            resp = es.search(index=index, body=agg_query)
            buckets = (
                resp.get("aggregations", {}).get("tokens", {}).get("buckets", [])
            )

            idf = {}
            for bucket in buckets:
                token = bucket["key"]
                df = bucket["doc_count"]
                idf[token] = _compute_idf(df, self._N)

            self._idf = idf
            self._ready = True
            logger.info(
                "TermWeighter: IDF built from %s, N=%d, terms=%d",
                index, self._N, len(idf),
            )
        except Exception:
            logger.warning("TermWeighter: IDF build failed, using equal weights", exc_info=True)

    def ensure_scope_from_es(
        self,
        es: Any,
        *,
        index: str,
        token_field: str,
        kb_id: int | None = None,
        index_generations: list[str] | None = None,
        profiles: list[str] | None = None,
        max_terms: int = 50000,
        refresh: bool = False,
    ) -> str:
        """Build or reuse an IDF scope for one retrieval corpus.

        The previous implementation used one global IDF dictionary. That is
        too coarse for multi-KB retrieval: policy documents and guarantee
        plans have very different high-frequency terms. Scope keys include the
        KB, profile and active index generations so one corpus cannot dilute
        another.
        """
        key = self.scope_key(
            index=index,
            token_field=token_field,
            kb_id=kb_id,
            index_generations=index_generations,
            profiles=profiles,
        )
        with self._lock:
            existing = self._scoped_stats.get(key)
            if existing and existing.get("ready") and not refresh:
                return key
        filters = self._scope_filters(kb_id=kb_id, index_generations=index_generations, profiles=profiles)
        try:
            query = {"bool": {"filter": filters}} if filters else {"match_all": {}}
            count_resp = es.count(index=index, body={"query": query})
            corpus_size = int(count_resp.get("count") or 0)
            if corpus_size <= 0:
                with self._lock:
                    self._scoped_stats[key] = {
                        "idf": {},
                        "N": 0,
                        "ready": False,
                        "built_at": time.time(),
                        "error": "empty_corpus",
                    }
                return key
            agg_query: dict[str, Any] = {
                "size": 0,
                "query": query,
                "aggs": {
                    "tokens": {
                        "terms": {
                            "field": token_field,
                            "size": max_terms,
                        }
                    }
                },
            }
            resp = es.search(index=index, body=agg_query)
            buckets = resp.get("aggregations", {}).get("tokens", {}).get("buckets", [])
            idf = {bucket["key"]: _compute_idf(int(bucket["doc_count"]), corpus_size) for bucket in buckets}
            with self._lock:
                self._scoped_stats[key] = {
                    "idf": idf,
                    "N": corpus_size,
                    "ready": True,
                    "built_at": time.time(),
                    "index": index,
                    "token_field": token_field,
                    "kb_id": kb_id,
                    "index_generations": sorted(str(item) for item in (index_generations or [])),
                    "profiles": sorted(str(item) for item in (profiles or [])),
                }
            logger.info("TermWeighter: scoped IDF built key=%s N=%d terms=%d", key, corpus_size, len(idf))
            return key
        except Exception as exc:
            with self._lock:
                self._scoped_stats[key] = {
                    "idf": {},
                    "N": 0,
                    "ready": False,
                    "built_at": time.time(),
                    "error": str(exc),
                }
            logger.warning("TermWeighter: scoped IDF build failed key=%s", key, exc_info=True)
            return key

    @staticmethod
    def _scope_filters(
        *,
        kb_id: int | None = None,
        index_generations: list[str] | None = None,
        profiles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if kb_id is not None:
            filters.append({"term": {"kb_id": int(kb_id)}})
        if index_generations:
            filters.append({"terms": {"index_generation": [str(item) for item in index_generations]}})
        if profiles:
            filters.append({"terms": {"profile": [str(item) for item in profiles]}})
        return filters

    @staticmethod
    def scope_key(
        *,
        index: str,
        token_field: str,
        kb_id: int | None = None,
        index_generations: list[str] | None = None,
        profiles: list[str] | None = None,
    ) -> str:
        generations = ",".join(sorted(str(item) for item in (index_generations or []))) or "*"
        profile_part = ",".join(sorted(str(item) for item in (profiles or []))) or "*"
        return f"{index}:{token_field}:kb={kb_id or '*'}:profile={profile_part}:gen={generations}"

    def get_scope_debug(self, scope_key: str | None) -> dict[str, Any]:
        if not scope_key:
            return {"scope_key": None, "ready": self._ready, "corpus_size": self._N, "mode": "global"}
        with self._lock:
            stats = dict(self._scoped_stats.get(scope_key) or {})
        return {
            "scope_key": scope_key,
            "ready": bool(stats.get("ready")),
            "corpus_size": int(stats.get("N") or 0),
            "term_count": len(stats.get("idf") or {}),
            "mode": "scoped",
            "error": stats.get("error"),
        }

    def get_idf(self, token: str, scope_key: str | None = None) -> float:
        """Get IDF weight for a token. Returns default if not in corpus."""
        if scope_key:
            with self._lock:
                stats = self._scoped_stats.get(scope_key) or {}
                idf = stats.get("idf") or {}
                corpus_size = int(stats.get("N") or 0)
                ready = bool(stats.get("ready"))
            if not ready:
                return 1.0
            return float(idf.get(token, _compute_idf(0, max(corpus_size, 1))))
        if not self._ready:
            return 1.0
        return self._idf.get(token, _compute_idf(0, max(self._N, 1)))

    def weight_tokens(self, query: str, scope_key: str | None = None) -> list[tuple[str, float]]:
        """Tokenize query and compute three-dimensional weight for each token.

        Returns list of (token, weight) where weight = idf * ner_boost * pos_boost.
        """
        results: list[tuple[str, float]] = []
        seen: set[str] = set()
        try:
            import jieba.posseg as pseg
            token_iter = pseg.cut(query)
        except ModuleNotFoundError:
            import re
            token_iter = ((item, "n") for item in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", query or ""))

        for word, pos in token_iter:
            word = word.strip()
            if not word or len(word) < 2:
                continue
            if word in seen:
                continue
            seen.add(word)

            # IDF dimension
            idf = self.get_idf(word, scope_key)

            # NER dimension (entity type from POS tag)
            ner = NER_BOOST.get(pos, 1.0)

            # POS dimension (base part of speech)
            # For tags like 'vn', 'ad' — check full tag first, then first char
            pos_boost = POS_BOOST.get(pos, POS_BOOST.get(pos[0] if pos else "", _DEFAULT_POS_BOOST))

            weight = idf * ner * pos_boost
            results.append((word, round(weight, 3)))

        return results

    def build_weighted_query(
        self,
        query: str,
        fields: list[str],
        minimum_should_match: int | str = 1,
        scope_key: str | None = None,
    ) -> dict[str, Any]:
        """Build ES bool.should query with per-token IDF×NER×POS boost.

        Each token becomes a separate multi_match clause targeting the given
        fields, with the token's three-dimensional weight as boost.

        If IDF stats are not ready, falls back to a single multi_match
        (equivalent to the old behavior).
        """
        weighted = self.weight_tokens(query, scope_key)

        scope_ready = True
        if scope_key:
            with self._lock:
                scope_ready = bool((self._scoped_stats.get(scope_key) or {}).get("ready"))
        if (scope_key and not scope_ready) or (not scope_key and not self._ready) or not weighted:
            # Fallback: single multi_match, no per-token weighting
            return {
                "multi_match": {
                    "query": query,
                    "fields": fields,
                }
            }

        should_clauses: list[dict[str, Any]] = []
        for token, w in weighted:
            should_clauses.append(
                {
                    "multi_match": {
                        "query": token,
                        "fields": fields,
                        "boost": w,
                    }
                }
            )

        return {
            "bool": {
                "should": should_clauses,
                "minimum_should_match": minimum_should_match,
            }
        }

    def weighted_tokens_string(self, query: str, scope_key: str | None = None) -> str:
        """Return tokenized query string (for backward compatibility).

        Same as tokenize_text() but goes through the posseg path.
        """
        weighted = self.weight_tokens(query, scope_key)
        return " ".join(tok for tok, _ in weighted)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: TermWeighter | None = None


def get_term_weighter() -> TermWeighter:
    """Get or create the global TermWeighter instance."""
    global _instance
    if _instance is None:
        _instance = TermWeighter()
    return _instance
