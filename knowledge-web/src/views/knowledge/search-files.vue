<template>
  <div class="kb-page sf-page">
    <div class="kb-page-inner sf-shell">
      <div class="sf-head">
        <div>
          <div class="sf-title-row">
            <span class="sf-title-icon"><a-icon type="file-search" /></span>
            <h2>搜文件</h2>
          </div>
          <p>在可访问的知识库文件中定位标题、摘要与正文片段</p>
        </div>
        <div class="sf-head-meta">
          <span><a-icon type="database" /> {{ kbList.length || "--" }} 个知识库</span>
          <span><a-icon type="safety-certificate" /> 权限内检索</span>
        </div>
      </div>

      <!-- 搜索条 -->
      <section class="sf-search-panel">
        <div class="sf-bar">
          <a-select v-model="scope" class="sf-scope-select" placeholder="知识范围">
            <a-select-option value="">全部知识库</a-select-option>
            <a-select-option v-for="kb in kbList" :key="kb.id" :value="kb.id">{{ kb.name }}</a-select-option>
          </a-select>
          <div class="sf-input-wrap">
            <a-icon type="search" class="sf-search-icon" />
            <input
              v-model="keyword"
              type="search"
              placeholder="输入关键词，如：巡检、入库、台账..."
              @keydown.enter="onSearch"
            />
            <button type="button" :disabled="loading" @click="onSearch">
              <a-icon v-if="loading" type="loading" />
              <span>{{ loading ? "搜索中" : "搜索" }}</span>
            </button>
          </div>
        </div>

        <!-- 筛选条 -->
        <div class="sf-filters">
          <div class="sf-filter-group">
            <span class="sf-filter-label">文件类型</span>
            <a-select v-model="filterType" size="small" class="sf-type-select">
              <a-select-option value="">全部</a-select-option>
              <a-select-option value="pdf">PDF</a-select-option>
              <a-select-option value="word">Word</a-select-option>
              <a-select-option value="excel">Excel</a-select-option>
            </a-select>
          </div>
          <label class="sf-check">
            <a-checkbox v-model="titleOnly" />
            <span>仅标题匹配</span>
          </label>
          <button v-if="hasFilter" type="button" class="sf-clear-btn" @click="resetFilters">
            <a-icon type="reload" /> 重置
          </button>
        </div>
      </section>

      <!-- 结果 -->
      <div v-if="searched" class="sf-result-head">
        <div>
          <span class="sf-result-label">检索结果</span>
          <p>
            在 <strong>{{ selectedScopeName }}</strong> 中找到 <strong>{{ results.length }}</strong> 个文件
          </p>
        </div>
        <span v-if="filterSummary" class="sf-filter-summary">{{ filterSummary }}</span>
      </div>

      <div v-if="loading" class="sf-loading">
        <a-icon type="loading" />
        <span>正在检索文件...</span>
      </div>

      <div v-else class="sf-result-list">
        <article v-for="(item, i) in results" :key="i" class="sf-result">
          <div class="sf-result-icon" :class="`is-${getFileTone(item)}`">
            <a-icon :type="getFileIcon(item)" />
          </div>
          <div class="sf-result-body">
            <div class="sf-result-title-row">
              <h4 v-html="highlightKeyword(resultFileLabel(item))"></h4>
              <span v-if="item.fileType" class="sf-file-tag">{{ formatFileType(item.fileType) }}</span>
            </div>
            <div class="sf-result-meta">
              <span v-if="item.kbName"><a-icon type="folder" /> {{ item.kbName }}</span>
              <span v-if="item.size"><a-icon type="hdd" /> {{ item.size }}</span>
              <span v-if="item.updateTime"><a-icon type="clock-circle" /> {{ item.updateTime }}</span>
            </div>
            <div
              v-if="item.snippet || item.description"
              class="sf-result-snippet"
              v-html="highlightKeyword(item.snippet || item.description || '')"
            ></div>
            <div class="sf-result-actions">
              <a v-if="item.id" @click.prevent="onPreview(item)"><a-icon type="eye" /> 预览</a>
              <a v-if="item.id" @click.prevent="onDownload(item)"><a-icon type="download" /> 下载</a>
            </div>
          </div>
        </article>
      </div>

      <div v-if="!searched && !loading" class="sf-guide">
        <div class="sf-guide-icon"><a-icon type="search" /></div>
        <div>
          <strong>输入关键词开始检索</strong>
          <p>可先选择知识范围与文件类型，结果会按文件展示匹配片段。</p>
        </div>
      </div>

      <div v-if="searched && !loading && results.length === 0" class="sf-empty">
        <div class="sf-empty-icon"><a-icon type="file-search" /></div>
        <p>未找到匹配的文件</p>
        <span>换个关键词或放宽筛选条件再试试</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { downLoadByFileId } from "@/api/common"
import { getKnowledgeBaseList, searchFiles } from "@/api/knowledge"
import { decodeDisplayText } from "@/utils/logic/decodeDisplayText"
import { previewFile } from "@/utils/previewFile"

const route = useRoute()

function normalizeRouteKeyword(value: unknown) {
  if (typeof value !== "string") {
    return ""
  }
  const text = value.trim()
  if (/^\[object\s.+\]$/i.test(text)) {
    return ""
  }
  return text
}

const keyword = ref("")
const scope = ref("")
const filterType = ref("")
const titleOnly = ref(false)
const searched = ref(false)
const loading = ref(false)
const results = ref<any[]>([])
const kbList = ref<any[]>([])

function applyRouteState() {
  keyword.value = normalizeRouteKeyword(route.query.q)
  scope.value = (route.query.kbId as string) || ""
  if (!keyword.value.trim()) {
    searched.value = false
    results.value = []
    loading.value = false
  }
}

function syncRouteStateAndSearch() {
  applyRouteState()
  if (keyword.value.trim()) {
    onSearch()
  }
}

const selectedScopeName = computed(() => {
  if (!scope.value) return "全部知识库"
  const found = kbList.value.find((item) => `${item.id}` === `${scope.value}`)
  return found?.name || "当前知识库"
})

const hasFilter = computed(() => !!filterType.value || titleOnly.value)
const filterSummary = computed(() => {
  const parts = []
  if (filterType.value) parts.push(formatFileType(filterType.value))
  if (titleOnly.value) parts.push("仅标题")
  return parts.join(" / ")
})

onMounted(async () => {
  try {
    const res = await getKnowledgeBaseList({ pageSize: 100 })
    kbList.value = Array.isArray(res?.data) ? res.data : []
  } catch (e) {
    console.error(e)
  }
})

watch(
  () => route.fullPath,
  () => {
    syncRouteStateAndSearch()
  }
)

onActivated(() => {
  syncRouteStateAndSearch()
})

async function onSearch() {
  if (!keyword.value.trim()) {
    message.warning("请输入关键词")
    return
  }
  searched.value = true
  loading.value = true
  try {
    const res = await searchFiles({
      keyword: keyword.value.trim(),
      kbId: scope.value || undefined,
      fileType: filterType.value || undefined,
      titleOnly: titleOnly.value || undefined
    })
    results.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    console.error(e)
    results.value = []
  } finally {
    loading.value = false
  }
}

function getFileIcon(item: any) {
  const ext = (item.fileType || item.name || "").toLowerCase()
  if (ext.includes("pdf")) return "file-pdf"
  if (ext.includes("word") || ext.includes("doc")) return "file-word"
  if (ext.includes("excel") || ext.includes("xls")) return "file-excel"
  return "file-text"
}

function getFileTone(item: any) {
  const ext = (item.fileType || item.name || "").toLowerCase()
  if (ext.includes("pdf")) return "pdf"
  if (ext.includes("word") || ext.includes("doc")) return "word"
  if (ext.includes("excel") || ext.includes("xls")) return "excel"
  return "text"
}

function resultFileLabel(item: any) {
  return decodeDisplayText(item.title || item.name || "未命名文件")
}

function formatFileType(type: string) {
  const normalized = `${type || ""}`.toLowerCase()
  if (normalized.includes("pdf")) return "PDF"
  if (normalized.includes("word") || normalized.includes("doc")) return "Word"
  if (normalized.includes("excel") || normalized.includes("xls")) return "Excel"
  return type || "文件"
}

function highlightKeyword(text: string) {
  const safeText = escapeHtml(`${text || ""}`)
  if (!keyword.value.trim()) return safeText
  const escaped = keyword.value.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return safeText.replace(new RegExp(`(${escaped})`, "gi"), "<mark>$1</mark>")
}

function escapeHtml(text: string) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function resetFilters() {
  filterType.value = ""
  titleOnly.value = false
}

function onPreview(item: any) {
  const fid = item?.fileId
  if (!fid) {
    message.warning("当前结果缺少文件 ID，无法预览")
    return
  }
  previewFile(String(fid), "page")
}

async function onDownload(item: any) {
  const fid = item?.fileId
  if (!fid) {
    message.warning("当前结果缺少文件 ID，无法下载")
    return
  }
  try {
    const res: any = await downLoadByFileId(fid)
    const blob = res?.data instanceof Blob ? res.data : new Blob([res?.data])
    if (blob.type === "application/json") {
      const data = JSON.parse(await blob.text())
      message.warning(data?.msg || data?.resp_msg || "下载失败")
      return
    }
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = resultFileLabel(item) || "download"
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    console.error(e)
    message.error("下载失败")
  }
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@border: #e5e7eb;
@muted: #64748b;
@text: #0f172a;

.sf-page {
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 30%),
    linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.sf-shell {
  width: 100%;
  max-width: 1040px;
}

.sf-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 14px 2px 18px;

  p {
    margin: 8px 0 0;
    color: @muted;
    line-height: 1.5;
  }
}

.sf-title-row {
  display: flex;
  align-items: center;
  gap: 10px;

  h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    color: @text;
  }
}

.sf-title-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e0f2fe;
  color: #0369a1;
  box-shadow: inset 0 0 0 1px rgba(3, 105, 161, 0.08);

  .anticon { font-size: 18px; }
}

.sf-head-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    border: 1px solid #dbeafe;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.78);
    color: #1e40af;
    font-size: 12px;
    font-weight: 600;
  }
}

.sf-search-panel {
  padding: 16px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 14px 38px rgba(15, 23, 42, 0.06);
}

.sf-bar {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.sf-scope-select {
  width: 220px;
  flex-shrink: 0;

  :deep(.ant-select-selection) {
    min-height: 46px;
    border-radius: 10px;
    border-color: @border;
    display: flex;
    align-items: center;
  }

  :deep(.ant-select-selection__rendered) {
    width: 100%;
    line-height: 44px;
  }
}

.sf-input-wrap {
  flex: 1;
  min-width: 260px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid @border;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
  padding-left: 16px;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:focus-within {
    border-color: @primary;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
  }

  input {
    flex: 1;
    border: none;
    outline: none;
    padding: 11px 0;
    font-size: 14px;
    background: transparent;
  }

  button {
    min-width: 92px;
    padding: 0 20px;
    height: 100%;
    border: none;
    background: @primary;
    color: #fff;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;

    &:hover:not(:disabled) { background: #1d4ed8; }
    &:disabled {
      cursor: not-allowed;
      opacity: 0.74;
    }
  }
}

.sf-search-icon { color: #64748b; }

.sf-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
  font-size: 13px;
}

.sf-filter-group,
.sf-check,
.sf-clear-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  color: @muted;
}

.sf-filter-label {
  font-size: 13px;
  color: #475569;
}

.sf-type-select {
  width: 96px;
}

.sf-clear-btn {
  height: 30px;
  padding: 0 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: #bfdbfe;
    color: #1d4ed8;
    background: #eff6ff;
  }
}

.sf-result-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  margin: 20px 2px 12px;

  p {
    margin: 3px 0 0;
    font-size: 14px;
    color: @muted;
  }

  strong { color: #1e293b; }
}

.sf-result-label {
  font-size: 12px;
  color: #2563eb;
  font-weight: 700;
}

.sf-filter-summary {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 4px 9px;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
}

.sf-result-list {
  display: grid;
  gap: 10px;
}

.sf-result {
  display: flex;
  gap: 14px;
  border: 1px solid @border;
  border-radius: 12px;
  padding: 16px 18px;
  background: #fff;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;

  &:hover {
    border-color: #93c5fd;
    box-shadow: 0 10px 28px rgba(37, 99, 235, 0.08);
    transform: translateY(-1px);
  }
}

.sf-result-icon {
  width: 44px;
  height: 44px;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: #f1f5f9;
  color: #475569;

  .anticon { font-size: 20px; }

  &.is-pdf { background: #fef2f2; color: #dc2626; }
  &.is-word { background: #eff6ff; color: #2563eb; }
  &.is-excel { background: #ecfdf5; color: #16a34a; }
  &.is-text { background: #f8fafc; color: #475569; }
}

.sf-result-body {
  flex: 1;
  min-width: 0;
}

.sf-result-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

  h4 {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: #0f172a;

    :deep(mark) { background: #fef08a; padding: 0 2px; border-radius: 2px; }
  }
}

.sf-file-tag {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
  line-height: 20px;
}

.sf-result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;

  span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #94a3b8;
  }
}

.sf-result-snippet {
  font-size: 13px;
  line-height: 1.55;
  color: #475569;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  border-left: 3px solid #bfdbfe;

  :deep(mark) { background: #fef08a; padding: 0 2px; border-radius: 2px; }
}

.sf-result-actions {
  display: flex;
  gap: 14px;
  margin-top: 10px;

  a {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: @primary;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.15s;

    &:hover { opacity: 0.8; }
  }
}

.sf-guide,
.sf-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 18px;
  padding: 52px 24px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.68);
  color: #64748b;
}

.sf-guide {
  justify-content: flex-start;

  strong {
    display: block;
    color: #1e293b;
    font-size: 15px;
    margin-bottom: 4px;
  }

  p {
    margin: 0;
    color: #64748b;
  }
}

.sf-guide-icon,
.sf-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #eff6ff;
  color: #2563eb;

  .anticon { font-size: 22px; }
}

.sf-loading {
  font-size: 14px;

  .anticon {
    font-size: 20px;
    color: @primary;
  }
}

.sf-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-top: 18px;
  padding: 60px 20px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  color: #64748b;
  font-size: 14px;

  p {
    margin: 4px 0 0;
    color: #1e293b;
    font-weight: 600;
  }

  span {
    font-size: 13px;
    color: #94a3b8;
  }
}

@media (max-width: 768px) {
  .sf-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .sf-head-meta { justify-content: flex-start; }
  .sf-bar { flex-direction: column; }
  .sf-scope-select,
  .sf-input-wrap {
    width: 100%;
    min-width: 0;
  }

  .sf-result-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .sf-result {
    padding: 14px;
  }
}
</style>
