import type { MaybeRefOrGetter } from "@vueuse/core"
import { isFunction } from "lodash-es"
import type { Ref } from "vue"

interface UseQueryOptions<Params, Data, TransRes> {
  /**
   * 函数的请求参数
   * 可以是响应式的值，在传递给请求方法时会自动解包
   * 如果传入响应式的值，则可以使用watchParams来监听参数的变化自动执行query
   */
  params: MaybeRefOrGetter<Params>
  /**
   * 是否在每次请求前将data的值重置为defaultData
   * @default false
   */
  resetBeforeQuery?: boolean
  /**
   * 初始的loading状态，在immediate为false的时候使用
   */
  initialLoading?: boolean
  /**
   * 立即调用query函数执行
   *
   * 当设置为false时，需要手动调用query函数
   *
   * @default true
   */
  immediate?: boolean
  /**
   * 当params是响应式的值时，可以设置此值
   * 是否根据params的变化自动执行query
   *
   * @default false
   */
  watchParams?: boolean
  /**
   * 监听params时的防抖时间
   * watchParams开启时才生效
   * @default 300
   */
  watchDebounce?: number
  /**
   * 转换数据，返回需要的数据,返回值可以在结果中使用transformedData接收
   * @param {Data} data
   */
  transformData?: (data: Data) => TransRes
  /**
   * query查询之前触发，返回false则取消执行query
   */
  beforeQuery?: (data: Params) => boolean | void
  // 请求成功后的回调
  onSuccess?: (data: Data) => void
  // 请求失败后的回调
  onFailure?: (error: unknown) => void
}

export const useQuery = <Data, Params, TransRes, DefaultData extends Data | undefined = undefined>(
  fn: (params: Params) => Promise<Data>,
  // 未请求到数据时的默认值
  defaultData: DefaultData,
  options: UseQueryOptions<Params, Data, TransRes>
) => {
  const {
    params,
    immediate = true,
    onSuccess,
    onFailure,
    resetBeforeQuery = false,
    watchParams = false,
    watchDebounce = 300,
    transformData,
    initialLoading = false,
    beforeQuery
  } = options

  // 转换后的数据
  const transformedData = ref<TransRes>()
  // 返回的数据
  const data = ref(defaultData) as DefaultData extends undefined ? Ref<Data | undefined> : Ref<Data>
  // 是否正在请求
  const loading = ref<boolean>(initialLoading)
  // 判断是否请求成功
  const isSuccess = ref<boolean>(false)
  // 错误信息
  const error = shallowRef<unknown | undefined>(undefined)

  function query(): Promise<Data> {
    return new Promise((resolve, reject) => {
      if (resetBeforeQuery) {
        data.value = defaultData
      }

      if (isFunction(beforeQuery) && beforeQuery(toValue(params)) === false) {
        console.log("beforeQuery return false")
        return
      }

      loading.value = true
      isSuccess.value = false
      error.value = undefined

      fn(toValue(params))
        .then((result) => {
          data.value = result as any
          if (transformData) {
            transformedData.value = transformData(result)
          }
          isSuccess.value = true
          onSuccess && onSuccess(result)
          resolve(result)
        })
        .catch((requestError) => {
          error.value = requestError
          console.log("query失败！！")
          onFailure && onFailure(requestError)
          reject(requestError)
        })
        .finally(() => {
          loading.value = false
        })
    })
  }

  /**
   * watchParams为true时，监听params的变化自动执行query
   * 如果params不是响应式的值，则不会执行watch并给出警告
   */
  ;(() => {
    if (!watchParams) {
      return
    }
    // 如果params不是响应式的值，则不会执行watch并给出警告
    if (!isProxy(params) && !isRef(params) && !isFunction(params)) {
      return console.warn(
        "[hooks:useQuery] params is not a proxy value or a getter function, watchParams will not work"
      )
    }
    // 防抖搜索
    // @ts-ignore
    watchDebounced(() => toValue(params), query, {
      debounce: watchDebounce,
      deep: true
    })
  })()

  immediate && query()

  return {
    data,
    transformedData,
    query,
    loading,
    isSuccess,
    error
  }
}
