import mitt from "mitt"

// 事件总线，用于不同组件间通信
export const eventBus = mitt()

// 所有事件常量key
// 打开预览弹窗事件
export const EVENTBUS_OPEN_FILE_PREVIEW_MODAL = "EVENTBUS_OPEN_FILE_PREVIEW_MODAL"
