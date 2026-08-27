// 字典相关类型
import { getDicts } from "@/api/common"
import dictionaryCodes from "@/config/dictionary"
import { DictItem, DictResponseItem, DictCode, DictMap } from "#/model/dict"
import { defineStore } from "pinia"
import { Ref } from "vue"
import store from "@/store"

export const useDictStore = defineStore(
  "dict",
  () => {
    // 所有字典的映射，key: 字典编码dictCode  value: dictCode对应的字典列表
    const dictMap = ref({}) as Ref<DictMap>

    function requestDictionary() {
      getDicts(dictionaryCodes).then((res) => {
        const allList = res.datas as DictResponseItem[]
        dictMap.value = getListMap(allList)
      })
    }

    // 根据字典项码值 和 code 查找对应的字典项
    function getItemByDictCodeAndCode(dictCode: DictCode, code: string): DictItem | undefined {
      const list = dictMap.value[dictCode]
      const item = list?.find((item) => item.code === code)
      return item
    }

    // 根据字典项码值 和 label 查找对应的字典项
    function getItemByDictCodeAndLabel(dictCode: DictCode, label: string): DictItem | undefined {
      const list = dictMap.value[dictCode]
      const item = list?.find((item) => item.label === label)
      return item
    }

    function getLabel(dictCode: DictCode, code: string) {
      const item = getItemByDictCodeAndCode(dictCode, code)
      return item?.label
    }

    function getCode(dictCode: DictCode, label: string) {
      const item = getItemByDictCodeAndLabel(dictCode, label)
      return item?.code
    }

    return {
      dictMap,
      requestDictionary,
      getItemByDictCodeAndCode,
      getItemByDictCodeAndLabel,
      getLabel,
      getCode
    }
  },
  {
    // true-开启数据持久化
    // persist: import.meta.env.VITE_CACHE_DICTIONAYR
    persist: false
  }
)

// 便捷获取不带 setup 的 userStore 实例
export const useDictStoreOut = () => {
  return useDictStore(store)
}

// ==================工具=========================
function getListMap(list: DictResponseItem[]): DictMap {
  const result = {} as DictMap
  list.forEach((item) => {
    if (!result[item.dictCode]) {
      result[item.dictCode] = []
    }
    result[item.dictCode].push({
      ...item,
      label: item.value // 将value重命名为label
    })
  })
  return result
}
