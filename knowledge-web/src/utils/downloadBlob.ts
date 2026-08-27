/**
 * response 转换为文件
 * @param {*} response Blob对象
 * @param fileName 文件名 可选
 */
export function downloadBlob(response, fileName?: string) {
  // 提取文件名
  const finalFileName = fileName || "下载文件.xlsx"
  // 将二进制流转为blob
  const blob = new Blob([response], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=utf-8"
  })

  // 前端获取业务码，成功执行正常业务
  const downloadElement = document.createElement("a")
  const href = window.URL.createObjectURL(blob) // 创建下载的链接
  downloadElement.href = href
  // const timeStamp = filename + new Date().toString();
  const nameStr = finalFileName
  downloadElement.download = nameStr // 下载后文件名
  document.body.appendChild(downloadElement)
  downloadElement.click() // 点击下载
  document.body.removeChild(downloadElement) // 下载完成移除元素
  window.URL.revokeObjectURL(href) // 释放掉blob对象
}
