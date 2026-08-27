import "./Header.less"

import "ant-design-vue/es/layout/style"
import Layout from "ant-design-vue/es/layout"

import PropTypes from "ant-design-vue/es/_util/vue-types"
import BaseMenu from "./components/RouteMenu/BaseMenu"
import { defaultRenderLogoAntTitle, SiderMenuProps } from "./components/SiderMenu/SiderMenuMain"
import GlobalHeader, { GlobalHeaderProps } from "./components/GlobalHeader"
import { VueFragment } from "./components"
import { isFun } from "./utils/util"
import TagsView from "@/components/tags-view/index.vue"

const { Header } = Layout

export const HeaderViewProps = {
  ...GlobalHeaderProps,
  ...SiderMenuProps,
  isMobile: PropTypes.bool.def(false),
  collapsed: PropTypes.bool,
  logo: PropTypes.any,
  showTabs: PropTypes.bool.def(false),
  hasSiderMenu: PropTypes.bool,
  autoHideHeader: PropTypes.bool,
  menuRender: PropTypes.any,
  headerRender: PropTypes.any,
  rightContentRender: PropTypes.any,
  fixedFirstRouteOnTags: PropTypes.any,
  visible: PropTypes.bool.def(true)
}

const renderContent = (h, props) => {
  const isTop = props.layout === "topmenu"
  const maxWidth = 1200 - 280 - 120
  const contentWidth = props.contentWidth === "Fixed"
  const baseCls = "ant-pro-top-nav-header"
  const { logo, title, theme, isMobile, headerRender, rightContentRender, menuRender, menuHeaderRender } = props
  const rightContentProps = { theme, isTop, isMobile }
  let defaultDom = <GlobalHeader {...{ props: props }} />
  if (isTop && !isMobile) {
    defaultDom = (
      <div class={[baseCls, theme]}>
        <div class={[`${baseCls}-main`, contentWidth ? "wide" : ""]}>
          {menuHeaderRender && (
            <div class={`${baseCls}-left`}>
              <div class={`${baseCls}-logo`} key="logo" id="logo">
                {defaultRenderLogoAntTitle(h, { logo, title, menuHeaderRender })}
              </div>
            </div>
          )}
          <div class={`${baseCls}-menu`} style={{ maxWidth: `${maxWidth}px`, flex: 1 }}>
            {(menuRender && ((isFun(menuRender) && menuRender(h, props)) || menuRender)) || (
              <BaseMenu {...{ props: props }} />
            )}
          </div>
          {(isFun(rightContentRender) && rightContentRender(h, rightContentProps)) || rightContentRender}
        </div>
      </div>
    )
  }
  if (headerRender) {
    return headerRender(h, props)
  }
  return defaultDom
}

const HeaderView = {
  name: "HeaderView",
  props: HeaderViewProps,
  render(h) {
    const {
      menus,
      visible,
      isMobile,
      layout,
      collapsed,
      collapsedWidth,
      siderWidth,
      fixedHeader,
      hasSiderMenu,
      showTabs,
      fixedFirstRouteOnTags,
      contentWidth
    } = this.$props
    const props = this.$props
    const isTop = layout === "topmenu"

    const needSettingWidth = fixedHeader && hasSiderMenu && !isTop && !isMobile

    const className = {
      "ant-pro-fixed-header": fixedHeader,
      "ant-pro-top-menu": isTop
    }

    const calcWidth = collapsed ? collapsedWidth || 80 : siderWidth

    const headerHeight = showTabs ? "112px" : "64px"

    const isFixedWidth = contentWidth === "Fixed"

    // 没有 <></> 暂时代替写法
    return visible ? (
      <VueFragment>
        {/* 该Header用来占位，无实际作用  */}
        {fixedHeader && <div style={{ height: headerHeight }} />}
        <Header
          style={{
            padding: 0,
            width: needSettingWidth ? `calc(100% - ${calcWidth}px)` : "100%",
            zIndex: 9,
            right: fixedHeader ? 0 : undefined,
            height: headerHeight
          }}
          class={className}
        >
          {renderContent(h, props)}
          {showTabs && (
            <TagsView menus={menus} fixedFirstRoute={fixedFirstRouteOnTags} fixedWidth={isFixedWidth}></TagsView>
          )}
        </Header>
      </VueFragment>
    ) : null
  }
}

export default HeaderView
