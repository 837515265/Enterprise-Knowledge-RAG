import loading from "@/utils/fullLoading"
import { instance } from "./instance"
import type { AxiosRequestConfig } from "axios"

export function request<T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T>
export function request<T = any>(config: AxiosRequestConfig): Promise<T>

/**
 * 优化后的 request 方法，支持泛型和多种参数形式
 * @param urlOrConfig - 请求地址或配置对象
 * @param paramsOrAdvance - 请求参数或高级配置
 * @param config - 请求配置
 * @returns Promise<T>
 */
export function request(
  urlOrConfig: string | AxiosRequestConfig,
  paramsOrAdvance: any = {},
  config: AxiosRequestConfig = {}
) {
  let finalConfig: AxiosRequestConfig

  // 参数：url，params，config
  if (typeof urlOrConfig === "string") {
    finalConfig = config || {}
    finalConfig.url = urlOrConfig
    const method = (finalConfig?.method || "GET").toUpperCase()
    const useParams = ["GET", "DELETE", "HEAD", "OPTIONS"].includes(method)
    const field = useParams ? "params" : "data"
    finalConfig[field] = finalConfig[field] || paramsOrAdvance || {}
  } else {
    // 参数：config
    finalConfig = urlOrConfig
  }

  const { headersType, headers, ...otherConfig } = finalConfig

  return instance({
    ...otherConfig,
    headers: {
      "Content-Type": headersType,
      ...headers
    }
  }).finally(() => {
    const { showLoading } = finalConfig
    if (showLoading) {
      loading.hide()
    }
  })
}

/**
 * GET 请求
 * @param url - 请求地址
 * @param params - 查询参数
 * @param config - 请求配置
 */
export const httpGet = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  return request<T>(url, params, { method: "GET", ...config })
}

/**
 * POST 请求
 * @param url - 请求地址
 * @param params - 请求体参数
 * @param config - 请求配置
 */
export const httpPost = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  return request<T>(url, params, { method: "POST", ...config })
}

/**
 * DELETE 请求
 * @param url - 请求地址
 * @param params - 查询参数
 * @param config - 请求配置
 */
export const httpDelete = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  return request<T>(url, params, { method: "DELETE", ...config })
}

/**
 * PUT 请求
 * @param url - 请求地址
 * @param params - 请求体参数
 * @param config - 请求配置
 */
export const httpPut = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  return request<T>(url, params, { method: "PUT", ...config })
}

/**
 * 文件下载（GET，返回 blob）
 * @param url - 请求地址
 * @param params - 查询参数
 * @param config - 请求配置
 */
export const httpDownload = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  return request<T>(url, params, { method: "GET", responseType: "blob", ...config })
}

/**
 * 文件上传（POST，multipart/form-data）
 * @param url - 请求地址
 * @param params - 请求体参数
 * @param config - 请求配置
 */
export const httpUpload = async <T = any>(url: string, params?: any, config: AxiosRequestConfig = {}): Promise<T> => {
  const newConfig = { ...config, headersType: "multipart/form-data" }
  return request<T>(url, params, { method: "POST", ...newConfig })
}

request.httpPost = httpPost
request.httpGet = httpGet
request.httpPut = httpPut
request.httpDelete = httpDelete
request.httpDownload = httpDownload
request.httpUpload = httpUpload

export default request
