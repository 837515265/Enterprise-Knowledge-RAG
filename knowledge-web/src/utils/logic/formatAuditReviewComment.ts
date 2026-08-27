type ChunkAuditDetail = {
  chunkId?: string | number
  seqNo?: number
  status?: string
  reason?: string
}

function isChunkAuditDetailArray(value: unknown): value is ChunkAuditDetail[] {
  if (!Array.isArray(value) || !value.length) return false
  return value.every(
    (item) =>
      item &&
      typeof item === "object" &&
      ("chunkId" in item || "seqNo" in item) &&
      ("status" in item || "reason" in item)
  )
}

function parseChunkAuditDetails(text: string): ChunkAuditDetail[] | null {
  const trimmed = text.trim()
  if (!trimmed.startsWith("[") && !trimmed.startsWith("{")) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (isChunkAuditDetailArray(parsed)) return parsed
  } catch {
    return null
  }
  return null
}

export function buildChunkAuditReviewSummary(details: ChunkAuditDetail[]): string {
  const approved = details.filter((item) => item.status === "approved")
  const rejected = details.filter((item) => item.status === "rejected")
  const total = details.length
  const parts: string[] = []

  if (!rejected.length) {
    parts.push(`全部通过（共 ${total} 条）`)
  } else if (!approved.length) {
    parts.push(`全部驳回（共 ${total} 条）`)
  } else {
    parts.push(`通过 ${approved.length} 条，驳回 ${rejected.length} 条（共 ${total} 条）`)
  }

  const reasonParts = rejected
    .filter((item) => item.reason && String(item.reason).trim())
    .map((item) => `#${item.seqNo ?? "-"}：${String(item.reason).trim()}`)
  if (reasonParts.length) {
    parts.push(`驳回原因：${reasonParts.join("；")}`)
  }

  return parts.join("；")
}

export function formatAuditReviewCommentDisplay(text?: string | null): string {
  if (!text || !String(text).trim()) return "无审核意见"
  const raw = String(text).trim()
  const details = parseChunkAuditDetails(raw)
  if (details) return buildChunkAuditReviewSummary(details)
  return raw
}
