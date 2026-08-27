/**
 * 将可能为 URL 百分号编码的展示文本解码为可读文件名/标题。
 */
export function decodeDisplayText(value: unknown): string {
  if (value === null || value === undefined) {
    return ""
  }
  const text = String(value).trim()
  if (!text || !/%[0-9A-Fa-f]{2}/.test(text)) {
    return text
  }
  try {
    return decodeURIComponent(text.replace(/\+/g, " "))
  } catch {
    return text
  }
}
