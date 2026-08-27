// 动态表单查询
export function dynamicsFormFind(params) {
  return httpPost(`${window.location.origin}/form-engine/api-formengine/formengine/findByKey`, params)
}

// 动态表单保存
export function dynamicsFormSave(params) {
  return httpPost(`${window.location.origin}/form-engine/api-formengine/formengine/formentry/save`, params)
}
