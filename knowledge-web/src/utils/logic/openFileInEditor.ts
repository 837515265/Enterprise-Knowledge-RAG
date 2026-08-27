/**
 * 在编辑器打开指定代码文件, 配合[vite-plugin-vue-inspector](https://www.npmjs.com/package/vite-plugin-vue-inspector)使用
 *
 * 如何修改默认打开的编辑器？
 *  1. 新建.env.development.local 文件。
 *  2. 添加VITE_INSPECTOR_LAUNCH_EDITOR环境变量 并指定值为您的编辑器（webstorm/code(vscode)/cursor）
 * @param {string} path 要打开的文件地址，如/src/config/theme
 * @param {number} row 可选，打开第几行
 * @param {number} col 可选，打开第几列
 * @returns {Promise<Response>}
 */
export function openFileInEditor(path: string, row = 1, col = 1) {
  const isDev = import.meta.env.DEV
  if (!isDev) {
    return new Error("只允许在开发模式使用！！！")
  }
  const prefix = import.meta.env.VITE_BASE_PATH?.endsWith("/") ? "" : "/"
  const targetUrl = `${import.meta.env.VITE_BASE_PATH}${prefix}__open-in-editor?file=${encodeURIComponent(
    path
  )}%3A${row}%3A${col}`
  return fetch(targetUrl).then((r) => {
    message.success("打开成功，请查看编辑器！")
    return r
  })
}
