<template>
  <a-checkbox-group v-model="currentValue" v-bind="$attrs" :options="options" v-on="$listeners" />
</template>

<script setup lang="ts">
import { useModelValue } from "@/hooks/useModelValue"

const props = withDefaults(
  defineProps<{
    // 字典编码
    dictCode?: string
    // 请求地址
    url?: string
    // 下拉选项
    options?: Recordable[]
    // 展示文字对应的字段
    labelField?: string
    // 获取的值对应字段
    valueField?: string
    // 传入url时的请求参数
    params?: Recordable
    // 请求方式
    method?: string
    // 展示结果对应字段， 仅在传入url时生效
    resultField?: string
    // 绑定值
    value?: any
  }>(),
  {
    dictCode: undefined,
    url: undefined,
    options: undefined,
    labelField: undefined,
    valueField: undefined,
    params: undefined,
    resultField: undefined,
    method: "get",
    value: undefined
  }
)

const emit = defineEmits(["input"])

const currentValue = useModelValue(props, emit)

const { options } = useSelectOptions(props)
</script>

<script lang="ts">
export default {}
</script>

<style scoped lang="less"></style>
