<template>
  <div v-loading="loading" class="c-list-wrapper flex size-full flex-col overflow-hidden bg-white p-[14px] pb-[8px]">
    <div class="table-page-search-wrapper flex-none">
      <slot name="header"></slot>
    </div>

    <slot name="headerBefore"></slot>
    <div ref="tableWrapperRef" class="mt-4 min-h-0 flex-1">
      <template v-if="isValidSlot || !isDev">
        <slot name="table" :tableHeight="height - 110"></slot>
      </template>
      <!-- 错误提示 -->
      <template v-else>
        <div class="flex h-full items-center justify-center">
          <div class="max-w-lg rounded-lg border border-red-200 bg-red-50 p-8 text-center">
            <div class="mb-4 flex items-center justify-center">
              <i class="anticon anticon-warning text-xl text-red-500"></i>
            </div>
            <div class="mb-2 font-medium text-red-500">
              <span
                class="cursor-pointer underline hover:text-red-600"
                @click="openFileInEditor('src/components/list-wrapper/index.vue', 19, 0)"
                >【list-wrapper】</span
              >
              插槽使用错误
            </div>
            <div class="text-red-600/70">
              table 插槽中只允许放置一个子元素，如需放置多余元素请使用 【header】、 【headerBefore】 或【default】 插槽
            </div>
          </div>
        </div>
      </template>
    </div>
    <slot></slot>
  </div>
</template>

<script lang="ts" setup>
import { openFileInEditor } from "@/utils/logic/openFileInEditor"

defineProps<{
  loading?: boolean
}>()

const isDev = import.meta.env.DEV
const slots = useSlots()

const tableWrapperRef = ref<HTMLElement | null>(null)

// 动态获取ld-list-wrapper的高度, 想歪暴露方法提供给a-table组件, 以支持table组件内部滚动
const { height } = useElementSize(tableWrapperRef)

// 检查 table 插槽内容是否有效
const isValidSlot = computed(() => {
  const tableSlot = slots.table?.()
  return !tableSlot || tableSlot.length <= 1
})
</script>

<style lang="less" scoped></style>
