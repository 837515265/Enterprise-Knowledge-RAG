import { useTagsStoreOut } from "@/store/modules/tags"
import { useLayoutStoreOut } from "@/store/modules/layout"
import router from "@/router"

/**
 * 返回打开该页面时的路由，仅在页签开启时生效
 */
function goBackOpener() {
  if (!router) {
    throw new Error("goBackOpener Error】无router实例")
  }
  const layoutStore = useLayoutStoreOut()
  if (layoutStore.openTag) {
    const tagStore = useTagsStoreOut()
    tagStore.closeCurrentAndBackFrom(router)
  } else {
    router.back()
  }
}

export const $page = {
  goBackOpener
}
