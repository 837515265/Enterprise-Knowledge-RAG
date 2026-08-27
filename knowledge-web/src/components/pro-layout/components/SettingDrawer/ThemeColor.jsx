import "./ThemeColor.less"

import PropTypes from "ant-design-vue/es/_util/vue-types"
import { genThemeToString } from "../../utils/util"
import "ant-design-vue/es/tooltip/style"
import Tooltip from "ant-design-vue/es/tooltip"
import "ant-design-vue/es/icon/style"
import Icon from "ant-design-vue/es/icon"

const baseClassName = "theme-color"

export const TagProps = {
  color: PropTypes.string,
  check: PropTypes.bool
}

const Tag = {
  props: TagProps,
  functional: true,
  render(h, content) {
    const {
      props: { color, check },
      data
    } = content
    return (
      <div {...data} style={{ backgroundColor: color }}>
        {check ? <Icon type="check" /> : null}
      </div>
    )
  }
}

export const ThemeColorProps = {
  colors: PropTypes.array,
  title: PropTypes.string,
  value: PropTypes.string,

  i18nRender: PropTypes.oneOfType([PropTypes.func, PropTypes.bool]).def(false)
}

const ThemeColor = {
  props: ThemeColorProps,
  inject: ["locale"],
  render() {
    const { title, value, colors = [] } = this
    const handleChange = (key) => {
      this.$emit("change", key)
    }

    return (
      <div class={baseClassName} ref={"ref"}>
        <h3 class={`${baseClassName}-title`}>{title}</h3>
        <div class={`${baseClassName}-content`}>
          {colors.map((item) => {
            const themeKey = genThemeToString(item.color.toUpperCase())
            const check =
              value.toUpperCase() === item.color.toUpperCase() ||
              genThemeToString(value.toUpperCase()) === item.color.toUpperCase()
            return (
              <Tooltip key={item.color.toUpperCase()} title={themeKey ? `主题色${themeKey}` : item.color.toUpperCase()}>
                <Tag
                  class={`${baseClassName}-block`}
                  color={item.color.toUpperCase()}
                  check={check}
                  onClick={() => handleChange(item.color.toUpperCase())}
                />
              </Tooltip>
            )
          })}
        </div>
      </div>
    )
  }
}

export default ThemeColor
