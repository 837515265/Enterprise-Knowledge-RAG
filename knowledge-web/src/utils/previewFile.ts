import router from "@/router"

/**
 * 在新页面预览文件
 * @param id 文件id
 * @param openType "modal" | "page" 弹窗或者页面, 默认为打开新页面
 */
export function previewFile(id: string, openType: "page" | "modal" = "page") {
  if (openType === "modal") {
    return eventBus.emit(EVENTBUS_OPEN_FILE_PREVIEW_MODAL, id)
  }
  if (!router) {
    throw new Error("【goPreviewPage Error】无router实例")
  }
  const target = router.resolve({
    path: `/file-preview/${id}`
  })
  window.open(target.href)
}
