export const DEFAULT_KNOWLEDGE_TYPE = "governance_rule"

export const KNOWLEDGE_TYPE_OPTIONS = [
  { value: "business_plan", label: "业务方案", icon: "profile" },
  { value: "governance_rule", label: "规章制度", icon: "file-text" },
  { value: "project_doc", label: "项目文件", icon: "book" },
  { value: "sql_analytics", label: "智能问数", icon: "bar-chart" }
]

export const KNOWLEDGE_TYPE_LABEL_MAP = KNOWLEDGE_TYPE_OPTIONS.reduce<Record<string, string>>((result, item) => {
  result[item.value] = item.label
  return result
}, {})

export const KNOWLEDGE_TYPE_ICON_MAP = KNOWLEDGE_TYPE_OPTIONS.reduce<Record<string, string>>((result, item) => {
  result[item.value] = item.icon
  return result
}, {})

export function normalizeKnowledgeTypeForForm(type?: string) {
  const raw = String(type || "").trim()
  if (KNOWLEDGE_TYPE_LABEL_MAP[raw]) return raw
  return DEFAULT_KNOWLEDGE_TYPE
}

export function getKnowledgeTypeLabel(type?: string) {
  const raw = String(type || "")
  return KNOWLEDGE_TYPE_LABEL_MAP[raw] || raw
}

export function getKnowledgeTypeIcon(type?: string) {
  return KNOWLEDGE_TYPE_ICON_MAP[String(type || "")] || "file-text"
}
