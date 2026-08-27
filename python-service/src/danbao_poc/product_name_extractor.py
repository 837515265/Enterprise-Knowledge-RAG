from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PRODUCT_NAME_ALIASES: dict[str, list[str]] = {
    "加工贷": ["鲁担惠农贷加工贷", "鲁担惠农贷_加工贷", "鲁担惠农贷-加工贷", "鲁担惠农贷 加工贷"],
    "种业贷": ["鲁担惠农贷种业贷", "鲁担惠农贷_种业贷", "鲁担惠农贷-种业贷", "鲁担惠农贷 种业贷"],
    "农服贷": ["鲁担惠农贷农服贷", "鲁担惠农贷_农服贷", "鲁担惠农贷-农服贷", "鲁担惠农贷 农服贷"],
    "农牧贷": ["鲁担惠农贷农牧贷", "鲁担惠农贷_农牧贷", "鲁担惠农贷-农牧贷", "鲁担惠农贷 农牧贷"],
    "强村贷": ["鲁担惠农贷强村贷", "鲁担惠农贷_强村贷", "鲁担惠农贷-强村贷", "鲁担惠农贷 强村贷"],
}

KNOWN_PRODUCT_NAMES = {
    "农贸贷", "农耕贷", "强村贷", "加工贷", "种业贷", "农牧贷", "农服贷",
    "果香贷", "文旅贷", "耕渔贷", "富农产业贷", "乡村文旅贷", "耕海牧渔贷",
    "鲁担惠农贷", "鲁担惠农贷加工贷", "鲁担惠农贷种业贷", "鲁担惠农贷农服贷", "鲁担惠农贷农牧贷",
    "莱阳梨", "冠县酥梨", "锦鲤养殖", "草莓产业", "烟台苹果", "数字设施渔业", "水产苗种繁育",
}

GENERIC_PRODUCT_NAMES = {"担保", "方案", "服务方案", "担保方案", "产品", "贷款"}
PRODUCT_PATTERN = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{2,18}(?:贷|保|方案)")


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _append_unique(items: list[str], value: Any) -> None:
    text = normalize_product_name(value)
    if text and text not in items:
        items.append(text)


def normalize_product_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = Path(text).stem
    text = re.sub(r"[\s_\-—–]+", "", text)
    text = re.sub(r"[《》（）()\[\]【】]", "", text)
    text = text.strip("：:；;，,。.")
    if not text or text in GENERIC_PRODUCT_NAMES or len(text) > 30:
        return ""
    return text


def expand_product_aliases(names: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    expanded: list[str] = []
    for raw in names:
        name = normalize_product_name(raw)
        if not name:
            continue
        _append_unique(expanded, name)
        for alias in PRODUCT_NAME_ALIASES.get(name, []):
            _append_unique(expanded, alias)
        for short_name, aliases in PRODUCT_NAME_ALIASES.items():
            normalized_aliases = {normalize_product_name(alias) for alias in aliases}
            if name in normalized_aliases:
                _append_unique(expanded, short_name)
                for alias in aliases:
                    _append_unique(expanded, alias)
    return expanded


def extract_product_names(*texts: Any, metadata: Any = None) -> list[str]:
    names: list[str] = []
    meta = _json_object(metadata)

    for key in ("product_names", "product_name", "plan_name", "scope_anchor", "scope_anchors"):
        value = meta.get(key)
        if isinstance(value, list):
            for item in value:
                _append_unique(names, item)
        else:
            _append_unique(names, value)

    joined = " ".join(str(text or "") for text in texts if text)
    normalized_joined = normalize_product_name(joined)
    for known in sorted(KNOWN_PRODUCT_NAMES, key=len, reverse=True):
        if known and known in joined:
            _append_unique(names, known)
    for match in PRODUCT_PATTERN.findall(joined):
        name = normalize_product_name(match)
        if name and name not in GENERIC_PRODUCT_NAMES:
            _append_unique(names, name)
    if normalized_joined in KNOWN_PRODUCT_NAMES:
        _append_unique(names, normalized_joined)

    return expand_product_aliases(names)
