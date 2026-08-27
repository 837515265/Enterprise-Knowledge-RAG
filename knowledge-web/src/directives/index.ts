/**
 * 指令注册入口文件
 *
 * 用途：
 *   统一注册全局自定义指令（如权限相关的 v-action、v-actions 等），
 *   便于在 main.js/main.ts 中一次性引入和注册所有指令。
 *
 * 使用方式：
 *   在 Vue 项目入口处调用 registerDirectives(Vue) 即可。
 */
import { registerActionDirectives } from "@/directives/permission/action"
import { registerActionsDirectives } from "@/directives/permission/actions"
import loadingDirective from "@/directives/loading"
import type { VueConstructor } from "vue"

/**
 * 注册所有自定义指令
 * @param Vue Vue 构造函数
 */
export function registerDirectives(Vue: VueConstructor) {
  registerActionDirectives(Vue)
  registerActionsDirectives(Vue)
  Vue.directive("loading", loadingDirective)
}
