/**
 * 用户相关 API
 * @module api/user
 */
/**
 * 根据 code 获取 token
 * @param {Object} param - 参数对象，包含 code、client_id、redirect_uri 等
 * @returns {Promise} 请求结果 Promise 对象，包含 token 信息
 */
export function getTokenByCode(param) {
  param.grant_type = "authorization_code"

  const prefix = import.meta.env.VITE_APP_GATEWAY_PREFIX?.startsWith("/") ? "" : "/"

  return httpPost(
    `${prefix}${import.meta.env.VITE_APP_GATEWAY_PREFIX}/token/getTokenCommon`,
    new URLSearchParams(param).toString(),
    {
      withoutToken: true,
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
      }
    }
  )
}

/**
 * 获取当前用户信息
 * @returns {Promise} 请求结果 Promise 对象，包含用户信息
 */
export function getInfo() {
  return httpGet("/api-user/users/current", null)
}

/**
 * 获取用户菜单树
 * @param {string} appName - 应用名称
 * @param {string} clientId - 客户端ID
 * @returns {Promise} 请求结果 Promise 对象，包含菜单树
 */
export function getUserMenuTree(appName, clientId) {
  return httpGet(
    `/api-user/menus/treeMenuWithClientIdOrAppNameScope?appName=${appName}&clientId=${clientId}&menuType=C`,
    null
  )
}

/**
 * 修改密码
 */
export function changePassword(params) {
  return httpPut("/api-user/resetPassword", params, { baseURL: "" })
}

/**
 * 按姓名、账号或手机号搜索用户
 * @param {string} keyword - 搜索关键词
 * @returns {Promise} 用户中心查询结果
 */
export function searchUserMembers(keyword) {
  if (keyword) {
    return httpGet("/api-user/findUserByNameAndRole", { userName: keyword })
  }
  return httpPost("/api-user/list?page=1&limit=20", {})
}

/**
 * 根据用户 ID 批量获取用户信息
 * @param {Array<string>} userIds - 用户 ID 列表
 * @returns {Promise} 用户中心查询结果
 */
export function getUsersByIds(userIds) {
  return httpPost("/api-user/getByUserIds", userIds)
}

/**
 * 按部门名称搜索部门
 * @param {string} keyword - 搜索关键词
 * @returns {Promise} 用户中心查询结果
 */
export function searchDeptMembers(keyword) {
  if (keyword) {
    return httpGet(`/api-user/sysdept/getByDeptName/${encodeURIComponent(keyword)}`, { limit: 20 })
  }
  return httpGet("/api-user/sysdept/tree", { parentId: "0", deptName: "" })
}

/**
 * 获取部门树
 * @param {string} parentId - 父部门 ID，空字符串表示根部门
 * @returns {Promise} 用户中心部门树
 */
export function getDeptTree(parentId = "") {
  return httpGet("/api-user/sysdept/tree", { parentId: parentId || "0", deptName: "" })
}

/**
 * 根据部门 ID 批量获取部门名称
 * @param {Array<string>} deptIds - 部门 ID 列表
 * @returns {Promise} 用户中心查询结果
 */
export function getDeptsByIds(deptIds) {
  return httpPost("/api-user/sysdept/getDeptInfoBatch", deptIds)
}

/**
 * 按角色名称搜索角色
 * @param {string} keyword - 搜索关键词
 * @returns {Promise} 用户中心查询结果
 */
export function searchRoleMembers(keyword) {
  return httpPost("/api-user/sysrole/list?page=1&limit=20", keyword ? { roleName: keyword } : {})
}

/**
 * 根据角色 ID 获取角色信息
 * @param {string} roleId - 角色 ID
 * @returns {Promise} 用户中心查询结果
 */
export function getRoleById(roleId) {
  return httpGet(`/api-user/sysrole/${roleId}`)
}
