// 全局loading
import Vue from "vue"
import Spin from "ant-design-vue/es/spin/index"

let instance: Vue | null = null
const style: Partial<CSSStyleDeclaration> = {
  position: "fixed",
  left: "0",
  top: "0",
  width: "100%",
  height: "100%",
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  background: "rgba(255,255,255,0.6)", // 稍微黑点的半透明
  zIndex: "99999"
}
let timeoutId: ReturnType<typeof setTimeout> | null = null
let loadingCount = 0
const getInstance = () => {
  // Vue.extend创建子类
  const Component = Vue.extend({
    data() {
      return {
        show: false,
        message: "Loading..."
      }
    },
    render(h: typeof Vue.prototype.$createElement) {
      return this.show ? h("div", { style: style as any }, [h(Spin, { props: { tip: this.message } })]) : null
    },
    methods: {
      /**
       * 显示loading
       * @param val 提示文字
       * @param timeout 超时时间 单位ms 0 不超时
       */
      loading(val = "正在加载", timeout = 0) {
        loadingCount++
        this.show = true
        this.message = val || "Loading..."
        if (timeout) {
          if (timeoutId) {
            clearTimeout(timeoutId)
          }
          timeoutId = setTimeout(() => {
            this.close()
          }, timeout)
        }
      },
      close() {
        if (loadingCount > 0) {
          loadingCount--
        }
        if (loadingCount === 0) {
          clearTimeout(timeoutId as any)
          timeoutId = null
          this.show = false
        }
      }
    },
    destroyed() {
      if (instance && instance.$el) {
        // 当组件卸载时，从DOM中移除元素以避免内存泄露
        ;(instance.$el as HTMLElement).remove()
      }
    }
  })
  if (!instance) {
    // 生成子类的实例
    instance = new Component()
    instance.$mount()
    document.body.appendChild(instance.$el as HTMLElement)
  }
  return instance as Vue & { loading: (val?: string, timeout?: number) => void; close: () => void }
}

const fullLoading = {
  ...Spin,
  show(text = "正在加载", timeout = 0) {
    getInstance().loading(text, timeout)
  },
  hide() {
    getInstance().close()
  }
} as {
  // 展示全局loading
  show(text?: string, timeout?: number): void
  // 关闭当前全局loading
  hide(): void
  setDefaultIndicator(content: any): void
  [key: string]: any
}

export default fullLoading
