import Vue from "vue"
import pinia from "@/store"
import App from "@/App.vue"
import router from "@/router"
import { registerDirectives } from "@/directives"
import { useLayoutStoreOut } from "@/store/modules/layout"
import { changeTheme } from "@/utils/theme"
import antdLocale from "@/utils/logic/loadLocale"
import { registerExtraAntdvComponents } from "@/utils/logic/loadAntdExtraComponnets.js"

/** =============================================
 *  q: 为什么要引入这个文件？
 *  a:  vform的渲染器和此项目共用一个axios包
 *      为了两者的拦截器和其他逻辑保持一致
 *      我们将axios的拦截器提前注册提供给vform使用
 *  =============================================
 */
import "@/utils/http/instance"

// ================css ==============
import "@/style/index.less"

Vue.config.productionTip = false
Vue.config.devtools = true

Vue.use(antdLocale)

// 修改主题色
const layoutStore = useLayoutStoreOut()
changeTheme(layoutStore.config.primaryColor)

registerDirectives(Vue)
registerExtraAntdvComponents(Vue)

new Vue({
  el: "#app",
  router,
  render: (h) => h(App),
  pinia
})
