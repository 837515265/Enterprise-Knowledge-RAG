<template>
  <div :class="wrpCls">
    <AvatarDropdown :menu="showMenu" :current-user="currentUser" :class="prefixCls" />
  </div>
</template>

<script>
import AvatarDropdown from "./AvatarDropdown.vue"
import { useUserStore } from "@/store/modules/user"
import { mapState } from "pinia"

export default {
  name: "RightContent",
  components: {
    AvatarDropdown
  },
  props: {
    prefixCls: {
      type: String,
      default: "ant-pro-global-header-index-action"
    },
    isMobile: {
      type: Boolean,
      default: () => false
    },
    topMenu: {
      type: Boolean,
      required: true
    },
    theme: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      showMenu: true
    }
  },
  computed: {
    ...mapState(useUserStore, ["userInfo"]),
    currentUser() {
      return this.userInfo || {}
    },
    wrpCls() {
      return {
        "ant-pro-global-header-index-right": true,
        [`ant-pro-global-header-index-${this.isMobile || !this.topMenu ? "light" : this.theme}`]: true
      }
    }
  }
}
</script>
