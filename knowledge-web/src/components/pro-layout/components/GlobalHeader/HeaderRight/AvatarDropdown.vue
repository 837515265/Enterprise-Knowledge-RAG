<template>
  <div>
    <a-dropdown v-if="userInfo && displayName" placement="bottomRight">
      <span class="ant-pro-account-avatar mr-[8px]">
        <a-avatar size="small" :src="displayAvatar" class="antd-pro-global-header-index-avatar !mr-[7px]">
          <a-icon v-if="!displayAvatar" slot="icon" type="user" class="!text-white"></a-icon>
        </a-avatar>
        <span>{{ displayName }}</span>
      </span>
      <template v-slot:overlay>
        <a-menu class="ant-pro-drop-down menu" :selected-keys="[]">
          <a-menu-item key="password" @click="handleChangePassword">
            <a-icon type="unlock" />
            修改密码
          </a-menu-item>
          <a-menu-divider v-if="menu" />
          <a-menu-item key="logout" @click="handleLogout">
            <a-icon type="logout" />
            退出登陆
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
    <span v-else>
      <a-spin size="small" :style="{ marginLeft: 8, marginRight: 8 }" />
    </span>
    <ChangePasswordModal ref="changePasswordModal" />
  </div>
</template>

<script>
import { useUserStore } from "@/store/modules/user"
import { mapActions, mapState } from "pinia"

export default {
  name: "AvatarDropdown",
  props: {
    menu: {
      type: Boolean,
      default: true
    }
  },
  data() {
    return {
      changePasswordModalRef: null
    }
  },
  computed: {
    ...mapState(useUserStore, ["userInfo", "avatar"]),
    displayName() {
      return this.userInfo?.realName || this.userInfo?.name || ""
    },
    displayAvatar() {
      return this.avatar || this.userInfo?.avatar || this.userInfo?.headImgUrl
    }
  },
  methods: {
    ...mapActions(useUserStore, ["logoutAction"]),
    handleChangePassword() {
      if (this.$refs.changePasswordModal) {
        this.$refs.changePasswordModal.show(this.userInfo?.code || this.userInfo?.username || this.userInfo?.name || "")
      }
    },
    handleLogout() {
      Modal.confirm({
        title: "确认退出",
        content: "确认要退出登录吗？",
        onOk: async () => {
          console.log(this.logoutAction)
          await this.logoutAction()
        }
      })
    }
  }
}
</script>

<style lang="less" scoped>
.ant-pro-drop-down {
  ::v-deep(.action) {
    margin-right: 8px;
  }

  ::v-deep(.ant-dropdown-menu-item) {
    display: flex;
    align-items: center;
  }

  ::v-deep(.ant-dropdown-menu-item) {
    min-width: 160px;
  }
}
</style>
