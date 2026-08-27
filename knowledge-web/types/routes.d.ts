import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /**
     * 同级路由的排序, 静态路由默认为99
     */
    order?: number
    /**
     * 是否显示为菜单，默认为true
     */
    hidden?: boolean
    /**
     * 标题
     */
    title: string
    /**
     * 权限标识, 传入权限标识字符串或由权限标识字符组成的数组，如果没有此权限，则无法加载该路由
     */
    permission?: string | string[]
    /**
     * 菜单icon图标
     */
    icon?: string
    // 是否缓存 默认为true
    keepAlive?: boolean
    // todo 旧版内容, 暂不支持
    isTabs?:  boolean
    isSide?: boolean
    subApp?: boolean
    target?: string
    [key: string]: any
  }
}

export {}
