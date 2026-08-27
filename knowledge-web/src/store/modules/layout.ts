// 字典相关类型
import layoutSetting from "@/config/layout"
import { LayoutSetting } from "#/model/layout"
import { defineStore } from "pinia"
import { Ref } from "vue"
import store from "@/store"

export const useLayoutStore = defineStore(
  "layout",
  () => {
    const config = ref(layoutSetting) as Ref<LayoutSetting>

    const openTag = computed(() => config.value?.showTabs)

    function changeConfigItem<T extends keyof LayoutSetting>(key: T, value: LayoutSetting[T]) {
      config.value[key] = value
    }

    return {
      config,
      openTag,
      changeConfigItem
    }
  },
  {
    // true-开启数据持久化
    persist: import.meta.env.DEV
  }
)

// 便捷获取不带 setup 的 userStore 实例
export const useLayoutStoreOut = () => {
  return useLayoutStore(store)
}
