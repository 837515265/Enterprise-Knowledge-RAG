import { useDictStoreOut } from "@/store/modules/dict"
import { useUserStoreWithOut } from "@/store/modules/user"
import { useMenuStoreOut } from "@/store/modules/menu"
import { getUrlConf } from "@/utils/auth/url"
import { storeToRefs } from "pinia"
import type VueRouter from "vue-router"
import type { Route, NavigationGuardNext } from "vue-router"
import { goToLoginToGetCode } from "@/utils/auth/goToLogin"

// 免登录白名单
const allowList = ["/404", "/redirect"]

/**
 * 注册权限守卫
 * @param router 路由实例（VueRouter）
 */
export function registerPermissionGuard(router: VueRouter) {
  // 注册全局前置守卫
  router.beforeEach(async (to: Route, from: Route, next: NavigationGuardNext) => {
    try {
      // 白名单页面，直接跳转
      if (allowList.includes(to.path)) {
        return next()
      }

      const userStore = useUserStoreWithOut()
      const menuStore = useMenuStoreOut()
      const dictStore = useDictStoreOut()

      const { token, roles } = storeToRefs(userStore)

      const urlConfig = getUrlConf(window.location.search)

      let isFormLogin = false

      // =======没有登录信息的情况===========
      if (!token.value) {
        // 没有认证code的情况，跳转登录页面获取code
        if (!urlConfig.code) {
          return goToLoginToGetCode()
        }

        // 获取token
        await userStore.getTokenAction({ code: urlConfig.code })
        // 清理 URL，去除 code 参数
        const newUrl = `${window.location.origin + window.location.pathname + window.location.hash}${urlConfig.state}`
        isFormLogin = true
        window.history.replaceState({}, "", newUrl)
      }

      const hasUserInfo = !!roles.value.length
      /**
       * 有token但没有用户信息 获取用户信息
       * 【首次登录刚获取完token】或者【不缓存用户信息时刷新页面】会出现此种情况
       */
      // ======= 有token 但是没有用户信息===========
      if (!hasUserInfo) {
        // 获取用户信息
        await userStore.getInfoAction()
        // 获取路由和菜单
        await menuStore.initRoutes(router)

        // 跳转到重定向地址或当前目标页
        const redirect = isFormLogin ? urlConfig.state : from.query.redirect || to.fullPath
        return next({ path: redirect as string, replace: true })
      }

      if (!Object.keys(dictStore.dictMap)?.length) {
        // 暂时不使用异步，否则容易出现页面最开始获取不到字典的情况
        await dictStore.requestDictionary()
      }

      // 判断目标路由是否存在, 如果不存在，跳转到404
      if (!to.matched?.length) {
        return next({ path: "/404", replace: true })
      }

      // 全部通过，放行
      return next()
    } catch (error) {
      console.log("error", error)
      return goToLoginToGetCode()
    } finally {
      const globalLoading = document.getElementById("global-loading")
      if (globalLoading) {
        setTimeout(() => {
          globalLoading.parentNode?.removeChild(globalLoading)
        }, 300)
      }
    }
  })

  // 注册全局后置钩子，设置页面标题
  router.afterEach((to: Route) => {
    const title = to.meta?.title

    document.title = title
      ? `${title} - ${import.meta.env.VITE_LDSK_PROJECT_NAME}`
      : (import.meta.env.VITE_APP_NAME as string)
  })

  return router
}
