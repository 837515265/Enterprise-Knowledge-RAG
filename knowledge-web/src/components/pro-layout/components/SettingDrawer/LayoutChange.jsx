import PropTypes from "ant-design-vue/es/_util/vue-types"

import "ant-design-vue/es/tooltip/style"
import Tooltip from "ant-design-vue/es/tooltip"
import "ant-design-vue/es/list/style"
import List from "ant-design-vue/es/list"
import ListItem from "ant-design-vue/es/list/Item.js"
import "ant-design-vue/es/select/style"
import Select from "ant-design-vue/es/select"
import "ant-design-vue/es/switch/style"
import Switch from "ant-design-vue/es/switch"

export const renderLayoutSettingItem = (h, item) => {
  const action = { ...item.action }
  return (
    <Tooltip title={item.disabled ? item.disabledReason : ""} placement="left">
      <ListItem actions={[action]}>
        <span style={{ opacity: item.disabled ? 0.5 : 1 }}>{item.title}</span>
      </ListItem>
    </Tooltip>
  )
}

export const LayoutSettingProps = {
  contentWidth: PropTypes.oneOf(["Fluid", "Fixed"]).def("Fluid"),
  fixedHeader: PropTypes.bool,
  fixSiderbar: PropTypes.bool,
  showTabs: PropTypes.bool,
  fixedFirstRouteOnTags: PropTypes.bool,
  layout: PropTypes.oneOf(["sidemenu", "topmenu"]),

  i18nRender: PropTypes.oneOfType([PropTypes.func, PropTypes.bool]).def(false)
}

export default {
  props: LayoutSettingProps,
  inject: ["locale"],
  render(h) {
    const { ...rest } = this.$props

    const handleChange = (type, value) => {
      this.$emit("change", { type, value })
    }

    return (
      <List
        split={false}
        dataSource={[
          {
            title: "内容区域宽度",
            action: (
              <Select
                value={rest.contentWidth}
                size="small"
                onSelect={(value) => handleChange("contentWidth", value)}
                style={{ width: "80px" }}
              >
                {rest.layout === "sidemenu" ? null : <Select.Option value="Fixed">固定</Select.Option>}
                <Select.Option value="Fluid">流式</Select.Option>
              </Select>
            )
          },
          {
            title: "固定页头",
            action: (
              <Switch
                size="small"
                checked={!!rest.fixedHeader}
                onChange={(checked) => handleChange("fixedHeader", checked)}
              />
            )
          },
          {
            title: "固定侧边栏",
            disabled: rest.layout === "topmenu",
            disabledReason: "仅在侧边菜单布局时可用",
            action: (
              <Switch
                size="small"
                disabled={rest.layout === "topmenu"}
                checked={!!rest.fixSiderbar}
                onChange={(checked) => handleChange("fixSiderbar", checked)}
              />
            )
          },
          {
            title: "展示页签",
            action: (
              <Switch
                size="small"
                checked={!!rest.showTabs}
                onChange={(checked) => handleChange("showTabs", checked)}
              />
            )
          },
          {
            title: "页签固定首个菜单",
            action: (
              <Switch
                size="small"
                disabled={!rest.showTabs}
                checked={!!rest.fixedFirstRouteOnTags}
                onChange={(checked) => handleChange("fixedFirstRouteOnTags", checked)}
              />
            )
          }
        ]}
        renderItem={(item) => renderLayoutSettingItem(h, item)}
      />
    )
  }
}
