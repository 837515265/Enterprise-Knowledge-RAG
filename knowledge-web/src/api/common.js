/**
 * 获取指定code列表对应的字典值
 * @param codes 字典code数组
 * @returns {Promise<any>} 请求结果
 */
export const getDicts = (codes) => {
  return httpPost("/api-cmv2/sysdatadictvalue/findByDictCode", { data: codes })
}

/**
 * 上传文件到oss
 * @param {string|number} fileId 文件id
 * @returns {Promise<any>} 请求结果
 */
export const uploadFile = (file, config = {}) => {
  const formData = new FormData()
  formData.append("file", file)
  return httpPost("/api-file/files/upload", formData, config)
}

/**
 * 基于文件id获取文件的详细信息
 * @param {string|number} fileId 文件id
 * @returns {Promise<any>} 请求结果
 */
export const getFileByFileId = (fileId) => {
  return httpGet(`/api-file/files/view/${fileId}`)
}

/**
 * 基于文件id下载文件
 * @param {string|number} fileId 文件id
 * @returns {Promise<Blob>} 文件二进制流
 */
export const downLoadByFileId = (fileId) => {
  return httpGet(`/api-file/files/${fileId}`, {}, { responseType: "blob", withNativeResponse: true })
}

/**
 * 参数管理-根据code获取参数
 * @param {string} code 参数code
 * @returns {Promise<any>} 请求结果
 */
export function getParamByCode(code) {
  return httpGet("/api-cmv2/sysparam/findByCode", {
    platform: "ewrs",
    paramCode: code
  })
}
