<template>
  <a-modal v-model="visible" width="60%" centered :footer="null" maskClosable v-bind="$attrs" @close="close">
    <template #title>
      <div class="flex w-full items-center justify-between pr-[50px]">
        <div>{{ fileRef?.fileName || "文件预览" }}</div>
        <a-button type="primary" :loading="loading" icon="download" @click="downloadFile">下载文件</a-button>
      </div>
    </template>
    <div class="h-[80vh] w-full">
      <file-preview v-if="fileId && visible" ref="fileRef" hideDownloadButton :fileId="fileId"></file-preview>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
const fileRef = ref()

const loading = ref(false)
const visible = ref(false)
const fileId = ref("")

function show(id: string) {
  fileId.value = id
  visible.value = true
}

function close() {
  visible.value = false
  fileId.value = ""
}

function downloadFile() {
  loading.value = true
  fileRef.value.downloadReport().finally(() => {
    loading.value = false
  })
}

defineExpose({
  show,
  close
})
</script>

<style scoped lang="less">
::v-deep .ant-modal-body {
  padding: 0 !important;
}

::v-deep .ant-modal-header {
  padding: 9px 12px !important;
}
</style>
