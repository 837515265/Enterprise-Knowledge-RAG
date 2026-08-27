<template>
  <div class="chat-page" :class="{ 'chat-page--embedded': embedded, 'chat-page--with-sessions': showSessions }">
    <div class="chat-bg chat-bg-primary"></div>
    <div class="chat-bg chat-bg-secondary"></div>
    <div class="chat-container">
      <div class="chat-shell">
        <!-- 左侧会话列表 -->
        <aside v-if="showSessions" class="chat-sessions">
          <div class="chat-sessions-head">
            <div>
              <span>会话列表</span>
              <small>知识问答记录</small>
            </div>
            <button type="button" class="chat-new-btn" @click="newSession"><a-icon type="plus" /> 新建</button>
          </div>
          <div class="chat-session-list">
            <div
              v-for="s in sessions"
              :key="s.id"
              class="chat-session-item"
              :class="{ 'is-active': getSessionKey(currentSessionId) === getSessionKey(s.id) }"
              @click="selectSession(s)"
            >
              <a-icon type="message" class="chat-session-icon" />
              <div class="chat-session-text">
                <span>{{ s.title || "未命名会话" }}</span>
                <small>{{ s.updateTime || s.time || "" }}</small>
              </div>
              <a-popconfirm title="确认删除该会话？" ok-text="删除" cancel-text="取消" @confirm="deleteSession(s)">
                <button type="button" class="chat-session-delete" title="删除会话" @click.stop>
                  <a-icon type="delete" />
                </button>
              </a-popconfirm>
            </div>
            <div v-if="!sessions.length" class="chat-session-empty">
              <a-icon type="inbox" style="font-size: 28px; color: #d1d5db" />
              <span>暂无会话</span>
            </div>
          </div>
        </aside>

        <!-- 右侧聊天面板 -->
        <div class="chat-panel">
          <div class="chat-toolbar">
            <div class="chat-toolbar-left">
              <div class="chat-toolbar-title">
                <strong>{{ currentSessionId ? "知识库对话" : "开始新的对话" }}</strong>
                <span>AI 会基于所选知识范围生成答案</span>
              </div>
              <template v-if="fixedKbId">
                <div class="chat-fixed-actions">
                  <span class="chat-scope-fixed">{{ fixedKbName || "当前知识库" }}</span>
                  <button type="button" class="chat-search-file-btn" @click="() => goSearchFiles()">
                    <a-icon type="search" /> 搜文件
                  </button>
                </div>
              </template>
              <template v-else>
                <a-select
                  v-model="chatScope"
                  class="chat-scope-select"
                  dropdown-class-name="chat-kb-dropdown"
                  placeholder="选择知识库"
                  :get-popup-container="getKbSelectPopupContainer"
                >
                  <a-select-option value="">全部知识库</a-select-option>
                  <a-select-option v-for="kb in kbOptions" :key="kb.id" :value="kb.id">{{ kb.name }}</a-select-option>
                </a-select>
              </template>
            </div>
          </div>

          <!-- 消息流 -->
          <div ref="threadRef" class="chat-thread">
            <div v-if="loadingSessionMessages && !displayedMessages.length" class="chat-session-loading">
              <a-icon type="loading" />
              <span>正在加载会话内容...</span>
            </div>

            <div v-else-if="!displayedMessages.length" class="chat-welcome">
              <div class="chat-welcome-icon">
                <a-icon type="robot" />
              </div>
              <h3>开始对话</h3>
              <p>选择知识范围，输入问题，AI 会帮你从知识库和文件中整理答案</p>
              <div class="chat-welcome-prompts">
                <button v-for="item in welcomePrompts" :key="item" type="button" @click="usePrompt(item)">
                  {{ item }}
                </button>
              </div>
            </div>

            <div v-for="msg in displayedMessages" :key="msg.id" class="chat-msg" :class="'chat-msg--' + msg.role">
              <div class="chat-msg-avatar">
                <a-icon :type="msg.role === 'user' ? 'user' : 'robot'" />
              </div>
              <div class="chat-msg-content">
                <div v-if="msg.role === 'assistant' && msg.reasoningContent" class="chat-reasoning">
                  <button type="button" class="chat-reasoning-head" @click="msg.reasoningOpen = !msg.reasoningOpen">
                    <span><a-icon type="bulb" />思考过程</span>
                    <a-icon :type="msg.reasoningOpen ? 'up' : 'down'" />
                  </button>
                  <pre v-show="msg.reasoningOpen" class="chat-reasoning-body">{{ msg.reasoningContent }}</pre>
                </div>
                <template v-if="msg.role === 'assistant'">
                  <div
                    v-if="msg.content"
                    class="chat-msg-bubble chat-markdown"
                    v-html="renderMarkdown(msg.content)"
                  ></div>
                  <div v-else-if="msg.generating" class="chat-msg-bubble chat-msg-typing">
                    <span></span><span></span><span></span>
                  </div>
                </template>
                <div v-else class="chat-msg-bubble">{{ msg.content }}</div>
                <div v-if="msg.role === 'assistant' && msg.source" class="chat-msg-source">
                  <a-icon type="link" /> {{ msg.source }}
                </div>
                <div v-if="msg.role === 'assistant' && msg.intentPayload" class="chat-intent-card">
                  <div class="chat-intent-head">
                    <span>
                      <a-icon :type="msg.intentPayload.intent === 'file_recent' ? 'clock-circle' : 'search'" />
                      {{ getIntentTitle(msg.intentPayload) }}
                    </span>
                    <button
                      v-if="msg.intentPayload.intent === 'file_search'"
                      type="button"
                      @click="goSearchFiles(msg.intentPayload.query)"
                    >
                      <a-icon type="search" /> 搜文件
                    </button>
                  </div>
                  <div v-if="msg.intentPayload.files && msg.intentPayload.files.length" class="chat-intent-files">
                    <button
                      v-for="file in msg.intentPayload.files"
                      :key="getIntentFileKey(file)"
                      type="button"
                      class="chat-intent-file"
                      @click="openIntentFile(file)"
                    >
                      <a-icon type="file" />
                      <span>{{ decodeDisplayText(file.title || file.name || "未命名文件") }}</span>
                      <small>{{ file.kbName || "" }}</small>
                      <em>{{ file.updateTime || file.size || "" }}</em>
                    </button>
                  </div>
                </div>
                <div v-if="msg.role === 'assistant' && msg.citations && msg.citations.length" class="chat-citations">
                  <button type="button" class="chat-citations-head" @click="msg.citationsOpen = !msg.citationsOpen">
                    <span><a-icon type="file-text" />引用来源 {{ msg.citations.length }}</span>
                    <a-icon :type="msg.citationsOpen ? 'up' : 'down'" />
                  </button>
                  <div v-show="msg.citationsOpen" class="chat-citation-list">
                    <button
                      v-for="item in msg.citations"
                      :key="getCitationKey(item)"
                      type="button"
                      class="chat-citation-item"
                      @click="openCitationFile(item)"
                    >
                      <div class="chat-citation-title">
                        <span class="chat-citation-index">[{{ item.index || "-" }}]</span>
                        <strong>{{ getCitationTitle(item) }}</strong>
                        <small v-if="isImageCitation(item)" class="chat-citation-image-tag">
                          <a-icon type="picture" />图片
                        </small>
                        <small v-if="item.score !== undefined && item.score !== null">
                          {{ formatCitationScore(item.score) }}
                        </small>
                      </div>
                      <div class="chat-citation-file">
                        <a-icon type="paper-clip" />
                        <span>{{ getCitationFileName(item) }}</span>
                        <em v-if="getCitationPage(item)">第 {{ getCitationPage(item) }} 页</em>
                      </div>
                      <div v-if="getCitationGraphPath(item)" class="chat-citation-graph">
                        <a-icon type="share-alt" />
                        <span>{{ formatCitationGraphPath(getCitationGraphPath(item)) }}</span>
                      </div>
                      <p>{{ item.content || "暂无片段内容" }}</p>
                    </button>
                  </div>
                </div>
                <div v-if="msg.role === 'assistant'" class="chat-msg-actions">
                  <button
                    type="button"
                    title="有帮助"
                    :class="{ 'is-active': isFeedbackActive(msg, 'like') }"
                    @click="onFeedback(msg, 'like')"
                  >
                    <a-icon type="like" />
                  </button>
                  <button
                    type="button"
                    title="无帮助"
                    :class="{ 'is-active': isFeedbackActive(msg, 'dislike') }"
                    @click="onFeedback(msg, 'dislike')"
                  >
                    <a-icon type="dislike" />
                  </button>
                  <button type="button" title="复制" @click="onCopy(msg)">
                    <a-icon type="copy" />
                  </button>
                  <button type="button" title="重新生成" @click="onRegenerate">
                    <a-icon type="reload" />
                  </button>
                </div>
              </div>
            </div>

            <div
              v-if="isCurrentSessionGenerating && !hasStreamingAssistantMessage"
              class="chat-msg chat-msg--assistant"
            >
              <div class="chat-msg-avatar">
                <a-icon type="robot" />
              </div>
              <div class="chat-msg-content">
                <div class="chat-msg-bubble chat-msg-typing"><span></span><span></span><span></span></div>
              </div>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-composer">
            <div class="chat-composer-inner">
              <textarea
                v-model="inputText"
                rows="3"
                placeholder="输入问题，Enter 发送，Shift+Enter 换行，例如：帮我总结这份制度的审批要求"
                @keydown="onKeydown"
              ></textarea>
              <div class="chat-composer-footer">
                <div class="chat-send-options">
                  <button
                    type="button"
                    class="chat-option-btn"
                    :class="{ 'is-active': onlineSearch }"
                    @click="onlineSearch = !onlineSearch"
                  >
                    <a-icon type="global" /> 联网搜索
                  </button>
                  <button
                    type="button"
                    class="chat-option-btn chat-thinking-btn"
                    :class="{ 'is-active': enableThinking }"
                    @click="enableThinking = !enableThinking"
                  >
                    <a-icon type="thunderbolt" /> 深度思考
                  </button>
                  <button
                    type="button"
                    class="chat-option-btn"
                    :class="{ 'is-active': graphSearch }"
                    title="先按原有方式召回，再用 Neo4j 扩展关联关系"
                    @click="graphSearch = !graphSearch"
                  >
                    <a-icon type="share-alt" /> 图关系
                  </button>
                </div>
                <button type="button" class="chat-send-btn" :disabled="generating" @click="onSend">
                  <a-icon type="arrow-up" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import MarkdownIt from "markdown-it"
import { decodeDisplayText } from "@/utils/logic/decodeDisplayText"
import { previewFile } from "@/utils/previewFile"
import {
  deleteChatSession,
  getChatSessions,
  getChatMessages,
  getKnowledgeBaseList,
  updateChatMessageFeedback
} from "@/api/knowledge"
import { useUserStoreWithOut } from "@/store/modules/user"

const route = useRoute()
const router = useRouter()
const userStore = useUserStoreWithOut()
const props = withDefaults(
  defineProps<{
    fixedKbId?: string | number
    fixedKbName?: string
    embedded?: boolean
    initialQuestion?: string
    initialKbId?: string | number
  }>(),
  {
    fixedKbId: "",
    fixedKbName: "",
    embedded: false,
    initialQuestion: "",
    initialKbId: ""
  }
)

const fixedKbId = computed(() => (props.fixedKbId ? String(props.fixedKbId) : ""))
const fixedKbName = computed(() => props.fixedKbName)
const embedded = computed(() => props.embedded)
const showSessions = computed(() => !embedded.value || fixedKbId.value)
const initialQ = computed(() => props.initialQuestion || (route.query.q as string) || "")
const initialKbId = computed(() => (props.initialKbId ? String(props.initialKbId) : (route.query.kbId as string) || ""))
const NEW_SESSION_KEY = "__new__"

const sessions = ref<any[]>([])
const currentSessionId = ref<string | null>(null)
const messages = ref<any[]>([])
const inputText = ref("")
const generating = ref(false)
const streamingSessionKey = ref("")
const streamingRequestId = ref(0)
const loadingSessionMessages = ref(false)
const sessionLoadRequestId = ref(0)
const routeQuestionConsuming = ref(false)
let lastConsumedRouteQuestionKey = ""
const threadRef = ref<HTMLElement | null>(null)
const chatScope = ref("")
const kbOptions = ref<any[]>([])
const currentSessionKey = computed(() => getSessionKey(currentSessionId.value))
const displayedMessages = computed(() =>
  messages.value.filter((item) => getSessionKey(item.__sessionKey) === currentSessionKey.value)
)
const hasStreamingAssistantMessage = computed(() =>
  displayedMessages.value.some((item) => item.role === "assistant" && item.generating)
)
const isCurrentSessionGenerating = computed(
  () => generating.value && streamingSessionKey.value && streamingSessionKey.value === currentSessionKey.value
)
const onlineSearch = ref(route.query.onlineSearch === "1")
const enableThinking = ref(route.query.enableThinking === "1")
const graphSearch = ref(route.query.graph === "1")
const thinkingBudget = ref(1024)
const welcomePrompts = ["制度条款怎么理解？", "帮我查找相关操作手册", "总结知识库最近更新", "这份文件有哪些风险点？"]
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: true
})
const defaultLinkOpen =
  markdown.renderer.rules.link_open || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet("target", "_blank")
  token.attrSet("rel", "noopener noreferrer")
  return defaultLinkOpen(tokens, idx, options, env, self)
}

onMounted(async () => {
  if (fixedKbId.value) {
    chatScope.value = fixedKbId.value
  } else if (initialKbId.value) {
    chatScope.value = initialKbId.value
  }
  await Promise.allSettled([loadSessions(), fixedKbId.value ? Promise.resolve() : loadKbOptions()])
  await hydrateRouteState()
})

watch(
  () => route.query.q,
  async (nextQ, prevQ) => {
    const normalizedNextQ = normalizeRouteQueryValue(nextQ)
    if (!normalizedNextQ || normalizedNextQ === normalizeRouteQueryValue(prevQ)) {
      return
    }
    await tryConsumeRouteQuestion(normalizedNextQ)
  },
  { immediate: true }
)

onDeactivated(() => {
  lastConsumedRouteQuestionKey = ""
})

watch(
  () => route.query.sessionId,
  async (nextSessionId, prevSessionId) => {
    const normalizedSessionId = normalizeRouteQueryValue(nextSessionId)
    if (!normalizedSessionId || normalizedSessionId === normalizeRouteQueryValue(prevSessionId)) {
      return
    }
    if (normalizedSessionId === getSessionKey(currentSessionId.value)) {
      return
    }
    await openSessionById(normalizedSessionId)
  }
)

async function loadSessions() {
  try {
    const userId = await getRequiredUserId()
    const params: Record<string, string> = { userId }
    if (fixedKbId.value) {
      params.kbId = fixedKbId.value
    }
    const res = await getChatSessions(params)
    sessions.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    console.error(e)
  }
}

async function loadKbOptions() {
  try {
    const res = await getKnowledgeBaseList({ pageSize: 100 })
    kbOptions.value = Array.isArray(res?.data) ? res.data : []
  } catch (e) {
    console.error(e)
  }
}

function newSession() {
  currentSessionId.value = null
  messages.value = []
  loadingSessionMessages.value = false
  syncChatRoute()
}

async function selectSession(s: any) {
  const sessionId = normalizeSessionId(s.id)
  if (!sessionId) {
    return
  }
  currentSessionId.value = sessionId
  messages.value = []
  loadingSessionMessages.value = true
  syncChatRoute(sessionId)
  await openSessionById(sessionId)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    onSend()
  }
}

/**
 * 使用空状态推荐问题填充输入框，降低首次提问成本。
 */
function usePrompt(text: string) {
  inputText.value = text
}

async function onSend(options: { presetText?: string } = {}) {
  const text = (options.presetText ?? inputText.value).trim()
  if (!text || generating.value) return

  let userId = ""
  try {
    userId = await getRequiredUserId()
  } catch (e) {
    console.error(e)
    return
  }
  const requestId = Date.now()
  const requestSessionKey = currentSessionKey.value
  messages.value.push({ id: Date.now(), role: "user", content: text, __sessionKey: requestSessionKey })
  inputText.value = ""
  generating.value = true
  streamingRequestId.value = requestId
  streamingSessionKey.value = requestSessionKey
  scrollToBottom()

  let activeAssistantMsg: any = null
  try {
    const response = await fetch(getChatStreamUrl(), {
      method: "POST",
      headers: buildChatStreamHeaders(),
      body: JSON.stringify({
        kbId: chatScope.value || undefined,
        sessionId: currentSessionId.value || undefined,
        userId,
        question: text,
        onlineSearch: onlineSearch.value,
        graph: graphSearch.value ? true : undefined,
        enableThinking: enableThinking.value,
        thinkingBudget: enableThinking.value ? thinkingBudget.value : undefined
      })
    })

    if (!response.ok) {
      throw new Error(await readChatError(response))
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error("浏览器未返回流式响应")
    }
    const decoder = new TextDecoder()
    let assistantContent = ""
    let pendingLine = ""
    const assistantMsg = reactive({
      id: Date.now() + 1,
      persistedId: null as number | null,
      role: "assistant",
      content: "",
      source: "",
      htmlContent: "",
      reasoningContent: "",
      reasoningOpen: true,
      citations: [] as any[],
      citationsOpen: false,
      intentPayload: null as any,
      generating: true,
      feedback: "",
      __sessionKey: requestSessionKey
    })
    activeAssistantMsg = assistantMsg
    messages.value.push(assistantMsg)

    while (reader) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      const lines = `${pendingLine}${chunk}`.split("\n")
      pendingLine = lines.pop() || ""
      for (const line of lines) {
        if (line.startsWith("data:")) {
          try {
            const data = JSON.parse(line.substring(5))
            if (data.type === "content") {
              assistantContent += data.content
              assistantMsg.content = assistantContent
            }
            if (data.type === "reasoning") {
              assistantMsg.reasoningContent += data.content
            }
            if (data.type === "error") {
              assistantMsg.content = data.content || "问AI失败"
              throw new Error(assistantMsg.content)
            }
            if (data.type === "source") {
              assistantMsg.source = data.source
            }
            if (data.type === "intent") {
              assistantMsg.intentPayload = normalizeIntentPayload(data)
            }
            if (data.type === "done" && Array.isArray(data.citations)) {
              assistantMsg.citations = data.citations
              assistantMsg.citationsOpen = false
            }
            if (data.messageId) {
              assistantMsg.persistedId = data.messageId
              assistantMsg.id = data.messageId
            }
            if (
              data.type === "done" &&
              data.sessionId &&
              streamingRequestId.value === requestId &&
              currentSessionKey.value === requestSessionKey
            ) {
              const nextSessionId = normalizeSessionId(data.sessionId)
              if (!nextSessionId) {
                continue
              }
              migrateMessageSessionKey(requestSessionKey, nextSessionId)
              currentSessionId.value = nextSessionId
              syncChatRoute(nextSessionId)
            }
          } catch (error) {
            if (line.includes('"type":"error"') || line.includes('"type": "error"')) {
              throw error
            }
          }
        }
      }
      scrollToBottom()
    }
    if (pendingLine.startsWith("data:")) {
      const data = JSON.parse(pendingLine.substring(5))
      if (data.type === "content") {
        assistantMsg.content = assistantContent + data.content
      }
      if (data.type === "reasoning") {
        assistantMsg.reasoningContent += data.content
      }
      if (data.type === "error") {
        assistantMsg.content = data.content || "问AI失败"
        throw new Error(assistantMsg.content)
      }
      if (data.type === "intent") {
        assistantMsg.intentPayload = normalizeIntentPayload(data)
      }
      if (data.type === "done" && Array.isArray(data.citations)) {
        assistantMsg.citations = data.citations
        assistantMsg.citationsOpen = false
      }
      if (
        data.type === "done" &&
        data.sessionId &&
        streamingRequestId.value === requestId &&
        currentSessionKey.value === requestSessionKey
      ) {
        const nextSessionId = normalizeSessionId(data.sessionId)
        if (nextSessionId) {
          migrateMessageSessionKey(requestSessionKey, nextSessionId)
          currentSessionId.value = nextSessionId
          syncChatRoute(nextSessionId)
        }
      }
    }
    loadSessions()
  } catch (e) {
    console.error(e)
    message.error("发送失败")
  } finally {
    if (activeAssistantMsg) {
      activeAssistantMsg.generating = false
    }
    generating.value = false
    if (streamingRequestId.value === requestId) {
      streamingSessionKey.value = ""
    }
  }
}

async function readChatError(response: Response) {
  try {
    const data = await response.clone().json()
    return data?.resp_msg || data?.message || `问AI请求失败：${response.status}`
  } catch (e) {
    return `问AI请求失败：${response.status}`
  }
}

/**
 * 获取当前真实登录用户主键，缺失时阻断发送和会话读取，不使用默认用户兜底。
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

function getChatStreamUrl() {
  const basePrefix = import.meta.env.VITE_BASE_URL_PREFIX || ""
  return `${basePrefix}/api-knowledge/api/v1/kb/chat`
}

function buildChatStreamHeaders() {
  const headers: Record<string, string> = {
    "Content-Type": "application/json"
  }
  if (userStore.token) {
    headers.Authorization = `Bearer ${userStore.token}`
  }
  if (import.meta.env.DEV) {
    const auditUserId = userStore.userInfo?.userId || import.meta.env.VITE_DEV_AUDIT_USER_ID
    const auditUserName = userStore.userInfo?.realName || import.meta.env.VITE_DEV_AUDIT_USER_NAME
    if (auditUserId) {
      headers["x-userid-header"] = auditUserId
    }
    if (auditUserName) {
      headers["x-realname-header"] = encodeURIComponent(auditUserName)
    }
  }
  return headers
}

/**
 * 知识范围下拉的浮层挂到 `document.body`，与全局 `dropdownClassName` 样式配合。
 */
function getKbSelectPopupContainer() {
  return document.body
}

function normalizeSearchKeyword(value: unknown) {
  if (typeof value !== "string") {
    return ""
  }
  return value.trim()
}

function goSearchFiles(queryText?: unknown) {
  const keyword = normalizeSearchKeyword(queryText)
  router.push({
    name: "SearchFiles",
    query: {
      kbId: chatScope.value || fixedKbId.value || undefined,
      q: keyword || undefined
    }
  })
}

function normalizeRouteQueryValue(value: unknown) {
  if (Array.isArray(value)) {
    return normalizeRouteQueryValue(value[0])
  }
  if (value === undefined || value === null) {
    return ""
  }
  return String(value).trim()
}

function normalizeSessionId(sessionId: string | number | null | undefined) {
  if (sessionId === undefined || sessionId === null) {
    return null
  }
  const text = String(sessionId).trim()
  return text === "" ? null : text
}

function getSessionKey(sessionId: string | number | null | undefined) {
  const normalizedSessionId = normalizeSessionId(sessionId)
  if (!normalizedSessionId) {
    return NEW_SESSION_KEY
  }
  return normalizedSessionId
}

async function hydrateRouteState() {
  const routeSessionId = normalizeRouteQueryValue(route.query.sessionId)
  if (routeSessionId) {
    await openSessionById(routeSessionId)
  }
}

function buildRouteQuestionKey(question: string) {
  const kbPart = normalizeRouteQueryValue(chatScope.value || fixedKbId.value || initialKbId.value)
  return `${kbPart}::${question.trim()}`
}

async function tryConsumeRouteQuestion(question: string) {
  if (embedded.value) {
    return
  }
  const text = `${question || ""}`.trim()
  if (!text || generating.value) {
    return
  }
  const consumeKey = buildRouteQuestionKey(text)
  if (routeQuestionConsuming.value || lastConsumedRouteQuestionKey === consumeKey) {
    return
  }
  routeQuestionConsuming.value = true
  lastConsumedRouteQuestionKey = consumeKey
  if (normalizeRouteQueryValue(route.query.sessionId)) {
    routeQuestionConsuming.value = false
    return
  }
  try {
    newSession()
    inputText.value = text
    await nextTick()
    await onSend({ presetText: text })
  } finally {
    routeQuestionConsuming.value = false
  }
}

async function openSessionById(sessionId: string | number) {
  const normalizedSessionId = normalizeSessionId(normalizeRouteQueryValue(sessionId))
  if (!normalizedSessionId) {
    return
  }
  const requestId = Date.now()
  sessionLoadRequestId.value = requestId
  try {
    currentSessionId.value = normalizedSessionId
    messages.value = []
    loadingSessionMessages.value = true
    const res = await getChatMessages(normalizedSessionId, { pageSize: 100 })
    if (sessionLoadRequestId.value !== requestId || getSessionKey(currentSessionId.value) !== normalizedSessionId) {
      return
    }
    messages.value = Array.isArray(res?.data)
      ? res.data.map((item: any) => normalizeMessage(item, normalizedSessionId))
      : []
    scrollToBottom()
  } catch (e) {
    console.error(e)
  } finally {
    if (sessionLoadRequestId.value === requestId && getSessionKey(currentSessionId.value) === normalizedSessionId) {
      loadingSessionMessages.value = false
    }
  }
}

function syncChatRoute(sessionId?: string | number | null) {
  if (embedded.value) {
    return
  }
  router.replace({
    name: "KbChat",
    query: {
      kbId: chatScope.value || fixedKbId.value || undefined,
      sessionId: sessionId ? String(sessionId) : undefined,
      onlineSearch: onlineSearch.value ? "1" : undefined,
      enableThinking: enableThinking.value ? "1" : undefined,
      graph: graphSearch.value ? "1" : undefined
    }
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (threadRef.value) {
      threadRef.value.scrollTop = threadRef.value.scrollHeight
    }
  })
}

async function onFeedback(msg: any, type: string) {
  const messageId = msg.persistedId || msg.id
  if (!messageId) {
    message.warning("回复尚未保存，稍后再试")
    return
  }
  try {
    await updateChatMessageFeedback(messageId, { feedback: type })
    updateLocalMessageFeedback(messageId, type)
    message.success(type === "like" ? "已点赞" : "已点踩")
  } catch (e) {
    message.error("反馈失败")
  }
}

function isFeedbackActive(msg: any, type: "like" | "dislike") {
  const legacyType = type === "like" ? "up" : "down"
  return msg.feedback === type || msg.feedback === legacyType
}

function updateLocalMessageFeedback(messageId: number | string, feedback: string) {
  messages.value = messages.value.map((item) => {
    const itemId = item.persistedId || item.id
    return `${itemId}` === `${messageId}` ? { ...item, feedback } : item
  })
}

function normalizeMessage(msg: any, sessionKey = currentSessionKey.value) {
  return {
    ...msg,
    __sessionKey: getSessionKey(sessionKey),
    feedback: msg.feedback || "",
    reasoningContent: msg.reasoningContent || "",
    reasoningOpen: msg.reasoningOpen ?? true,
    citations: Array.isArray(msg.citations) ? msg.citations : [],
    citationsOpen: msg.citationsOpen ?? false,
    intentPayload: msg.intentPayload || null,
    generating: false
  }
}

async function deleteSession(sessionItem: any) {
  try {
    await deleteChatSession(sessionItem.id)
    if (getSessionKey(currentSessionId.value) === getSessionKey(sessionItem.id)) {
      newSession()
    }
    const deletedSessionKey = getSessionKey(sessionItem.id)
    sessions.value = sessions.value.filter((item) => getSessionKey(item.id) !== deletedSessionKey)
    message.success("会话已删除")
  } catch (e) {
    console.error(e)
    message.error("删除会话失败")
  }
}

async function onCopy(msg: any) {
  const content = String(msg?.content || "").trim()
  if (!content) {
    message.warning("当前回答暂无可复制内容")
    return
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(content)
    } else {
      fallbackCopyText(content)
    }
    message.success("已复制")
  } catch (e) {
    try {
      fallbackCopyText(content)
      message.success("已复制")
    } catch (copyError) {
      console.error(copyError)
      message.error("复制失败，请检查浏览器剪贴板权限")
    }
  }
}

function fallbackCopyText(text: string) {
  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.setAttribute("readonly", "true")
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  textarea.style.pointerEvents = "none"
  document.body.appendChild(textarea)
  textarea.select()
  textarea.setSelectionRange(0, textarea.value.length)
  const copied = document.execCommand("copy")
  document.body.removeChild(textarea)
  if (!copied) {
    throw new Error("document.execCommand(copy) failed")
  }
}

function onRegenerate() {
  if (generating.value) return
  const lastUser = [...displayedMessages.value].reverse().find((item) => item.role === "user")
  if (!lastUser?.content) {
    message.warning("暂无可重新生成的问题")
    return
  }
  inputText.value = lastUser.content
  onSend()
}

function migrateMessageSessionKey(fromSessionKey: string | number, toSessionKey: string | number) {
  const fromKey = getSessionKey(fromSessionKey)
  const toKey = getSessionKey(toSessionKey)
  messages.value.forEach((item) => {
    if (getSessionKey(item.__sessionKey) === fromKey) {
      item.__sessionKey = toKey
    }
  })
}

function renderMarkdown(content: string) {
  return markdown.render(normalizeMarkdownContent(content))
}

function normalizeMarkdownContent(content: string) {
  if (!content) return ""
  return content
    .replace(/\\r\\n/g, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "  ")
    .replace(/\*\*依据[:：]\*\*[*\s]*/g, "\n\n**依据：**\n\n")
    .replace(/([。！？；;：:])\s*(\d+\.)/g, "$1\n\n$2")
    .replace(/([^\n])\*知识库/g, "$1\n- 知识库")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

function getCitationKey(item: any) {
  return `${item.index || "x"}-${item.chunkId || item.content || ""}`
}

function getCitationTitle(item: any) {
  const metadata = item?.metadata || {}
  const raw =
    metadata.title ||
    metadata.field_name_cn ||
    metadata.plan_name ||
    metadata.file_node_name ||
    metadata.original_name ||
    metadata.file_name ||
    metadata.fileName ||
    (metadata.file_node_id ? `文件 ${metadata.file_node_id}` : "") ||
    (item.chunkId ? `片段 ${item.chunkId}` : "知识库片段")
  return decodeDisplayText(raw)
}

function getCitationFileName(item: any) {
  const metadata = item?.metadata || {}
  const raw =
    metadata.original_name ||
    metadata.file_node_name ||
    metadata.file_name ||
    metadata.fileName ||
    metadata.plan_name ||
    (metadata.file_node_id ? `文件节点 ${metadata.file_node_id}` : "来源文件")
  return decodeDisplayText(raw)
}

function getCitationPage(item: any) {
  const metadata = item?.metadata || {}
  return metadata.page_no || metadata.page_num || ""
}

function getCitationGraphPath(item: any) {
  return item?.graphPath || item?.metadata?.graph_path || null
}

function formatCitationGraphPath(path: any) {
  if (path?.fact) return decodeDisplayText(path.fact)
  const nodes = Array.isArray(path?.nodes) ? path.nodes.map((node: any) => node?.name).filter(Boolean) : []
  const relations = Array.isArray(path?.relationships) ? path.relationships : []
  return nodes.reduce((text: string, name: string, index: number) => (
    index === 0 ? name : `${text} —${relations[index - 1] || "关联"}→ ${name}`
  ), "图关系命中")
}

function getSourceFileId(item: any) {
  const metadata = item?.metadata || {}
  return metadata.source_file_id || metadata.file_id || metadata.fileId || ""
}

function isImageCitation(item: any) {
  return item?.metadata?.chunk_type === "image"
}

function openCitationFile(item: any) {
  const metadata = item?.metadata || {}
  // 图片类引用：优先预览原图（file_center_file_id，多模态解析上传文件中心后才有值）
  if (isImageCitation(item) && metadata.file_center_file_id) {
    previewFile(String(metadata.file_center_file_id), "modal")
    return
  }
  const sourceFileId = getSourceFileId(item)
  if (!sourceFileId) {
    message.warning("当前引用未返回可预览的文件 ID")
    return
  }
  previewFile(String(sourceFileId), "modal")
}

function normalizeIntentPayload(data: any) {
  if (!data || !data.intent || data.intent === "knowledge_qa" || data.intent === "casual_chat") {
    return null
  }
  return {
    intent: data.intent,
    query: data.query || "",
    confidence: data.confidence,
    reason: data.reason || "",
    files: Array.isArray(data.files) ? data.files : []
  }
}

function getIntentTitle(payload: any) {
  if (payload?.intent === "file_recent") {
    return `最近更新文档 ${payload.files?.length || 0}`
  }
  if (payload?.intent === "file_search") {
    return `文件搜索${payload.query ? `：${payload.query}` : ""}`
  }
  return "文件动作"
}

function getIntentFileKey(file: any) {
  return `${file.fileNodeId || file.id || file.fileId || file.name}`
}

function openIntentFile(file: any) {
  const fileId = file?.fileId || file?.source_file_id
  if (!fileId) {
    message.warning("当前文件未返回可预览的文件 ID")
    return
  }
  previewFile(String(fileId), "modal")
}

function formatCitationScore(score: number | string) {
  const value = Number(score)
  if (Number.isNaN(value)) return ""
  return `得分 ${value.toFixed(2)}`
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@primary-light: #eff6ff;
@border: #e5e7eb;
@muted: #64748b;
@text: #0f172a;
@violet: #7c3aed;
@cyan: #06b6d4;

.chat-page {
  position: relative;
  display: flex;
  overflow: hidden;
  padding: 16px 20px;
  height: 100vh;
  box-sizing: border-box;
  background: radial-gradient(circle at 18% 8%, rgba(37, 99, 235, 0.12), transparent 28%),
    radial-gradient(circle at 82% 18%, rgba(124, 58, 237, 0.1), transparent 26%),
    linear-gradient(180deg, #f8fbff 0%, #f4f7fb 100%);
  flex-direction: column;

  &::before {
    position: absolute;
    inset: 0;
    pointer-events: none;
    content: "";
    background-image: linear-gradient(rgba(37, 99, 235, 0.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(37, 99, 235, 0.05) 1px, transparent 1px);
    background-size: 40px 40px;
    opacity: 0.38;
    mask-image: linear-gradient(180deg, #000 0%, transparent 72%);
  }
}

.chat-page--embedded {
  padding: 0;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: transparent;

  &::before,
  .chat-bg {
    display: none;
  }
}

.chat-bg {
  position: absolute;
  pointer-events: none;
  border-radius: 999px;
  filter: blur(8px);
}

.chat-bg-primary {
  top: 86px;
  left: 30%;
  width: 260px;
  height: 260px;
  background: rgba(37, 99, 235, 0.08);
}

.chat-bg-secondary {
  right: 8%;
  bottom: 12%;
  width: 340px;
  height: 340px;
  background: rgba(6, 182, 212, 0.08);
}

.chat-container {
  position: relative;
  z-index: 1;
  margin: 0 auto;
  width: 100%;
  max-width: 1320px;
  min-height: 0;
  flex: 1;
}

.chat-shell {
  display: grid;
  overflow: hidden;
  height: 100%;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 26px;
  box-shadow: 0 30px 80px rgba(15, 23, 42, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(20px);
  grid-template-columns: 300px minmax(0, 1fr);
}

.chat-page--embedded .chat-shell {
  display: block;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  backdrop-filter: none;
}

.chat-page--embedded.chat-page--with-sessions .chat-shell {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
}

.chat-page--embedded .chat-container,
.chat-page--embedded .chat-panel,
.chat-page--embedded .chat-shell,
.chat-page--embedded .chat-sessions {
  height: 100%;
  min-height: 0;
}

.chat-page--embedded .chat-container {
  margin: 0;
  max-width: none;
}

.chat-page--embedded .chat-toolbar {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.86);
}

.chat-page--embedded .chat-thread {
  padding: 20px 24px;
}

/* ---- 会话列表 ---- */
.chat-sessions {
  display: flex;
  min-height: 0;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9), rgba(255, 255, 255, 0.74)),
    radial-gradient(circle at 30% 8%, rgba(37, 99, 235, 0.1), transparent 36%);
  border-right: 1px solid rgba(226, 232, 240, 0.78);
  flex-direction: column;
}

.chat-sessions-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 18px 14px;
  font-size: 13px;
  font-weight: 600;
  color: @text;
  border-bottom: 1px solid rgba(226, 232, 240, 0.68);

  small {
    display: block;
    margin-top: 4px;
    font-size: 11px;
    font-weight: 400;
    color: #94a3b8;
  }
}

.chat-new-btn {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  color: @primary;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(191, 219, 254, 0.9);
  border-radius: 999px;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08);
  transition: all 0.2s ease;
  gap: 4px;
  cursor: pointer;

  &:hover {
    background: #fff;
    border-color: #93c5fd;
    transform: translateY(-1px);
  }
}

.chat-session-list {
  overflow: auto;
  flex: 1;
  padding: 8px;
}

.chat-session-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 15px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: rgba(255, 255, 255, 0.72);
    border-color: rgba(226, 232, 240, 0.88);
    transform: translateY(-1px);
  }

  &.is-active {
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.1), rgba(124, 58, 237, 0.08));
    border-color: rgba(147, 197, 253, 0.7);
    box-shadow: 0 12px 24px rgba(37, 99, 235, 0.08);
  }
}

.chat-session-icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  margin-top: 0;
  width: 28px;
  height: 28px;
  font-size: 14px;
  color: @primary;
  background: #eef6ff;
  border-radius: 10px;

  .is-active & {
    color: #fff;
    background: linear-gradient(135deg, @primary, @violet);
  }
}

.chat-session-text {
  flex: 1;
  min-width: 0;

  span {
    display: block;
    overflow: hidden;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #475569;
  }

  small {
    display: block;
    margin-top: 2px;
    font-size: 11px;
    color: #94a3b8;
  }

  .is-active & span {
    font-weight: 600;
    color: #1d4ed8;
  }
}

.chat-session-delete {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  margin-left: auto;
  width: 28px;
  height: 28px;
  color: #94a3b8;
  background: transparent;
  border: none;
  border-radius: 8px;
  opacity: 0;
  transition: all 0.16s ease;
  flex-shrink: 0;
  cursor: pointer;

  &:hover {
    color: #dc2626;
    background: #fef2f2;
  }

  .chat-session-item:hover &,
  .chat-session-item.is-active & {
    opacity: 1;
  }
}

.chat-session-empty {
  display: flex;
  align-items: center;
  padding: 48px 16px;
  font-size: 13px;
  color: #94a3b8;
  flex-direction: column;
  gap: 8px;
}

/* ---- 聊天面板 ---- */
.chat-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: radial-gradient(circle at 72% 4%, rgba(37, 99, 235, 0.08), transparent 26%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(255, 255, 255, 0.96));
}

.chat-toolbar {
  display: flex;
  align-items: center;
  padding: 15px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.72);
}

.chat-toolbar-left {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 14px;
}

.chat-toolbar-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;

  strong {
    font-size: 15px;
    color: @text;
  }

  span {
    font-size: 12px;
    color: #94a3b8;
  }
}

.chat-toolbar-label {
  font-size: 12px;
  white-space: nowrap;
  color: #94a3b8;
}

.chat-scope-fixed {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #1d4ed8;
  background: rgba(239, 246, 255, 0.92);
  border: 1px solid rgba(191, 219, 254, 0.9);
  border-radius: 999px;
}

.chat-fixed-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.chat-search-file-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  background: #fff;
  border: 1px solid rgba(203, 213, 225, 0.9);
  border-radius: 999px;
  cursor: pointer;
  transition: all 0.16s;

  &:hover {
    color: @primary;
    border-color: #93c5fd;
  }
}

.chat-scope-select {
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

.chat-thread {
  display: flex;
  overflow: auto;
  padding: 28px 32px;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  gap: 22px;
}

/* 空状态欢迎页 */
.chat-welcome {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 32px;
  margin: auto;
  width: 100%;
  max-width: 560px;
  text-align: center;
  color: #64748b;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.72)),
    radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.12), transparent 54%);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 28px;
  box-shadow: 0 26px 70px rgba(15, 23, 42, 0.08);
  flex-direction: column;
  gap: 12px;
}

.chat-welcome-icon {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 2px;
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.22), transparent),
    linear-gradient(135deg, @primary, @violet 58%, @cyan);
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 22px;
  box-shadow: 0 18px 36px rgba(37, 99, 235, 0.26);

  .anticon {
    font-size: 28px;
    color: #fff;
  }
}

.chat-welcome h3 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: @text;
}

.chat-welcome p {
  margin: 0;
  font-size: 14px;
}

.chat-welcome-prompts {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  margin-top: 8px;
  gap: 8px;

  button {
    padding: 7px 12px;
    font-size: 12px;
    color: #475569;
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(226, 232, 240, 0.88);
    border-radius: 999px;
    transition: all 0.2s ease;
    cursor: pointer;

    &:hover {
      color: @primary;
      background: #fff;
      border-color: rgba(147, 197, 253, 0.9);
      box-shadow: 0 10px 24px rgba(37, 99, 235, 0.1);
      transform: translateY(-1px);
    }
  }
}

/* ---- 消息 ---- */
.chat-msg {
  display: flex;
  gap: 12px;
  max-width: 78%;
}

.chat-msg--user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-msg--assistant {
  align-self: flex-start;
}

.chat-msg-avatar {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  flex-shrink: 0;

  .chat-msg--user & {
    background: linear-gradient(135deg, @primary, @violet);
    box-shadow: 0 10px 22px rgba(37, 99, 235, 0.24);

    .anticon {
      color: #fff;
    }
  }

  .chat-msg--assistant & {
    background: #fff;
    border: 1px solid rgba(226, 232, 240, 0.9);
    box-shadow: 0 10px 22px rgba(15, 23, 42, 0.06);

    .anticon {
      color: @primary;
    }
  }
}

.chat-msg-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-msg-bubble {
  padding: 13px 17px;
  font-size: 14px;
  white-space: pre-wrap;
  border-radius: 18px;
  line-height: 1.6;
  word-break: break-word;

  .chat-msg--user & {
    color: #fff;
    background: linear-gradient(135deg, @primary, #1d4ed8);
    border-bottom-right-radius: 6px;
    box-shadow: 0 12px 26px rgba(37, 99, 235, 0.18);
  }

  .chat-msg--assistant & {
    color: #1e293b;
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(226, 232, 240, 0.86);
    border-bottom-left-radius: 6px;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
  }
}

.chat-markdown {
  white-space: normal;
  overflow-x: auto;

  ::v-deep(p) {
    margin: 0 0 10px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  ::v-deep(h1),
  ::v-deep(h2),
  ::v-deep(h3),
  ::v-deep(h4) {
    margin: 14px 0 8px;
    font-weight: 700;
    line-height: 1.35;
    color: #0f172a;

    &:first-child {
      margin-top: 0;
    }
  }

  ::v-deep(h1) {
    font-size: 20px;
  }

  ::v-deep(h2) {
    font-size: 18px;
  }

  ::v-deep(h3) {
    font-size: 16px;
  }

  ::v-deep(h4) {
    font-size: 15px;
  }

  ::v-deep(ul),
  ::v-deep(ol) {
    list-style-position: outside;
    padding-left: 22px;
    margin: 8px 0 10px;
  }

  ::v-deep(ul) {
    list-style-type: disc;
  }

  ::v-deep(ol) {
    list-style-type: decimal;
  }

  ::v-deep(li) {
    margin: 4px 0;

    > p {
      margin: 0 0 6px;
    }
  }

  ::v-deep(hr) {
    margin: 14px 0;
    border: none;
    border-top: 1px solid #e2e8f0;
  }

  ::v-deep(blockquote) {
    padding: 2px 0 2px 12px;
    margin: 10px 0;
    color: #475569;
    border-left: 3px solid #bfdbfe;
  }

  ::v-deep(code) {
    padding: 2px 5px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size: 12px;
    color: #be123c;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 5px;
  }

  ::v-deep(pre) {
    overflow: auto;
    padding: 12px;
    margin: 10px 0;
    background: #0f172a;
    border-radius: 10px;

    code {
      padding: 0;
      color: #e2e8f0;
      background: transparent;
      border: none;
      border-radius: 0;
    }
  }

  ::v-deep(table) {
    display: block;
    overflow: auto;
    width: 100%;
    margin: 10px 0;
    border-collapse: collapse;
  }

  ::v-deep(th),
  ::v-deep(td) {
    padding: 7px 9px;
    border: 1px solid #e2e8f0;
  }

  ::v-deep(th) {
    font-weight: 700;
    background: #f8fafc;
  }

  ::v-deep(a) {
    color: @primary;
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}

.chat-citations {
  overflow: hidden;
  max-width: 720px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 14px;
}

.chat-intent-card {
  max-width: 720px;
  padding: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.chat-intent-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;

  span {
    display: inline-flex;
    align-items: center;
    min-width: 0;
    font-size: 13px;
    font-weight: 700;
    color: #334155;
    gap: 6px;
  }

  button {
    display: inline-flex;
    align-items: center;
    height: 28px;
    padding: 0 10px;
    font-size: 12px;
    font-weight: 700;
    color: @primary;
    background: #fff;
    border: 1px solid #bfdbfe;
    border-radius: 6px;
    cursor: pointer;
    gap: 5px;
    white-space: nowrap;
  }
}

.chat-intent-files {
  display: grid;
  margin-top: 10px;
  gap: 8px;
}

.chat-intent-file {
  display: grid;
  align-items: center;
  width: 100%;
  min-height: 42px;
  padding: 8px 10px;
  text-align: left;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  gap: 8px;

  span {
    overflow: hidden;
    font-size: 13px;
    font-weight: 600;
    color: #0f172a;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    overflow: hidden;
    grid-column: 2 / 3;
    font-size: 12px;
    color: #64748b;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  em {
    grid-column: 3 / 4;
    grid-row: 1 / 3;
    font-size: 12px;
    font-style: normal;
    color: #94a3b8;
    white-space: nowrap;
  }
}

.chat-citations-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  background: transparent;
  border: none;
  cursor: pointer;

  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
}

.chat-citation-list {
  display: flex;
  padding: 0 10px 10px;
  flex-direction: column;
  gap: 8px;
}

.chat-citation-item {
  width: 100%;
  padding: 10px;
  text-align: left;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.16s, box-shadow 0.16s, transform 0.16s;

  &:hover {
    border-color: #bfdbfe;
    box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08);
    transform: translateY(-1px);
  }

  p {
    display: -webkit-box;
    overflow: hidden;
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.55;
    color: #64748b;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
  }
}

.chat-citation-file {
  display: flex;
  align-items: center;
  min-width: 0;
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
  gap: 5px;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  em {
    margin-left: auto;
    font-style: normal;
    color: #94a3b8;
    white-space: nowrap;
  }
}

.chat-citation-graph {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 7px;
  padding: 7px 8px;
  font-size: 11px;
  line-height: 1.5;
  color: #92400e;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;

  .anticon {
    margin-top: 2px;
    color: #d97706;
  }
}

.chat-citation-title {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;

  strong {
    overflow: hidden;
    font-size: 12px;
    color: #0f172a;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  small {
    margin-left: auto;
    font-size: 11px;
    color: #94a3b8;
    white-space: nowrap;
  }
}

.chat-citation-index {
  font-size: 12px;
  font-weight: 800;
  color: @primary;
}

.chat-reasoning {
  overflow: hidden;
  background: #faf5ff;
  border: 1px solid #e9d5ff;
  border-radius: 14px;
}

.chat-reasoning-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #7e22ce;
  background: transparent;
  border: none;
  cursor: pointer;

  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
}

.chat-reasoning-body {
  padding: 0 12px 12px;
  margin: 0;
  max-width: 680px;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  color: #581c87;
  line-height: 1.6;
}

/* 打字动画 */
.chat-msg-typing {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px 18px;

  span {
    width: 6px;
    height: 6px;
    background: #94a3b8;
    border-radius: 50%;
    animation: typing 1.2s infinite;

    &:nth-child(2) {
      animation-delay: 0.2s;
    }

    &:nth-child(3) {
      animation-delay: 0.4s;
    }
  }
}

@keyframes typing {
  0%,
  60%,
  100% {
    opacity: 0.3;
    transform: scale(0.8);
  }

  30% {
    opacity: 1;
    transform: scale(1);
  }
}

.chat-msg-source {
  padding: 6px 10px;
  font-size: 12px;
  color: @muted;
  background: rgba(248, 250, 252, 0.86);
  border: 1px solid rgba(226, 232, 240, 0.78);
  border-radius: 10px;

  .anticon {
    margin-right: 4px;
    font-size: 11px;
  }
}

.chat-msg-actions {
  display: flex;
  gap: 4px;

  button {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 28px;
    height: 28px;
    color: #94a3b8;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    transition: all 0.15s;
    cursor: pointer;

    &:hover {
      color: @primary;
      background: #eff6ff;
      border-color: @border;
    }

    &.is-active {
      color: @primary;
      background: #eff6ff;
      border-color: #bfdbfe;
    }
  }
}

/* ---- 输入区 ---- */
.chat-composer {
  padding: 14px 18px 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0), rgba(248, 250, 252, 0.92));
  border-top: 1px solid rgba(226, 232, 240, 0.72);
}

.chat-composer-inner {
  display: flex;
  align-items: stretch;
  padding: 13px 14px 12px 16px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(226, 232, 240, 0.96);
  border-radius: 18px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.07);
  transition: all 0.2s ease;
  flex-direction: column;
  gap: 12px;

  &:focus-within {
    border-color: #93c5fd;
    box-shadow: 0 18px 40px rgba(37, 99, 235, 0.1), 0 0 0 4px rgba(37, 99, 235, 0.06);
  }

  textarea {
    min-height: 74px;
    max-height: 180px;
    font-size: 14px;
    font-family: inherit;
    color: @text;
    background: transparent;
    border: none;
    outline: none;
    resize: none;
    line-height: 1.5;
  }
}

.chat-composer-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.chat-send-options {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.chat-option-btn {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  height: 32px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
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

.chat-thinking-btn.is-active {
  color: #7c3aed;
  background: #f5f3ff;
  border-color: #ddd6fe;

  .anticon {
    color: #7c3aed;
  }
}

.chat-send-btn {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 40px;
  height: 40px;
  color: #fff;
  background: linear-gradient(135deg, @primary, @violet);
  border: none;
  border-radius: 13px;
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.24);
  transition: all 0.2s ease;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 28px rgba(37, 99, 235, 0.32);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .anticon {
    display: inline-flex;
    font-size: 18px;
  }
}

@media (max-width: 900px) {
  .chat-shell {
    grid-template-columns: 1fr;
  }

  .chat-sessions {
    border-right: none;
    border-bottom: 1px solid @border;
    max-height: 200px;
  }

  .chat-toolbar-left {
    align-items: flex-start;
    flex-direction: column;
  }

  .chat-scope-select {
    width: 100%;
  }

  .chat-msg {
    max-width: 92%;
  }
}
</style>

<style lang="less">
@chat-primary: #2563eb;

/* 对话页知识范围下拉的浮层在 body 上 */
.chat-kb-dropdown.ant-select-dropdown {
  padding: 6px 0;
  background: #fff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 12px;
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.12);
}

.chat-kb-dropdown .ant-select-dropdown-menu {
  margin: 0;
  max-height: 320px;
  border-radius: 0;
  box-shadow: none;
}

.chat-kb-dropdown .ant-select-dropdown-menu-item {
  padding: 8px 14px;
  font-size: 13px;
  line-height: 1.4;
  color: #334155;
}

.chat-kb-dropdown .ant-select-dropdown-menu-item:hover {
  color: @chat-primary;
  background: #eff6ff;
}

.chat-kb-dropdown .ant-select-dropdown-menu-item-selected {
  font-weight: 600;
  color: @chat-primary;
  background: rgba(239, 246, 255, 0.95);
}
</style>
