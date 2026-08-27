<template>
  <div class="kb-page pt-page">
    <div class="kb-page-inner kb-page-inner--wide">
      <!-- 页头 -->
      <div class="kb-page-head">
        <div>
          <h1 class="kb-page-title">解析任务进度</h1>
          <p class="kb-page-desc">查看当前和最近的文件解析任务状态</p>
        </div>
      </div>

      <!-- 指标区 -->
      <section class="pt-metrics">
        <div class="pt-metric pt-metric--running">
          <strong>{{ metrics.running }}</strong>
          <span>运行中</span>
        </div>
        <div class="pt-metric pt-metric--queued">
          <strong>{{ metrics.queued }}</strong>
          <span>排队中</span>
        </div>
        <div class="pt-metric pt-metric--done">
          <strong>{{ metrics.done }}</strong>
          <span>已完成</span>
        </div>
        <div class="pt-metric pt-metric--failed">
          <strong>{{ metrics.failed }}</strong>
          <span>失败</span>
        </div>
      </section>

      <!-- 筛选区 -->
      <section class="pt-toolbar">
        <a-select v-model="filters.status" class="pt-filter" placeholder="状态" allow-clear>
          <a-select-option value="">全部</a-select-option>
          <a-select-option value="running">running</a-select-option>
          <a-select-option value="queued">queued</a-select-option>
          <a-select-option value="done">done</a-select-option>
          <a-select-option value="failed">failed</a-select-option>
        </a-select>
        <a-input v-model="filters.kb_id" class="pt-filter" placeholder="kb_id" allow-clear />
        <a-input v-model="filters.file_node_id" class="pt-filter" placeholder="file_node_id" allow-clear />
        <a-input-number
          v-model="filters.limit"
          class="pt-filter pt-filter--limit"
          :min="1"
          :max="100"
          placeholder="limit"
        />
        <a-button type="primary" :loading="loading" @click="onSearch">
          <a-icon type="search" />查询
        </a-button>
        <a-button :loading="loading" @click="onRefresh">
          <a-icon type="reload" />刷新
        </a-button>
        <div class="pt-auto-refresh">
          <span>自动刷新</span>
          <a-switch v-model="autoRefresh" size="small" />
          <span v-if="autoRefresh" class="pt-auto-hint">每 5 秒</span>
        </div>
      </section>

      <!-- 错误提示 -->
      <a-alert v-if="loadError" type="error" :message="loadError" show-icon closable class="pt-error" @close="loadError = ''" />

      <!-- 任务表格 -->
      <a-table
        row-key="task_id"
        :columns="columns"
        :data-source="tasks"
        :loading="loading"
        :pagination="false"
        :locale="{ emptyText: loading ? '加载中...' : '暂无解析任务' }"
        class="pt-table"
        :scroll="{ x: 1200 }"
      >
        <template #status="text">
          <a-badge :status="getStatusBadge(text).status" :text="text || '-'" />
        </template>

        <template #stage="text, record">
          <div class="pt-stage-cell">
            <span class="pt-stage-label">{{ getStageInfo(record).label }}</span>
            <a-progress
              :percent="getStageInfo(record).percent"
              :status="getStageInfo(record).progressStatus"
              :show-info="false"
              size="small"
            />
          </div>
        </template>

        <template #task_id="text">
          <a-tooltip v-if="text" :title="text">
            <span class="pt-truncate">{{ truncateId(text) }}</span>
          </a-tooltip>
          <span v-else>-</span>
        </template>

        <template #updated_at="text">
          {{ formatTimestamp(text) }}
        </template>

        <template #duration="text, record">
          {{ formatDuration(record.created_at, record.updated_at) }}
        </template>

        <template #error="text, record">
          <template v-if="isFailedStatus(record.status) && text">
            <a-tooltip :title="text">
              <span class="pt-error-text">{{ truncateError(text) }}</span>
            </a-tooltip>
          </template>
          <span v-else>-</span>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getParseTasks } from "@/api/knowledge"

interface ParseTask {
  task_id?: string
  status?: string
  stage?: string
  kb_id?: string | number
  file_node_id?: string | number
  file_id?: string | number
  profile?: string
  parse_generation?: number
  platform_task_id?: string
  created_at?: number
  updated_at?: number
  error?: string
  summary?: string
}

const STAGE_ORDER = [
  "accepted",
  "queued",
  "waiting_slot",
  "slot_acquired",
  "downloading",
  "ocr",
  "chunking",
  "extracting",
  "graph_building",
  "saving",
  "done"
]

const STAGE_LABELS: Record<string, string> = {
  accepted: "已接收",
  queued: "排队中",
  waiting_slot: "等待资源",
  slot_acquired: "已获得资源",
  downloading: "下载文件",
  ocr: "OCR识别",
  chunking: "文本切分",
  extracting: "信息抽取",
  graph_building: "构建图谱",
  saving: "保存结果",
  done: "完成",
  failed: "失败"
}

const DONE_STAGE_INDEX = STAGE_ORDER.indexOf("done")

const filters = reactive({
  status: "",
  kb_id: "",
  file_node_id: "",
  limit: 20
})

const tasks = ref<ParseTask[]>([])
const loading = ref(false)
const loadError = ref("")
const autoRefresh = ref(false)
const isPageActive = ref(true)

let refreshTimer: ReturnType<typeof setInterval> | null = null

const columns = [
  { title: "状态", dataIndex: "status", key: "status", width: 110, scopedSlots: { customRender: "status" } },
  { title: "阶段", dataIndex: "stage", key: "stage", width: 160, scopedSlots: { customRender: "stage" } },
  { title: "task_id", dataIndex: "task_id", key: "task_id", width: 120, scopedSlots: { customRender: "task_id" } },
  { title: "kb_id", dataIndex: "kb_id", key: "kb_id", width: 90 },
  { title: "file_node_id", dataIndex: "file_node_id", key: "file_node_id", width: 110 },
  { title: "profile", dataIndex: "profile", key: "profile", width: 100 },
  { title: "更新时间", dataIndex: "updated_at", key: "updated_at", width: 170, scopedSlots: { customRender: "updated_at" } },
  { title: "耗时", key: "duration", width: 90, scopedSlots: { customRender: "duration" } },
  { title: "错误", dataIndex: "error", key: "error", width: 160, scopedSlots: { customRender: "error" } }
]

const metrics = computed(() => {
  const result = { running: 0, queued: 0, done: 0, failed: 0 }
  for (const task of tasks.value) {
    const group = getStatusGroup(task.status)
    if (group) result[group] += 1
  }
  return result
})

function normalizeStatus(status?: string): string {
  return (status || "").toLowerCase()
}

function isRunningStatus(status?: string): boolean {
  const s = normalizeStatus(status)
  return ["running", "parsing", "processing"].includes(s)
}

function isQueuedStatus(status?: string): boolean {
  const s = normalizeStatus(status)
  return ["queued", "pending"].includes(s)
}

function isDoneStatus(status?: string): boolean {
  const s = normalizeStatus(status)
  return ["done", "success", "completed"].includes(s)
}

function isFailedStatus(status?: string): boolean {
  const s = normalizeStatus(status)
  return ["failed", "error"].includes(s)
}

function getStatusGroup(status?: string): "running" | "queued" | "done" | "failed" | null {
  if (isRunningStatus(status)) return "running"
  if (isQueuedStatus(status)) return "queued"
  if (isDoneStatus(status)) return "done"
  if (isFailedStatus(status)) return "failed"
  return null
}

function getStatusBadge(status?: string): { status: string; text: string } {
  const text = status || "-"
  if (isRunningStatus(status)) return { status: "processing", text }
  if (isQueuedStatus(status)) return { status: "warning", text }
  if (isDoneStatus(status)) return { status: "success", text }
  if (isFailedStatus(status)) return { status: "error", text }
  return { status: "default", text }
}

function getStageInfo(record: ParseTask): {
  label: string
  percent: number
  progressStatus: "success" | "exception" | "active" | "normal"
} {
  const stage = record.stage || ""
  const status = record.status || ""

  if (isFailedStatus(status) || stage === "failed") {
    const label = STAGE_LABELS[stage] || (stage ? stage : "失败")
    return { label, percent: 100, progressStatus: "exception" }
  }

  if (isDoneStatus(status) || stage === "done") {
    return { label: STAGE_LABELS.done, percent: 100, progressStatus: "success" }
  }

  const idx = STAGE_ORDER.indexOf(stage)
  if (idx === -1) {
    return { label: "未知阶段", percent: 0, progressStatus: "normal" }
  }

  const percent = Math.round((idx / DONE_STAGE_INDEX) * 100)
  return {
    label: STAGE_LABELS[stage] || stage,
    percent,
    progressStatus: "active"
  }
}

function formatTimestamp(ts?: number | string): string {
  if (ts === undefined || ts === null || ts === "") return "-"
  const num = typeof ts === "string" ? parseInt(ts, 10) : ts
  if (!num || Number.isNaN(num)) return "-"
  const d = new Date(num * 1000)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatDuration(createdAt?: number, updatedAt?: number): string {
  if (!createdAt || !updatedAt) return "-"
  const diff = updatedAt - createdAt
  if (diff < 0) return "-"
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  const hours = Math.floor(diff / 3600)
  const mins = Math.floor((diff % 3600) / 60)
  return `${hours}h ${mins}m`
}

function truncateId(id: string, len = 12): string {
  if (id.length <= len) return id
  return `${id.slice(0, len)}…`
}

function truncateError(text: string, len = 40): string {
  if (text.length <= len) return text
  return `${text.slice(0, len)}…`
}

function buildQueryParams() {
  const params: Record<string, string | number> = {
    limit: Math.min(100, Math.max(1, filters.limit || 20))
  }
  if (filters.status) params.status = filters.status
  if (filters.kb_id) params.kb_id = filters.kb_id.trim()
  if (filters.file_node_id) params.file_node_id = filters.file_node_id.trim()
  return params
}

async function loadTasks(showLoading = true) {
  if (showLoading) loading.value = true
  loadError.value = ""
  try {
    const res = await getParseTasks(buildQueryParams())
    tasks.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e: any) {
    tasks.value = []
    loadError.value = e?.message || e?.resp_msg || "加载解析任务失败，请稍后重试"
  } finally {
    if (showLoading) loading.value = false
  }
}

function onSearch() {
  loadTasks(true)
}

function onRefresh() {
  loadTasks(true)
}

function clearRefreshTimer() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function setupRefreshTimer() {
  clearRefreshTimer()
  if (autoRefresh.value && isPageActive.value) {
    refreshTimer = setInterval(() => {
      loadTasks(false)
    }, 5000)
  }
}

watch(autoRefresh, setupRefreshTimer)

onMounted(() => {
  isPageActive.value = true
  loadTasks(true)
  setupRefreshTimer()
})

onActivated(() => {
  isPageActive.value = true
  setupRefreshTimer()
})

onDeactivated(() => {
  isPageActive.value = false
  clearRefreshTimer()
})

onUnmounted(() => {
  isPageActive.value = false
  clearRefreshTimer()
})
</script>

<style lang="less" scoped>
@border: #e5e7eb;
@primary: #2563eb;

.pt-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.pt-metric {
  padding: 18px 18px 16px;
  border: 1px solid @border;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);

  strong {
    display: block;
    margin-bottom: 6px;
    font-size: 28px;
    line-height: 1;
    color: #0f172a;
  }

  span {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #334155;
  }

  &--running strong { color: @primary; }
  &--queued strong { color: #d97706; }
  &--done strong { color: #16a34a; }
  &--failed strong { color: #dc2626; }
}

.pt-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid @border;
  border-radius: 14px;
  background: #fff;
}

.pt-filter {
  width: 140px;

  &--limit {
    width: 100px;
  }
}

.pt-auto-refresh {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  font-size: 13px;
  color: #64748b;
}

.pt-auto-hint {
  font-size: 12px;
  color: #94a3b8;
}

.pt-error {
  margin-bottom: 14px;
}

.pt-table {
  border: 1px solid @border;
  border-radius: 14px;
  overflow: hidden;
  background: #fff;
}

.pt-stage-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
}

.pt-stage-label {
  font-size: 12px;
  color: #475569;
}

.pt-truncate {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: #334155;
  cursor: default;
}

.pt-error-text {
  font-size: 12px;
  color: #dc2626;
  cursor: default;
}

@media (max-width: 900px) {
  .pt-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pt-auto-refresh {
    margin-left: 0;
    width: 100%;
  }
}
</style>
