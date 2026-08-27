/**
 * 跳转到登录页，获取认证code
 */
export function goToLoginToGetCode() {
  const originUrl = import.meta.env.DEV ? import.meta.env.VITE_PROXY_URL : window.location.origin
  // 登录地址 跳转的时候再拼接重定向url！！
  const loginPath = `${originUrl}/api-uaa/oauth/authorize?response_type=code&client_id=${
    import.meta.env.VITE_LDSK_CLIENT_ID
  }&scope=all` // &state=xxx&redirect_uri=
  const currentUrl = window.location.origin + window.location.pathname + window.location.search
  const noHashUrl = `${currentUrl.replace(/\/+$/, "")}/`
  // state 用于记录跳转前的 hash 路径，redirect_uri 用于回跳
  window.location.href = `${loginPath}&state=${window.location.hash.replace("#", "") || "/"}&redirect_uri=${noHashUrl}`
}

/**
 * 回到登录页面并注销当前登录状态
 * @param {string} token 当前使用的token
 */
export function goToLoginToRemoveAuth(token: string) {
  const originUrl = import.meta.env.DEV ? import.meta.env.VITE_PROXY_URL : window.location.origin
  window.location.href = `${originUrl}/api-uaa/oauth/remove/token?token=${token}&redirect_uri=${window.location.href}`
}
