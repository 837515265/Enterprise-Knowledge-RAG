import type { RouteConfig } from "vue-router"
import CommonView from "@/views/common/route-view.vue"

/**
 * ================= 布局页面 - 所有在默认布局下的页面应该添加在该配置中， 动态路由也会自动合并到改配置的children中 =================
 */
export const layoutRoute: RouteConfig = {
  path: "/",
  name: "Home",
  component: () => import("@/layout/kb-layout.vue"),
  redirect: "/knowledge/ask-ai",
  children: [
    {
      path: "ask-ai",
      name: "AskAI",
      component: () => import("@/views/knowledge/ask-ai.vue"),
      meta: { title: "问AI" }
    }
  ]
}

/**
 * ================= 知识库布局 - 使用独立侧栏布局，不受 basic-layout 影响 =================
 */
export const kbLayoutRoute: RouteConfig = {
  path: "/knowledge",
  name: "KnowledgeLayout",
  component: () => import("@/layout/kb-layout.vue"),
  redirect: "/knowledge/ask-ai",
  meta: { title: "知识库" },
  children: [
    {
      path: "workbench",
      name: "KbWorkbench",
      component: () => import("@/views/knowledge/workbench.vue"),
      meta: { title: "工作台" }
    },
    {
      path: "ask-ai",
      name: "AskAI",
      component: () => import("@/views/knowledge/ask-ai.vue"),
      meta: { title: "问AI" }
    },
    {
      path: "chat",
      name: "KbChat",
      component: () => import("@/views/knowledge/chat.vue"),
      meta: { title: "对话" }
    },
    {
      path: "search-files",
      name: "SearchFiles",
      component: () => import("@/views/knowledge/search-files.vue"),
      meta: { title: "搜文件" }
    },
    {
      path: "plaza",
      name: "KbPlaza",
      component: () => import("@/views/knowledge/plaza.vue"),
      meta: { title: "知识广场" }
    },
    {
      path: "list",
      name: "KbList",
      component: () => import("@/views/knowledge/kb-list.vue"),
      meta: { title: "我的知识库" }
    },
    {
      path: "parse-strategies",
      name: "KbParseStrategies",
      component: () => import("@/views/knowledge/strategy-manage.vue"),
      props: { strategyType: "parse" },
      meta: { title: "解析策略管理" }
    },
    {
      path: "retrieval-strategies",
      name: "KbRetrievalStrategies",
      component: () => import("@/views/knowledge/strategy-manage.vue"),
      props: { strategyType: "retrieval" },
      meta: { title: "检索策略管理" }
    },
    {
      path: "parse-tasks",
      name: "KbParseTasks",
      component: () => import("@/views/knowledge/parse-tasks.vue"),
      meta: { title: "任务进度" }
    },
    {
      path: "create",
      name: "KbCreate",
      component: () => import("@/views/knowledge/kb-create.vue"),
      meta: { title: "创建知识库" }
    },
    {
      path: "edit/:kbId",
      name: "KbEdit",
      component: () => import("@/views/knowledge/kb-create.vue"),
      props: true,
      meta: { title: "编辑知识库" }
    },
    {
      path: "detail/:kbId",
      name: "KbDetail",
      component: () => import("@/views/knowledge/kb-detail.vue"),
      props: true,
      meta: { title: "知识库详情" }
    }
  ]
}

/**
 * =================== 路由列表，布局路由layoutRoute 最终会在合并静态路由后并入该列表 ====================
 */
export const routes: RouteConfig[] = [
  {
    name: "404",
    path: "/404",
    component: () => import("@/views/common/404.vue"),
    meta: {
      title: "404"
    }
  },
  {
    name: "file-preview",
    path: "/file-preview/:id",
    component: () => import("@/views/common/file-preview-page.vue"),
    props: true,
    meta: {
      title: "文件预览"
    }
  },
  {
    path: "/redirect/:path(.*)",
    component: () => import("@/views/common/redirect.vue"),
    meta: {
      title: ""
    }
  }
]

export { CommonView }
