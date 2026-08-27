import { useUserStoreWithOut } from "@/store/modules/user"
import loading from "@/utils/fullLoading"
import { AxiosDefaults, AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios"
import qs from "qs"
/**
 * axios 默认配置
 */
export const axiosConfig: Partial<AxiosDefaults> = {
  baseURL: import.meta.env.VITE_BASE_URL_PREFIX, // api 的 baseUrl
  timeout: 300000, // 请求超时时间（5 分钟，兼容大文件上传 + 多模态解析触发）
  withCredentials: false, // 禁用 Cookie 等信息
  // 自定义参数序列化函数，参数类型为 Record<string, any>
  paramsSerializer: (params: Record<string, any>) => {
    return qs.stringify(params, { allowDots: true })
  }
}

function getHttpErrorMessage(data: any, error: AxiosError, fallback: string) {
  return data?.resp_msg || data?.message || error.message || fallback
}

/**
 * axios 拦截器
 */
export const axiosInterceptors = {
  // =======================================
  // ===============请求拦截器================
  // =======================================
  requestInterceptor: async (config: InternalAxiosRequestConfig) => {
    // 获取自定义配置
    const { withoutToken = false, showLoading } = config
    const userStore = useUserStoreWithOut()
    // 是否需要设置 token
    const token = userStore.token
    // 如果 token 存在
    // 让每个请求携带自定义 token 请根据实际情况自行修改
    if (token && !withoutToken) {
      config.headers["Authorization"] = `Bearer ${token}`
    }

    if (import.meta.env.DEV) {
      const auditUserId = userStore.userInfo?.userId || import.meta.env.VITE_DEV_AUDIT_USER_ID
      const auditUserName = userStore.userInfo?.realName || import.meta.env.VITE_DEV_AUDIT_USER_NAME

      if (auditUserId) {
        config.headers["x-userid-header"] = auditUserId
      }
      if (auditUserName) {
        config.headers["x-realname-header"] = encodeURIComponent(auditUserName)
      }
    }

    if (showLoading) {
      loading.show()
    }

    // 开启mock服务，设置baseUrl为代理地址
    if (import.meta.env.DEV && config.devMock) {
      if (!import.meta.env.VITE_MOCK_PROXY_URL) {
        message.error("mock失败，未配置环境变量【VITE_MOCK_PROXY_URL】")
      } else {
        config.baseURL = `${import.meta.env.VITE_MOCK_PROXY_URL}/`
      }
    }

    const method = config.method?.toUpperCase()
    // 防止 GET 请求缓存
    if (method === "GET") {
      config.headers["Cache-Control"] = "no-cache"
      config.headers["Pragma"] = "no-cache"
    }
    // 自定义参数序列化函数
    else if (method === "POST") {
      const contentType = config.headers["Content-Type"] || config.headers["content-type"]
      if (contentType === "application/x-www-form-urlencoded") {
        if (config.data && typeof config.data !== "string") {
          config.data = qs.stringify(config.data)
        }
      }
    }

    return config
  },
  // =======================================
  // =============请求错误拦截器==============
  // =======================================
  requestErrorInterceptor: async (error: AxiosError) => {
    console.log(error) // for debug
    return Promise.reject(error)
  },
  // =======================================
  // ===============响应拦截器================
  // =======================================
  responseInterceptor: async (response: AxiosResponse<any>) => {
    const config = response.config || {}

    const { withNativeResponse = false } = config

    // 如果配置withNativeResponse，则返回axios对象包裹的返回值
    if (withNativeResponse) {
      return response
    }

    let { data } = response

    // if (!data) {
    //   // 返回"[HTTP]请求没有返回值";
    //   throw new Error("返回[HTTP]请求没有返回值")
    // }
    // 未设置状态码则默认成功状态
    // 二进制数据则直接返回，例如说 Excel 导出
    if (response.request?.responseType === "blob" || response.request?.responseType === "arraybuffer") {
      // 注意：如果导出的响应为 json，说明可能失败了，不直接返回进行下载
      if (response.data.type !== "application/json") {
        return response.data
      }
      data = await new Response(response.data).json()
    }

    return data
  },
  // =======================================
  // =============响应错误拦截器==============
  // =======================================
  responseErrorInterceptor: async (error: AxiosError) => {
    if (error.response) {
      const data = error.response.data as any

      // 无权限 or 权限过期 跳转到统一登陆页面
      if (error.response.status === 401 && !(data?.result && data?.result?.isLogin)) {
        const userStore = useUserStoreWithOut()
        return userStore.logoutAction()
      }

      if (error.response.status === 403) {
        notification.error({
          message: "Forbidden",
          description: getHttpErrorMessage(data, error, "无访问权限")
        })
      }

      if (error.response.status === 500) {
        notification.error({
          message: "错误",
          description: getHttpErrorMessage(data, error, "服务器内部错误")
        })
      }
    }
    return Promise.reject(error)
  }
}
