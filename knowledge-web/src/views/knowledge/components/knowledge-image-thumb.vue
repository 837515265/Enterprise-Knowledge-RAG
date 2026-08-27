<template>
  <div class="knowledge-image-thumb" :class="{ 'is-natural': natural }">
    <a-spin v-if="loading" size="small" />
    <img v-else-if="src" :src="src" :alt="alt || '解析图片'" />
    <div v-else class="thumb-empty"><a-icon type="file-image" /></div>
  </div>
</template>

<script setup lang="ts">
import { getFileByFileId } from "@/api/common"
import { resolveFileUrl } from "@/utils/logic/file"

const props = defineProps<{ fileId?: string | number | null; alt?: string; natural?: boolean }>()
const src = ref("")
const loading = ref(false)

async function load() {
  src.value = ""
  if (!props.fileId) return
  loading.value = true
  try {
    const res = await getFileByFileId(props.fileId)
    const path = String(res?.datas || res?.data || res?.path || res || "")
    if (path) src.value = resolveFileUrl(path, false)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

watch(() => props.fileId, load, { immediate: true })
</script>

<style scoped lang="less">
.knowledge-image-thumb {
  display: flex;
  justify-content: center;
  align-items: center;
  overflow: hidden;
  width: 100%;
  height: 100%;
  min-height: 72px;
  background: #f1f5f9;
}

img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.knowledge-image-thumb.is-natural {
  height: auto;
  min-height: 0;
}

.knowledge-image-thumb.is-natural img {
  height: auto;
}

.thumb-empty {
  font-size: 24px;
  color: #94a3b8;
}
</style>
