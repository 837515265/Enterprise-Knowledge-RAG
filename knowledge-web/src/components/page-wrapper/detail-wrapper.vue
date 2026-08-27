<template>
  <div v-loading="loading" class="c-detail-wrapper">
    <a-page-header v-if="props.showHeader" :title="props.title || route.meta?.title" @back="onClickBack">
      <template v-if="!props.hideBack" #backIcon>
        <a-icon type="arrow-left" />
      </template>
      <!--   允许外部传入extra插槽   -->
      <template #extra>
        <slot name="extra"></slot>
      </template>
    </a-page-header>
    <div class="c-detail-content">
      <slot></slot>
    </div>
  </div>
</template>

<script lang="ts" setup>
const vueInstance = getCurrentInstance()
const route = useRoute()
const router = useRouter()

const emit = defineEmits(["back"])

const props = withDefaults(
  defineProps<{
    showHeader?: boolean
    title?: string
    hideBack?: boolean
    loading?: boolean
    // 当打开顶部页签的时候，返回打开该页面的页面而非上一个页面
    backFrom?: boolean
  }>(),
  {
    title: "",
    backFrom: true
  }
)

function onClickBack() {
  // 如果没有back事件，则默认返回上个页面
  if (!vueInstance?.proxy?.$listeners.back) {
    if (props.backFrom) {
      $page.goBackOpener()
    } else {
      router.go(-1)
    }
  }
  emit("back")
}
</script>

<style lang="less" scoped>
@detail-x-padding: 16px;

.c-detail-wrapper {
  display: flex;
  overflow: hidden;
  padding-top: 16px;
  width: 100%;
  height: 100%;
  background-color: #fff;
  flex-direction: column;

  ::v-deep .ant-page-header {
    padding: 0 @detail-x-padding 14px;
    margin-bottom: 10px;
    font-size: 18px;
    border-bottom: 1px solid hsl(216deg, 14%, 93%);
  }

  .c-detail-content {
    overflow: auto;
    padding: 0 @detail-x-padding 16px;
    height: 100%;
  }
}
</style>
