import { updateAntdTheme } from "@/utils/theme/core/updateAntdTheme"
import { updateColorWeak } from "./core/updateAntdTheme"
import generatePrimaryColors from "./client/generatePrimaryColors"

/**
 * 校验是否为hex颜色
 * @param {string} color
 * @returns {boolean}
 */
function isHexColor(color: string): boolean {
  return /^#([\da-fA-F]{3}|[\da-fA-F]{6})$/.test(color)
}

/**
 * 修改全局主题色
 * @param {string} color 新的主题色
 */
export function changeTheme(color: string) {
  if (!isHexColor(color)) {
    return message.error("只允许传入hex格式的颜色作为主题色！")
  }
  updateAntdTheme(color)

  document.documentElement.style.setProperty("--primary-color", color)

  const colors: Record<string, string> = generatePrimaryColors(color)
  Object.keys(colors).forEach((key) => {
    document.documentElement.style.setProperty(`--${key}`, colors[key])
  })
}

export { updateColorWeak }
