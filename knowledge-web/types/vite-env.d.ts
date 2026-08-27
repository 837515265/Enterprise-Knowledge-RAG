declare global {
    interface ImportMetaEnv extends ViteEnv {
      __: unknown
    }
  
    declare interface ViteEnv {
      [key: string]: any
      BASE_URL: string
      MODE: string
      /** 布尔值，是否开发环境 */
      DEV: boolean
      /** 布尔值，是否生产环境 */
      PROD: boolean
      SSR: boolean
      /** 代理地址 */
      VITE_PROXY_URL: string
       /** 代理地址 */
       VITE_MOCK_PROXY_URL: string
      /** 项目名称，用于项目内部布局组件和顶部导航展示 */
      VITE_APP_NAME: string
      /** 访问路径 public-path */
      VITE_BASE_PATH: string
      /** axios请求接口前缀baseUrl */
      VITE_BASE_URL_PREFIX: string
      /** 端口号 */
      VITE_SERVER_PORT: number
      /** 网关前缀地址 系统网关前缀，对应【用户中心-菜单管理-服务上下文】字段 */
      VITE_APP_GATEWAY_PREFIX: string
      /** 统一登录 client-id 对应【用户中心-菜单管理-客户端】字段 */
      VITE_LDSK_CLIENT_ID: string
      /** 统一登录 项目名称 对应【用户中心-菜单-菜单名称】字段 */
      VITE_LDSK_PROJECT_NAME: string
      // 是否缓存 用户信息 和 菜单 （开启后会自动缓存 user-store, 且页面刷新时会优先使用缓存数据）
      VITE_CACHE_USERINFO: boolean
      // 是否缓存字典（开启后会自动缓存 dict-store, 且页面刷新时会优先使用缓存数据）
      VITE_CACHE_DICTIONAYR: boolean
      /** vform表单tenant-id */
      VITE_LDSK_VFORM_TENANT_ID: string
      /** vite-plugin-vue-inspector插件使用的启动编辑器 webstorm/code(vscode) */
      VITE_INSPECTOR_LAUNCH_EDITOR: "webstorm" | "code" | string
    }
  }
  
  export {}
  