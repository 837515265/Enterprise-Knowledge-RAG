// 后台分页接口返回的字段
export enum PAGE_ENUM {
  // 分页字段
  PAGE_NUM = "pageNo",
  // 页码字段
  PAGE_SIZE = "pageSize",
  // 总数
  TOTAL = "count",
  // 数据列表字段
  DATALIST = "data",
  // 接口请求时的起始页码, 传入0则代表接口以0作为第一页数据，以此类推
  START_PAGENUM = 1
}
