// 上传接口返回的数据
export interface FileResponseData {
  id: string
  name: string
  isImg: number
  contentType: string
  size: number
  path: string
  url: string
  source: string
  createTime: string
  updateTime: string
}

// fileList 中维护的数据项
export interface FileListItem {
  uid: string
  name: string
  status: "uploading" | "done" | "error" | "removed"
  url?: string
  responeseData: FileResponseData
  [key: string]: any
}
