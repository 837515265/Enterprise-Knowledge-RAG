import { defineStore } from "pinia"
import store from "@/store"
import { TreeMenuList } from "#/model/menu"
import type { RouteConfig } from "vue-router"
import { getUserMenuTree } from "@/api/common-user"
import { useUserStoreWithOut } from "@/store/modules/user"
import { transformAsyncMenusToRoutes } from "@/utils/auth/transformMenuInfoToRoutes"
import { isNumber, cloneDeep } from "lodash-es"
import type VueRouter from "vue-router"
import { layoutRoute as _layoutRoute, kbLayoutRoute as _kbLayoutRoute, routes as _routes } from "@/router/routes/routes"

// 用于存储菜单图标（目前为空对象，可根据实际需求扩展）
const icons = {}

export const useMenuStore = defineStore(
  "menus",
  () => {
    // 所有路由
    const allRoutes = ref<RouteConfig[]>([])
    // 菜单数据
    const menus = ref<RouteConfig[]>([])

    /**
     * 加载异步路由, 合并静态路由 ，并注册到路由实例
     * @param router 路由实例（VueRouter）
     * @returns {Promise<void>}
     */
    async function initRoutes(router: VueRouter): Promise<void> {
      // 获取动态菜单
      const asynMenus = (await requestAsyncMenus()) || []
      // 将异步菜单树转换为异步路由
      const asyncRoutes = transformAsyncMenusToRoutes(asynMenus, icons)

      // 获取当前用户的权限
      const userStore = useUserStoreWithOut()
      const permissions = userStore.permissions

      // 深拷贝layout路由和静态路由，避免直接修改原始数据
      const layoutRoutes = cloneDeep(_layoutRoute)
      const routes = cloneDeep(_routes)

      // 合并静态路由和动态路由
      const layoutChildren = (layoutRoutes.children || []) as RouteConfig[]
      menus.value = [...(asyncRoutes || []), ...layoutChildren]

      // 根据权限过滤
      menus.value = filterRoutesByPermissions(menus.value, permissions)
      // 对 layout 下的子路由根据 order 排序
      menus.value = orderRoutes(menus.value || [])

      // 设置 layout 的重定向为第一个子路由
      const redirectUrl = menus.value[0]?.path

      // 重新设置 布局路由 的配置，将合并后的菜单覆盖原本的路由
      layoutRoutes.redirect = redirectUrl
      layoutRoutes.children = menus.value

      // 知识库独立布局路由
      const kbRoutes = cloneDeep(_kbLayoutRoute)

      // 合并 layout 路由、知识库路由和静态路由，得到最终的全部路由
      allRoutes.value = [layoutRoutes, kbRoutes, ...filterRoutesByPermissions(routes, permissions)]

      // 打印最终生成的全部路由，便于调试
      console.log("======生成全部路由=====", allRoutes.value)

      // 遍历注册所有路由到路由实例
      allRoutes.value.forEach((menu) => {
        router.addRoute(menu)
      })
    }

    /**
     *  清空menuStore数据
     */
    function resetMenuInfo() {
      allRoutes.value = []
      menus.value = []
    }

    // 加载异步路由信息
    async function requestAsyncMenus(): Promise<TreeMenuList> {
      const { VITE_LDSK_PROJECT_NAME, VITE_LDSK_CLIENT_ID } = import.meta.env
      const res = await getUserMenuTree(VITE_LDSK_PROJECT_NAME, VITE_LDSK_CLIENT_ID)
      return res
    }

    /**
     * 根据权限过滤路由
     * @param routes 路由数组
     * @param permissions 权限数组
     * @returns 过滤后的路由数组
     */
    function filterRoutesByPermissions(routes: any[], permissions: string[]): RouteConfig[] {
      return routes.reduce((prev, route) => {
        // 递归处理子路由的权限
        if (route.children) {
          route.children = filterRoutesByPermissions(route.children, permissions)
        }
        // 获取当前路由的权限标识
        let permissionKey = route.meta?.permission as string | string[] | undefined

        if (permissionKey) {
          // 如果有权限标识，统一转为数组
          if (typeof permissionKey === "string") {
            permissionKey = [permissionKey]
          }
          // 判断用户是否有该权限
          const hasPermission = (permissionKey as string[]).some((key) => permissions.includes(key))

          if (hasPermission) {
            prev.push(route)
          }
        } else {
          // 没有权限标识，默认有权限
          prev.push(route)
        }

        return prev
      }, [])
    }

    /**
     * 根据 meta.order 字段对路由进行排序
     * @param routes 路由数组
     * @returns 排序后的路由数组
     */
    function orderRoutes(routes: RouteConfig[]): RouteConfig[] {
      // 先对当前层级排序
      const _routes = routes.sort((a, b) => {
        const orderA = isNumber(a.meta?.order) ? Number(a.meta?.order) : 999
        const orderB = isNumber(b.meta?.order) ? Number(b.meta?.order) : 999
        return orderA - orderB
      })
      // 递归对子路由排序
      return _routes.map((route) => {
        return {
          ...route,
          children: route.children ? orderRoutes(route.children) : null
        }
      }) as RouteConfig[]
    }

    return {
      allRoutes,
      menus,
      initRoutes,
      resetMenuInfo
    }
  },
  {
    // true-开启数据持久化
    // persist: import.meta.env.VITE_CACHE_USERINFO
    persist: false
  }
)

// 便捷获取不带 setup 的 userStore 实例
export const useMenuStoreOut = () => {
  return useMenuStore(store)
}
