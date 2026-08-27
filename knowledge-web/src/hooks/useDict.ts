import { useDictStoreOut } from "@/store/modules/dict"
import { DictCode } from "#/model/dict"

/**
 * 根据传入的dictCode 获取dictCode对应的简易方法
 * @param dictCode
 * @returns
 */
export function useDict(dictCode: DictCode) {
  const dictStore = useDictStoreOut()

  const instance = reactive({
    list: dictStore.dictMap[dictCode] || [],
    getItemByCode(code: string) {
      return dictStore.getItemByDictCodeAndCode(dictCode, code)
    },
    getItemByLabel(code: string) {
      return dictStore.getItemByDictCodeAndLabel(dictCode, code)
    },
    getCode(code: string) {
      return dictStore.getCode(dictCode, code)
    },
    getLabel(code: string) {
      return dictStore.getLabel(dictCode, code)
    }
  })

  watch(
    () => dictStore.dictMap,
    () => {
      // 不改变引用，只替换内容
      instance.list.splice(0, instance.list.length, ...(dictStore.dictMap[dictCode] || []))
    },
    {
      deep: false
    }
  )

  return instance
}
