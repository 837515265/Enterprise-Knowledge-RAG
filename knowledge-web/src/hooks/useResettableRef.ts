import { cloneDeep } from "lodash-es"
import { Ref } from "vue"

/**
 *
 * 创建一个可以重置为初始值的ref
 * @param {T} defaultValue
 * @returns {[Ref<T>, () => void]}  返回一个数组，数组第一个值为 响应式的ref，第二值为 重置ref为初始值的方法
 */
export function useResettableRef<T = any>(defaultValue: T) {
  const state = ref(defaultValue) as Ref<T>
  const initialData = cloneDeep(defaultValue)

  function reset() {
    state.value = cloneDeep(initialData) as T
  }

  return [state, reset] as const
}
