// @ts-nocheck
import AutoComplete from "ant-design-vue/es/auto-complete"
import DatePicker from "ant-design-vue/es/date-picker"
import Descriptions from "ant-design-vue/es/descriptions"
import Layout from "ant-design-vue/es/layout"
import Mentions from "ant-design-vue/es/mentions"
import Menu from "ant-design-vue/es/menu"
import message from "ant-design-vue/es/message"
import Modal from "ant-design-vue/es/modal"
import List from "ant-design-vue/es/list/index"
import ListItem from "ant-design-vue/es/list/Item"

import notification from "ant-design-vue/es/notification"
import Select from "ant-design-vue/es/select"
import Steps from "ant-design-vue/es/steps"
import Tabs from "ant-design-vue/es/tabs"
import { VueConstructor } from "vue"
import AntPortal from "ant-design-vue/es/_util/portalDirective"
import "ant-design-vue/es/date-picker/style/index.less"
import "ant-design-vue/es/message/style/index.less"
import "ant-design-vue/es/modal/style/index.less"
import "ant-design-vue/es/notification/style/index.less"

/**
 * 无需加载其他antd组件，已经通过插件自动加载了
 * 只加载 unplugin-components 解析不了的ant design组件和指令
 */

// 定义需要导入的组件映射
const componentMap = [
  // @ts-ignore
  AutoComplete.Option,
  // @ts-ignore
  AutoComplete.OptGroup,
  DatePicker.MonthPicker,
  DatePicker.WeekPicker,
  DatePicker.RangePicker,
  Descriptions.Item,
  Layout.Header,
  Layout.Footer,
  Layout.Content,
  Mentions.Option,
  Menu.Divider,
  Menu.ItemGroup,
  Select.Option,
  Select.OptGroup,
  Steps.Step,
  Tabs.TabPane,
  // @ts-ignore
  Tabs.TabContent,
  List,
  ListItem,
  ListItem.Meta
]

export function registerExtraAntdvComponents(vueInstance: VueConstructor) {
  // ============= 指令 ===============
  vueInstance.directive("ant-portal", AntPortal)

  // =============  组件  ==============
  componentMap.forEach((item) => {
    vueInstance.component(item.name, item)
  })

  // =============  方法  ==============
  // 创建一个函数，等价于 message.info
  const messageFn = (...args: any[]) => message.info(...args)
  // 把 message 的所有方法挂到 messageFn 上
  Object.assign(messageFn, message)

  vueInstance.prototype.$message = messageFn
  vueInstance.prototype.$notification = notification
  vueInstance.prototype.$info = Modal.info
  vueInstance.prototype.$success = Modal.success
  vueInstance.prototype.$error = Modal.error
  vueInstance.prototype.$warning = Modal.warning
  vueInstance.prototype.$confirm = Modal.confirm
  vueInstance.prototype.$destroyAll = Modal.destroyAll
}
