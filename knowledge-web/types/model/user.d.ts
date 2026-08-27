export interface UserState {
  token: string
  name: string
  welcome: string
  avatar: string
  roles: boolean | string[]
  permissions: string[]
  info: Record<string, any>
}

export interface DeptInfo {
  createTime: any
  updateTime: any
  creator: any
  updator: any
  createName: any
  updateName: any
  params: any
  title: any
  key: any
  value: any
  label: any
  isLeaf: boolean
  deptId: any
  parentId: any
  areaId: any
  ancestors: any
  level: any
  leaf: any
  deptName: any
  orderNum: any
  leader: any
  phone: any
  email: any
  status: any
  delFlag: any
  createBy: any
  updateBy: any
  startTime: any
  endTime: any
  children: Array<any>
}

export interface RoleInfo {
  id: any
  createTime: string
  updateTime: string
  roleId: string
  code: string
  name: string
  userId: any
}

export interface AreaInfo {
  createTime: string
  updateTime: string
  creator: any
  updator: any
  createName: any
  updateName: any
  params: any
  title: string
  label: string
  key: string
  value: string
  isLeaf: boolean
  areaId: string
  areaName: string
  parentId: string
  ancestors: string
  level: number
  leaf: number
  startTime: any
  endTime: any
  children: Array<any>
}

export interface MenuInfo {
  id: any
  createTime: string
  updateTime: string
  parentId: any
  menuId: string
  menuName: any
  name: string
  css?: string
  url: string
  path: string
  sort: number
  type: number
  hidden: boolean
  perms: string
  icon: string
  component: string
  componentName: string
  pathMethod?: string
  subMenus: any
  roleId: any
  menuIds: any
  children: any
}

export interface AuthInfo {
  createTime: string
  updateTime: string
  creator: any
  updator: any
  createName: any
  updateName: any
  params: any
  authId: string
  authName: string
  startTime: any
  endTime: any
}

export interface UserInfo {
  id: any
  createTime: string
  updateTime: string
  userId: any
  deptId: string
  areaId: string
  nickName: string
  realName: string
  sex: string
  email: string
  phoneNumber: string
  idNum: string
  avatar: string
  password: string
  userType: string
  status: string
  delFlag: string
  loginIp: string
  loginDate: string
  createBy: string
  updateBy: string
  remark: string
  openId: any
  oldPassword: any
  newPassword: any
  dept: DeptInfo
  startTime: any
  endTime: any
  postIds: any
  roleIds: any
  roles: RoleInfo[]
  perms: any
  sysUserId: string
  username: string
  headImgUrl: string
  mobile: string
  enabled: boolean
  type: string
  area: AreaInfo
  menus: MenuInfo[]
  auths: AuthInfo[]
  roleId: any
  permissions: string[]
  isDisplayClientRoadshows: number
  clientForRoadshowsList: string
  accountNonExpired: boolean
  accountNonLocked: boolean
  credentialsNonExpired: boolean
  del: boolean
}
