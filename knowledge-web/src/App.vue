<template>
  <a-config-provider :locale="zhCN">
    <div id="app">
      <RouterView />
      <file-preview-modal ref="filePreviewRef" />
    </div>
  </a-config-provider>
</template>

<script setup lang="ts">
import zhCN from "ant-design-vue/es/locale/zh_CN"

const filePreviewRef = ref()

onMounted(() => {
  eventBus.on(EVENTBUS_OPEN_FILE_PREVIEW_MODAL, (id: string) => {
    filePreviewRef.value?.show(id)
  })
})

setTimeout(() => {
  const globalLoading = document.getElementById("global-loading")
  if (globalLoading) {
    globalLoading.parentNode?.removeChild(globalLoading)
  }
}, 10 * 1000)
</script>
