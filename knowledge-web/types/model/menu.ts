// 动态路由接口返回的类型
export type TreeMenuItem = {
    createTime: string
    updateTime: string
    params: any
    title: string
    key: string
    value: string
    roleCodeList: any
    menuId: string
    menuName: string
    parentId: string
    ancestors: any
    orderNum: number
    path: string
    component: string
    isFrame: number
    isCache: number
    menuType: string
    visible: string
    status: string
    perms: string
    icon: string
    serverContext: string
    clientId: string
    logo: any
    name: any
    bg: any
    copyright: any
    accountType: string
    componentName: string
    subApp: boolean
    whetherTabs: any
    whetherSide: any
    createBy: string
    updateBy: string
    remark: string
    url: string
    css: any
    pathMethod: any
    tenantId: any
    startTime: any
    endTime: any
    children?: TreeMenuItem[]
  }

  

  export type TreeMenuList = TreeMenuItem[]