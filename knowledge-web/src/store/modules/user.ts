// 用户信息相关类型
import { UserInfo } from "#/model/user"
import { defineStore } from "pinia"
import { getInfo, getTokenByCode } from "@/api/common-user.js"
import store from "@/store"
import { goToLoginToRemoveAuth } from "@/utils/auth/goToLogin"
import { useMenuStoreOut } from "./menu"
import { useTagsStoreOut } from "./tags"

export const useUserStore = defineStore(
  "user",
  () => {
    /**
     * ========================
     * 代替State：状态数据
     * ========================
     */
    // 用户信息
    const userInfo = ref<UserInfo | null>(null)
    // token, 每次修改token会自动存储到本地存储里
    const token = useStorage("storage-access-token", "")

    // 菜单数据
    const menus = ref([])

    /**
     * ========================
     * 代替Getters：计算属性
     * ========================
     */
    // 用户姓名
    const name = computed(() => userInfo.value?.realName || "")
    // 用户头像
    const avatar = computed(() => userInfo.value?.avatar || userInfo.value?.headImgUrl || "")
    // 角色列表
    const roles = computed(() => userInfo.value?.roles || [])
    // 手机号
    const mobile = computed(() => userInfo.value?.mobile || "")
    // 部门名称
    const deptName = computed(() => userInfo.value?.dept?.deptName || "")
    // 部门ID
    const deptId = computed(() => userInfo.value?.dept?.deptId || "")
    // 权限列表
    const permissions = computed(() => userInfo.value?.permissions || [])

    /**
     * ==============================
     * 代替Actions/Mutations：方法/动作
     * ==============================
     */

    // 通过 code 获取 token
    async function getTokenAction(codeInfo: any) {
      try {
        const response = await getTokenByCode(codeInfo)
        if (response && response.resp_code === 0) {
          const result = response.datas || {}
          token.value = result.access_token
        } else {
          throw response
        }
      } catch (error) {
        console.log(error)
        logoutAction()
      }
    }

    // 获取用户信息
    async function getInfoAction() {
      const response = await getInfo()
      userInfo.value = normalizeCurrentUserInfo(response.datas as UserInfo)
      return userInfo.value
    }

    /**
     * 归一化当前用户信息。
     * 用户中心 current 接口返回的 id/userId 可能为空，前端统一补成 sysUserId，避免各业务页面重复处理。
     */
    function normalizeCurrentUserInfo(info: UserInfo) {
      if (!info) return info
      if (info.sysUserId) {
        info.id = info.id || info.sysUserId
        info.userId = info.userId || info.sysUserId
      }
      return info
    }

    function resetUserInfo() {
      userInfo.value = null
      menus.value = []
      token.value = ""
    }

    // 退出登录
    async function logoutAction() {
      const menuStore = useMenuStoreOut()
      const tagsStore = useTagsStoreOut()
      const oldToken = token.value

      menuStore.resetMenuInfo()
      tagsStore.resetTagsInfo()
      resetUserInfo()
      goToLoginToRemoveAuth(oldToken)
    }

    return {
      // state
      userInfo,
      token,
      menus,
      // computed
      name,
      avatar,
      roles,
      permissions,
      mobile,
      deptName,
      deptId,
      // actions
      getTokenAction,
      getInfoAction,
      logoutAction,
      resetUserInfo
    }
  },
  {
    // true-开启数据持久化
    // persist: import.meta.env.VITE_CACHE_USERINFO
    persist: false
  }
)

// 便捷获取不带 setup 的 userStore 实例
export const useUserStoreWithOut = () => {
  return useUserStore(store)
}
