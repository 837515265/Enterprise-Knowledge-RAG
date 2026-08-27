export function exportExcel() {
  return httpGet("/api-dict/sysdatadict/excel/export", {}, { responseType: "blob", showLoading: true })
}

// 测试loading效果
export function testLoading() {
  return httpGet("/announce/selectAnnounceList", null, {
    showLoading: true,
    devMock: true
  })
}

// 测试页面接口
export function mockQueryPageList(params) {
  return httpGet("/foo", params, {
    devMock: true
  })
}

// 测试页面接口
export function mockQueryDetail(id) {
  return httpGet(
    `/foo/${id}`,
    {},
    {
      devMock: true
    }
  )
}

export function mockSaveDetail(params) {
  return httpPost("/foo", params, {
    devMock: true
  })
}
