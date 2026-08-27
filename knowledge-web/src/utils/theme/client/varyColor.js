export default {
  lighten: lighten, // 淡化
  darken: darken, // 加深
  mix: mix, // 混合
  toNum3: toNum3,
  rgb: rgbaToRgb,
  rgbaToRgb: rgbaToRgb,
  pad2: pad2,
  rgbToHsl: rgbToHsl,
  rrggbbToHsl: rrggbbToHsl
}

function pad2(num) {
  let t = num.toString(16)
  if (t.length === 1) {
    t = `0${t}`
  }
  return t
}

function lighten(colorStr, weight) {
  return mix("fff", colorStr, weight)
}

function darken(colorStr, weight) {
  return mix("000", colorStr, weight)
}

function mix(color1, color2, weight1, alpha1, alpha2) {
  color1 = dropPrefix(color1)
  color2 = dropPrefix(color2)
  if (weight1 === undefined) {
    weight1 = 0.5
  }
  if (alpha1 === undefined) {
    alpha1 = 1
  }
  if (alpha2 === undefined) {
    alpha2 = 1
  }

  const w = 2 * weight1 - 1
  const alphaDelta = alpha1 - alpha2
  const w1 = ((w * alphaDelta === -1 ? w : (w + alphaDelta) / (1 + w * alphaDelta)) + 1) / 2
  const w2 = 1 - w1

  const rgb1 = toNum3(color1)
  const rgb2 = toNum3(color2)
  const r = Math.round(w1 * rgb1[0] + w2 * rgb2[0])
  const g = Math.round(w1 * rgb1[1] + w2 * rgb2[1])
  const b = Math.round(w1 * rgb1[2] + w2 * rgb2[2])
  return `#${pad2(r)}${pad2(g)}${pad2(b)}`
}

function rgbaToRgb(colorStr, alpha, bgColorStr) {
  return mix(colorStr, bgColorStr || "fff", 0.5, alpha, 1 - alpha)
}

function toNum3(colorStr) {
  colorStr = dropPrefix(colorStr)
  if (colorStr.length === 3) {
    colorStr = colorStr[0] + colorStr[0] + colorStr[1] + colorStr[1] + colorStr[2] + colorStr[2]
  }
  const r = parseInt(colorStr.slice(0, 2), 16)
  const g = parseInt(colorStr.slice(2, 4), 16)
  const b = parseInt(colorStr.slice(4, 6), 16)
  return [r, g, b]
}

function dropPrefix(colorStr) {
  return colorStr.replace("#", "")
}

function rrggbbToHsl(rrggbb) {
  const rgb = toNum3(rrggbb)
  const hsl = rgbToHsl.apply(0, rgb)
  return [hsl[0].toFixed(0), `${(hsl[1] * 100).toFixed(3)}%`, `${(hsl[2] * 100).toFixed(3)}%`].join(",")
}

function rgbToHsl(r, g, b) {
  const r_r = r / 255
  const r_g = g / 255
  const r_b = b / 255

  const max = Math.max(r_r, r_g, r_b)
  const min = Math.min(r_r, r_g, r_b)
  const delta = max - min
  const l = (max + min) / 2
  let h = 0
  let s = 0
  if (Math.abs(delta) > 0.00001) {
    if (l <= 0.5) {
      s = delta / (max + min)
    } else {
      s = delta / (2 - max - min)
    }
    const r_dist = (max - r_r) / delta
    const g_dist = (max - r_g) / delta
    const b_dist = (max - r_b) / delta
    if (r_r === max) {
      h = b_dist - g_dist
    } else if (r_g === max) {
      h = 2 + r_dist - b_dist
    } else {
      h = 4 + g_dist - r_dist
    }
    h = h * 60
    if (h < 0) {
      h += 360
    }
  }
  return [h, s, l]
}
