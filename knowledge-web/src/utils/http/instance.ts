import { axiosConfig, axiosInterceptors } from "@/utils/http/config"
import axios, { AxiosStatic } from "axios"

/**
 * ==================================================================
 * 为什么不用axios.create来创建实例?
 * 因为vform内部与所属项目共享axios实例，但无法共享axios.create创建的实例
 * 为了vform和项目内部能够统一axios实例（config以及拦截器），所以直接使用axios本身作为实例
 * ==================================================================
 */

const GLOBAL_KEY = "__AXIOS_INSTANCE__"

// @ts-ignore
const globalObj: any = window

let instance: AxiosStatic

if (globalObj[GLOBAL_KEY]) {
  instance = globalObj[GLOBAL_KEY]
} else {
  instance = axios

  // 循环依次将默认配置赋值给axios.defaults，不能直接覆盖axios.defaults, 会导致无法生效
  Object.keys(axiosConfig).forEach((key) => {
    // 由于 axios.defaults 的类型限制，这里需要做类型断言
    instance!.defaults[key as keyof typeof axiosConfig] = axiosConfig[key as keyof typeof axiosConfig]
  })

  // request拦截器
  instance.interceptors.request.use(axiosInterceptors.requestInterceptor, axiosInterceptors.requestErrorInterceptor)
  // response 拦截器
  instance.interceptors.response.use(axiosInterceptors.responseInterceptor, axiosInterceptors.responseErrorInterceptor)

  globalObj[GLOBAL_KEY] = instance
}

export { instance }
