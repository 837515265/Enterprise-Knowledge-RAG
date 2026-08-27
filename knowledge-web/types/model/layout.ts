export enum CONTENT_WIDTH_TYPE {
  Fluid = "Fluid",
  Fixed = "Fixed"
}

// 主题类型定义
export interface LayoutSetting {
  /**
   * 布局方式：顶部菜单或侧边菜单
   */
  layout: "topmenu" | "sidemenu"
  /**
   * 内容区域宽度：流式布局
   */
  contentWidth: `${CONTENT_WIDTH_TYPE}` 
   /**
   * 主题风格：暗色或亮色
   */
  theme: "dark" | "light"
  /**
   * 主题主色
   * ! 只允许传入hex格式的颜色码值 如 #999999
   */
  primaryColor: `#${string}`
  /**
   * 是否固定头部
   */
  fixedHeader: boolean
  /**
   * 是否固定侧边栏
   */
  fixSiderbar: boolean
  /**
   * 是否展示标签页
   */
  showTabs: boolean
  /**
   * 是否开启色弱模式
   */
  colorWeak?: boolean
  /**
   * 开启后 将路由第一个子组件展示为固定页签
   */
  fixedFirstRouteOnTags: boolean
}
