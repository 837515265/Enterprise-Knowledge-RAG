import client from "../client"
import generate from "@ant-design/colors/lib/generate"

export const themeColor = {
  getAntdSerials(color: string) {
    // 淡化（即less的tint）
    const lightens = new Array(9).fill(null).map((_t, i) => {
      return client.varyColor.lighten(color, i / 10)
    })
    // colorPalette 变换得到颜色值
    const colorPalettes = generate(color)
    const rgb = client.varyColor.toNum3(color.replace("#", "")).join(",")
    return lightens.concat(colorPalettes).concat(rgb)
  },
  changeColor(newColor: string) {
    const options = {
      newColors: this.getAntdSerials(newColor), // new colors array, one-to-one corresponde with `matchColors`
      changeUrl(cssUrl) {
        return `/${cssUrl}` // while router is not `hash` mode, it needs absolute path
      }
    }
    return client.changer.changeColor(options, Promise)
  }
}

export const updateAntdTheme = (newPrimaryColor: string) => {
  // const hideMessage = message.loading("正在切换主题", 0)
  themeColor.changeColor(newPrimaryColor).then(() => {
    // hideMessage()
  })
}

export const updateColorWeak = (colorWeak) => {
  // document.body.className = colorWeak ? 'colorWeak' : '';
  const app = document.body.querySelector("#app .ant-pro-basicLayout")
  colorWeak ? app?.classList.add("colorWeak") : app?.classList.remove("colorWeak")
}
