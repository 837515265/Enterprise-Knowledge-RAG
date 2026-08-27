import { Base64 } from "js-base64"
import { getFileByFileId } from "@/api/common"

function getServerOrigin() {
  return import.meta.env.DEV ? import.meta.env.VITE_PROXY_URL : window.location.origin
}

/**
 * 根据接口path解析返回对应的路径
 * @param path 接口获取的path
 * @param encode 是否转换url为base64
 * @returns url
 */
export function resolveFileUrl(path: string, encode = true): string {
  const origin = getServerOrigin()
  const url = `${origin}/api-file${path}`
  if (encode) {
    return encodeURIComponent(Base64.encode(`${origin}/api-file${path}`))
  } else {
    return url
  }
}

/**
 * 根据文件id获取对应url
 * @param fileId oss文件id
 * @returns {string} 文件路径 如果是iframe，直接返回文件地址，否则返回kkfile的预览链接
 */
export async function getPreviewUrlByFileId(fileId: string) {
  const origin = getServerOrigin()
  const res = await getFileByFileId(fileId)
  const path = String(res?.datas || res?.data || res?.path || res || "")

  if (!path) {
    throw new Error("文件地址为空")
  }

  let url = ""
  if (path.endsWith(".pdf")) {
    url = resolveFileUrl(path, false)
  } else {
    url = `${origin}/preview/onlinePreview?url=${resolveFileUrl(path, true)}`
  }

  // 获取文件名称
  const list = path.split("/")
  const name = list[list.length - 1] || ""

  return {
    name,
    url
  }
}
