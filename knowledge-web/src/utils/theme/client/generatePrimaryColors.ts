import color from "css-color-function"

const formula: Record<string, string> = {
  "primary-color-100": "color(primary tint(99%))",
  "primary-color-200": "color(primary tint(80%))",
  "primary-color-300": "color(primary tint(60%))",
  "primary-color-400": "color(primary tint(40%))",
  "primary-color-500": "color(primary tint(20%))",
  "primary-color-600": "primary",
  "primary-color-700": "color(primary shade(20%))",
  "primary-color-800": "color(primary shade(40%))",
  "primary-color-900": "color(primary shade(60%))"
}

const generatePrimaryColors = (primary: string): Record<string, string> => {
  const colors: Record<string, string> = {}
  Object.keys(formula).forEach((key) => {
    const value = formula[key].replace(/primary/g, primary)
    colors[key] = color.convert(value)
  })
  return colors
}

export default generatePrimaryColors
