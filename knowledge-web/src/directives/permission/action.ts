import { useUserStoreWithOut } from "@/store/modules/user"
import type { VueConstructor } from "vue"
import type { DirectiveBinding } from "vue/types/options"

const userStore = useUserStoreWithOut()
/**
 * v-action 权限指令
 *
 * 用途：
 *   用于根据用户的权限动态控制组件（如按钮、链接等）的显示与隐藏。
 *   适用于需要基于 action 权限点进行前端按钮级别权限控制的场景。
 *
 * 指令用法：
 *   - 在需要控制 action 级别权限的组件上使用 v-action="'权限标识'"，如：
 *     <a-button v-action="'sys:add'">添加用户</a-button>
 *     <a-button v-action="'sys:delete'">删除用户</a-button>
 *
 * 参数说明：
 *   - binding.value：字符串类型，表示 action 权限标识。
 *
 * 行为说明：
 *   - 当前用户拥有该权限标识时，组件正常显示。
 *   - 当前用户没有该权限标识时，组件会被从 DOM 中移除，若无法移除则隐藏（display: none）。
 *
 * 注意事项：
 *   - 权限标识需与后端返回的权限点保持一致。
 *   - 如需适配不同的权限模式，可修改本文件的权限判断逻辑。
 */
export function registerActionDirectives(Vue: VueConstructor) {
  Vue.directive("action", {
    inserted: function (el: HTMLElement, binding: DirectiveBinding) {
      const actionName = binding.value
      const permissions = userStore.permissions

      if (!actionName || permissions.includes(actionName)) {
        return
      }
      ;(el.parentNode && el.parentNode.removeChild(el)) || (el.style.display = "none")
    }
  })
}
