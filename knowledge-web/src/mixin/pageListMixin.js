import { PAGE_ENUM } from "@/config/page"

/**
 * 分页列表混入 (PageListMixin)
 *
 * 这是一个通用的分页列表混入，提供了完整的分页查询功能，包括：
 * - 分页数据管理（页码、页大小、总数、列表数据）
 * - 加载状态和错误处理
 * - 自动查询和手动查询
 * - 分页器配置
 * - 各种生命周期钩子
 *
 * 使用方式：
 * 1. 在组件中引入此混入
 * 2. 实现必需的 getListApi 方法
 * 3. 可选实现其他钩子方法来自定义行为
 */
export default {
  data() {
    return {
      // 组件可选实现：是否立即查询
      immediateQuery: true,
      // 当前页码
      pageNum: 1,
      // 每页显示条数
      pageSize: 10,
      // 总记录数
      total: 0,
      // 列表数据
      list: [],
      // 加载状态
      loading: false,
      // 错误信息
      error: null,
      // 查询是否成功
      isSuccess: false
    }
  },
  computed: {
    /**
     * 分页器配置对象
     * 用于 ant-design-vue 的 Pagination 组件
     */
    pagination() {
      return {
        total: this.total,
        pageSize: this.pageSize,
        current: this.pageNum,
        showTotal: () => `共${this.total}条`,
        showSizeChanger: true,
        showQuickJumper: true,
        size: "small",
        onChange: this.setPageNum,
        onShowSizeChange: this.setPageSize
      }
    }
  },
  watch: {
    /**
     * 监听页码变化，自动触发查询
     */
    pageNum() {
      this.queryList()
    },
    /**
     * 监听页大小变化，重置到第一页并查询
     */
    pageSize() {
      this.pageNum = 1
      this.queryList()
    }
  },
  created() {
    /**
     * 组件创建时，如果 immediateQuery 不为 false，则立即执行查询
     */
    if (this.immediateQuery !== false) {
      this.queryList()
    }
  },
  methods: {
    /**
     * 获取列表数据的API方法
     *
     * @description 组件必须实现此方法，返回一个Promise
     * @param {Object} params - 查询参数，包含分页信息
     * @returns {Promise} 返回API调用的Promise
     * @throws {Error} 如果组件未实现此方法
     *
     * @example
     * getListApi(params) {
     *   return this.$api.getUserList(params)
     * }
     */
    getListApi(params) {
      console.log("getListApi", params)
      throw new Error("请在组件中实现 getListApi 方法，返回 Promise")
    },

    /**
     * 获取额外的查询参数
     *
     * @description 组件可选实现，用于添加除分页外的其他查询条件
     * @returns {Object} 额外的查询参数
     *
     * @example
     * getExtraParams() {
     *   return {
     *     status: this.status,
     *     keyword: this.keyword
     *   }
     * }
     */
    getExtraParams() {
      return {}
    },

    /**
     * 列表数据转换
     *
     * @description 组件可选实现，用于在设置列表数据前进行转换处理
     * @param {Array} list - 原始列表数据
     * @returns {Array} 转换后的列表数据
     *
     * @example
     * transformList(list) {
     *   return list.map(item => ({
     *     ...item,
     *     statusText: this.getStatusText(item.status)
     *   }))
     * }
     */
    transformList(list) {
      return list
    },

    /**
     * 查询前钩子
     *
     * @description 组件可选实现，在查询执行前调用
     * @param {Object} params - 即将发送的查询参数
     * @returns {boolean|undefined} 返回 false 可阻止查询执行
     *
     * @example
     * beforeQuery(params) {
     *   if (!this.keyword) {
     *     this.$message.warning('请输入关键词')
     *     return false
     *   }
     * }
     */
    beforeQuery(params) {
      // return false 可阻止查询
      console.log("beforeQuery", params)
    },

    /**
     * 查询成功回调
     *
     * @description 组件可选实现，在查询成功后调用
     * @param {Object} res - API返回的完整响应数据
     *
     * @example
     * onListSuccess(res) {
     *   this.$message.success('查询成功')
     *   console.log('查询结果:', res)
     * }
     */
    onListSuccess(res) {
      console.log("onListSuccess", res)
      // 组件可选实现
    },

    /**
     * 查询失败回调
     *
     * @description 组件可选实现，在查询失败后调用
     * @param {Error} e - 错误对象
     *
     * @example
     * onListFailure(e) {
     *   this.$message.error('查询失败：' + e.message)
     * }
     */
    onListFailure(e) {
      // 组件可选实现
      console.log("onListFailure", e)
    },

    /**
     * 重置回调
     *
     * @description 组件可选实现，在重置操作时调用
     *
     * @example
     * onListReset() {
     *   this.keyword = ''
     *   this.status = ''
     * }
     */
    onListReset() {
      // 组件可选实现
    },

    /**
     * 执行列表查询
     *
     * @description 核心查询方法，自动处理加载状态、错误处理和数据处理
     */
    async queryList() {
      // 构建查询参数
      const params = {
        ...this.getExtraParams(),
        [PAGE_ENUM.PAGE_NUM]: this.pageNum,
        [PAGE_ENUM.PAGE_SIZE]: this.pageSize
      }

      // 执行查询前钩子
      if (this.beforeQuery && this.beforeQuery(params) === false) {
        return
      }

      // 设置加载状态
      this.loading = true
      this.error = null

      try {
        // 调用API获取数据
        const res = await this.getListApi(params)

        // 更新数据
        this.total = res[PAGE_ENUM.TOTAL]
        this.list = this.transformList ? this.transformList(res[PAGE_ENUM.DATALIST]) : res[PAGE_ENUM.DATALIST]
        this.isSuccess = true

        // 执行成功回调
        this.onListSuccess && this.onListSuccess(res)
      } catch (e) {
        // 处理错误
        this.error = e
        this.isSuccess = false
        this.onListFailure && this.onListFailure(e)
        console.log(`查询报错！错误：${e.message}`)
      } finally {
        // 清除加载状态
        this.loading = false
      }
    },

    /**
     * 重置列表
     *
     * @description 重置到第一页并重新查询
     */
    reset() {
      this.onListReset && this.onListReset()
      this.pageNum = 1
      this.queryList()
    },

    /**
     * 设置页码
     *
     * @param {number} page - 页码
     */
    setPageNum(page) {
      this.pageNum = page
    },

    /**
     * 设置页大小
     *
     * @param {number} size - 页大小
     */
    setPageSize(size) {
      this.pageSize = size
    },

    /**
     * 适配 ant-design-vue 的 table change 事件
     *
     * @description 用于 a-table 组件的 @change 事件
     * @param {Object} pagination - 分页信息
     * @param {number} pagination.current - 当前页码
     * @param {number} pagination.pageSize - 页大小
     *
     * @example
     * <a-table @change="onPageInfoChange" />
     */
    onPageInfoChange({ current, pageSize }) {
      this.setPageNum(current)
      this.setPageSize(pageSize)
    }
  }
}
