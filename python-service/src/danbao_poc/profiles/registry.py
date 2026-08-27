"""Profile 注册中心：标准化、别名兼容、策略分发。

业务系统在上传文件或创建知识库时已经标注了文档分类（profile），
解析服务只负责校验和标准化，不做复杂自动分类。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import unquote

logger = logging.getLogger(__name__)

from danbao_poc.chunker_common import (
    chunk_by_headers as _chunk_by_headers,
    doc_title as _doc_title,
    embedding_text as _embedding_text,
    renumber_chunks as _renumber_chunks,
)
from danbao_poc.common import canonical_key, clean_text


# ── 支持的 Profile 集合 ──────────────────────────────────────
SUPPORTED_PROFILES = {
    "business_plan",
    "general_document",
    "governance_rule",
    "project_doc",
    "sql_analytics",
    "contract_agreement",
    "structured_data",
    "operation_knowledge",
}

# ── 别名映射（业务系统可能传中文、旧值等） ──────────────────
PROFILE_ALIASES: dict[str, str] = {
    # 旧值 → 新值
    "guarantee_plan": "business_plan",
    "general": "general_document",
    # 中文 → 英文
    "担保方案": "business_plan",
    "授信方案": "business_plan",
    "业务方案": "business_plan",
    "运营知识": "operation_knowledge",
    "运营": "operation_knowledge",
    "经营知识": "operation_knowledge",
    "普通文档": "general_document",
    "通用文档": "general_document",
    "制度": "governance_rule",
    "制度办法": "governance_rule",
    "制度规章": "governance_rule",
    "规章制度": "governance_rule",
    "项目文档": "project_doc",
    "技术方案": "project_doc",
    "技术文档": "project_doc",
    "智能问数": "sql_analytics",
    "SQL问数": "sql_analytics",
    "经营问数": "sql_analytics",
    "sql_planner": "sql_analytics",
    "nl2sql": "sql_analytics",
    "合同": "contract_agreement",
    "协议": "contract_agreement",
    "合同协议": "contract_agreement",
    "表格": "structured_data",
    "台账": "structured_data",
    "报表": "structured_data",
}


def normalize_profile(profile: str | None) -> str | None:
    """把外部传入的 profile 标准化为内部名称。"""
    if not profile:
        return None
    value = profile.strip()
    return PROFILE_ALIASES.get(value, value)


def profile_filter_values(profile: str) -> list[str]:
    """ES/MySQL 查询时需要兼容新旧值的 filter 列表。"""
    normalized = normalize_profile(profile) or profile
    if normalized == "business_plan":
        return ["business_plan", "guarantee_plan"]
    return [normalized]


def resolve_profile(
    requested_profile: str | None,
    *,
    file_name: str = "",
    text_sample: str = "",
    allow_fallback: bool = False,
) -> str:
    """严格校验并规范化外部 profile，不做任何自动分类或兜底。

    ``file_name``、``text_sample`` 和 ``allow_fallback`` 仅为兼容旧调用签名保留；
    文件名、内容、后缀以及非法值都不会再触发 profile 推测。
    """
    normalized = normalize_profile(requested_profile)
    if normalized and normalized != "auto":
        if normalized in SUPPORTED_PROFILES:
            return normalized
        raise ValueError(f"Unsupported profile: {requested_profile}")
    raise ValueError("Profile is required; provide a file profile or use the knowledge base profile")


# ── ProfileSpec：每个 Profile 的策略组合 ──────────────────────
@dataclass(frozen=True)
class ProfileSpec:
    """一个 Profile 的完整策略描述。"""
    code: str
    display_name: str
    chunker: Callable[[dict[str, Any]], list[dict[str, Any]]]
    extractor: Callable[..., dict[str, Any]]
    graph_builder: Callable[[dict[str, Any]], tuple[list[dict], list[dict]]] | None = None
    default_modes: tuple[str, ...] = ("bm25", "vector")
    field_aliases: dict[str, list[str]] = field(default_factory=dict)
    field_hints: dict[str, str] = field(default_factory=dict)
    catalog_builder: Callable[..., Any] | None = None
    enable_section_summaries: bool = True
    enable_knowledge_extraction: bool = True
    enable_answer_prebuild: bool = True


# ── 延迟注册表（各 profile 模块启动时注册） ────────────────────
_REGISTRY: dict[str, ProfileSpec] = {}
_DEFAULT_PROFILES_REGISTERED = False


def register_profile(spec: ProfileSpec) -> None:
    _REGISTRY[spec.code] = spec


def get_profile_spec(profile: str) -> ProfileSpec:
    register_default_profiles()
    normalized = normalize_profile(profile) or profile
    if normalized in _REGISTRY:
        return _REGISTRY[normalized]
    if normalized in SUPPORTED_PROFILES:
        raise ValueError(f"Profile '{profile}' is recognized but no parser strategy is registered")
    if "general_document" in _REGISTRY:
        return _REGISTRY["general_document"]
    raise ValueError(f"Profile '{profile}' not registered and no general_document fallback")


def list_profiles() -> list[str]:
    register_default_profiles()
    return sorted(_REGISTRY.keys())


# ── 默认 Profile 实现 ─────────────────────────────────────────
_CLAUSE_RE = re.compile(r"(第[一二三四五六七八九十百千万0-9]+条)")
_CHAPTER_RE = re.compile(r"(第[一二三四五六七八九十百千万0-9]+章|第[一二三四五六七八九十百千万0-9]+节)")
_ITEM_MARK_RE = re.compile(r"(?m)(（[一二三四五六七八九十0-9]+）|\([一二三四五六七八九十0-9]+\)|[0-9]+[.．、])")
_API_RE = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH)\s+([/\w.\-{}:]+)", re.IGNORECASE)
_PARAM_RE = re.compile(r"(?:参数|入参|请求参数)[:：]\s*([^\n]+)", re.IGNORECASE)
_ERROR_RE = re.compile(r"(?:错误码|异常码|返回码)[:：]\s*([^\n]+)", re.IGNORECASE)
_CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?([A-Za-z_][\w]*)[`\"']?", re.IGNORECASE)
_FENCED_CODE_RE = re.compile(r"```(\w+)?\s*\n(.*?)```", re.DOTALL)
_CONFIG_RE = re.compile(r"(?m)^\s*([A-Z][A-Z0-9_]{2,}|[a-z][a-z0-9_.-]{2,})\s*[:=]\s*(.+)$")
_AMOUNT_RE = re.compile(r"(?:(人民币|RMB|¥)\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万元|亿元|元)?")
_DATE_RE = re.compile(r"(\d{4}[-年/.]\d{1,2}(?:[-月/.]\d{1,2}日?)?)")
_PARTY_NAME_RE = re.compile(r"(甲方|乙方|丙方|委托方|受托方|双方)?(?:名称|全称)[:：]\s*([^；;\n]+)")


def _clone_chunk_with_content(
    base: dict[str, Any],
    *,
    content: str,
    title: str | None = None,
    chunk_type: str | None = None,
    section_type: str | None = None,
    section_id: str | None = None,
    chunk_group_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from danbao_poc.common import clean_text, stable_hash

    content = clean_text(content)
    new_chunk = dict(base)
    resolved_title = clean_text(title or base.get("title") or "")
    new_chunk["content"] = content
    new_chunk["summary"] = content[:180]
    new_chunk["content_hash"] = stable_hash(content, 40)
    new_chunk["title"] = resolved_title
    title_path = list(base.get("title_path") or [])
    if title_path:
        title_path[-1] = resolved_title
    else:
        title_path = [resolved_title]
    new_chunk["title_path"] = title_path
    if chunk_type:
        new_chunk["chunk_type"] = chunk_type
    if section_type:
        new_chunk["section_type"] = section_type
    if section_id:
        new_chunk["section_id"] = section_id
    if chunk_group_id:
        new_chunk["chunk_group_id"] = chunk_group_id
    doc_title = (base.get("metadata") or {}).get("document_title") or (title_path[0] if title_path else "")
    new_chunk["content_for_embedding"] = _embedding_text(doc_title, resolved_title, content)
    new_chunk["content_for_bm25"] = clean_text(f"{doc_title} {resolved_title} {content}")
    new_chunk["metadata"] = {**(base.get("metadata") or {}), **(metadata or {})}
    return new_chunk


def _extract_chapter_id(title: str, content: str) -> str | None:
    match = _CHAPTER_RE.search(f"{title}\n{content}")
    return match.group(1) if match else None


def _split_by_matches(content: str, matches: list[re.Match]) -> list[tuple[str, str]]:
    from danbao_poc.common import clean_text

    parts: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        part = clean_text(content[match.start():end])
        if part:
            parts.append((match.group(1), part))
    return parts


def _detect_rule_section_type(text: str) -> str:
    if "附件" in text:
        return "appendix"
    if "附则" in text:
        return "supplementary_clause"
    if any(word in text for word in ["生效", "施行", "废止", "解释权"]):
        return "effective_clause"
    if any(word in text for word in ["职责", "职权", "权限", "负责", "责任部门", "职责分工"]):
        return "responsibility_clause"
    if any(word in text for word in ["流程", "程序", "申请", "审批", "办理", "授权", "决策", "表决", "议事规则", "会议"]):
        return "procedure_clause"
    if any(word in text for word in ["处罚", "追责", "责任追究", "问责"]):
        return "penalty_clause"
    if any(word in text for word in ["标准", "费用", "收费", "额度", "比例", "财务", "资金", "预算", "大额资金"]):
        return "standard_clause"
    return "clause"


def _module_from_title_path(chunk: dict[str, Any]) -> str | None:
    title_path = chunk.get("title_path") or []
    if isinstance(title_path, list) and len(title_path) >= 2:
        return str(title_path[-2] or title_path[-1])
    return chunk.get("title")


def _ast_fallback_if_useful(
    middle_document: dict[str, Any],
    current_chunks: list[dict[str, Any]],
    *,
    profile: str,
    chunk_type: str,
) -> list[dict[str, Any]]:
    from danbao_poc.ast_chunker import chunk_by_markdown_ast_fallback

    ast_chunks = chunk_by_markdown_ast_fallback(middle_document, profile=profile, chunk_type=chunk_type)
    if len(ast_chunks) >= 2 and len(ast_chunks) > len(current_chunks):
        return ast_chunks
    return current_chunks


def _chunk_general_document(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    # 文件名以"字段-"开头的表结构文件 → 按物理表拆，保持每个表一个完整 chunk
    file_name = unquote(clean_text(middle_document.get("file_name") or ""))
    if file_name.startswith("字段-"):
        field_chunks = _chunk_sql_field_tables(middle_document)
        if field_chunks:
            return field_chunks
    chunks = _chunk_by_headers(middle_document, chunk_type="text_section")
    return _ast_fallback_if_useful(
        middle_document,
        chunks,
        profile="general_document",
        chunk_type="text_section",
    )


# 表结构文件：按表名标题切 chunk 的辅助正则
# 表名标题：以"表"结尾的标题行（如"智能问数数据表"、"智能问数业务数据表"）。
# 排除含冒号的（如"业务说明：智能问数数据表"、"物理表：xxx"）——那是元信息行不是标题。
_TABLE_TITLE_RE = re.compile(r"^#{0,6}\s*[一-龥A-Za-z0-9_（）()\- ]{1,60}表\s*$")


def _chunk_sql_field_tables(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    """把"字段-XX表结构"文件按表名标题拆成多个 chunk。

    每个 chunk = 一个完整表块：表名标题 + 表元信息行（数据源/Catalog/物理表等）
    + 字段标题 + 字段表格（markdown 或空格分隔均可）。切分边界 = 下一个表名标题。
    """
    from danbao_poc.ast_chunker import _append_chunk as _ast_append_chunk, _source_text

    text = clean_text(_source_text(middle_document))
    logger.info("_chunk_sql_field_tables invoked file_name=%s text_len=%s", middle_document.get("file_name"), len(text))
    if not text:
        return []
    lines = text.splitlines()
    doc_title_value = _doc_title(middle_document)

    # 定位所有"表名标题"行（以"表"结尾、不含冒号）
    title_indices: list[int] = []
    for i, raw_line in enumerate(lines):
        line = clean_text(raw_line)
        if not line:
            continue
        if "：" in line or ":" in line:
            continue
        if _TABLE_TITLE_RE.match(line):
            title_indices.append(i)
    if not title_indices:
        return []

    chunks: list[dict[str, Any]] = []
    # 第一个表名标题之前的"文件头"（如"# XX表结构知识"总标题），并入第一个表块
    file_header = [clean_text(line) for line in lines[: title_indices[0]] if clean_text(line)] if title_indices else []
    for idx, title_idx in enumerate(title_indices):
        # 表块范围 = [title_idx, 下一个表名标题)
        next_title_idx = title_indices[idx + 1] if idx + 1 < len(title_indices) else len(lines)
        block_lines = [clean_text(line) for line in lines[title_idx:next_title_idx] if clean_text(line)]
        if idx == 0 and file_header:
            block_lines = [*file_header, *block_lines]
        content = clean_text("\n".join(block_lines))
        if not content:
            continue
        table_name = clean_text(lines[title_idx]).lstrip("#").strip()
        title_path = [doc_title_value, table_name]
        _ast_append_chunk(
            chunks,
            doc_title_value=doc_title_value,
            middle_document=middle_document,
            title_path=title_path,
            content=content,
            chunk_type="table_region",
            section_type="table_region",
            pages=[],
            block_ids=[],
            metadata={
                "table_name": table_name,
                "sql_field_table": True,
                "profile": middle_document.get("profile"),
            },
        )
    return _renumber_chunks(chunks) if chunks else []


def _chunk_sql_analytics(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    """sql_analytics 文件切块：委托通用切块（已内置字段表按物理表拆分）。"""
    return _chunk_general_document(middle_document)


def _catalog_builder_field_aware(
    middle_document: dict[str, Any],
    *,
    profile: str,
    document_title: str,
    parse_options: dict[str, Any] | None,
) -> "Any":
    """通用 catalog builder：文件名以"字段-"开头的表结构文件按表名拆，
    其余走默认 LLM catalog。
    """
    from danbao_poc.catalog_chunker import CatalogBuildResult, build_catalog_driven_chunks

    file_name = clean_text(middle_document.get("file_name") or document_title or "")
    file_name = unquote(file_name)  # middle_document.file_name 可能是 URL 编码
    if file_name.startswith("字段-"):
        chunks = _chunk_sql_field_tables(middle_document)
        if chunks:
            return CatalogBuildResult(
                chunks=chunks,
                catalog_artifact={
                    "catalog_source": "sql_field_table_name",
                    "fallback": None,
                    "profile": profile,
                    "document_title": document_title,
                    "chunk_count": len(chunks),
                },
                warnings=[],
            )
    return build_catalog_driven_chunks(
        middle_document,
        profile=profile,
        document_title=document_title,
        parse_options=parse_options,
    )


def _chunk_governance_rule(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    from danbao_poc.common import clean_text

    chunks: list[dict[str, Any]] = []
    source_chunks = _ast_fallback_if_useful(
        middle_document,
        _chunk_by_headers(middle_document, chunk_type="clause"),
        profile="governance_rule",
        chunk_type="clause",
    )
    for chunk in source_chunks:
        content = chunk.get("content") or ""
        chapter_id = _extract_chapter_id(chunk.get("title") or "", content)
        matches = list(_CLAUSE_RE.finditer(content))
        if len(matches) <= 1:
            clause_id = matches[0].group(1) if matches else None
            section_type = _detect_rule_section_type(f"{chunk.get('title') or ''}\n{content}")
            chunk["section_type"] = section_type if clause_id else chunk.get("section_type")
            chunk["metadata"] = {
                **(chunk.get("metadata") or {}),
                "chapter_id": chapter_id,
                "clause_id": clause_id,
                "hierarchy_level": "article" if clause_id else "section",
                "confidence": "EXTRACTED" if clause_id else "INFERRED",
            }
            chunks.append(chunk)
            continue
        for clause_index, (clause_id, part) in enumerate(_split_by_matches(content, matches), 1):
            section_type = _detect_rule_section_type(part)
            item_matches = list(_ITEM_MARK_RE.finditer(part))
            has_items = len(item_matches) >= 2
            parent_chunk = _clone_chunk_with_content(
                chunk,
                content=part if not has_items else clean_text(part[: item_matches[0].start()]) or part[:300],
                title=f"{clause_id} {chunk.get('title') or ''}".strip(),
                chunk_type="clause_parent" if has_items else "clause",
                section_type="clause_parent" if has_items else section_type,
                section_id=clause_id,
                chunk_group_id=f"clause:{clause_id}",
                metadata={
                    "chapter_id": chapter_id,
                    "clause_id": clause_id,
                    "clause_order": clause_index,
                    "hierarchy_level": "article",
                    "rule_section_type": section_type,
                    "has_child_items": has_items,
                    "confidence": "EXTRACTED",
                },
            )
            chunks.append(parent_chunk)
            if not has_items:
                continue
            for item_index, (item_id, item_content) in enumerate(_split_by_matches(part, item_matches), 1):
                child_title = f"{clause_id}{item_id}"
                chunks.append(
                    _clone_chunk_with_content(
                        chunk,
                        content=item_content,
                        title=child_title,
                        chunk_type="clause_item",
                        section_type=section_type,
                        section_id=f"{clause_id}:{item_id}",
                        chunk_group_id=f"clause:{clause_id}",
                        metadata={
                            "chapter_id": chapter_id,
                            "clause_id": clause_id,
                            "parent_clause_id": clause_id,
                            "item_id": item_id,
                            "clause_order": clause_index,
                            "item_order": item_index,
                            "hierarchy_level": "item",
                            "rule_section_type": section_type,
                            "confidence": "EXTRACTED",
                        },
                    )
                )
    return _renumber_chunks(chunks)


def _chunk_project_doc(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    from danbao_poc.common import clean_text

    enhanced: list[dict[str, Any]] = []
    source_chunks = _ast_fallback_if_useful(
        middle_document,
        _chunk_by_headers(middle_document, chunk_type="project_section"),
        profile="project_doc",
        chunk_type="project_section",
    )
    for chunk in source_chunks:
        content = chunk.get("content") or ""
        module_name = _module_from_title_path(chunk)
        module_key = canonical_key("module", module_name)
        api_matches = list(_API_RE.finditer(content))
        code_matches = list(_FENCED_CODE_RE.finditer(content))
        table_matches = list(_CREATE_TABLE_RE.finditer(content))
        config_matches = list(_CONFIG_RE.finditer(content))

        added_specialized = False
        if api_matches:
            for api_index, match in enumerate(api_matches, 1):
                end = api_matches[api_index].start() if api_index < len(api_matches) else len(content)
                api_content = clean_text(content[match.start():end])
                method = match.group(1).upper()
                path = match.group(2)
                api_key = f"{method} {path}"
                api_identity = canonical_key("api", method, path)
                enhanced.append(
                    _clone_chunk_with_content(
                        chunk,
                        content=api_content,
                        title=api_key,
                        chunk_type="api_spec",
                        section_type="api_spec",
                        section_id=f"api:{method}:{path}",
                        chunk_group_id=f"api:{method}:{path}",
                        metadata={
                            "project_chunk_strategy": "api_spec",
                            "module": module_name,
                            "module_key": module_key,
                            "api_method": method,
                            "api_path": path,
                            "api_group_id": f"{method} {path}",
                            "api_key": api_identity,
                            "confidence": "EXTRACTED",
                        },
                    )
                )
                added_specialized = True
                if any(word in api_content for word in ["参数", "请求体", "入参", "出参", "返回"]):
                    param_lines = [item.group(0) for item in _PARAM_RE.finditer(api_content)]
                    param_content = clean_text("\n".join(param_lines)) or api_content
                    enhanced.append(
                        _clone_chunk_with_content(
                            chunk,
                            content=param_content,
                            title=f"{api_key} 参数",
                            chunk_type="api_param",
                            section_type="api_param",
                            section_id=f"api_param:{method}:{path}",
                            chunk_group_id=f"api:{method}:{path}",
                            metadata={
                                "project_chunk_strategy": "api_param",
                                "module": module_name,
                                "module_key": module_key,
                                "api_method": method,
                                "api_path": path,
                                "api_group_id": f"{method} {path}",
                                "api_key": api_identity,
                                "confidence": "EXTRACTED",
                            },
                        )
                    )
                if any(word in api_content for word in ["错误码", "状态码", "异常码", "error code"]):
                    error_lines = [item.group(0) for item in _ERROR_RE.finditer(api_content)]
                    error_content = clean_text("\n".join(error_lines)) or api_content
                    enhanced.append(
                        _clone_chunk_with_content(
                            chunk,
                            content=error_content,
                            title=f"{api_key} 错误码",
                            chunk_type="api_error_code",
                            section_type="api_error_code",
                            section_id=f"api_error:{method}:{path}",
                            chunk_group_id=f"api:{method}:{path}",
                            metadata={
                                "project_chunk_strategy": "api_error_code",
                                "module": module_name,
                                "module_key": module_key,
                                "api_method": method,
                                "api_path": path,
                                "api_group_id": f"{method} {path}",
                                "api_key": api_identity,
                                "confidence": "EXTRACTED",
                            },
                        )
                    )

        if table_matches:
            for match in table_matches:
                table_name = match.group(1)
                table_content = clean_text(content[match.start():])
                column_candidates = re.findall(r"(?m)^\s*[`\"']?([A-Za-z_][\w]*)[`\"']?\s+(BIGINT|INT|VARCHAR|CHAR|TEXT|DATETIME|DATE|DECIMAL|NUMERIC|JSON|TINYINT)", table_content, flags=re.IGNORECASE)
                table_key = canonical_key("db_table", table_name)
                enhanced.append(
                    _clone_chunk_with_content(
                        chunk,
                        content=table_content,
                        title=f"数据表 {table_name}",
                        chunk_type="db_table",
                        section_type="db_table",
                        section_id=f"db:{table_name}",
                        chunk_group_id=f"db:{table_name}",
                        metadata={
                            "project_chunk_strategy": "db_table",
                            "module": module_name,
                            "module_key": module_key,
                            "table_name": table_name,
                            "table_key": table_key,
                            "db_columns": [name for name, _ in column_candidates[:80]],
                            "confidence": "EXTRACTED",
                        },
                    )
                )
                added_specialized = True

        if code_matches:
            for code_index, match in enumerate(code_matches, 1):
                language = (match.group(1) or "").lower() or "text"
                code_content = clean_text(match.group(2))
                is_sql_ddl = bool(_CREATE_TABLE_RE.search(code_content))
                nearest_api = None
                if api_matches:
                    nearest = [item for item in api_matches if item.start() < match.start()]
                    nearest_api_match = nearest[-1] if nearest else api_matches[0]
                    nearest_api = f"{nearest_api_match.group(1).upper()} {nearest_api_match.group(2)}"
                code_chunk_type = "code_block"
                if nearest_api and not is_sql_ddl and language in {"json", "bash", "shell", "http", "curl", "text"}:
                    code_chunk_type = "api_example"
                enhanced.append(
                    _clone_chunk_with_content(
                        chunk,
                        content=code_content,
                        title=f"{nearest_api or chunk.get('title') or module_name} {'示例' if code_chunk_type == 'api_example' else '代码块'}{code_index}",
                        chunk_type=code_chunk_type,
                        section_type=code_chunk_type,
                        section_id=f"code:{chunk.get('chunk_key')}:{code_index}",
                        chunk_group_id=f"api:{nearest_api}" if code_chunk_type == "api_example" else f"module:{module_name}",
                        metadata={
                            "project_chunk_strategy": code_chunk_type,
                            "module": module_name,
                            "module_key": module_key,
                            "api_group_id": nearest_api,
                            "api_key": canonical_key("api", nearest_api) if nearest_api else "",
                            "code_language": language,
                            "confidence": "EXTRACTED",
                        },
                    )
                )
                added_specialized = True

        if config_matches or re.search(r"(配置项|环境变量|config|yaml|properties)", content, re.IGNORECASE):
            config_keys = [match.group(1) for match in config_matches[:60]]
            enhanced.append(
                _clone_chunk_with_content(
                    chunk,
                    content=content,
                    title=chunk.get("title") or "配置项",
                    chunk_type="config_item",
                    section_type="config_item",
                    section_id=f"config:{chunk.get('section_id')}",
                    chunk_group_id=f"module:{module_name}",
                    metadata={
                        "project_chunk_strategy": "config_item",
                        "module": module_name,
                        "module_key": module_key,
                        "config_keys": config_keys,
                        "confidence": "EXTRACTED" if config_keys else "INFERRED",
                    },
                )
            )
            added_specialized = True

        if added_specialized:
            continue
        chunk["metadata"] = {
            **(chunk.get("metadata") or {}),
            "project_chunk_strategy": chunk.get("chunk_type"),
            "module": module_name,
            "module_key": module_key,
            "confidence": "INFERRED",
        }
        enhanced.append(chunk)
    return _renumber_chunks(enhanced)


def _chunk_contract_agreement(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    clause_order = 0
    for base_chunk in _chunk_by_headers(middle_document, chunk_type="contract_clause"):
        content = base_chunk.get("content") or ""
        matches = list(_CLAUSE_RE.finditer(content))
        if len(matches) > 1:
            parts = _split_by_matches(content, matches)
        else:
            clause_id = matches[0].group(1) if matches else None
            parts = [(clause_id or "", content)]
        for clause_id_from_split, part in parts:
            clause_order += 1
            title = clause_id_from_split or base_chunk.get("title")
            chunk = _clone_chunk_with_content(
                base_chunk,
                content=part,
                title=title,
                chunk_type="contract_clause",
                section_id=clause_id_from_split or base_chunk.get("section_id"),
                chunk_group_id=f"contract_clause:{clause_id_from_split}" if clause_id_from_split else base_chunk.get("chunk_group_id"),
            )
            chunks.append(chunk)

    for clause_order, chunk in enumerate(chunks, 1):
        text = f"{chunk.get('title') or ''}\n{chunk.get('content') or ''}"
        match = _CLAUSE_RE.search(text)
        if any(word in text for word in ["甲方", "乙方", "丙方", "双方", "委托方", "受托方"]) and any(word in text for word in ["名称", "地址", "联系人", "法定代表"]):
            chunk["section_type"] = "party_info"
        elif any(word in text for word in ["标的", "服务内容", "项目内容", "采购内容", "委托事项"]):
            chunk["section_type"] = "subject_matter"
        elif "违约" in text:
            chunk["section_type"] = "breach_clause"
        elif "付款" in text or "支付" in text:
            chunk["section_type"] = "payment_term"
        elif any(word in text for word in ["价款", "金额", "费用", "报酬", "合同总价"]):
            chunk["section_type"] = "amount_term"
        elif any(word in text for word in ["交付", "验收", "交验", "成果"]):
            chunk["section_type"] = "delivery_acceptance"
        elif any(word in text for word in ["期限", "有效期", "起止", "生效"]):
            chunk["section_type"] = "term_effective"
        elif "保密" in text:
            chunk["section_type"] = "confidentiality_clause"
        elif any(word in text for word in ["解除", "终止"]):
            chunk["section_type"] = "termination_clause"
        elif any(word in text for word in ["争议", "仲裁", "诉讼", "管辖"]):
            chunk["section_type"] = "dispute_resolution"
        elif "不可抗力" in text:
            chunk["section_type"] = "force_majeure"
        elif "附件" in text or "补充协议" in text:
            chunk["section_type"] = "attachment_clause"
        elif "签章" in text or "盖章" in text:
            chunk["section_type"] = "signature_region"
        else:
            chunk["section_type"] = "contract_clause"
        parties = []
        for party in ["甲方", "乙方", "丙方", "双方"]:
            if party in text:
                parties.append(party)
        party_names: dict[str, str] = {}
        for party_label, party_name in _PARTY_NAME_RE.findall(text):
            label = party_label or "未标注"
            party_names[label] = clean_text(party_name)
        party_keys = {
            label: canonical_key("contract_party", name)
            for label, name in party_names.items()
            if name
        }
        obligation_subject = parties[0] if len(parties) == 1 else ("双方" if "双方" in parties or len(parties) > 1 else None)
        obligation_subject_name = party_names.get(obligation_subject) if obligation_subject else None
        amounts = [
            "".join(part for part in match.groups() if part)
            for match in _AMOUNT_RE.finditer(text)
            if match.group(2) and (match.group(1) or match.group(3))
        ][:10]
        dates = _DATE_RE.findall(text)[:10]
        clause_id = match.group(1) if match else None
        chunk["section_id"] = clause_id or chunk.get("section_id")
        chunk["chunk_group_id"] = f"contract_clause:{clause_id}" if clause_id else chunk.get("chunk_group_id")
        section_type = chunk.get("section_type")
        chunk["metadata"] = {
            **(chunk.get("metadata") or {}),
            "clause_id": clause_id,
            "clause_key": canonical_key("contract_clause", clause_id or chunk.get("title")),
            "clause_order": clause_order,
            "contract_parties": parties,
            "contract_party_names": party_names,
            "contract_party_keys": party_keys,
            "obligation_subject": obligation_subject,
            "obligation_subject_name": obligation_subject_name,
            "obligation_subject_key": canonical_key("contract_party", obligation_subject_name or obligation_subject),
            "amount_candidates": amounts,
            "date_candidates": dates,
            "deadline_candidates": dates if section_type in {"payment_term", "delivery_acceptance", "term_effective", "breach_clause"} else [],
            "confidence": "EXTRACTED" if clause_id else "INFERRED",
        }
    return _renumber_chunks(chunks)


def _chunk_structured_data(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
    from danbao_poc.common import clean_text, stable_hash

    doc_title = _doc_title(middle_document)
    chunks: list[dict[str, Any]] = []

    def append_chunk(
        *,
        chunk_type: str,
        section_type: str,
        title: str,
        content: str,
        table_key: str,
        page_no: int | None,
        metadata: dict[str, Any],
    ) -> None:
        seq_no = len(chunks) + 1
        content = clean_text(content)
        if not content:
            return
        section_id = f"table:{table_key}"
        chunks.append(
            {
                "chunk_key": f"chunk_{seq_no:03d}",
                "seq_no": seq_no,
                "chunk_type": chunk_type,
                "section_type": section_type,
                "section_id": section_id,
                "chunk_group_id": section_id,
                "title": title,
                "title_path": [doc_title, title],
                "content": content,
                "summary": content[:180],
                "content_hash": stable_hash(content, 40),
                "content_for_embedding": _embedding_text(doc_title, title, content),
                "content_for_bm25": clean_text(f"{doc_title} {title} {content}"),
                "page_start": page_no,
                "page_end": page_no,
                "block_ids": [],
                "bbox": [],
                "metadata": {
                    "document_title": doc_title,
                    "profile": middle_document.get("profile"),
                    "table_key": table_key,
                    **metadata,
                },
            }
        )

    for table_index, table in enumerate(middle_document.get("tables") or [], 1):
        table_key = table.get("table_key") or f"table_{table_index:03d}"
        title = table.get("title") or table_key
        columns = table.get("columns") or []
        rows = table.get("rows") or []
        page_no = table.get("page_no")
        column_text = "；".join(
            f"{column.get('name') or column}: {column.get('data_type') or 'string'}" if isinstance(column, dict) else str(column)
            for column in columns
        )
        append_chunk(
            chunk_type="table_schema",
            section_type="table_schema",
            title=f"{title} 表结构",
            content=f"表名：{title}\n列信息：{column_text}\n行数：{len(rows)}",
            table_key=table_key,
            page_no=page_no,
            metadata={"row_count": len(rows), "column_count": len(columns)},
        )
        numeric_columns = [
            column.get("name")
            for column in columns
            if isinstance(column, dict) and column.get("data_type") == "number" and column.get("name")
        ]
        if numeric_columns and rows:
            metrics: list[str] = []
            for column in numeric_columns[:10]:
                values: list[float] = []
                for row in rows:
                    raw = str(row.get(column) or "").replace(",", "").strip()
                    try:
                        values.append(float(raw))
                    except ValueError:
                        continue
                if values:
                    metrics.append(f"{column}: count={len(values)}, sum={sum(values):.2f}, min={min(values):.2f}, max={max(values):.2f}")
            if metrics:
                append_chunk(
                    chunk_type="metric_summary",
                    section_type="metric_summary",
                    title=f"{title} 指标摘要",
                    content="\n".join(metrics),
                    table_key=table_key,
                    page_no=page_no,
                    metadata={"numeric_columns": numeric_columns[:10]},
                )
        for start in range(0, len(rows), 25):
            row_slice = rows[start:start + 25]
            lines = []
            for row_offset, row in enumerate(row_slice, start + 1):
                cells = [f"{key}={value}" for key, value in row.items() if clean_text(value)]
                if cells:
                    lines.append(f"第{row_offset}行：" + "；".join(cells))
            append_chunk(
                chunk_type="table_row",
                section_type="table_row",
                title=f"{title} 第{start + 1}-{start + len(row_slice)}行",
                content="\n".join(lines),
                table_key=table_key,
                page_no=page_no,
                metadata={"row_start": start + 1, "row_end": start + len(row_slice)},
            )

    if chunks:
        return chunks
    return _chunk_by_headers(middle_document, chunk_type="table_text")


def _empty_extraction(chunks: list[dict[str, Any]], parse_options: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"fields": []}


def _compact_chunks_for_prompt(chunks: list[dict[str, Any]], max_chars: int = 20000) -> str:
    rows: list[str] = []
    size = 0
    for chunk in chunks:
        block = (
            f"[{chunk.get('chunk_key')}] 标题: {chunk.get('title') or ''}\n"
            f"section_type: {chunk.get('section_type') or 'text_section'}\n"
            f"page: {chunk.get('page_start')}~{chunk.get('page_end')}\n"
            f"content: {chunk.get('content') or ''}\n"
        )
        if size + len(block) > max_chars:
            break
        rows.append(block)
        size += len(block)
    return "\n".join(rows)


def _make_prompt_extractor(profile: str) -> Callable[[list[dict[str, Any]]], dict[str, Any]]:
    def extract(chunks: list[dict[str, Any]], parse_options: dict[str, Any] | None = None) -> dict[str, Any]:
        from danbao_poc.common import clean_text, stable_hash
        from danbao_poc.extraction_merge import extraction_pass_count, merge_overlaps_enabled, merge_pass_record_lists
        from danbao_poc.openai_compat import JsonChatClient
        from danbao_poc.profiles.field_aliases import get_field_aliases
        from danbao_poc.profiles.prompt_templates import PROFILE_PROMPT_CONFIG, build_extract_prompt

        config = PROFILE_PROMPT_CONFIG.get(profile)
        if not config or not chunks:
            return {"fields": []}

        from danbao_poc.context_budget import select_priority_chunks
        selected = select_priority_chunks(chunks, max_chars=20000)
        chunk_text = _compact_chunks_for_prompt(selected)
        system_prompt, user_prompt = build_extract_prompt(profile, chunk_text)
        try:
            client = JsonChatClient("EXTRACT", default_model=True, enable_fallback=True)
            pass_count = extraction_pass_count(parse_options)
            pass_payloads = [
                client.complete_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0 if pass_index == 0 else min(0.35, 0.15 + (pass_index - 1) * 0.1),
                    max_tokens=3000,
                )
                for pass_index in range(pass_count)
            ]
        except Exception:
            return {"fields": []}

        aliases = get_field_aliases(profile)
        field_schema = config.get("fields") or {}
        chunk_by_key = {chunk.get("chunk_key"): chunk for chunk in chunks}
        fields: list[dict[str, Any]] = []
        raw_field_lists = [
            payload.get("fields") or []
            for payload in pass_payloads
            if isinstance(payload, dict)
        ]
        raw_items, merge_report = merge_pass_record_lists(
            raw_field_lists,
            exact_fields=["field_code", "source_chunk_key", "value_text", "evidence_quote"],
            group_fields=["field_code", "source_chunk_key"],
            text_fields=["evidence_quote", "value_text"],
            merge_overlaps=merge_overlaps_enabled(parse_options),
        )

        for index, item in enumerate(raw_items, 1):
            if not isinstance(item, dict):
                continue
            field_code = clean_text(item.get("field_code"))
            if field_code not in field_schema:
                continue
            value = item.get("value_text")
            value_text = clean_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            if not value_text:
                continue
            source_chunk_key = clean_text(item.get("source_chunk_key"))
            source_chunk = chunk_by_key.get(source_chunk_key) or chunks[0]
            normalized_json = item.get("normalized_json")
            if not isinstance(normalized_json, dict):
                normalized_json = {}
            evidence_text = clean_text(item.get("evidence_quote") or value_text)
            confidence = clean_text(item.get("confidence")).upper()
            if confidence not in {"HIGH", "MEDIUM", "LOW"}:
                confidence = "MEDIUM"
            fields.append(
                {
                    "field_key": f"field_{index:03d}_{field_code}",
                    "field_code": field_code,
                    "field_name_cn": field_schema[field_code].get("name_cn") or field_code,
                    "value_text": value_text,
                    "aliases": aliases.get(field_code, []),
                    "normalized_json": normalized_json,
                    "source_chunk_key": source_chunk.get("chunk_key"),
                    "source_section_type": source_chunk.get("section_type"),
                    "metadata": {
                        "profile": profile,
                        "content_hash": stable_hash(value_text),
                        "evidence_quote": evidence_text,
                        "confidence": confidence,
                    },
                    "mention": {
                        "evidence_text": evidence_text,
                        "page_no": source_chunk.get("page_start"),
                        "block_ids": source_chunk.get("block_ids") or [],
                        "bbox": source_chunk.get("bbox") or [],
                    },
                }
            )
        return {"fields": fields, "_debug": {"multi_pass": merge_report}}

    return extract


def register_default_profiles() -> None:
    global _DEFAULT_PROFILES_REGISTERED
    if _DEFAULT_PROFILES_REGISTERED:
        return
    from danbao_poc.profiles.field_aliases import get_field_aliases, get_field_hints

    _DEFAULT_PROFILES_REGISTERED = True

    def _business_plan_chunker(middle_document: dict[str, Any]) -> list[dict[str, Any]]:
        from danbao_poc.chunker import chunk_guarantee_plan

        return chunk_guarantee_plan(middle_document)

    def _business_plan_extractor(chunks: list[dict[str, Any]], parse_options: dict[str, Any] | None = None) -> dict[str, Any]:
        from danbao_poc.extractor import extract_guarantee_plan

        return extract_guarantee_plan(chunks, parse_options=parse_options)

    def _business_plan_graph_builder(extraction: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        from danbao_poc.graph_builder import build_business_graph

        return build_business_graph(extraction)

    def _universal_graph_builder(extraction: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        from danbao_poc.knowledge_graph_builder import build_knowledge_graph

        profile = extraction.get("_profile") or "general_document"
        return build_knowledge_graph(
            profile=profile,
            anchors=extraction.get("anchors") or [],
            knowledge_units=extraction.get("knowledge_units") or [],
            relations=extraction.get("relations") or [],
            chunks=extraction.get("chunks") or [],
            fields=extraction.get("fields") or [],
        )

    register_profile(
        ProfileSpec(
            code="business_plan",
            display_name="业务/担保方案",
            chunker=_business_plan_chunker,
            extractor=_business_plan_extractor,
            graph_builder=_universal_graph_builder,
            default_modes=("graph", "bm25", "vector"),
            field_aliases=get_field_aliases("business_plan"),
            field_hints=get_field_hints("business_plan"),
        )
    )
    register_profile(
        ProfileSpec(
            code="general_document",
            display_name="通用文档",
            chunker=_chunk_general_document,
            extractor=_empty_extraction,
            graph_builder=_universal_graph_builder,
            default_modes=("graph", "bm25", "vector"),
            field_aliases=get_field_aliases("general_document"),
            field_hints=get_field_hints("general_document"),
            catalog_builder=_catalog_builder_field_aware,
        )
    )
    register_profile(
        ProfileSpec(
            code="operation_knowledge",
            display_name="运营知识库",
            chunker=_chunk_general_document,
            extractor=_empty_extraction,
            graph_builder=_universal_graph_builder,
            default_modes=("qa", "bm25", "vector"),
            field_aliases=get_field_aliases("general_document"),
            field_hints=get_field_hints("general_document"),
        )
    )
    from danbao_poc.profiles.sql_analytics import extract_sql_analytics_fields

    register_profile(
        ProfileSpec(
            code="sql_analytics",
            display_name="智能问数/NL2SQL知识",
            chunker=_chunk_sql_analytics,
            extractor=extract_sql_analytics_fields,
            graph_builder=None,
            default_modes=("structured", "bm25", "vector"),
            field_aliases=get_field_aliases("sql_analytics"),
            field_hints=get_field_hints("sql_analytics"),
            # SQL knowledge is intentionally allowed to use ordinary Markdown.
            # The shared catalog planner asks the LLM to identify semantic
            # boundaries, while the profile switches off every later LLM
            # enrichment stage below.
            catalog_builder=_catalog_builder_field_aware,
            enable_section_summaries=False,
            enable_knowledge_extraction=False,
            enable_answer_prebuild=False,
        )
    )
    for code, display_name, chunker in [
        ("governance_rule", "制度规章", _chunk_governance_rule),
        ("project_doc", "项目文档", _chunk_project_doc),
        ("contract_agreement", "合同协议", _chunk_contract_agreement),
        ("structured_data", "结构化表格", _chunk_structured_data),
    ]:
        register_profile(
            ProfileSpec(
                code=code,
                display_name=display_name,
                chunker=chunker,
                extractor=_empty_extraction if code == "structured_data" else _make_prompt_extractor(code),
                graph_builder=_universal_graph_builder,
                default_modes=("graph", "bm25", "vector"),
                field_aliases=get_field_aliases(code),
                field_hints=get_field_hints(code),
            )
        )
