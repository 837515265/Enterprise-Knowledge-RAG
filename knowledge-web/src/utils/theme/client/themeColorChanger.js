const _urlColors = {} // {[url]: {id,colors}}
let theme_COLOR_config

export default {
  _tryNum: 0,
  changeColor: function (options, promiseForIE) {
    const Promise = promiseForIE || win().Promise
    const _this = this
    if (!theme_COLOR_config) {
      theme_COLOR_config = {
        url: "css/theme-colors-d74d437f.css",
        colors: [
          "#1890ff",
          "#2f9bff",
          "#46a6ff",
          "#5db1ff",
          "#74bcff",
          "#8cc8ff",
          "#a3d3ff",
          "#badeff",
          "#d1e9ff",
          "#e6f7ff",
          "#bae7ff",
          "#91d5ff",
          "#69c0ff",
          "#40a9ff",
          "#1890ff",
          "#096dd9",
          "#0050b3",
          "#003a8c",
          "#002766",
          "24,144,255"
        ]
      }
      const later = retry()
      // 重试直到theme_COLOR_config加载
      if (later) {
        return later
      }
    }
    let oldColors = options.oldColors || theme_COLOR_config.colors || []
    const newColors = options.newColors || []

    let cssUrl = theme_COLOR_config.url || options.cssUrl
    if (options.changeUrl) {
      cssUrl = options.changeUrl(cssUrl)
    }

    return new Promise((resolve, reject) => {
      const last = _urlColors[cssUrl] // url可能被changeUrl改变
      if (last) {
        // 之前已替换过
        oldColors = last.colors
      }

      if (isSameArr(oldColors, newColors)) {
        resolve()
      } else {
        setCssText(last, cssUrl, resolve, reject)
      }
    })

    function retry() {
      if (!theme_COLOR_config) {
        if (_this._tryNum < 9) {
          _this._tryNum = _this._tryNum + 1
          return new Promise((resolve) => {
            setTimeout(() => {
              resolve(_this.changeColor(options, promiseForIE))
            }, 100)
          })
        } else {
          theme_COLOR_config = {}
        }
      }
    }

    function setCssText(last, url, resolve, reject) {
      let elStyle = last && document.getElementById(last.id)
      if (elStyle && last.colors) {
        setCssTo(elStyle.innerText)
        last.colors = newColors
        resolve()
      } else {
        // 第一次替换
        const id = `css_${+new Date()}`
        elStyle = document.querySelector(options.appendToEl || "body").appendChild(document.createElement("style"))

        elStyle.setAttribute("id", id)

        _this.getCssString(
          url,
          (cssText) => {
            setCssTo(cssText)
            _urlColors[url] = { id: id, colors: newColors }
            resolve()
          },
          reject
        )
      }

      function setCssTo(cssText) {
        cssText = _this.replaceCssText(cssText, oldColors, newColors)
        elStyle.innerText = cssText
      }
    }
  },
  replaceCssText: function (cssText, oldColors, newColors) {
    oldColors.forEach((color, t) => {
      // #222、#222223、#22222350、222, 255,3 => #333、#333334、#33333450、211,133,53、hsl(27, 92.531%, 52.745%)
      const reg = new RegExp(`${color.replace(/\s/g, "").replace(/,/g, ",\\s*")}([\\da-f]{2})?(\\b|\\)|,|\\s)`, "ig")
      cssText = cssText.replace(reg, `${newColors[t]}$1$2`) // 255, 255,3
    })
    return cssText
  },
  getCssString: function (url, resolve, reject) {
    const css = theme_COLOR_config.cssCode
    if (css) {
      // css已内嵌在js中
      theme_COLOR_config.cssCode = ""
      resolve(css)
      return
    }

    const xhr = new XMLHttpRequest()
    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4) {
        if (xhr.status === 200) {
          resolve(xhr.responseText)
        } else {
          reject(xhr.status)
        }
      }
    }
    xhr.onerror = function (e) {
      reject(e)
    }
    xhr.ontimeout = function (e) {
      reject(e)
    }
    // xhr.open("GET", `${url}`)
    xhr.open("GET", `${import.meta.env.BASE_URL}/theme.less`)
    xhr.send()
  }
}
function win() {
  return typeof window === "undefined" ? global : window
}
function isSameArr(oldColors, newColors) {
  if (oldColors.length !== newColors.length) {
    return false
  }
  for (let i = 0, j = oldColors.length; i < j; i++) {
    if (oldColors[i] !== newColors[i]) {
      return false
    }
  }
  return true
}
