import { registerPermissionGuard } from "@/router/guard/permissionGuard"
import Vue from "vue"
import VueRouter from "vue-router"

Vue.use(VueRouter)

const router = new VueRouter({
  base: import.meta.env.VITE_BASE_PATH,
  mode: "hash",
  routes: []
})

/**
 * 路由守卫/权限控制
 */
registerPermissionGuard(router)

export default router
