export {}
declare module "axios" {
  // 扩展axios的config配置项
  export interface AxiosRequestConfig {
    /**
     * 自定义 Content-Type 类型
     */
    headersType?: string
    /**
     * 接口请求时是否不传递token，默认为false
     */
    withoutToken?: boolean
    /**
     * 接口是否直接返回axios的包装对象， 默认为false
     */
    withNativeResponse?: boolean
    /**
     * 接口请求时，是否展示全局loading，默认为false
     */
    showLoading?: boolean
    /**
     * dev环境开启使用mock服务，仅dev环境生效
    */
    devMock?: boolean
  }
}
