import { useQuery } from "./useQuery"
import { PAGE_ENUM } from "@/config/page"
import type { MaybeRefOrGetter } from "@vueuse/core"
import type { Ref } from "vue"

type PageResult<T> = {
  [PAGE_ENUM.TOTAL]: number
  [PAGE_ENUM.DATALIST]: T[]
  [key: string]: any
}

/**
 * 导出时的pagination信息转换字段
 */
enum EXPORT_PAGE_INFO {
  pageNum = "current",
  pageSize = "pageSize",
  total = "total"
}

type ListApi<T> = (params: any) => Promise<PageResult<T>>

type ConfigProps<T> = {
  /**
   * 立即执行搜索
   * @default true
   */
  immediate?: boolean
  /**
   * 除了pageNum和pageSize之外的参数
   */
  extraParams?: MaybeRefOrGetter<Record<string, any>>
  /**
   * 对列表数据进行转换
   */
  transformList?: (list: T[]) => any[]
  /**
   * reset方法执行时触发，用于重置pagination信息之外的信息
   */
  onReset?: () => void
  /**
   * 请求成功后的回调
   */
  onSuccess?: (data: PageResult<T>) => void
  /**
   * 请求失败后的回调
   */
  onFailure?: (error: unknown) => void
  /**
   * 默认的pageSize
   */
  defaultPageSize?: number
  /**
   * 在queryList之前执行，如果返回false则不执行queryList
   * 参数为查询参数
   */
  beforeQuery?: (params: Record<string, any>) => boolean | void
}

export function usePageList<T>(queryApi: ListApi<T>, config?: ConfigProps<T>) {
  const {
    defaultPageSize = 10,
    extraParams,
    immediate = true,
    transformList,
    onSuccess,
    onFailure,
    onReset,
    beforeQuery
  } = config || {}

  const pageNumFix = 1 - PAGE_ENUM.START_PAGENUM

  const pageNum = ref(1)
  const pageSize = ref(defaultPageSize)
  const total = ref(0)

  // 列表数据
  const list: Ref<T[]> = ref([])

  const {
    data,
    query: queryList,
    loading,
    isSuccess,
    error
  } = useQuery(queryApi, undefined, {
    params: computed(() => {
      return {
        ...unref(extraParams),
        [PAGE_ENUM.PAGE_NUM]: pageNum.value - pageNumFix,
        [PAGE_ENUM.PAGE_SIZE]: pageSize.value
      }
    }),
    immediate: false,
    onSuccess(res) {
      total.value = res[PAGE_ENUM.TOTAL]
      list.value = transformList ? transformList(res[PAGE_ENUM.DATALIST]) : res[PAGE_ENUM.DATALIST]
      onSuccess && onSuccess(res)
    },
    onFailure(e) {
      console.error(e)
      onFailure && onFailure(e)
    },
    beforeQuery
  })

  /**
   * 一般用于搜索条件修改时清空分页信息等
   *
   * 清除分页信息以及列表数据
   * 并且触发onReset回调
   */
  function reset() {
    onReset && onReset()
    pageNum.value = 1
    // pageSize.value = 10
    // total.value = 0
    // list.value = []
    // todo 暂时添加queryList 后续是否需要reset时query根据情况添加参数判断
    queryList().then((r) => r)
  }

  watch(pageNum, () => {
    queryList().then((r) => r)
  })

  watch(pageSize, () => {
    pageNum.value = 1
    queryList().then((r) => r)
  })

  // 如果是立即执行，就执行一次
  immediate && queryList()

  function setPageNum(page: number) {
    pageNum.value = page
  }

  function setPageSize(size: number) {
    pageSize.value = size
  }

  return {
    data,
    loading,
    list,
    queryList,
    reset,
    isSuccess,
    error,
    setPageNum,
    setPageSize,
    // 提供给ant-design-vue的table的change事件使用
    onPageInfoChange({ current, pageSize }: { current: number; pageSize: number }) {
      setPageNum(current)
      setPageSize(pageSize)
    },
    // 提供给commonPagination直接绑定使用
    pagination: computed(() => {
      return {
        [EXPORT_PAGE_INFO.total]: total.value,
        [EXPORT_PAGE_INFO.pageSize]: pageSize.value,
        [EXPORT_PAGE_INFO.pageNum]: pageNum.value,
        showTotal: () => {
          return `共${total.value}条`
        },
        // showTitle: true,
        showSizeChanger: true,
        showQuickJumper: true,
        size: "small",
        onChange: setPageNum,
        onShowSizeChange: setPageSize
      }
    })
  }
}
