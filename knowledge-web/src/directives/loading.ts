import Vue from "vue"
import Spin from "ant-design-vue/es/spin"
import "ant-design-vue/es/spin/style/index.less"

// 扩展 HTMLElement 类型，增加 _loading 属性
interface LoadingHTMLElement extends HTMLElement {
  _loading?: HTMLElement | null
}

// 创建一个 loading 组件构造器
const SpinWrapper = Vue.extend({
  components: {
    "a-spin": Spin
  },
  render(h) {
    // 遮罩层样式
    const maskStyle = {
      position: "absolute",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      background: "rgba(255,255,255,0.6)", // 稍微黑点的半透明
      zIndex: 9999,
      display: "flex",
      alignItems: "center",
      justifyContent: "center"
    }
    return h("div", { style: maskStyle as any, class: "v-loading-mask" }, [
      h("a-spin", {
        props: {
          spinning: true,
          size: "large"
        }
      })
    ])
  }
})

// 移除未使用的 el 参数
function createLoadingInstance() {
  // 创建 loading 实例
  const instance = new SpinWrapper()
  const component = instance.$mount()
  return component.$el as HTMLElement
}

const loadingDirective = {
  inserted(el, binding) {
    const target = el as LoadingHTMLElement
    // 保证父元素是相对定位
    const position = window.getComputedStyle(target).position
    if (position === "static" || !position) {
      target.style.position = "relative"
    }
    if (binding.value) {
      if (!target._loading) {
        const loadingEl = createLoadingInstance()
        target.appendChild(loadingEl)
        target._loading = loadingEl
      }
    }
  },
  update(el, binding) {
    const target = el as LoadingHTMLElement
    if (binding.value !== binding.oldValue) {
      if (binding.value) {
        if (!target._loading) {
          const loadingEl = createLoadingInstance()
          target.appendChild(loadingEl)
          target._loading = loadingEl
        }
      } else {
        if (target._loading) {
          target.removeChild(target._loading)
          target._loading = null
        }
      }
    }
  },
  unbind(el) {
    const target = el as LoadingHTMLElement
    if (target._loading) {
      target.removeChild(target._loading)
      target._loading = null
    }
  }
}

export default loadingDirective
