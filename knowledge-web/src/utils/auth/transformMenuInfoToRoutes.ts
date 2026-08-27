import { CommonView } from "@/router/routes/routes"
import { TreeMenuList } from "#/model/menu"
import { RouteConfig } from "vue-router"

/**
 * @param menus 接口返回的菜单数据列表
 * @param svgIcons 图标集
 * @returns RouteConfig[] 路由列表
 */
export function transformAsyncMenusToRoutes(menus: TreeMenuList, svgIcons: Recordable = {}) {
  if (!menus) return
  return menus?.map((item) => {
    // 取得前端组件信息中的 component 字段
    let routeMeta: Recordable = {}
    if (item.isFrame === 1 && item.componentName) {
      // 不是外链 才去取componentName
      try {
        // eslint-disable-next-line no-eval
        routeMeta = eval(`(${item.componentName})`)
      } catch (e: any) {
        console.error(`【异步路由组件信息对象（routeMeta）解析失败】${e.message}`)
      }
      // 如果路由上配置 routeType === 'nomenu' 无菜单模式，退出本次循环。
      if (routeMeta && routeMeta.routeType === "nomenu") {
        return ""
      }
    }

    // todo 处理 subApp isTabs isSide
    if (item.subApp) {
      routeMeta.subApp = item.subApp
    }
    if (item.whetherSide) {
      routeMeta.isSide = item.whetherSide
    }
    if (item.whetherTabs) {
      routeMeta.isTabs = item.whetherTabs
    }

    if (item.path.startsWith("/")) {
      item.path = item.path.replace("/", "")
    }

    const prefix = "/"

    // 每项菜单的信息
    const menuItem = {
      path: `${prefix}${item.path}`,
      name: item.path,
      component: null,
      children: undefined,
      meta: {
        title: item.menuName,
        // 异步路由：1 则不缓存  0 缓存 默认缓存
        keepAlive: item.isCache !== 1,
        icon: item.icon && item.icon.includes("svg") ? svgIcons[item.icon] : item.icon,
        hidden: item.visible === "1",
        order: item.orderNum,
        ...(routeMeta as RouteConfig["meta"])
      }
    } as RouteConfig & { component?: any; meta: RouteConfig["meta"]; children: RouteConfig["children"] }

    // 不是外链，才去加载 component
    if (item.isFrame === 1) {
      menuItem.component = item.component ? loadView(item.component) : CommonView
    } else {
      // 是外链, 取消prefix
      menuItem.path = item.path
      menuItem.meta!.target = "_blank"
    }
    // 重定向
    if (item.url && item.url !== item.path) {
      menuItem.redirect = item.url
    }
    // 子菜单
    if (item.children && Array.isArray(item.children) && item.children.length > 0) {
      menuItem.children = transformAsyncMenusToRoutes(item.children, svgIcons) || []
    }

    return menuItem
  }) as RouteConfig[]
}

/**
 * 获得componentName.component相匹配的路由信息
 * @param {*} routerMap 路由信息 {}
 * @param {*} key 对应的component名称
 * @returns
 */
export function getComponent(routerMap, key) {
  if (!key) {
    return ""
  }
  return routerMap[key]
}

const modules = import.meta.glob("@/views/**/*.vue")

export function loadView(view: string) {
  const hasSuffix = view.endsWith(".vue") || view.endsWith(".jsx") || view.endsWith(".tsx")
  const path = `/src/views${view.startsWith("/") ? view : `/${view}`}${hasSuffix ? "" : ".vue"}`
  const mod = modules[path]
  if (!mod) {
    // console.info("未找到视图组件: ", view)
    // throw new Error(`未找到视图组件: ${view}`)
  }
  return mod
}
