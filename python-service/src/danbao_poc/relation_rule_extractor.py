from __future__ import annotations

import re
from typing import Any

from .common import clean_text, stable_hash
from .graph_schema import global_knowledge_relation_types


ALLOWED_RELATION_TYPES = global_knowledge_relation_types()


RELATION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Adapted from GraphRAG-Example's CN_PATTERNS: regex relation extraction,
    # but constrained to guarantee-domain relations.
    ("alias_of", re.compile(r"(简称|又称|也称|也叫|别称|以下简称)")),
    ("belongs_to", re.compile(r"(属于|隶属于|归属于|划归|纳入|归口|由.+管理)")),
    ("contains", re.compile(r"(包括|包含|涵盖|由.{0,40}组成|分为|下设|设有|组成部分)")),
    ("responsible_for", re.compile(r"(负责|承担.{0,8}职责|履行.{0,8}职责|职责分工|牵头|配合|主办|承办)")),
    ("approves", re.compile(r"(审批|批准|备案|报批|核准|审议|决策|授权|签批|同意后)")),
    ("excludes_industry", re.compile(r"(禁入|限制|不支持|不得准入|禁止|负面清单).{0,20}(行业|领域|客户)")),
    ("prohibits", re.compile(r"(禁止|不得|严禁|不允许|不予|限制|不得.{0,20}办理|不得.{0,20}开展)")),
    ("applies_to", re.compile(r"(适用|适用于|覆盖|支持|面向|服务于|范围|区域|地区|省内|市内)")),
    ("targets_customer", re.compile(r"(服务对象|适用客户|客户类型|面向|主体|申请人)")),
    ("cooperates_with", re.compile(r"(合作银行|合作机构|经办机构|银行|机构)")),
    ("requires", re.compile(r"(需|需要|应|必须|提供|提交|满足|符合)")),
    ("depends_on", re.compile(r"(依赖|前置|基于|取决于|满足.{0,20}后|通过.{0,20}后|以.+为前提)")),
    ("constrained_by", re.compile(r"(不超过|不得超过|上限|最高|期限|费率|比例|额度)")),
    ("references", re.compile(r"(依据|根据|参照|引用|按照|遵循|依照)")),
]


def classify_relation_type(text: str) -> str | None:
    text = clean_text(text)
    if not text:
        return None
    for relation_type, pattern in RELATION_PATTERNS:
        if pattern.search(text):
            return relation_type
    return None


def build_rule_relations(
    *,
    anchors: list[dict[str, Any]],
    units: list[dict[str, Any]],
    existing_relations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    primary_anchor = anchors[0] if anchors else None
    if not primary_anchor:
        return []
    existing_keys = {
        (
            clean_text(item.get("from_id")),
            clean_text(item.get("to_id")),
            clean_text(item.get("relation_type")),
        )
        for item in (existing_relations or [])
    }
    existing_pairs = {(from_id, to_id) for from_id, to_id, _relation_type in existing_keys}
    result: list[dict[str, Any]] = []
    for unit in units:
        relation_text = clean_text(
            " ".join(
                str(part or "")
                for part in [
                    unit.get("unit_type"),
                    unit.get("unit_subtype"),
                    unit.get("subject_text"),
                    unit.get("predicate_text"),
                    unit.get("object_text"),
                    unit.get("evidence_quote"),
                ]
            )
        )
        relation_type = classify_relation_type(relation_text) or "has_unit"
        if relation_type not in ALLOWED_RELATION_TYPES:
            relation_type = "related_to"
        key = (primary_anchor["anchor_id"], unit["unit_id"], relation_type)
        if key in existing_keys or (key[0], key[1]) in existing_pairs:
            continue
        relation_id = f"rel_rule_{stable_hash('|'.join(key), 18)}"
        result.append(
            {
                "relation_id": relation_id,
                "relation_type": relation_type,
                "from_type": "anchor",
                "from_id": primary_anchor["anchor_id"],
                "to_type": "unit",
                "to_id": unit["unit_id"],
                "source_chunk_key": unit.get("primary_chunk_key"),
                "evidence_quote": unit.get("evidence_quote"),
                "confidence": min(float(unit.get("confidence") or 0.7), 0.86),
                "metadata": {
                    "rule_source": "graph_rag_cn_patterns",
                    "matched_text": relation_text[:300],
                },
            }
        )
    return result
