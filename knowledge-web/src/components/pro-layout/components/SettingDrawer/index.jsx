import "./index.less"

import { omit } from "lodash-es"
import PropTypes from "ant-design-vue/es/_util/vue-types"

import "ant-design-vue/es/divider/style"
import Divider from "ant-design-vue/es/divider"

import "ant-design-vue/es/drawer/style"
import Drawer from "ant-design-vue/es/drawer"

import "ant-design-vue/es/list/style"
import List from "ant-design-vue/es/list"

import "ant-design-vue/es/switch/style"
import Switch from "ant-design-vue/es/switch"

import "ant-design-vue/es/button/style"
import Button from "ant-design-vue/es/button"

import "ant-design-vue/es/icon/style"
import Icon from "ant-design-vue/es/icon"

import "ant-design-vue/es/alert/style"
import Alert from "ant-design-vue/es/alert"

import antPortal from "ant-design-vue/es/_util/portalDirective"

import "ant-design-vue/es/message/style"

import BlockCheckbox from "./BlockCheckbox"
import ThemeColor from "./ThemeColor"
import LayoutSetting, { renderLayoutSettingItem } from "./LayoutChange"
import { genStringToTheme } from "../../utils/util"
import CopyToClipboard from "vue-copy-to-clipboard"
import themePluginConfig from "@/config/layoutConfig"
import { changeTheme, updateColorWeak } from "@/utils/theme"
import { openFileInEditor } from "@/utils/logic/openFileInEditor"

const baseClassName = "ant-pro-setting-drawer"

const BodyProps = {
  title: PropTypes.string.def("")
}

const Body = {
  props: BodyProps,
  render() {
    const { title } = this

    return (
      <div style={{ marginBottom: 24 }}>
        <h3 class={`${baseClassName}-title`}>{title}</h3>
        {this.$slots.default}
      </div>
    )
  }
}

const defaultI18nRender = (t) => t

const getThemeList = () => {
  const list = themePluginConfig.theme || []

  const themeList = [
    {
      key: "light",
      url: "https://gw.alipayobjects.com/zos/antfincdn/NQ%24zoisaD2/jpRkZQMyYRryryPNtyIC.svg",
      title: "亮色模式"
    },
    {
      key: "dark",
      url: "https://gw.alipayobjects.com/zos/antfincdn/XwFOFbLkSM/LCkqqYNmvBEbokSDscrm.svg",
      title: "暗色模式"
    }
  ]

  const darkColorList = [
    {
      key: "#1677FF",
      color: "#1677FF",
      theme: "dark"
    }
  ]

  const lightColorList = [
    {
      key: "#1677FF",
      color: "#1677FF",
      theme: "dark"
    }
  ]

  // insert  theme color List
  list.forEach((item) => {
    const color = item.color
    if (item.theme === "dark" && color) {
      darkColorList.push({
        color,
        ...item
      })
    }
    if (!item.theme || item.theme === "light") {
      lightColorList.push({
        color,
        ...item
      })
    }
  })

  return {
    colorList: {
      dark: darkColorList,
      light: lightColorList
    },
    themeList
  }
}

const handleChangeSetting = (key, value) => {
  if (key === "primaryColor") {
    changeTheme(value)
  }
  if (key === "colorWeak") {
    updateColorWeak(value)
  }
}

const genCopySettingJson = (settings) =>
  JSON.stringify(
    omit(
      {
        ...settings,
        primaryColor: genStringToTheme(settings.primaryColor)
      },
      ["colorWeak"]
    ),
    null,
    2
  )

export const settings = {
  theme: PropTypes.oneOf(["dark", "light"]),
  primaryColor: PropTypes.string,
  layout: PropTypes.oneOf(["sidemenu", "topmenu"]),
  colorWeak: PropTypes.bool,
  contentWidth: PropTypes.oneOf(["Fluid", "Fixed"]).def("Fluid"),
  // 替换兼容 PropTypes.oneOf(['Fluid', 'Fixed']).def('Fluid')
  // contentWidth: PropTypes.oneOfType([PropTypes.string, PropTypes.bool]).def('Fluid'),
  fixedHeader: PropTypes.bool,
  fixSiderbar: PropTypes.bool,
  showTabs: PropTypes.bool,
  fixedFirstRouteOnTags: PropTypes.bool
}

export const SettingDrawerProps = {
  getContainer: PropTypes.func,
  settings: PropTypes.objectOf(settings),
  i18nRender: PropTypes.oneOfType([PropTypes.func, PropTypes.bool]).def(false)
}

const SettingDrawer = {
  name: "SettingDrawer",
  props: SettingDrawerProps,
  inject: ["locale"],
  data() {
    return {
      show: false
    }
  },
  render(h) {
    const { setShow, getContainer, settings } = this

    const {
      theme = "dark",
      primaryColor = "daybreak",
      layout = "sidemenu",
      fixedHeader = false,
      fixSiderbar = false,
      contentWidth,
      colorWeak,
      showTabs,
      fixedFirstRouteOnTags
    } = settings

    const i18n = this.$props.i18nRender || this.locale || defaultI18nRender
    const themeList = getThemeList()
    const isTopMenu = layout === "topmenu"

    const iconStyle = {
      color: "#fff",
      fontSize: 20
    }

    const changeSetting = (type, value) => {
      this.$emit("change", { type, value })
      handleChangeSetting(type, value, false)
    }

    const handleCopy = () => {
      const filePath = "src/config/layout.ts"
      Modal.confirm({
        title: () => "拷贝成功",
        content: () => (
          <div>
            拷贝设置成功，请到
            <span class={"text-blue-400"}>{filePath}</span>
            中替换默认配置
          </div>
        ),
        cancelText: "关闭",
        okText: "在编辑器中打开",
        onOk() {
          openFileInEditor(filePath)
        }
      })
    }

    return (
      <Drawer
        visible={this.show}
        width={300}
        onClose={() => setShow(false)}
        placement="right"
        getContainer={getContainer}
        /* handle={
              <div class="ant-pro-setting-drawer-handle" onClick={() => setShow(!this.show)}>
                {this.show
                  ? (<Icon type="close" style={iconStyle} />)
                  : (<Icon type="setting" style={iconStyle} />)
                }
              </div>
            } */
        style={{
          zIndex: 999
        }}
      >
        <template slot="handle">
          <div class={`${baseClassName}-handle`} onClick={() => setShow(!this.show)}>
            {this.show ? <Icon type="close" style={iconStyle} /> : <Icon type="setting" style={iconStyle} />}
          </div>
        </template>
        <div class={`${baseClassName}-content`}>
          <Alert
            type="warning"
            message={"配置栏只用于在开发环境预览，生产环境不会展现。"}
            icon={<Icon type={"notification"} />}
            showIcon
            style={{ marginBottom: "16px", marginTop: "10px" }}
          />
          <Alert
            type="warning"
            message={"如果想在生产环境生效，请点击下方拷贝设置并粘贴到对应的项目配置文件中。"}
            icon={<Icon type={"notification"} />}
            showIcon
            style={{ marginBottom: "16px", marginTop: "10px" }}
          />
          <Body title={"页面风格"}>
            <BlockCheckbox
              i18nRender={i18n}
              list={themeList.themeList}
              value={theme}
              onChange={(val) => {
                changeSetting("theme", val)
              }}
            />
          </Body>
          <ThemeColor
            i18nRender={i18n}
            title={"主题色"}
            value={primaryColor}
            colors={themeList.colorList["light"]}
            onChange={(color) => {
              changeSetting("primaryColor", color, null)
            }}
          />
          <Divider />
          <Body title={"导航模式"}>
            <BlockCheckbox
              i18nRender={i18n}
              value={layout}
              onChange={(value) => {
                changeSetting("layout", value, null)
              }}
            />
          </Body>
          <LayoutSetting
            i18nRender={i18n}
            contentWidth={contentWidth}
            fixedHeader={fixedHeader}
            fixSiderbar={isTopMenu ? false : fixSiderbar}
            showTabs={showTabs}
            fixedFirstRouteOnTags={fixedFirstRouteOnTags}
            layout={layout}
            onChange={({ type, value }) => {
              changeSetting(type, value)
            }}
          />
          <Divider />
          <Body title={"其他设置"}>
            <List
              split={false}
              renderItem={(item) => renderLayoutSettingItem(h, item)}
              dataSource={[
                {
                  title: "色弱模式",
                  action: (
                    <Switch
                      size="small"
                      checked={!!colorWeak}
                      onChange={(checked) => changeSetting("colorWeak", checked)}
                    />
                  )
                }
              ]}
            />
          </Body>

          <CopyToClipboard text={genCopySettingJson(settings)} onCopy={handleCopy}>
            <Button block>
              <Icon type={"copy"} />
              {"拷贝设置"}
            </Button>
          </CopyToClipboard>
          <div class={`${baseClassName}-content-footer`}>{this.$slots.default}</div>
        </div>
      </Drawer>
    )
  },
  methods: {
    setShow(flag) {
      this.show = flag
    }
  }
}

SettingDrawer.install = function (Vue) {
  Vue.use(antPortal)
  Vue.component(SettingDrawer.name, SettingDrawer)
}

export default SettingDrawer
