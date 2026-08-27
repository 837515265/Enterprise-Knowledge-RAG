import "./index.less"

import "ant-design-vue/es/drawer/style"
import Drawer from "ant-design-vue/es/drawer"
import SiderMenuMain, { SiderMenuProps } from "./SiderMenuMain"

const Index = {
  name: "SiderMenuWrapper",
  model: {
    prop: "collapsed",
    event: "collapse"
  },
  props: SiderMenuProps,
  render() {
    const { layout, isMobile, collapsed } = this
    const isTopMenu = layout === "topmenu"
    const handleCollapse = () => {
      this.$emit("collapse", true)
    }
    return isMobile ? (
      <Drawer
        class="ant-pro-sider-menu"
        visible={!collapsed}
        placement="left"
        maskClosable
        getContainer={null}
        onClose={handleCollapse}
        bodyStyle={{
          padding: 0,
          height: "100vh"
        }}
      >
        <SiderMenuMain {...{ props: { ...this.$props, collapsed: isMobile ? false : collapsed } }} />
      </Drawer>
    ) : (
      !isTopMenu && <SiderMenuMain class="ant-pro-sider-menu" {...{ props: this.$props }} />
    )
  }
}

Index.install = function (Vue) {
  Vue.component(Index.name, Index)
}

export { SiderMenuMain, SiderMenuProps }

export default Index
