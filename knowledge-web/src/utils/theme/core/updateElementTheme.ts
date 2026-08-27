import generateColors from "../client/color"

let colors: Record<string, string> = { primary: "#409eff" }
let originalStyle = ""
let count = 0

function getFile(url: string, isBlob = false): Promise<{ data: any; url: string }> {
  return new Promise((resolve, reject) => {
    const client = new XMLHttpRequest()
    client.responseType = isBlob ? "blob" : ""
    client.onreadystatechange = () => {
      if (client.readyState !== 4) {
        return
      }
      if (client.status === 200) {
        const urlArr = client.responseURL.split("/")
        resolve({
          data: client.response,
          url: urlArr[urlArr.length - 1]
        })
      } else {
        reject(new Error(client.statusText))
      }
    }
    client.open("GET", url)
    client.send()
  })
}

function getStyleTemplate(data: string): string {
  const colorMap: Record<string, string> = {
    "#3a8ee6": "shade-1",
    "#409eff": "primary",
    "#53a8ff": "light-1",
    "#66b1ff": "light-2",
    "#79bbff": "light-3",
    "#8cc5ff": "light-4",
    "#a0cfff": "light-5",
    "#b3d8ff": "light-6",
    "#c6e2ff": "light-7",
    "#d9ecff": "light-8",
    "#ecf5ff": "light-9"
  }
  Object.keys(colorMap).forEach((key) => {
    const value = colorMap[key]
    data = data.replace(new RegExp(key, "ig"), value)
  })
  return data
}

async function getIndexStyle() {
  const { data } = await getFile(`${import.meta.env.VITE_BASE_PATH}/theme-el.css`)
  originalStyle = getStyleTemplate(data)
}

function writeNewStyle() {
  let cssText = originalStyle
  Object.keys(colors).forEach((key) => {
    cssText = cssText.replace(new RegExp(`(:|\\s+)${key}`, "g"), `$1${colors[key]}`)
  })

  const STYLE_ID = "el-theme-style-98888811"
  let style = document.getElementById(STYLE_ID) as HTMLStyleElement | null
  if (!style) {
    style = document.createElement("style")
    style.id = STYLE_ID
    style.innerText = cssText
    document.head.appendChild(style)
  } else {
    style.innerText = cssText
  }
}

export default function updateElTheme(primary: string) {
  colors = {
    ...colors,
    ...generateColors(primary),
    primary
  }
  if (!originalStyle && count++ < 30) {
    return setTimeout(() => {
      updateElTheme(primary)
    }, 100)
  }
  writeNewStyle()
}

// 初始化逻辑：引入文件时自动执行
getIndexStyle()
