<template>
  <div class="ask-page">
    <div class="ask-bg ask-bg-primary"></div>
    <div class="ask-bg ask-bg-secondary"></div>
    <div class="ask-layout">
      <div class="ask-main">
        <div class="ask-hero">
          <div class="ask-hero-icon">
            <a-icon type="robot" />
          </div>
          <h2>智能问答</h2>
          <p>连接知识库、文件与业务经验，快速获得可追溯的答案与检索线索</p>
        </div>

        <div class="ask-workbench">
          <div class="ask-workbench-head">
            <div>
              <span class="ask-workbench-label">今天想了解什么？</span>
              <strong>{{ mode === "qa" ? "向知识库提问" : "在文件中搜索" }}</strong>
            </div>
            <span class="ask-workbench-status"><i></i> 已连接知识服务</span>
          </div>

          <div class="ask-composer">
            <div class="ask-composer-toolbar">
              <div class="ask-mode-group">
                <button
                  type="button"
                  class="ask-mode-btn"
                  :class="{ 'is-active': mode === 'qa' }"
                  @click="setAskMode('qa')"
                >
                  <a-icon type="message" /> AI 问答
                </button>
                <button
                  type="button"
                  class="ask-mode-btn"
                  :class="{ 'is-active': mode === 'file' }"
                  @click="setAskMode('file')"
                >
                  <a-icon type="search" /> 搜文件
                </button>
              </div>
            </div>
            <div class="ask-input-area">
              <a-textarea
                v-model="inputText"
                class="ask-textarea"
                :placeholder="
                  mode === 'qa' ? '输入问题，AI 会基于知识库为你整理答案…' : '输入关键词，快速定位相关文件与内容…'
                "
                :auto-size="{ minRows: 3, maxRows: 5 }"
                @pressEnter.ctrl="onSubmit"
              />
            </div>
            <div class="ask-composer-footer">
              <div class="ask-send-options">
                <a-select
                  v-model="scope"
                  class="ask-scope"
                  dropdown-class-name="ask-kb-dropdown"
                  placeholder="选择知识库"
                  :get-popup-container="getSelectPopupContainer"
                >
                  <a-select-option value="">全部知识库</a-select-option>
                  <a-select-option v-for="kb in kbList" :key="kb.id" :value="kb.id">
                    {{ kb.name }}
                  </a-select-option>
                </a-select>
                <button
                  type="button"
                  class="ask-online-btn"
                  :class="{ 'is-active': onlineSearch }"
                  @click="onlineSearch = !onlineSearch"
                >
                  <a-icon type="global" /> 联网搜索
                </button>
                <button
                  type="button"
                  class="ask-online-btn ask-thinking-btn"
                  :class="{ 'is-active': enableThinking }"
                  @click="enableThinking = !enableThinking"
                >
                  <a-icon type="thunderbolt" /> 深度思考
                </button>
              </div>
              <button type="button" class="ask-send-btn" :class="{ 'is-ready': inputText.trim() }" @click="onSubmit">
                <a-icon type="arrow-up" /> 发送
              </button>
            </div>
          </div>

          <div class="ask-history">
            <div class="ask-history-title">
              <div>
                <span>历史记录</span>
                <small>继续之前的思路</small>
              </div>
              <router-link v-if="hasMoreSessions" to="/knowledge/chat" class="ask-history-more">
                查看更多 <a-icon type="right" />
              </router-link>
            </div>
            <div v-if="recentSessions.length" class="ask-history-list">
              <button
                v-for="s in recentSessions"
                :key="s.id"
                type="button"
                class="ask-history-item"
                :class="{ 'is-active': selectedSession === s.id }"
                @click="selectedSession = s.id"
              >
                <span class="ask-history-icon">
                  <a-icon type="message" />
                </span>
                <span class="ask-history-text">
                  <strong>{{ s.title || "未命名会话" }}</strong>
                  <small>{{ s.updateTime || s.time || "最近对话" }}</small>
                </span>
                <a-icon type="right" class="ask-history-arrow" />
              </button>
            </div>
            <div v-else class="ask-history-empty">
              <a-icon type="inbox" />
              <span>暂无对话记录</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getChatSessions, getKnowledgeBaseList } from "@/api/knowledge"
import { useUserStoreWithOut } from "@/store/modules/user"

const router = useRouter()
const userStore = useUserStoreWithOut()

const mode = ref<"qa" | "file">("qa")
const scope = ref("")
const inputText = ref("")
const onlineSearch = ref(false)
const enableThinking = ref(false)
const selectedSession = ref<number | null>(null)
const sessions = ref<any[]>([])
const kbList = ref<any[]>([])

const recentSessions = computed(() => sessions.value.slice(0, 3))
const hasMoreSessions = computed(() => sessions.value.length > 3)

function unwrapListResult(payload: any) {
  if (Array.isArray(payload?.data)) return payload.data
  if (Array.isArray(payload?.datas)) return payload.datas
  return []
}

async function loadRecentSessions() {
  const userId = await getRequiredUserId()
  const res = await getChatSessions({ userId, pageSize: 4 })
  sessions.value = unwrapListResult(res)
}

async function loadKbList() {
  const res = await getKnowledgeBaseList({ pageSize: 100 })
  kbList.value = unwrapListResult(res)
}

/** 恢复问 AI 首页默认输入态（侧栏再次进入时 keep-alive 会复用实例） */
function resetAskFormState() {
  mode.value = "qa"
  scope.value = ""
  inputText.value = ""
  onlineSearch.value = false
  enableThinking.value = false
  selectedSession.value = null
}

onMounted(async () => {
  try {
    await Promise.allSettled([loadRecentSessions(), loadKbList()])
  } catch (e) {
    console.error(e)
  }
})

/** 从其他页回到问 AI 时组件被 keep-alive 复用，需重置表单并刷新历史记录 */
onActivated(() => {
  resetAskFormState()
  loadRecentSessions().catch(console.error)
})

/**
 * 获取当前真实登录用户主键，缺失时阻断问AI会话读取，不使用默认用户兜底。
 */
async function getRequiredUserId() {
  const userInfo = userStore.userInfo || (await userStore.getInfoAction())
  const userId = userInfo?.userId
  if (userId === undefined || userId === null || `${userId}`.trim() === "") {
    message.error("未获取到当前登录用户，请重新登录后再使用问AI")
    throw new Error("缺少当前登录用户 userId")
  }
  return `${userId}`.trim()
}

/**
 * 下拉挂到 `document.body`，避免被带 overflow 的容器裁切（AntD Select 浮层在 body 下时样式用全局类名覆盖）。
 */
function getSelectPopupContainer() {
  return document.body
}

function buildSearchFilesQuery(keyword = "") {
  const text = `${keyword || ""}`.trim()
  const query: Record<string, string> = {}
  if (text) {
    query.q = text
  }
  if (scope.value) {
    query.kbId = scope.value
  }
  return query
}

function goSearchFilesPage(keyword = "") {
  router.push({
    path: "/knowledge/search-files",
    query: buildSearchFilesQuery(keyword)
  })
}

function setAskMode(nextMode: "qa" | "file") {
  mode.value = nextMode
}

function onSubmit() {
  const text = inputText.value.trim()
  if (!text) return

  if (mode.value === "file") {
    goSearchFilesPage(text)
    return
  }

  router.push({
    name: "KbChat",
    query: {
      q: text,
      kbId: scope.value || undefined,
      onlineSearch: onlineSearch.value ? "1" : undefined,
      enableThinking: enableThinking.value ? "1" : undefined
    }
  })
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@primary-light: #eff6ff;
@border: #e5e7eb;
@text: #0f172a;
@muted: #64748b;
@violet: #7c3aed;
@cyan: #06b6d4;

.ask-page {
  position: relative;
  overflow: hidden;
  padding: 22px 28px;
  min-height: 100vh;
  background: radial-gradient(circle at 26% 12%, rgba(37, 99, 235, 0.12), transparent 28%),
    radial-gradient(circle at 78% 18%, rgba(124, 58, 237, 0.12), transparent 26%),
    linear-gradient(180deg, #f8fbff 0%, #f4f7fb 100%);

  &::before {
    position: absolute;
    inset: 0;
    pointer-events: none;
    content: "";
    background-image: linear-gradient(rgba(37, 99, 235, 0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(37, 99, 235, 0.06) 1px, transparent 1px);
    background-size: 38px 38px;
    opacity: 0.42;
    mask-image: linear-gradient(180deg, #000 0%, transparent 68%);
  }
}

.ask-bg {
  position: absolute;
  pointer-events: none;
  border-radius: 999px;
  filter: blur(6px);
}

.ask-bg-primary {
  top: 86px;
  left: 38%;
  width: 240px;
  height: 240px;
  background: rgba(37, 99, 235, 0.08);
}

.ask-bg-secondary {
  right: 8%;
  bottom: 18%;
  width: 320px;
  height: 320px;
  background: rgba(6, 182, 212, 0.08);
}

.ask-layout {
  position: relative;
  z-index: 1;
  margin: 0 auto;
  max-width: 880px;
}

/* ---- 主区域 ---- */
.ask-main {
  min-width: 0;
}

.ask-hero {
  padding: 16px 0 22px;
  text-align: center;
}

.ask-hero-icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 12px;
  width: 58px;
  height: 58px;
  color: #fff;
  background: radial-gradient(circle at 32% 24%, rgba(255, 255, 255, 0.55), transparent 28%),
    linear-gradient(135deg, @primary, @violet 62%, @cyan);
  border: 1px solid rgba(255, 255, 255, 0.86);
  border-radius: 18px;
  box-shadow: 0 18px 34px rgba(37, 99, 235, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.45);

  .anticon {
    font-size: 28px;
  }
}

.ask-hero h2 {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 800;
  line-height: 1.22;
  color: @text;
}

.ask-hero p {
  margin: 0;
  font-size: 14px;
  color: @muted;
}

/* ---- Workbench ---- */
.ask-workbench {
  position: relative;
  padding: 16px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.76)),
    linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(124, 58, 237, 0.08));
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 28px;
  box-shadow: 0 30px 70px rgba(15, 23, 42, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);

  &::before {
    position: absolute;
    top: 18px;
    right: 22px;
    width: 160px;
    height: 80px;
    pointer-events: none;
    content: "";
    background: radial-gradient(circle, rgba(37, 99, 235, 0.16), transparent 68%);
  }
}

.ask-workbench-head {
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;

  strong {
    display: block;
    margin-top: 2px;
    font-size: 18px;
    color: @text;
  }
}

.ask-workbench-label {
  font-size: 12px;
  font-weight: 600;
  color: @muted;
}

.ask-workbench-status {
  display: inline-flex;
  align-items: center;
  padding: 7px 11px;
  font-size: 12px;
  color: #0f766e;
  background: rgba(240, 253, 250, 0.9);
  border: 1px solid rgba(153, 246, 228, 0.76);
  border-radius: 999px;
  gap: 6px;

  i {
    width: 7px;
    height: 7px;
    background: #14b8a6;
    border-radius: 50%;
    box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.14);
  }
}

/* ---- Composer ---- */
.ask-composer {
  position: relative;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 22px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.07);
}

.ask-composer-toolbar {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  padding: 14px 16px 12px;
  gap: 12px;
  border-bottom: 1px solid rgba(241, 245, 249, 0.92);
}

.ask-mode-group {
  display: flex;
  padding: 3px;
  background: #eef2ff;
  border: 1px solid rgba(219, 234, 254, 0.9);
  border-radius: 13px;
  gap: 4px;
}

.ask-mode-btn {
  display: flex;
  align-items: center;
  padding: 7px 15px;
  font-size: 13px;
  font-weight: 500;
  color: @muted;
  background: transparent;
  border: none;
  border-radius: 8px;
  transition: all 0.15s;
  gap: 6px;
  cursor: pointer;

  &.is-active {
    font-weight: 600;
    color: @primary;
    background: #fff;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.12);
  }
}

.ask-scope {
  min-width: 200px;
  max-width: 280px;

  ::v-deep(.ant-select-selection) {
    height: 32px;
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid rgba(203, 213, 225, 0.95) !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }

  ::v-deep(.ant-select-selection__rendered) {
    margin-right: 36px;
    margin-left: 12px;
    line-height: 30px;
  }

  ::v-deep(.ant-select-selection-selected-value),
  ::v-deep(.ant-select-selection-placeholder) {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
  }

  ::v-deep(.ant-select-selection-placeholder) {
    font-weight: 500;
    color: #94a3b8;
  }

  ::v-deep(.ant-select-arrow) {
    right: 10px;
    color: #64748b;
  }

  &:hover ::v-deep(.ant-select-selection),
  &.ant-select-focused ::v-deep(.ant-select-selection) {
    border-color: rgba(147, 197, 253, 0.95) !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
  }
}

.ask-input-area {
  padding: 16px 18px 12px;
}

.ask-textarea {
  padding: 0 !important;
  font-size: 16px !important;
  line-height: 1.7 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  resize: none;

  &::placeholder {
    color: #94a3b8;
  }
}

.ask-composer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0), rgba(248, 250, 252, 0.78));
  gap: 12px;
}

.ask-send-options {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.ask-online-btn {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  height: 32px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  color: #475569;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 10px;
  transition: all 0.2s ease;
  gap: 5px;
  cursor: pointer;

  .anticon {
    color: #64748b;
  }

  &:hover,
  &.is-active {
    color: @primary;
    background: #eff6ff;
    border-color: rgba(147, 197, 253, 0.9);
    box-shadow: 0 8px 18px rgba(37, 99, 235, 0.1);

    .anticon {
      color: @primary;
    }
  }
}

.ask-send-btn {
  display: flex;
  align-items: center;
  padding: 9px 24px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, @primary, #1d4ed8);
  border: none;
  border-radius: 13px;
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.22);
  transition: all 0.2s ease;
  gap: 6px;
  cursor: pointer;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 26px rgba(37, 99, 235, 0.32);
  }

  &.is-ready {
    background: linear-gradient(135deg, @primary, @violet);
  }
}

/* ---- 历史记录 ---- */
.ask-history {
  padding: 2px 2px 0;
  margin-top: 14px;
}

.ask-history-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;

  span {
    display: block;
    font-size: 13px;
    font-weight: 700;
    color: @text;
  }

  small {
    font-size: 12px;
    color: #94a3b8;
  }
}

.ask-history-more {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  color: @primary;
  background: rgba(239, 246, 255, 0.78);
  border: 1px solid rgba(191, 219, 254, 0.82);
  border-radius: 999px;
  gap: 2px;
}

.ask-history-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.ask-history-item {
  display: grid;
  align-items: center;
  padding: 13px 12px;
  text-align: left;
  color: #475569;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 15px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.04);
  transition: all 0.2s ease;
  grid-template-columns: 34px minmax(0, 1fr) 14px;
  gap: 8px;
  cursor: pointer;

  &:hover {
    color: @primary;
    background: #fff;
    border-color: rgba(147, 197, 253, 0.9);
    box-shadow: 0 14px 28px rgba(37, 99, 235, 0.1);
    transform: translateY(-1px);
  }
}

.ask-history-icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 34px;
  height: 34px;
  color: @primary;
  background: linear-gradient(135deg, #eff6ff, #eef2ff);
  border: 1px solid rgba(191, 219, 254, 0.82);
  border-radius: 12px;
}

.ask-history-text {
  min-width: 0;

  strong,
  small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  strong {
    font-size: 13px;
    font-weight: 700;
    color: #334155;
  }

  small {
    margin-top: 3px;
    font-size: 11px;
    color: #94a3b8;
  }
}

.ask-history-arrow {
  font-size: 11px;
  color: #cbd5e1;
}

.ask-history-empty {
  display: flex;
  align-items: center;
  padding: 16px;
  font-size: 13px;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.62);
  border: 1px dashed rgba(203, 213, 225, 0.9);
  border-radius: 15px;
  gap: 8px;
}

@media (max-width: 900px) {
  .ask-history-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .ask-page {
    padding: 18px 14px;
  }

  .ask-workbench-head,
  .ask-composer-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .ask-send-options {
    align-items: stretch;
    flex-direction: column;
  }

  .ask-scope,
  .ask-online-btn,
  .ask-send-btn {
    width: 100%;
  }

  .ask-history-list {
    grid-template-columns: 1fr;
  }
}
</style>

<style lang="less">
@ask-primary: #2563eb;

/* 问 AI 页知识库下拉的浮层挂在 body 上，需与 scoped 分开写 */
.ask-kb-dropdown.ant-select-dropdown {
  padding: 6px 0;
  background: #fff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.12);
}

.ask-kb-dropdown .ant-select-dropdown-menu {
  margin: 0;
  max-height: 320px;
  border-radius: 0;
  box-shadow: none;
}

.ask-kb-dropdown .ant-select-dropdown-menu-item {
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1.4;
  color: #334155;
}

.ask-kb-dropdown .ant-select-dropdown-menu-item:hover {
  color: @ask-primary;
  background: #eff6ff;
}

.ask-kb-dropdown .ant-select-dropdown-menu-item-selected {
  font-weight: 600;
  color: @ask-primary;
  background: rgba(239, 246, 255, 0.95);
}
</style>
