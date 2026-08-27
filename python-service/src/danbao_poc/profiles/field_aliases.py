"""按 Profile 组织的字段别名和检索提示，供 query.py 使用。"""
from __future__ import annotations

from typing import Any

# ── 各 Profile 字段别名（QU 阶段用于识别用户意图） ──────────
PROFILE_FIELD_ALIASES: dict[str, dict[str, list[str]]] = {
    "business_plan": {
        "plan_name": ["方案名称", "方案名", "文件名称", "项目名称"],
        "document_no": ["文号", "发文号", "批文号", "文件号"],
        "service_object": ["服务对象", "支持对象", "适用客户", "适用人群", "客群"],
        "access_condition": ["准入条件", "准入要求", "申请条件", "办理条件", "门槛", "谁能申请"],
        "credit_purpose": ["授信用途", "贷款用途", "资金用途", "干什么用"],
        "credit_limit": ["授信额度", "贷款额度", "担保额度", "最高额度", "能贷多少", "最多能批多少", "额度上限", "单户额度"],
        "credit_term": ["担保期限", "贷款期限", "授信期限", "最长期限", "几年", "多久", "多长时间"],
        "guarantee_rate": ["担保费率", "担保费", "费率", "收费标准", "年化费率"],
        "risk_share_ratio": ["分险比例", "风险分担", "风险承担", "财政分险", "银担分险"],
        "risk_mitigation": ["风险缓释", "风险措施", "风控措施"],
        "counter_guarantee": ["反担保", "担保措施", "抵押", "质押", "保证措施"],
        "applicable_scope": ["适用范围", "适用地区", "支持区域", "哪些地区", "什么范围"],
        "business_process": ["办理流程", "业务流程", "申请流程", "办理步骤", "怎么办理"],
        "required_materials": ["申请资料", "申报材料", "所需材料", "需要哪些材料", "交什么材料"],
        "cooperation_org": ["合作机构", "合作银行", "承办机构", "哪家银行"],
        "policy_basis": ["政策依据", "文件依据", "文号依据", "依据什么政策"],
    },
    "governance_rule": {
        "rule_name": ["制度名称", "制度名", "办法名称", "规定名称"],
        "rule_no": ["制度编号", "文号", "制度文号"],
        "applicable_scope": ["适用范围", "谁适用", "哪些部门", "适用人员", "适用对象"],
        "responsible_dept": ["责任部门", "归口部门", "主管部门", "谁管", "职责", "职权", "权限", "负责部门", "职责分工"],
        "approval_authority": ["审批权限", "谁审批", "谁有权", "审批流程", "审批额度", "授权", "决策", "表决", "议事规则", "大额资金"],
        "expense_standard": ["费用标准", "报销标准", "标准是多少", "上限", "补贴标准", "多少钱", "财务", "资金", "预算", "大额资金"],
        "prohibited_items": ["禁止事项", "不能做什么", "禁止", "不允许"],
        "effective_date": ["生效日期", "什么时候执行", "何时生效"],
        "penalty_clause": ["违规处罚", "处罚", "怎么罚", "违规怎么办", "追责", "责任追究", "问责"],
        "exception_handling": ["例外处理", "超标准怎么办", "特殊情况", "例外"],
    },
    "project_doc": {
        "project_name": ["项目名", "系统名", "项目名称", "系统名称", "产品名"],
        "doc_phase": ["阶段", "类型", "什么文档", "哪个阶段"],
        "version": ["版本", "版本号", "第几版", "V几"],
        "module_name": ["模块", "子系统", "组件", "服务", "微服务"],
        "api_list": ["接口", "API", "路径", "Endpoint", "接口文档", "接口列表"],
        "table_list": ["表结构", "数据库表", "表名", "字段", "建表"],
        "config_key": ["配置项", "参数", "环境变量", "配置"],
        "dependency": ["依赖", "中间件", "第三方", "组件依赖", "技术栈"],
        "risk_item": ["风险", "问题", "隐患", "待解决", "风险项"],
        "test_conclusion": ["测试结果", "通过率", "覆盖率", "缺陷", "测试结论"],
        "milestone": ["里程碑", "计划", "节点", "排期"],
        "tech_stack": ["技术栈", "用什么技术", "框架", "语言"],
        "author": ["作者", "编写人", "负责人", "谁写的"],
    },
    "contract_agreement": {
        "contract_name": ["合同名称", "合同名", "协议名称"],
        "contract_no": ["合同编号", "合同号", "协议编号"],
        "party_a": ["甲方", "买方", "委托方", "甲方是谁"],
        "party_b": ["乙方", "卖方", "受托方", "乙方是谁"],
        "contract_amount": ["合同金额", "合同价", "总价", "多少钱", "成交价"],
        "payment_terms": ["付款条款", "付款方式", "怎么付款", "付款比例"],
        "contract_period": ["合同期限", "合同期", "有效期", "起止时间"],
        "delivery_standard": ["交付标准", "验收条件", "怎么验收"],
        "confidentiality": ["保密条款", "保密义务", "保密"],
        "breach_liability": ["违约责任", "违约金", "违约怎么办"],
        "sla_metrics": ["SLA", "服务水平", "可用性", "响应时间"],
        "termination_clause": ["终止条件", "解除条件", "退出"],
        "warranty_period": ["质保期", "保修期", "免费维护"],
    },
    "sql_analytics": {
        "metric": ["指标", "指标定义", "计算口径", "统计口径", "聚合公式", "度量"],
        "term": ["术语", "业务术语", "业务定义", "口径说明", "概念"],
        "verified_sql": ["SQL示例", "已验证SQL", "查询示例", "参考SQL", "SQL模板"],
        "table": ["数据表", "表结构", "表名"],
        "field": ["字段", "列", "字段定义", "数据字典"],
        "dimension": ["维度", "分析维度", "分组字段"],
        "enum": ["枚举", "枚举值", "字段取值"],
        "time_rule": ["时间口径", "时间规则", "本月", "本年", "同比", "环比"],
        "scene": ["问数场景", "业务场景", "数据源"],
    },
    "general_document": {},  # 通用文档不做字段检索
}

# ── 各 Profile 字段提示（QU 阶段给 LLM 的辅助描述） ─────────
PROFILE_FIELD_HINTS: dict[str, dict[str, str]] = {
    "business_plan": {
        "plan_name": "方案主体名称",
        "document_no": "文号或批文编号",
        "service_object": "适用对象、客户群体",
        "access_condition": "准入门槛、申请条件",
        "credit_purpose": "贷款或授信用途",
        "credit_limit": "金额上限、最高额度",
        "credit_term": "期限、月份、年限",
        "guarantee_rate": "担保费率、收费标准",
        "risk_share_ratio": "各方风险分担比例",
        "risk_mitigation": "分险、风险缓释安排",
        "counter_guarantee": "反担保和增信要求",
        "applicable_scope": "适用地区、地域范围",
        "business_process": "办理流程和步骤",
        "required_materials": "申请资料和材料清单",
        "cooperation_org": "合作银行和机构",
        "policy_basis": "政策文件和文号",
    },
    "governance_rule": {
        "rule_name": "制度/办法名称",
        "applicable_scope": "适用范围和对象",
        "responsible_dept": "归口管理部门",
        "approval_authority": "审批人和权限",
        "expense_standard": "费用/报销标准",
        "prohibited_items": "禁止事项",
        "penalty_clause": "违规处罚措施",
        "exception_handling": "特殊/超标处理",
    },
    "project_doc": {
        "project_name": "项目或系统名",
        "module_name": "模块/子系统名",
        "api_list": "接口路径和方法",
        "table_list": "数据库表名和用途",
        "dependency": "依赖组件和版本",
        "test_conclusion": "测试结论和数据",
        "tech_stack": "技术栈和框架",
    },
    "contract_agreement": {
        "party_a": "甲方全称",
        "party_b": "乙方全称",
        "contract_amount": "合同总金额",
        "payment_terms": "付款节点和比例",
        "breach_liability": "违约责任和违约金",
        "contract_period": "合同起止日期",
    },
    "sql_analytics": {
        "metric": "指标定义、聚合表达式、固定过滤条件、单位和时间粒度",
        "term": "业务术语、别名、定义和关联字段",
        "verified_sql": "经过真实数据验证的只读SQL及其适用问题",
        "table": "允许查询的数据表和数据源",
        "field": "物理字段、类型、含义和敏感属性",
        "dimension": "可分组、筛选和排名的业务维度",
        "enum": "维度或字段的合法取值",
        "time_rule": "自然期、数据切片、同比和环比时间口径",
        "scene": "问数场景与数据源边界",
    },
    "general_document": {},
}


def get_field_aliases(profile: str) -> dict[str, list[str]]:
    """获取指定 profile 的字段别名表。"""
    from .registry import normalize_profile
    normalized = normalize_profile(profile) or profile
    return PROFILE_FIELD_ALIASES.get(normalized, {})


def get_field_hints(profile: str) -> dict[str, str]:
    """获取指定 profile 的字段提示表。"""
    from .registry import normalize_profile
    normalized = normalize_profile(profile) or profile
    return PROFILE_FIELD_HINTS.get(normalized, {})
