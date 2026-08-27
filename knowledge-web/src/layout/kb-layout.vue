<template>
  <div class="kb-app">
    <!-- 侧栏 -->
    <aside
      class="kb-sidenav"
      :class="{
        'kb-sidenav--collapsed': collapsed
      }"
    >
      <div class="kb-brand-row">
        <div class="kb-brand" @click="goHome">
          <span class="kb-brand-mark">知</span>
          <span v-show="!collapsed" class="kb-brand-text">{{ appName }}</span>
        </div>
        <button type="button" class="kb-detail-toggle kb-detail-toggle--inside" @click="toggleSidenav" :title="collapsed ? '展开菜单' : '收起菜单'">
          <a-icon :type="collapsed ? 'menu-unfold' : 'menu-fold'" />
        </button>
      </div>

      <nav class="kb-nav">
        <router-link
          to="/knowledge/ask-ai"
          class="kb-nav-item"
          :class="{ 'is-active': isActiveGroup('ask-ai', 'chat', 'search-files') }"
          title="问AI"
        >
          <a-icon type="message" />
          <span v-show="!collapsed">问AI</span>
        </router-link>

        <div v-show="!collapsed" class="kb-nav-label">知识库</div>

        <router-link
          to="/knowledge/plaza"
          class="kb-nav-item"
          :class="{ 'is-active': isActive('plaza') }"
          title="知识广场"
        >
          <a-icon type="appstore" />
          <span v-show="!collapsed">知识广场</span>
        </router-link>

        <router-link
          to="/knowledge/list"
          class="kb-nav-item"
          :class="{ 'is-active': isActiveGroup('list', 'create', 'edit', 'detail') }"
          title="我的知识库"
        >
          <a-icon type="database" />
          <span v-show="!collapsed">我的知识库</span>
        </router-link>

        <div v-show="!collapsed" class="kb-nav-label">策略管理</div>

        <router-link
          to="/knowledge/parse-strategies"
          class="kb-nav-item"
          :class="{ 'is-active': isActive('parse-strategies') }"
          title="解析策略"
        >
          <a-icon type="apartment" />
          <span v-show="!collapsed">解析策略</span>
        </router-link>

        <router-link
          to="/knowledge/retrieval-strategies"
          class="kb-nav-item"
          :class="{ 'is-active': isActive('retrieval-strategies') }"
          title="检索策略"
        >
          <a-icon type="sliders" />
          <span v-show="!collapsed">检索策略</span>
        </router-link>

        <div v-show="!collapsed" class="kb-nav-label">运维</div>

        <router-link
          to="/knowledge/parse-tasks"
          class="kb-nav-item"
          :class="{ 'is-active': isActive('parse-tasks') }"
          title="任务进度"
        >
          <a-icon type="sync" />
          <span v-show="!collapsed">任务进度</span>
        </router-link>
      </nav>

      <!-- 侧栏底部用户信息 -->
      <div class="kb-sidenav-foot">
        <a-dropdown placement="topCenter">
          <div class="kb-user-trigger">
            <span class="kb-avatar">{{ userInitial }}</span>
            <span v-show="!collapsed" class="kb-user-name">{{ userName }}</span>
          </div>
          <template #overlay>
            <a-menu>
              <a-menu-item @click="goWorkbench">
                <a-icon type="dashboard" />
                <span>工作台</span>
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item @click="onLogout">
                <a-icon type="logout" />
                <span>退出登录</span>
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="kb-main">
      <transition name="kb-fade" mode="out-in">
        <keep-alive v-if="isKeepAlive">
          <router-view :key="$route.path" />
        </keep-alive>
        <router-view v-else :key="$route.path" />
      </transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useUserStoreWithOut } from "@/store/modules/user"

const appName = import.meta.env.VITE_APP_NAME || "知识库管理平台"
const route = useRoute()
const router = useRouter()
const userStore = useUserStoreWithOut()

const collapsed = ref(route.name === "KbDetail")

const userName = computed(() => userStore.name || "用户")
const userInitial = computed(() => (userName.value?.[0] || "U").toUpperCase())

const isKeepAlive = computed(() => route.meta?.keepAlive !== false)

/**
 * 判断当前路由是否匹配指定路径片段
 */
function isActive(segment: string): boolean {
  return route.path === `/knowledge/${segment}`
}

/**
 * 判断当前路由是否匹配一组路径片段（用于子页面高亮父级菜单）
 */
function isActiveGroup(...segments: string[]): boolean {
  return segments.some((s) => route.path.startsWith(`/knowledge/${s}`))
}

function goHome() {
  router.push("/knowledge/ask-ai")
}

function goWorkbench() {
  router.push("/knowledge/workbench")
}

/**
 * 全局切换知识库侧栏显示状态。
 */
function toggleSidenav() {
  collapsed.value = !collapsed.value
}

function onLogout() {
  userStore.logoutAction()
}
</script>

<style lang="less" scoped>
@sidebar-w: 252px;
@sidebar-collapsed-w: 64px;
@primary: #2563eb;
@primary-soft: #eff6ff;
@border: #e5e7eb;
@text: #0f172a;
@muted: #64748b;
@radius: 10px;

.kb-app {
  display: flex;
  min-height: 100vh;
  background: #f5f7fa;
}

/* ---- 侧栏 ---- */
.kb-sidenav {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  width: @sidebar-w;
  flex-shrink: 0;
  padding: 16px 12px 12px;
  background: #fff;
  border-right: 1px solid #f1f5f9;
  transition: width 0.2s ease;

  &--collapsed {
    width: @sidebar-collapsed-w;

    .kb-brand-row {
      flex-direction: column;
      justify-content: flex-start;
      gap: 10px;
      margin-bottom: 20px;
    }

    .kb-brand {
      flex: none;
      justify-content: center;
      width: 40px;
      height: 40px;
      padding: 2px;
    }

    .kb-brand-mark {
      width: 34px;
      height: 34px;
      border-radius: 9px;
    }

    .kb-nav {
      align-items: center;
    }

    .kb-nav-item {
      justify-content: center;
      width: 40px;
      height: 40px;
      padding: 0;

      &.is-active::before {
        left: -12px;
      }

      .anticon {
        font-size: 17px;
      }
    }

    .kb-sidenav-foot {
      display: flex;
      justify-content: center;
    }

    .kb-user-trigger {
      justify-content: center;
      width: 40px;
      height: 40px;
      padding: 0;
    }
  }
}

.kb-brand-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
}

.kb-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 6px;
  min-width: 0;
  cursor: pointer;
  flex: 1;
  border-radius: @radius;
  transition: background 0.15s;

  &:hover { background: #f8fafc; }
}

.kb-brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, @primary, #7c3aed);
  color: #fff;
  font-weight: 800;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.kb-brand-text {
  font-weight: 700;
  font-size: 15px;
  line-height: 1.25;
  color: @text;
  white-space: nowrap;
}

/* ---- 导航 ---- */
.kb-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
}

.kb-nav-label {
  margin: 14px 8px 6px;
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.kb-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: @radius;
  font-size: 14px;
  color: #475569;
  text-decoration: none;
  transition: all 0.15s ease;
  position: relative;

  &:hover {
    background: #f8fafc;
    color: #334155;
  }

  &.is-active {
    background: @primary-soft;
    color: #1d4ed8;
    font-weight: 600;

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 20px;
      border-radius: 0 3px 3px 0;
      background: @primary;
    }
  }

  .anticon {
    font-size: 16px;
  }
}

/* ---- 侧栏底部 ---- */
.kb-sidenav-foot {
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
}

.kb-user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: @radius;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: #f8fafc;
  }
}

.kb-avatar {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  background: #e0e7ff;
  color: #3730a3;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kb-user-name {
  font-size: 13px;
  color: @muted;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- 主内容 ---- */
.kb-main {
  flex: 1;
  min-width: 0;
  margin-left: @sidebar-w;
  transition: margin-left 0.28s ease;

  .kb-sidenav--collapsed ~ & {
    margin-left: @sidebar-collapsed-w;
  }
}

.kb-detail-toggle {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  color: #334155;
  background: rgba(255, 255, 255, 0.88);
  border-radius: 999px;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(12px);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.12);
    transform: translateY(-1px);
  }

  .anticon {
    font-size: 15px;
  }
}

.kb-detail-toggle--inside {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
}

/* ---- 过渡动画 ---- */
.kb-fade-enter-active,
.kb-fade-leave-active {
  transition: opacity 0.15s ease;
}

.kb-fade-enter,
.kb-fade-leave-to {
  opacity: 0;
}

</style>
