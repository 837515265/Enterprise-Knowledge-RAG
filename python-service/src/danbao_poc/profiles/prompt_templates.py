"""各 Profile 的 LLM 抽取 Prompt 模板。

每个 Profile 定义：
  - SYSTEM_PROMPT: 固定角色和输出约束
  - FIELD_SCHEMA: {field_code: {name_cn, hint, example, normalize}}
  - USER_TEMPLATE: 带 {field_codes}, {field_hints}, {chunk_text} 占位符
  - build_user_prompt(): 组装最终 user prompt
"""
from __future__ import annotations

import json
from typing import Any


CATALOG_SECTION_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "business_plan": {
        "document_meta": {
            "name_cn": "文档基本信息",
            "definition": "方案名称、文号、发文背景、总体目标、政策依据等总览性内容。",
            "positive_examples": ["方案名称", "政策依据", "背景说明", "总体目标"],
        },
        "service_object": {
            "name_cn": "服务对象",
            "definition": "方案明确面向的客户、主体、产业经营者或适用人群。",
            "positive_examples": ["服务对象", "支持对象", "客户范围", "适用主体"],
        },
        "business_scope": {
            "name_cn": "适用范围/业务范围",
            "definition": "方案覆盖的地区、产业、业务场景、品类、客户类型或业务边界。",
            "positive_examples": ["适用范围", "业务范围", "产业范围", "区域范围"],
        },
        "admission_requirement": {
            "name_cn": "准入条件",
            "definition": "申请主体必须满足的资质、经营、信用、资产负债、合规等准入要求。",
            "positive_examples": ["准入条件", "客户准入", "基本条件", "申请条件"],
        },
        "credit_limit": {
            "name_cn": "授信/担保额度",
            "definition": "单户、单笔、最高、最低额度，额度测算公式，资产负债率约束等。",
            "positive_examples": ["授信额度", "担保额度", "单户额度", "额度测算"],
        },
        "guarantee_term": {
            "name_cn": "期限",
            "definition": "贷款期限、担保期限、授信期限、续保期限等时间长度约束。",
            "positive_examples": ["授信期限", "担保期限", "贷款期限"],
        },
        "credit_purpose": {
            "name_cn": "资金用途",
            "definition": "贷款、授信或担保资金允许或禁止用于哪些生产经营事项。",
            "positive_examples": ["贷款用途", "授信用途", "资金用途"],
        },
        "fee_rate": {
            "name_cn": "费率/收费标准",
            "definition": "担保费率、年化费率、服务费、优惠费率、收费方式等。",
            "positive_examples": ["担保费率", "收费标准", "费率优惠"],
        },
        "risk_mitigation": {
            "name_cn": "风险缓释/风控措施",
            "definition": "风险分担、风险补偿、保证金、质押率、监测预警、贷后管理等。",
            "positive_examples": ["风险缓释", "风险分担", "贷后管理", "风险控制"],
        },
        "counter_guarantee": {
            "name_cn": "反担保",
            "definition": "抵押、质押、保证人、免抵押、追加担保等反担保安排。",
            "positive_examples": ["反担保", "抵质押", "保证措施"],
        },
        "material_requirement": {
            "name_cn": "申请材料",
            "definition": "申请、准入、审批、放款所需提交的材料清单。",
            "positive_examples": ["申请材料", "资料清单", "所需材料"],
        },
        "procedure": {
            "name_cn": "办理流程",
            "definition": "申请、受理、尽调、审批、签约、放款、备案等流程步骤。",
            "positive_examples": ["办理流程", "操作流程", "业务流程", "审批流程"],
        },
        "cooperation_org": {
            "name_cn": "合作机构/职责分工",
            "definition": "银行、担保机构、政府部门、平台方等参与主体及职责分工。",
            "positive_examples": ["合作机构", "职责分工", "参与主体"],
        },
        "appendix": {
            "name_cn": "附件",
            "definition": "附件、模板、表单、补充说明、附录等。",
            "positive_examples": ["附件", "附表", "申请表"],
        },
        "text_section": {
            "name_cn": "普通正文",
            "definition": "无法稳定归入上述业务类别，但仍需保留的正文段落。",
            "positive_examples": ["其他说明", "一般正文"],
        },
    },
    "governance_rule": {
        "document_meta": {
            "name_cn": "制度基本信息",
            "definition": "制度名称、文号、版本、制定依据、修订说明等。",
            "positive_examples": ["制度名称", "制定依据", "修订记录"],
        },
        "general_principle": {
            "name_cn": "总则/原则",
            "definition": "目的、依据、总体原则、适用边界等总则性内容。",
            "positive_examples": ["总则", "目的", "原则"],
        },
        "applicable_scope": {
            "name_cn": "适用范围",
            "definition": "制度适用的部门、人员、业务场景、机构或事项。",
            "positive_examples": ["适用范围", "适用对象"],
        },
        "responsibility_clause": {
            "name_cn": "职责权限",
            "definition": "部门、岗位、人员、委员会等主体的职责、权限、分工。",
            "positive_examples": ["职责", "权限", "分工", "责任部门"],
        },
        "procedure_clause": {
            "name_cn": "流程程序",
            "definition": "申请、审批、办理、执行、归档、检查等程序要求。",
            "positive_examples": ["流程", "程序", "审批", "办理"],
        },
        "standard_clause": {
            "name_cn": "标准/额度/费用",
            "definition": "金额标准、费用标准、比例、额度、时限、指标等量化要求。",
            "positive_examples": ["标准", "费用", "额度", "比例", "时限"],
        },
        "prohibited_clause": {
            "name_cn": "禁止事项",
            "definition": "制度明确禁止、不得、严禁、限制的行为或事项。",
            "positive_examples": ["禁止", "不得", "严禁"],
        },
        "penalty_clause": {
            "name_cn": "违规处罚",
            "definition": "违规责任、处罚措施、问责、扣罚、处分等。",
            "positive_examples": ["处罚", "问责", "违规处理"],
        },
        "effective_clause": {
            "name_cn": "生效/解释/废止",
            "definition": "生效日期、施行日期、解释权、废止旧制度等。",
            "positive_examples": ["生效", "施行", "解释权", "废止"],
        },
        "appendix": {
            "name_cn": "附件/表单",
            "definition": "制度附表、模板、流程图、附件说明。",
            "positive_examples": ["附件", "附表", "模板"],
        },
        "clause": {
            "name_cn": "普通条款",
            "definition": "能识别为制度条款，但无法稳定归入其他类别的条款。",
            "positive_examples": ["第三条", "第十条"],
        },
        "text_section": {
            "name_cn": "普通正文",
            "definition": "无法稳定归类但需要保留的正文。",
            "positive_examples": ["其他说明"],
        },
    },
    "project_doc": {
        "document_meta": {
            "name_cn": "项目文档基本信息",
            "definition": "项目名称、版本、作者、日期、背景、目标、范围等。",
            "positive_examples": ["项目背景", "文档信息", "版本记录"],
        },
        "requirement": {
            "name_cn": "需求/业务规则",
            "definition": "业务需求、功能需求、非功能需求、用户场景、规则约束。",
            "positive_examples": ["功能需求", "业务规则", "非功能需求"],
        },
        "architecture": {
            "name_cn": "架构/总体设计",
            "definition": "系统架构、模块划分、数据流、部署拓扑、技术路线。",
            "positive_examples": ["总体架构", "系统架构", "模块设计"],
        },
        "module_design": {
            "name_cn": "模块设计",
            "definition": "模块职责、处理流程、类/服务/组件设计、状态流转。",
            "positive_examples": ["模块设计", "流程设计", "状态机"],
        },
        "api_spec": {
            "name_cn": "接口定义",
            "definition": "HTTP/RPC/API 接口、方法、路径、请求参数、返回结构。",
            "positive_examples": ["接口", "API", "POST /api", "请求参数"],
        },
        "db_table": {
            "name_cn": "数据表/数据模型",
            "definition": "数据库表、字段、索引、ER关系、数据字典。",
            "positive_examples": ["数据表", "表结构", "字段说明", "CREATE TABLE"],
        },
        "config_item": {
            "name_cn": "配置/部署",
            "definition": "环境变量、配置项、部署步骤、中间件、启动参数。",
            "positive_examples": ["配置项", "部署", "环境变量", "YAML"],
        },
        "test_case": {
            "name_cn": "测试/验收",
            "definition": "测试范围、测试用例、验收标准、测试结论、缺陷问题。",
            "positive_examples": ["测试用例", "验收标准", "测试结论"],
        },
        "risk_item": {
            "name_cn": "风险/问题/待办",
            "definition": "技术风险、遗留问题、限制条件、待办事项、优化建议。",
            "positive_examples": ["风险", "问题", "TODO", "优化建议"],
        },
        "code_block": {
            "name_cn": "代码块/示例",
            "definition": "代码片段、SQL、JSON、配置示例、调用示例。",
            "positive_examples": ["代码示例", "SQL", "JSON 示例"],
        },
        "text_section": {
            "name_cn": "普通正文",
            "definition": "无法稳定归类但需要保留的正文。",
            "positive_examples": ["其他说明"],
        },
    },
    "sql_analytics": {
        "scene": {
            "name_cn": "问数场景",
            "definition": "场景代码、数据源和允许的数据边界。",
            "positive_examples": ["sceneCode", "datasourceKey", "业务场景"],
        },
        "schema": {
            "name_cn": "数据Schema",
            "definition": "数据库Schema、表集合及整体数据模型。",
            "positive_examples": ["Schema", "数据模型"],
        },
        "table": {
            "name_cn": "数据表",
            "definition": "允许查询的数据表、主键、切片字段和用途。",
            "positive_examples": ["tableName", "数据表"],
        },
        "field": {
            "name_cn": "物理字段",
            "definition": "字段名、数据类型、中文含义和查询限制。",
            "positive_examples": ["fieldName", "字段定义"],
        },
        "dimension": {
            "name_cn": "分析维度",
            "definition": "可用于分组、筛选、排序的业务维度。",
            "positive_examples": ["dimensionCode", "地区维度"],
        },
        "enum": {
            "name_cn": "枚举值",
            "definition": "字段或维度允许的真实取值及别名。",
            "positive_examples": ["enumValue", "业务状态取值"],
        },
        "term": {
            "name_cn": "业务术语",
            "definition": "业务概念、别名、定义和关联字段。",
            "positive_examples": ["objectType: TERM", "术语定义"],
        },
        "metric": {
            "name_cn": "业务指标",
            "definition": "指标定义、聚合表达式、单位、过滤条件和时间口径。",
            "positive_examples": ["objectType: METRIC", "sqlExpression"],
        },
        "time_rule": {
            "name_cn": "时间规则",
            "definition": "自然期、数据切片、同比、环比等确定性时间口径。",
            "positive_examples": ["TIME_RULE", "本月口径"],
        },
        "verified_sql": {
            "name_cn": "已验证SQL",
            "definition": "经过真实数据切片校验的只读SQL及适用问题。",
            "positive_examples": ["objectType: VERIFIED_SQL", "```sql"],
        },
        "text_section": {
            "name_cn": "未分类内容",
            "definition": "无法识别为受治理SQL知识对象的内容。",
            "positive_examples": ["发布说明"],
        },
    },
    "general_document": {
        "document_meta": {
            "name_cn": "文档基本信息",
            "definition": "标题、背景、目的、版本、作者等基本信息。",
            "positive_examples": ["文档信息", "背景", "目的"],
        },
        "procedure": {
            "name_cn": "流程步骤",
            "definition": "按步骤、阶段、顺序描述的操作流程或处理过程。",
            "positive_examples": ["流程", "步骤", "操作说明"],
        },
        "requirement": {
            "name_cn": "要求/规则",
            "definition": "必须满足的要求、规则、条件、约束。",
            "positive_examples": ["要求", "规则", "条件"],
        },
        "appendix": {
            "name_cn": "附件",
            "definition": "附件、附录、补充材料。",
            "positive_examples": ["附件", "附录"],
        },
        "text_section": {
            "name_cn": "普通正文",
            "definition": "通用正文段落。",
            "positive_examples": ["正文"],
        },
    },
}


def catalog_section_schema_for_profile(profile: str) -> dict[str, dict[str, Any]]:
    """Return the catalog section schema isolated by profile."""
    try:
        from .registry import normalize_profile

        normalized = normalize_profile(profile) or profile
    except Exception:
        normalized = profile
    schema = CATALOG_SECTION_SCHEMAS.get(normalized) or CATALOG_SECTION_SCHEMAS["general_document"]
    return schema


def catalog_section_types_for_profile(profile: str) -> list[str]:
    return list(catalog_section_schema_for_profile(profile).keys())


def build_catalog_profile_context(profile: str) -> str:
    """Render profile-specific catalog taxonomy for the LLM catalog planner."""
    schema = catalog_section_schema_for_profile(profile)
    lines = [f"当前 profile: {profile}", "", "section_type 只能从下面白名单选择，不能创造新类型："]
    for code, item in schema.items():
        examples = "、".join(str(value) for value in item.get("positive_examples") or [])
        lines.append(
            f"- {code}（{item.get('name_cn') or code}）：{item.get('definition') or ''}"
            + (f"  典型标题/内容：{examples}" if examples else "")
        )
    lines.extend(
        [
            "",
            "分类判定规则：",
            "1. 优先按章节标题和正文首段的真实语义分类，不要只看关键词。",
            "2. 只要不能稳定判断，就输出 text_section，不能猜测。",
            "3. 同一个父级下重复出现的同名小节要分别保留，不要合并。",
            "4. section_type 只影响检索路由，不影响原文保留；宁可保守，也不要跨 profile 误分类。",
        ]
    )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 1. business_plan — 担保/授信/业务方案
# ═══════════════════════════════════════════════════════════════

BUSINESS_PLAN_SYSTEM = (
    "你是企业担保方案结构化抽取器。\n"
    "规则：\n"
    "1. 只返回 JSON，不要解释。\n"
    "2. field_code 只能从白名单选择，不允许创造新字段。\n"
    "3. value_text 必须来自原文正文内容，不允许改写、补充或推测。\n"
    "4. 每个字段必须给出 source_chunk_key（来源分块编号，必填）和 evidence_quote（20-200字原文证据，必填）。\n"
    "5. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n"
    "6. 金额字段同时输出 value_text（中文原文）和 normalized_json.amount_min_yuan / amount_max_yuan（元）。\n"
    "7. 期限字段同时输出 value_text 和 normalized_json.term_max_months（月）。\n"
    "8. 比例字段同时输出 value_text 和 normalized_json.ratio_value（小数）。\n"
    "9. 列表类字段（准入条件、材料、流程等）value_text 必须包含全部子条款，用中文分号或换行分隔。\n"
    "10. 如果原文没有某字段，该字段不要出现在 fields 数组中，不要猜测。\n\n"
    "禁止事项：\n"
    "- 禁止将章节标题作为字段值（如 value_text = \"（五）授信期限\" 是错误的，必须包含正文内容）。\n"
    "- 禁止只抽取列表类字段的第一条（如准入条件有6条，必须全部包含）。\n"
    "- 禁止将机构所在地、抄送单位、政策引用地名作为适用地区。\n"
    "- 禁止从房地产市场/证券市场/期货市场等市场词中截取伪地区。"
)


BUSINESS_PLAN_FIELDS: dict[str, dict[str, Any]] = {
    "plan_name": {
        "name_cn": "方案名称",
        "hint": "担保方案/授信方案/服务方案的完整名称，通常在标题或首段",
        "example": "邹城市草莓产业集群担保服务方案",
        "normalize": None,
    },
    "document_no": {
        "name_cn": "文号",
        "hint": "发文号/批文号，格式如 X〔2025〕X号",
        "example": "鲁农担批〔2025〕7号",
        "normalize": None,
    },
    "region": {
        "name_cn": "适用地区",
        "hint": "方案明确适用、覆盖或限定的行政区划；不要把机构所在地、抄送单位、举例地名、政策引用地名、房地产市场/证券市场/期货市场等市场词当地区",
        "example": "邹城市",
        "normalize": "标准行政区名",
    },
    "industry": {
        "name_cn": "适用产业",
        "hint": "方案覆盖的产业/行业",
        "example": "草莓产业",
        "normalize": "产业标准名",
    },
    "credit_limit": {
        "name_cn": "授信额度",
        "hint": "单户/单笔最高授信金额，包含上下限",
        "example": "单户10万元至300万元",
        "normalize": "amount_min_yuan, amount_max_yuan, currency=CNY",
    },
    "guarantee_term": {
        "name_cn": "担保期限",
        "hint": "贷款/担保的最长期限",
        "example": "最长不超过12个月",
        "normalize": "term_max_months",
    },
    "guarantee_rate": {
        "name_cn": "担保费率",
        "hint": "年化担保费率或收费标准",
        "example": "年化0.8%",
        "normalize": "ratio_value",
    },
    "risk_share_ratio": {
        "name_cn": "风险分担比例",
        "hint": "政府/银行/担保公司各自承担的风险比例",
        "example": "政府20%、银行20%、担保60%",
        "normalize": "各主体 ratio_value",
    },
    "admission_requirement": {
        "name_cn": "准入条件",
        "hint": "申请人必须满足的条件列表",
        "example": "从事草莓种植满3年、信用记录良好、在邹城市辖区内经营",
        "normalize": "条件列表",
    },
    "counter_guarantee": {
        "name_cn": "反担保要求",
        "hint": "是否需要抵押/质押/保证人",
        "example": "原则上免抵押，可追加保证人",
        "normalize": "是否必需 + 类型",
    },
    "cooperation_org": {
        "name_cn": "合作机构",
        "hint": "合作银行、担保公司、财政等机构名称",
        "example": "山东农担、邹城农商银行",
        "normalize": "机构全称列表",
    },
    "material_requirement": {
        "name_cn": "申请材料",
        "hint": "申请时需要提交的材料清单",
        "example": "身份证、营业执照、种植证明",
        "normalize": "材料列表",
    },
    "process_requirement": {
        "name_cn": "办理流程",
        "hint": "从申请到放款的步骤",
        "example": "申请→初审→尽调→审批→放款",
        "normalize": "步骤列表",
    },
    "policy_basis": {
        "name_cn": "政策依据",
        "hint": "引用的政策文件名称和文号",
        "example": "鲁农担批〔2025〕7号",
        "normalize": "文号+文件名",
    },
    "service_object": {
        "name_cn": "服务对象",
        "hint": "方案适用的客户群体",
        "example": "从事草莓种植的新型农业经营主体",
        "normalize": None,
    },
    "credit_purpose": {
        "name_cn": "授信用途",
        "hint": "贷款资金可用于的用途",
        "example": "草莓种植、采购农资、设施建设",
        "normalize": None,
    },
}

BUSINESS_PLAN_USER_TEMPLATE = (
    "请从以下担保方案/授信方案文档中抽取结构化字段。\n\n"
    "## 抽取要求\n"
    "1. value_text 必须是正文内容的摘要或原文，不能只是章节标题。\n"
    "   错误示例：risk_mitigation = \"（十）风险缓释措施\"（这只是标题，没有正文内容）\n"
    "   正确示例：risk_mitigation = \"质押率设置为50%，当农产品货值低于贷款余额时…\"（包含正文实质内容）\n"
    "2. 列表类字段（准入条件、材料、流程等）必须包含全部子条款的合并摘要。\n"
    "   错误示例：access_condition = \"符合国家产业政策\"（只有第1条）\n"
    "   正确示例：access_condition = \"1.符合国家产业政策；2.须依法登记注册；3.信用记录良好…\"（合并全部子条款）\n"
    "3. 每个字段必须包含 source_chunk_key（必填）、evidence_quote（20-200字原文证据，必填）和 confidence（HIGH/MEDIUM/LOW）。\n\n"
    "4. 如果文档分块中包含“字段优先上下文索引”，抽取对应字段时应优先查看索引列出的 chunk_key。\n\n"
    "## 地区抽取规则\n"
    "regions 只允许填写能由原文明确证明为方案适用范围的行政区划。\n"
    "不要因为出现市/县/区字样就抽取。机构所在地、抄送单位、政策引用地名不是适用地区。\n"
    "如果不能确定，返回空数组。\n\n"
    "## 多板块文档处理\n"
    "如果文档包含多个业务板块（如一、农产品贸易类、二、惠农电商类），\n"
    "每个板块的同类字段应分别抽取，在 value_text 中标注所属板块名称，\n"
    "并尽量填写 business_block_id、business_block_title。\n\n"
    "允许的 field_code 及说明：\n{field_hints}\n\n"
    "返回格式：\n"
    '{{\"plan\": {{\"plan_name\": \"...\", \"document_no\": \"...\", \"regions\": [...], '
    '\"industries\": [...], \"organizations\": [...]}}, '
    '\"fields\": [{{\"field_code\": \"...\", \"value_text\": \"...\", '
    '\"business_block_id\": \"...\", \"business_block_title\": \"...\", '
    '\"source_chunk_key\": \"...\", \"evidence_quote\": \"...\", '
    '\"confidence\": \"HIGH\", \"normalized_json\": {{...}}}}]}}\n\n'
    "文档分块如下：\n{chunk_text}"
)


# ═══════════════════════════════════════════════════════════════
# 2. governance_rule — 内部制度规章
# ═══════════════════════════════════════════════════════════════

GOVERNANCE_RULE_SYSTEM = (
    "你是企业内部制度规章结构化抽取器。\n"
    "规则：\n"
    "1. 只返回 JSON，不要解释。\n"
    "2. field_code 只能从白名单选择。\n"
    "3. value_text 必须来自原文原句，不允许改写或推测。\n"
    "4. 每个字段必须给出 source_chunk_key（必填）和 evidence_quote（20-80字原文证据片段，必填）。\n"
    "5. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n"
    "6. 列表类字段用中文顿号分隔各项，必须包含原文中的全部子条款。\n"
    "7. 金额标准同时输出中文原文和归一化值（元）。\n"
    "8. 日期字段输出 YYYY-MM-DD 或原文表述。\n"
    "9. 如果原文没有某字段，不要出现在 fields 数组中。\n\n"
    "禁止事项：\n"
    "- 禁止将章节标题作为字段值（如 value_text = \"第三条 费用标准\" 是错误的，必须包含正文内容）。\n"
    "- 禁止只抽取列表类字段的部分条款。"
)

GOVERNANCE_RULE_FIELDS: dict[str, dict[str, Any]] = {
    "rule_name": {
        "name_cn": "制度名称",
        "hint": "制度/办法/规范的完整名称",
        "example": "XX公司差旅费管理办法",
    },
    "rule_no": {
        "name_cn": "制度编号/文号",
        "hint": "制度文件的编号或发文号",
        "example": "行政〔2025〕12号",
    },
    "applicable_scope": {
        "name_cn": "适用范围",
        "hint": "制度适用的部门、人员、场景或业务范围",
        "example": "公司全体正式员工因公出差",
    },
    "responsible_dept": {
        "name_cn": "责任部门",
        "hint": "制度的归口管理部门或执行部门",
        "example": "行政管理部",
    },
    "approval_authority": {
        "name_cn": "审批权限",
        "hint": "审批人、审批层级、金额限额",
        "example": "部门经理审批5000元以下，总经理审批5000元以上",
    },
    "expense_standard": {
        "name_cn": "费用标准",
        "hint": "金额上限、报销标准、补贴标准等具体数值",
        "example": "住宿标准：一类城市不超过500元/天，二类城市不超过350元/天",
    },
    "prohibited_items": {
        "name_cn": "禁止事项",
        "hint": "制度明确禁止的行为或事项",
        "example": "禁止虚开发票、禁止借差旅之名旅游",
    },
    "effective_date": {
        "name_cn": "生效日期",
        "hint": "制度开始执行的日期",
        "example": "2025-01-01",
    },
    "version": {
        "name_cn": "版本号",
        "hint": "制度版本或修订版次",
        "example": "V2.0（2025年修订）",
    },
    "penalty_clause": {
        "name_cn": "违规处罚",
        "hint": "违反制度时的处罚措施",
        "example": "虚开发票一经查实，退回全部报销款项并给予警告处分",
    },
    "exception_handling": {
        "name_cn": "例外处理",
        "hint": "超标准或特殊情况的处理方式",
        "example": "确需超标准住宿的，需事前书面申请，经总经理审批",
    },
}

GOVERNANCE_RULE_USER_TEMPLATE = (
    "请从以下企业内部制度/办法/规范文本中抽取结构化字段。\n\n"
    "## 抽取要求\n"
    "1. value_text 必须是正文内容，不能只是条款标题。\n"
    "2. 列表类字段（如禁止事项）必须包含原文中的全部子条款。\n"
    "3. source_chunk_key 和 evidence_quote 是必填项。\n"
    "4. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n\n"
    "允许的 field_code 及说明：\n{field_hints}\n\n"
    "返回格式：\n"
    '{{\"rule_name\": \"...\", \"rule_no\": \"...\", '
    '\"fields\": [{{\"field_code\": \"...\", \"value_text\": \"...\", '
    '\"source_chunk_key\": \"...\", \"evidence_quote\": \"...\", '
    '\"confidence\": \"HIGH\"}}]}}\n\n'
    "文档分块如下：\n{chunk_text}"
)

# ═══════════════════════════════════════════════════════════════
# 3. project_doc — 项目文档（需求/设计/评审/测试/实施/API）
# ═══════════════════════════════════════════════════════════════

PROJECT_DOC_SYSTEM = (
    "你是项目文档结构化抽取器。\n"
    "你的任务是从需求文档、技术设计、架构设计、技术评审、技术方案、\n"
    "产品说明书、测试报告、优化方案、实施方案、API文档、部署手册等\n"
    "项目材料中抽取结构化字段。\n"
    "规则：\n"
    "1. 只返回 JSON，不要解释。\n"
    "2. field_code 只能从白名单选择。\n"
    "3. value_text 必须来自原文，不允许改写或推测。\n"
    "4. 每个字段必须给出 source_chunk_key（必填）和 evidence_quote（20-100字原文片段，必填）。\n"
    "5. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n"
    "6. doc_phase 必须从以下选择：requirement, requirement_design, "
    "technical_design, technical_review, technical_proposal, "
    "product_manual, test_report, optimization_proposal, "
    "implementation, api_spec, ops_record。\n"
    "7. 数组类字段（module_name, api_list, table_list, dependency等）每项单独一个对象。\n"
    "8. api_list 每项包含 method（GET/POST等）、path（如/api/v1/xxx）、description。\n"
    "9. table_list 每项包含 table_name 和 description。\n"
    "10. 如果原文没有某字段，不要出现在 fields 数组中。\n\n"
    "禁止事项：\n"
    "- 禁止将章节标题作为字段值，必须包含正文内容。\n"
    "- 禁止只抽取列表的部分条目。"
)

PROJECT_DOC_FIELDS: dict[str, dict[str, Any]] = {
    "project_name": {
        "name_cn": "项目/系统名称",
        "hint": "项目、系统或产品的名称",
        "example": "企业知识问答解析检索服务",
    },
    "doc_phase": {
        "name_cn": "文档阶段",
        "hint": "文档属于项目生命周期的哪个阶段",
        "example": "technical_design",
        "enum": ["requirement", "requirement_design", "technical_design",
                 "technical_review", "technical_proposal", "product_manual",
                 "test_report", "optimization_proposal", "implementation",
                 "api_spec", "ops_record"],
    },
    "version": {
        "name_cn": "版本号",
        "hint": "文档版本，如 V1.0、V2.1、第3版",
        "example": "V2.0",
    },
    "module_name": {
        "name_cn": "模块/子系统",
        "hint": "文档涉及的模块、子系统、微服务或组件名称",
        "example": "parse-service、retrieve-service、用户管理模块",
        "is_array": True,
    },
    "author": {
        "name_cn": "作者/负责人",
        "hint": "文档编写人、负责人或评审人",
        "example": "张三",
    },
    "review_date": {
        "name_cn": "评审/编写日期",
        "hint": "文档编写或评审日期",
        "example": "2025-04-20",
    },
    "api_list": {
        "name_cn": "接口清单",
        "hint": "文档中定义的 API 接口，含方法、路径、说明",
        "example": "POST /api/v1/parse/file 提交单文件解析",
        "is_array": True,
    },
    "table_list": {
        "name_cn": "数据库表清单",
        "hint": "文档中涉及的数据库表名及用途",
        "example": "kb_file_node 文件注册表",
        "is_array": True,
    },
    "config_key": {
        "name_cn": "配置项",
        "hint": "重要的环境变量、配置参数",
        "example": "EMBEDDING_BASE_URL、DATA_DIR",
        "is_array": True,
    },
    "dependency": {
        "name_cn": "依赖组件",
        "hint": "依赖的中间件、第三方库、外部服务",
        "example": "MySQL 8.0、Elasticsearch 8.x、Neo4j 5.x、Redis",
        "is_array": True,
    },
    "risk_item": {
        "name_cn": "风险项/问题项",
        "hint": "文档提到的风险、问题或待解决事项",
        "example": "OCR对手写体识别率低、并发超过100时ES查询超时",
        "is_array": True,
    },
    "test_conclusion": {
        "name_cn": "测试结论",
        "hint": "测试通过率、覆盖率、缺陷数等结论性数据",
        "example": "通过率95%，覆盖率82%，遗留P3缺陷3个",
    },
    "milestone": {
        "name_cn": "里程碑/计划节点",
        "hint": "项目计划中的关键节点和时间",
        "example": "需求评审 4/15、技术评审 4/22、上线 5/10",
        "is_array": True,
    },
    "tech_stack": {
        "name_cn": "技术栈",
        "hint": "使用的编程语言、框架、工具",
        "example": "Python 3.11、FastAPI、Vue3、PaddleOCR",
        "is_array": True,
    },
}

PROJECT_DOC_USER_TEMPLATE = (
    "请从以下项目文档中抽取结构化字段。\n\n"
    "## 抽取要求\n"
    "1. value_text 必须是正文内容，不能只是章节标题。\n"
    "2. 每个字段必须包含 source_chunk_key（必填）和 evidence_quote（必填）。\n"
    "3. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n\n"
    "允许的 field_code 及说明：\n{field_hints}\n\n"
    "返回格式：\n"
    '{{\"project_name\": \"...\", \"doc_phase\": \"...\", \"version\": \"...\", '
    '\"fields\": [{{\"field_code\": \"...\", \"value_text\": \"...\", '
    '\"source_chunk_key\": \"...\", \"evidence_quote\": \"...\", '
    '\"confidence\": \"HIGH\"}}]}}\n\n'
    "注意：\n"
    "- api_list 每项格式: \"METHOD /path 说明\"\n"
    "- table_list 每项格式: \"表名 用途说明\"\n"
    "- 数组类字段有多个值时，每个值单独一条 field 记录\n\n"
    "文档分块如下：\n{chunk_text}"
)

# ═══════════════════════════════════════════════════════════════
# 4. contract_agreement — 合同/协议
# ═══════════════════════════════════════════════════════════════

CONTRACT_SYSTEM = (
    "你是合同协议结构化抽取器。\n"
    "规则：\n"
    "1. 只返回 JSON，不要解释。\n"
    "2. field_code 只能从白名单选择。\n"
    "3. value_text 必须来自原文原句，不允许改写。\n"
    "4. 每个字段必须给出 source_chunk_key（必填）和 evidence_quote（20-80字原文片段，必填）。\n"
    "5. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n"
    "6. 金额同时输出中文原文和 normalized_json（元）。\n"
    "7. 日期输出 YYYY-MM-DD 或原文表述。\n"
    "8. 甲方乙方必须是全称。\n"
    "9. 如果原文没有某字段，不要出现在 fields 数组中。\n\n"
    "禁止事项：\n"
    "- 禁止将条款标题作为字段值，必须包含正文内容。\n"
    "- 禁止只抽取列表的部分条目。"
)

CONTRACT_FIELDS: dict[str, dict[str, Any]] = {
    "contract_name": {
        "name_cn": "合同名称",
        "hint": "合同/协议的完整名称",
        "example": "XX项目软件开发服务合同",
    },
    "contract_no": {
        "name_cn": "合同编号",
        "hint": "合同唯一编号",
        "example": "HT-2025-0042",
    },
    "party_a": {
        "name_cn": "甲方",
        "hint": "甲方/买方/委托方的全称",
        "example": "XX市财政局",
    },
    "party_b": {
        "name_cn": "乙方",
        "hint": "乙方/卖方/受托方的全称",
        "example": "XX科技有限公司",
    },
    "contract_amount": {
        "name_cn": "合同金额",
        "hint": "合同总价/成交金额",
        "example": "人民币壹佰贰拾万元整（¥1,200,000.00）",
        "normalize": "amount_yuan",
    },
    "payment_terms": {
        "name_cn": "付款条款",
        "hint": "付款方式、付款比例、付款节点",
        "example": "签订合同后付30%，验收合格后付60%，质保期满付10%",
    },
    "contract_period": {
        "name_cn": "合同期限",
        "hint": "合同起止日期或有效期",
        "example": "2025年5月1日至2026年4月30日",
    },
    "delivery_standard": {
        "name_cn": "交付标准/验收条件",
        "hint": "交付物、验收方式、验收标准",
        "example": "通过甲方组织的验收测试，验收报告签字确认",
    },
    "confidentiality": {
        "name_cn": "保密条款",
        "hint": "保密义务、保密范围、保密期限",
        "example": "合同期内及终止后3年内，双方不得泄露对方商业秘密",
    },
    "breach_liability": {
        "name_cn": "违约责任",
        "hint": "违约情形和违约金/赔偿计算方式",
        "example": "逾期交付每日按合同金额0.5‰支付违约金",
    },
    "sla_metrics": {
        "name_cn": "SLA指标",
        "hint": "服务可用性、响应时间、故障恢复等服务水平指标",
        "example": "系统可用性≥99.9%，故障响应≤30分钟",
    },
    "termination_clause": {
        "name_cn": "终止/解除条件",
        "hint": "合同提前终止或解除的条件",
        "example": "任一方严重违约，守约方有权书面通知解除合同",
    },
    "dispute_resolution": {
        "name_cn": "争议解决",
        "hint": "争议解决方式（协商/仲裁/诉讼）",
        "example": "协商不成，提交甲方所在地人民法院诉讼解决",
    },
    "warranty_period": {
        "name_cn": "质保期",
        "hint": "免费维护/质量保证的期限",
        "example": "验收合格后12个月",
    },
}

CONTRACT_USER_TEMPLATE = (
    "请从以下合同/协议文本中抽取结构化字段。\n\n"
    "## 抽取要求\n"
    "1. value_text 必须是正文内容，不能只是条款标题。\n"
    "2. 每个字段必须包含 source_chunk_key（必填）和 evidence_quote（必填）。\n"
    "3. confidence 必须为 HIGH/MEDIUM/LOW 之一。\n\n"
    "允许的 field_code 及说明：\n{field_hints}\n\n"
    "返回格式：\n"
    '{{\"contract_name\": \"...\", \"contract_no\": \"...\", '
    '\"fields\": [{{\"field_code\": \"...\", \"value_text\": \"...\", '
    '\"source_chunk_key\": \"...\", \"evidence_quote\": \"...\", '
    '\"confidence\": \"HIGH\"}}]}}\n\n'
    "文档分块如下：\n{chunk_text}"
)

# ═══════════════════════════════════════════════════════════════
# 通用工具函数
# ═══════════════════════════════════════════════════════════════

def _build_field_hints(fields: dict[str, dict[str, Any]]) -> str:
    """把 FIELD_SCHEMA 格式化为 prompt 中的字段说明文本。"""
    lines = []
    for code, info in fields.items():
        hint = info.get("hint", "")
        example = info.get("example", "")
        line = f"  - {code}（{info['name_cn']}）：{hint}。示例：{example}"
        lines.append(line)
    return "\n".join(lines)


def build_extract_prompt(
    profile: str,
    chunk_text: str,
) -> tuple[str, str]:
    """根据 profile 返回 (system_prompt, user_prompt)。"""
    config = PROFILE_PROMPT_CONFIG.get(profile)
    if not config:
        raise ValueError(f"No prompt config for profile: {profile}")
    system = config["system"]
    fields = config["fields"]
    template = config["user_template"]
    field_hints = _build_field_hints(fields)
    field_codes = json.dumps(sorted(fields.keys()), ensure_ascii=False)
    user = template.format(
        field_codes=field_codes,
        field_hints=field_hints,
        chunk_text=chunk_text,
    )
    return system, user


# ── Profile → Prompt 配置映射 ───────────────────────────────
PROFILE_PROMPT_CONFIG: dict[str, dict[str, Any]] = {
    "business_plan": {
        "system": BUSINESS_PLAN_SYSTEM,
        "fields": BUSINESS_PLAN_FIELDS,
        "user_template": BUSINESS_PLAN_USER_TEMPLATE,
    },
    "governance_rule": {
        "system": GOVERNANCE_RULE_SYSTEM,
        "fields": GOVERNANCE_RULE_FIELDS,
        "user_template": GOVERNANCE_RULE_USER_TEMPLATE,
    },
    "project_doc": {
        "system": PROJECT_DOC_SYSTEM,
        "fields": PROJECT_DOC_FIELDS,
        "user_template": PROJECT_DOC_USER_TEMPLATE,
    },
    "contract_agreement": {
        "system": CONTRACT_SYSTEM,
        "fields": CONTRACT_FIELDS,
        "user_template": CONTRACT_USER_TEMPLATE,
    },
    # general_document 不使用 LLM 抽取
}
