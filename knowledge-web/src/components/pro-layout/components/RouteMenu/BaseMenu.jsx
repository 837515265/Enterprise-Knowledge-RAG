import PropTypes from "ant-design-vue/es/_util/vue-types"

import "ant-design-vue/es/menu/style"
import Menu from "ant-design-vue/es/menu"
import "ant-design-vue/es/icon/style"
import Icon from "ant-design-vue/es/icon"
import "./BaseMenu.less"

const { Item: MenuItem, SubMenu } = Menu

export const RouteMenuProps = {
  menus: PropTypes.array,
  theme: PropTypes.string.def("dark"),
  mode: PropTypes.string.def("inline"),
  collapsed: PropTypes.bool.def(false),
  collapsedWidth: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).def(80),
  openKeys: PropTypes.array.def(undefined),
  selectedKeys: PropTypes.array.def(undefined),
  openOnceKey: PropTypes.bool.def(true),
  i18nRender: PropTypes.oneOfType([PropTypes.func, PropTypes.bool]).def(false),
  // 手风琴模式
  accordion: PropTypes.bool.def(true)
}

const httpReg = /(http|https|ftp):\/\/([\w.]+\/?)\S*/

const calcMarginLeft = (collapsed, collapsedWidth) => {
  if (collapsed) {
    return `-${collapsedWidth ? Math.abs(32 - (collapsedWidth - 16) / 2) : 0}px`
  }
  return 0
}

const renderIcon = (h, icon) => {
  if (icon === undefined || icon === "none" || icon === null) {
    return null
  }
  const props = {}
  typeof icon === "object" ? (props.component = icon) : (props.type = icon)
  return <Icon {...{ props }} />
}

const renderTitle = (h, title) => {
  return <span>{title}</span>
}

const renderMenuItem = (h, item, i18nRender, collapsed, collapsedWidth) => {
  const meta = Object.assign({}, item.meta)
  const target = meta.target || null
  const hasRemoteUrl = httpReg.test(item.path)
  const CustomTag = (target && "a") || "router-link"
  const props = { to: { name: item.name } }
  const attrs = hasRemoteUrl || target ? { href: item.path, target: target } : {}
  if (item.children && item.hideChildrenInMenu) {
    // 把有子菜单的 并且 父菜单是要隐藏子菜单的
    // 都给子菜单增加一个 hidden 属性
    // 用来给刷新页面时， selectedKeys 做控制用
    item.children.forEach((cd) => {
      cd.meta = Object.assign(cd.meta || {}, { hidden: true })
    })
  }
  return (
    <MenuItem key={item.path} style={{ marginLeft: calcMarginLeft(collapsed, collapsedWidth) }}>
      <CustomTag {...{ props, attrs }} style={"display: flex;align-items:center"}>
        {renderIcon(h, meta.icon)}
        {renderTitle(h, meta.title, i18nRender)}
      </CustomTag>
    </MenuItem>
  )
}

const renderSubMenu = (h, item, i18nRender, collapsed, collapsedWidth) => {
  return (
    <SubMenu
      key={item.path}
      style={{ marginLeft: calcMarginLeft(collapsed, collapsedWidth) }}
      title={
        <span style={"display: flex;align-items:center"}>
          {renderIcon(h, item.meta.icon)}
          <span>{renderTitle(h, item.meta.title, i18nRender)}</span>
        </span>
      }
    >
      {/* eslint-disable-next-line @typescript-eslint/no-use-before-define */}
      {!item.hideChildrenInMenu && item.children.map((cd) => renderMenu(h, cd, i18nRender))}
    </SubMenu>
  )
}

const renderMenu = (h, item, i18nRender, collapsed, collapsedWidth) => {
  if (item && !item.meta?.hidden) {
    const bool = item.children && !item.hideChildrenInMenu
    return bool
      ? renderSubMenu(h, item, i18nRender, collapsed, collapsedWidth)
      : renderMenuItem(h, item, i18nRender, collapsed, collapsedWidth)
  }
  return null
}

const RouteMenu = {
  name: "RouteMenu",
  props: RouteMenuProps,
  data() {
    return {
      sOpenKeys: [],
      sSelectedKeys: [],
      cachedOpenKeys: [],
      cachedSelectedKeys: []
    }
  },
  render(h) {
    // 解构所需的属性
    const { mode, theme, menus, i18nRender, collapsed, collapsedWidth, accordion } = this

    // 菜单展开/收起时的回调
    const handleOpenChange = (openKeys) => {
      if (mode === "horizontal") {
        this.sOpenKeys = openKeys
        return
      }
      let uniqueOpenKeys = Array.from(new Set(openKeys))
      if (accordion) {
        uniqueOpenKeys = uniqueOpenKeys.length > 0 ? [uniqueOpenKeys.pop()] : []
      }
      this.sOpenKeys = uniqueOpenKeys
      this.$emit("openChange", uniqueOpenKeys)
    }

    // 计算菜单宽度，折叠时为 collapsedWidth，展开时为 100%
    const calcWidth = (collapsed, collapsedWidth) => {
      if (collapsed) {
        return `${collapsedWidth || 80}px`
      }
      return "100%"
    }

    // 动态生成 Menu 组件的 props 和事件
    const dynamicProps = {
      props: {
        mode, // 菜单模式（inline、horizontal）
        theme, // 菜单主题
        openKeys: this.openKeys || this.sOpenKeys, // 当前展开的菜单项
        selectedKeys: this.selectedKeys || this.sSelectedKeys // 当前选中的菜单项
      },
      on: {
        // 菜单项被选中时
        select: (args) => {
          this.$emit("select", args.selectedKeys)
          // 如果不是外链，更新本地选中状态
          if (!httpReg.test(args.key)) {
            this.sSelectedKeys = args.selectedKeys
          }
        },
        // 菜单项被点击时
        click: (args) => {
          this.$emit("click", args)
        },
        // 菜单展开/收起时
        openChange: handleOpenChange
      },
      style: {
        width: calcWidth(collapsed, collapsedWidth) // 设置菜单宽度
      }
    }

    // 渲染菜单项，过滤掉隐藏的菜单
    const menuItems = menus.map((item) => {
      if (item.meta?.hidden) {
        return null
      }
      return renderMenu(h, item, i18nRender, collapsed, collapsedWidth)
    })

    // 返回 Menu 组件
    return <Menu {...dynamicProps}>{menuItems}</Menu>
  },
  methods: {
    // 根据当前路由更新菜单的选中和展开状态
    updateMenu() {
      const routes = this.$route.matched.concat()
      // 如果没有外部传入 selectedKeys，则自动根据路由设置
      if (this.selectedKeys === undefined) {
        const { hidden } = this.$route.meta
        // 处理三级路由且当前路由被隐藏的情况
        if (routes.length >= 3 && hidden) {
          routes.pop()
          this.sSelectedKeys = [routes[routes.length - 1].path]
        } else {
          this.sSelectedKeys = [routes.pop().path]
        }
      }

      // 计算需要展开的菜单项
      let openKeys = []
      if (this.mode === "inline") {
        routes.forEach((item) => {
          item.path && openKeys.push(item.path)
        })
      }
      // 如果 openOnceKey 为 false，则合并之前展开的菜单项
      if (!this.openOnceKey) {
        this.sOpenKeys.forEach((item) => {
          openKeys.push(item)
        })
      }

      // 去重，防止 openKeys 出现重复
      openKeys = Array.from(new Set(openKeys))

      // 折叠时缓存 openKeys，展开时恢复
      this.collapsed ? (this.cachedOpenKeys = openKeys) : (this.sOpenKeys = openKeys)
    }
  },
  computed: {
    // 获取所有一级菜单的 key（path），用于判断单开模式
    rootSubmenuKeys: (vm) => {
      const keys = vm.menus.map((item) => item.path) || []
      return keys
    }
  },
  created() {
    this.$watch("$route", () => {
      this.updateMenu()
    })
    this.$watch("collapsed", (val) => {
      if (val) {
        this.cachedOpenKeys = this.sOpenKeys.concat()
        this.sOpenKeys = []
      } else {
        this.sOpenKeys = this.cachedOpenKeys
      }
    })

    if (this.selectedKeys !== undefined) {
      this.sSelectedKeys = this.selectedKeys
    }
    if (this.openKeys !== undefined) {
      this.sOpenKeys = this.openKeys
    }
  },
  mounted() {
    this.updateMenu()
  }
}

export default RouteMenu
