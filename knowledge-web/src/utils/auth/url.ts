// 解析 URL 参数
export function getUrlConf(search: string) {
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`)
  const obj: Record<string, string> = {}
  params.forEach((v, k) => {
    obj[k] = v
  })
  return obj
}
