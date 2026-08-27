import { get, isArray } from "lodash-es"

interface PropsType {
  // 字典编码
  dictCode?: string
  // 请求地址
  url?: string
  // 下拉选项
  options?: Recordable[]
  // 展示文字对应的字段, 字典模式默认为value url或options模式默认为label
  labelField?: string
  // 获取的值对应字段，字典模式默认为code， url或options模式默认为value
  valueField?: string
  // 传入url时的请求参数
  params?: Recordable
  // 请求方式
  method?: string
  // 展示结果对应字段， 仅在传入url时生效
  resultField?: string
  // 绑定值
  value?: any
  // 绑定值
  modelValue?: any
}

// todo 接口请求没处理 可以暴露出手动请求api
export function useSelectOptions(props: PropsType) {
  const rawOptions = ref<any[]>([])

  const labelField = props.labelField || (props.dictCode ? "value" : "label")
  const valueField = props.valueField || (props.dictCode ? "code" : "value")

  // 获取options
  if (props.dictCode) {
    const res = useDict(props.dictCode as any)
    rawOptions.value = res.list || []
  } else if (props.url) {
    request(props.url, props.params, {
      method: props.method
    }).then((res) => {
      if (props.resultField) {
        rawOptions.value = get(res, props.resultField) || []
      } else {
        rawOptions.value = Array.isArray(res?.datas) ? res.datas : []
      }
      if (!isArray(rawOptions.value)) {
        throw new Error("获取到的options不是一个数组，请检查接口以及其他配置")
      }
    })
  } else if (props.options) {
    rawOptions.value = props.options
  } else {
    throw new Error("必须传入【options】/【url】/【dictCode】属性中的一个")
  }

  return {
    options: computed<{ value: any; label: string; disabled?: boolean; [key: string]: any }[]>(() => {
      return rawOptions.value.map((item) => {
        const value = valueField ? item[valueField] : item.value || ""
        return {
          ...item,
          label: labelField ? item[labelField] : item.label || "",
          value: value,
          key: item.key || value
        }
      })
    })
  }
}
