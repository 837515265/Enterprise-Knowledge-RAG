import { defineStore } from "pinia"
import store from "@/store"
import VueRouter, { RouteConfig, Route } from "vue-router"

// TagView 类型定义
export interface TagView {
  fullPath: string
  // 路由名称
  name: string
  // 路由路径
  path: string
  // 路由元信息
  meta: {
    title?: string
    affix?: boolean // 是否固定标签
    noCache?: boolean // 是否不缓存
    [key: string]: any
  }
  // 记录打开当前页面时的fullPath
  fromPath: string
  [key: string]: any
}

export const useTagsStore = defineStore(
  "tags",
  () => {
    const tags = ref<TagView[]>([])

    const fixedTag = ref<TagView | null>(null)

    const currentTag = ref<TagView>()

    const currentTagKey = computed(() => currentTag.value?.fullPath)

    function onChangeRoute(route: Route) {
      let tag = tags.value.find((item) => item.fullPath === route.fullPath)
      if (!tag) {
        tag = {
          name: typeof route.name === "string" ? route.name : "",
          path: route.path,
          meta: route.meta || {},
          fullPath: route.fullPath,
          query: route.query,
          fromPath: currentTag.value?.fullPath || "/"
        }
        tags.value.push(tag)
      }
      currentTag.value = tag
    }

    // 刷新标签
    function refreshTag(view: TagView, router: VueRouter) {
      setTimeout(() => {
        router.replace({ path: `/redirect${view.fullPath}` })
      })
    }

    function closeTags(command: "left" | "right" | "self" | "all" | "others", tag: TagView, router: VueRouter) {
      const idx = tags.value.findIndex((item) => item.fullPath === tag.fullPath)

      if (idx === -1) {
        return
      }

      switch (command) {
        case "left":
          tags.value = tags.value.filter((_, i) => i >= idx || isFixedTag(tags.value[i]))
          break
        case "right":
          tags.value = tags.value.filter((_, i) => i <= idx || isFixedTag(tags.value[i]))
          break
        case "self":
          tags.value = tags.value.filter((_, i) => i !== idx || isFixedTag(tags.value[i]))
          break
        case "all":
          tags.value = tags.value.filter(isFixedTag)
          break
        case "others":
          tags.value = tags.value.filter((_, i) => i === idx || isFixedTag(tags.value[i]))
          break
      }

      // 判断是否当前标签是否被清除, 如果被清除，跳转到最后一个页面
      const isCurrenClosed = !tags.value.some((item) => currentTagKey.value === item.fullPath)
      if (isCurrenClosed) {
        toLastViewOrHome(router)
      }
    }

    // 递归查找第一个可用菜单
    const findFirstChildMenu = (routes: RouteConfig[]) => {
      let firstRoute = routes[0]
      if (firstRoute.children?.length) {
        firstRoute = findFirstChildMenu(firstRoute.children || [])
      }
      return firstRoute
    }

    // 设置第一个页签为固定页签
    function setFixFirstTag(menusOrClose: RouteConfig[] | false) {
      if (menusOrClose !== false) {
        fixedTag.value = findFirstChildMenu(menusOrClose)
        fixedTag.value!.fullPath = fixedTag.value!.path
        if (!tags.value.some((item) => item.fullPath === fixedTag.value!.fullPath)) {
          tags.value.unshift(fixedTag.value!)
        }
      } else {
        if (fixedTag.value) {
          tags.value = tags.value.filter((item) => item.fullPath !== fixedTag.value!.fullPath)
          fixedTag.value = null
        }
      }
    }

    // 跳转到最后一个标签
    function toLastViewOrHome(router: VueRouter) {
      const latestView = tags.value.slice(-1)[0]
      if (latestView) {
        router.push(latestView.fullPath)
      } else {
        router.push("/")
      }
    }

    // 判断是否为fixedTag
    function isFixedTag(tag: TagView) {
      return fixedTag.value && tag.fullPath === fixedTag.value.fullPath
    }

    // 判断是否为第一个
    function isFirstTag(tag: TagView) {
      const firstTagIdx = fixedTag.value ? 1 : 0
      return tags.value.some((item, idx) => {
        return item === tag && idx <= firstTagIdx
      })
    }

    // 判断是否为最后一个
    function isLastTag(tag: TagView) {
      const last = tags.value[tags.value.length - 1]
      return tag === last
    }

    // 关闭当前标签并返回来时的页面
    function closeCurrentAndBackFrom(router: VueRouter) {
      tags.value = tags.value.filter((item) => item !== currentTag.value)
      router.replace({
        path: currentTag.value?.fromPath
      })
    }

    function resetTagsInfo() {
      tags.value = []
      currentTag.value = null as any
      fixedTag.value = null
    }

    return {
      tags,
      fixedTag,
      currentTag,
      currentTagKey,
      onChangeRoute,
      closeTags,
      setFixFirstTag,
      isFixedTag,
      isFirstTag,
      isLastTag,
      refreshTag,
      resetTagsInfo,
      closeCurrentAndBackFrom
    }
  },
  {
    persist: true // 持久化存储
  }
)

// 便捷获取不带 setup 的 tagsStore 实例
export const useTagsStoreOut = () => {
  return useTagsStore(store)
}
