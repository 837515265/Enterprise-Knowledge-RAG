import dictionaryCodes from "@/config/dictionary"

// 所有字典码值
export type DictCode = (typeof dictionaryCodes)[number]

// 接口返回的数据项
export type DictResponseItem = {
  createTime: string
  updateTime: string
  creator: string
  updator: string
  createName: string
  updateName: string
  id: string
  dictCode: DictCode
  code: string
  value: string
  parentDictValueCode: any
  orderBy: number
  extA: string
  extB: any
  enable: boolean
}

// 实际的字典中的项
export type DictItem  = DictResponseItem &  {
  // 字典项中文名
  label: string
  // 字典项编码值
  code: string
  // 字典编码
  dictCode: DictCode
}

// 字典码值和对应的字典列表组成的对象
export type DictMap = Record<DictCode, DictItem[]>


