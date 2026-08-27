export function useModelValue(props, emit) {
  // 内部状态管理
  const internalValue = ref(props.value)

  // 监听 props.value 变化
  watch(
    () => props.value,
    (newVal) => {
      internalValue.value = newVal
    }
  )

  // computed 实现 v-model
  const currentValue = computed({
    get: () => internalValue.value,
    set: (val) => {
      internalValue.value = val
      emit("input", val)
    }
  })

  return currentValue
}
