import { useUserStoreWithOut } from "@/store/modules/user"

/**
 * 查询当前用户是否具有某个权限编码 或 某个权限编码组成的数组中任意一个编码 的权限
 * @param {string | string[]} permissionKey 要查询的权限或者权限数组
 *
 */
export function hasPermission(permissionKey: string | string[]): boolean {
  const userStore = useUserStoreWithOut()
  const permissions = userStore.permissions

  permissionKey = Array.isArray(permissionKey) ? permissionKey : [permissionKey]

  const hasPermission = permissionKey.some((actionName) => {
    return permissions.includes(actionName)
  })

  return hasPermission
}
