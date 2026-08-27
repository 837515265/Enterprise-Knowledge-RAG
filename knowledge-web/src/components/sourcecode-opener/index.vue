<template>
  <div
    v-if="isDev"
    class="flex items-center rounded border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
  >
    <div class="mr-[100px] flex min-w-0 items-center gap-2">
      <svg class="size-4 text-yellow-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M21 12A9 9 0 11 3 12a9 9 0 0118 0z" />
      </svg>
      <span>代码位置：</span>
      <span class="select-all truncate font-mono text-xs text-gray-700">{{ sourceCodeUrl }}</span>
    </div>
    <a-button type="primary" size="small" icon="edit" @click.prevent="openSourceCode"> 在编辑器中打开 </a-button>
  </div>
</template>

<script setup lang="ts">
import { openFileInEditor } from "@/utils/logic/openFileInEditor"

const props = withDefaults(
  defineProps<{
    // 不要以/开头
    sourceCodeUrl: string
    row?: number
    col?: number
  }>(),
  {
    row: 1,
    col: 1
  }
)

const isDev = import.meta.env.DEV

function openSourceCode() {
  openFileInEditor(props.sourceCodeUrl, props.row, props.col)
}
</script>

<style scoped lang="less"></style>
