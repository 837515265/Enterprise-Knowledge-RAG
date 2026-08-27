<template>
  <div class="retrieval-test">
    <div class="retrieval-hero">
      <div>
        <div class="retrieval-hero__eyebrow">Retrieval Lab</div>
        <div class="retrieval-hero__title">检索测试</div>
        <div class="retrieval-hero__desc">
          调用 app-rag-doc 混合检索，查看当前知识库召回条数、得分与片段（与生产检索链路一致）。
        </div>
      </div>
      <div class="retrieval-hero__metric">
        <strong>{{ results.length }}</strong>
        <span>条结果</span>
      </div>
    </div>

    <div class="retrieval-console">
      <div class="retrieval-search">
        <a-icon type="search" class="retrieval-search__icon" />
        <a-input
          v-model="query"
          size="large"
          placeholder="例如：合同解除条件有哪些？"
          class="retrieval-search__input"
          @pressEnter="onTest"
        />
      </div>
      <div class="retrieval-topk">
        <span>TopK</span>
        <a-input-number v-model="topK" :min="1" :max="50" size="large" class="retrieval-topk__input" />
      </div>
      <a-button type="primary" size="large" :loading="testing" class="retrieval-submit" @click="onTest">
        开始测试
      </a-button>
    </div>

    <!-- Advanced Options Panel -->
    <div class="advanced-panel">
      <div class="advanced-toggle" :class="{ open: showAdvanced }" @click="showAdvanced = !showAdvanced">
        <div class="advanced-toggle-left">
          <span>高级选项</span>
          <span style="font-size:11px;color:#94a3b8;">路由控制 · Rerank · Query改写 · 重试策略 等</span>
        </div>
        <div class="advanced-toggle-right" @click.stop>
          <span class="advanced-enable-label">启用</span>
          <a-switch v-model="advEnabled" size="small" />
          <a-icon :type="showAdvanced ? 'up' : 'down'" class="advanced-arrow" @click="showAdvanced = !showAdvanced" />
        </div>
      </div>
      <div v-show="showAdvanced" class="advanced-body" :class="{ disabled: !advEnabled }">
        <div class="adv-grid">
          <!-- 路由控制 -->
          <div class="adv-section-label">
            路由控制
            <span class="route-actions">
              <a @click.stop="selectAllRoutes">全选</a>
              <a-divider type="vertical" />
              <a @click.stop="invertRoutes">反选</a>
            </span>
          </div>
          <div class="adv-opt" style="grid-column: span 4;">
            <div class="route-chips">
              <span class="route-chip" :class="{ active: adv.routeQa }" @click="adv.routeQa = !adv.routeQa">QA</span>
              <span class="route-chip" :class="{ active: adv.routeGraph }" @click="adv.routeGraph = !adv.routeGraph">Neo4j 关系扩展</span>
              <span class="route-chip" :class="{ active: adv.routeBm25 }" @click="adv.routeBm25 = !adv.routeBm25">BM25</span>
              <span class="route-chip" :class="{ active: adv.routeVector }" @click="adv.routeVector = !adv.routeVector">向量</span>
              <span class="route-chip" :class="{ active: adv.routeStructured }" @click="adv.routeStructured = !adv.routeStructured">结构化</span>
              <span class="route-chip" :class="{ active: adv.routeSectionSummary }" @click="adv.routeSectionSummary = !adv.routeSectionSummary">章节摘要</span>
            </div>
          </div>

          <!-- Query 优化 -->
          <div class="adv-section-label">Query 优化</div>
          <div class="adv-opt adv-opt--switch">
            <label>Query 改写</label>
            <a-switch v-model="adv.queryAssistEnabled" size="small" />
          </div>
          <div class="adv-opt adv-opt--switch">
            <label>强制模型改写</label>
            <a-switch v-model="adv.forceRewrite" size="small" />
          </div>
          <div class="adv-opt">
            <label>最小改写字数</label>
            <a-input-number v-model="adv.rewriteMinWords" :min="0" size="small" />
          </div>
          <div class="adv-opt">
            <label>精确字段最大字符</label>
            <a-input-number v-model="adv.exactFieldMaxChars" :min="0" size="small" />
          </div>

          <!-- Rerank -->
          <div class="adv-section-label">Rerank</div>
          <div class="adv-opt adv-opt--switch"><label>启用 Rerank</label><a-switch v-model="adv.rerankEnabled" size="small" /></div>
          <div class="adv-opt">
            <label>Top N</label>
            <a-input-number v-model="adv.rerankTopN" :min="1" :max="100" size="small" />
          </div>
          <div class="adv-opt">
            <label>Score 权重 ({{ adv.rerankScoreWeight.toFixed(2) }})</label>
            <a-slider v-model="adv.rerankScoreWeight" :min="0" :max="1" :step="0.01" />
          </div>

          <!-- 上下文扩展 -->
          <div class="adv-section-label">上下文扩展</div>
          <div class="adv-opt adv-opt--switch"><label>扩展上下文</label><a-switch v-model="expandContext" size="small" /></div>
          <div class="adv-opt adv-opt--switch"><label>父级上下文</label><a-switch v-model="adv.parentContext" size="small" /></div>
          <div class="adv-opt adv-opt--switch"><label>替换子级上下文</label><a-switch v-model="adv.replaceChildContext" size="small" /></div>
          <div class="adv-opt">
            <label>父级最大字符</label>
            <a-input-number v-model="adv.parentMaxChars" :min="0" size="small" />
          </div>
          <div class="adv-opt">
            <label>父级最小字符</label>
            <a-input-number v-model="adv.parentMinChars" :min="0" size="small" />
          </div>

          <!-- 多样性 & 阈值 -->
          <div class="adv-section-label">多样性控制 &amp; 相似度</div>
          <div class="adv-opt">
            <label>每章节最大分组</label>
            <a-input-number v-model="adv.diversityPerSection" :min="0" size="small" />
          </div>
          <div class="adv-opt">
            <label>每文件最大分组</label>
            <a-input-number v-model="adv.diversityPerFile" :min="0" size="small" />
          </div>
          <div class="adv-opt" style="grid-column: span 2;">
            <label>相似度阈值 ({{ adv.similarityThreshold.toFixed(2) }})</label>
            <a-slider v-model="adv.similarityThreshold" :min="0" :max="1" :step="0.01" />
          </div>

          <!-- 文档匹配 & 图谱 -->
          <div class="adv-section-label">文档匹配 &amp; 图谱</div>
          <div class="adv-opt">
            <label>匹配加权 ({{ adv.docMatchBoost.toFixed(2) }})</label>
            <a-slider v-model="adv.docMatchBoost" :min="0" :max="1" :step="0.01" />
          </div>
          <div class="adv-opt">
            <label>不匹配惩罚 ({{ adv.docMismatchPenalty.toFixed(2) }})</label>
            <a-slider v-model="adv.docMismatchPenalty" :min="0" :max="1" :step="0.01" />
          </div>
          <div class="adv-opt adv-opt--switch"><label>图谱上下文规划</label><a-switch v-model="adv.graphContextPlanning" size="small" /></div>
          <div class="adv-opt adv-opt--switch"><label>全局社区检索</label><a-switch v-model="adv.graphGlobal" size="small" /></div>
          <div class="adv-opt">
            <label>图谱种子 Chunk</label>
            <a-input-number v-model="adv.graphSeedTopK" :min="1" :max="30" size="small" />
          </div>
          <div class="adv-opt">
            <label>图谱最大跳数</label>
            <a-input-number v-model="adv.graphMaxHops" :min="1" :max="2" size="small" />
          </div>
          <div class="adv-opt">
            <label>每种子最大节点</label>
            <a-input-number v-model="adv.graphMaxNodesPerSeed" :min="1" :max="50" size="small" />
          </div>
          <div class="adv-opt">
            <label>图谱全局上限</label>
            <a-input-number v-model="adv.graphMaxTotalNodes" :min="1" :max="200" size="small" />
          </div>
          <div class="adv-opt" style="grid-column: span 2;">
            <label>关系最低置信度 ({{ adv.graphMinConfidence.toFixed(2) }})</label>
            <a-slider v-model="adv.graphMinConfidence" :min="0" :max="1" :step="0.05" />
          </div>

          <!-- 范围锚点 -->
          <div class="adv-section-label">范围锚点</div>
          <div class="adv-opt" style="grid-column: span 2;">
            <label>锚点关键词</label>
            <a-select v-model="adv.scopeAnchors" mode="tags" size="small" placeholder="输入关键词后回车" :token-separators="[',']" />
          </div>
          <div class="adv-opt adv-opt--switch"><label>锚点过滤</label><a-switch v-model="adv.anchorFilter" size="small" /></div>
          <div class="adv-opt adv-opt--switch"><label>严格模式</label><a-switch v-model="adv.strictMode" size="small" /></div>

          <!-- 检索重试 -->
          <div class="adv-section-label">检索重试</div>
          <div class="adv-opt adv-opt--switch"><label>启用重试</label><a-switch v-model="adv.retryEnabled" size="small" /></div>
          <div class="adv-opt">
            <label>低置信度阈值 ({{ adv.retryLowConfidence.toFixed(2) }})</label>
            <a-slider v-model="adv.retryLowConfidence" :min="0" :max="1" :step="0.01" />
          </div>
          <div class="adv-opt">
            <label>最小匹配通道</label>
            <a-input-number v-model="adv.retryMinChannels" :min="0" size="small" />
          </div>
          <div class="adv-opt">
            <label>TopK 倍数</label>
            <a-input-number v-model="adv.retryTopKMultiplier" :min="1" size="small" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="lastError" class="retrieval-error">
      <a-icon type="warning" />
      <span>{{ lastError }}</span>
    </div>

    <div v-if="testing" class="retrieval-state">
      <a-icon type="loading" />
      正在召回相关内容…
    </div>

    <template v-else>
      <a-empty
        v-if="!hasSearched"
        class="retrieval-empty"
        description="输入检索语句后点击「开始测试」，将展示召回结果"
      />
      <div v-else-if="!results.length" class="retrieval-hint">
        <a-icon type="info-circle" />
        <div>
          <strong>本次未召回任何片段</strong>
          <p>请确认该库已在 app-rag-doc 侧完成索引；或尝试更换关键词、增大 TopK。</p>
        </div>
      </div>

      <div v-else class="retrieval-results">
        <div v-for="(item, index) in results" :key="index" class="retrieval-card">
          <div class="retrieval-card__head">
            <span class="retrieval-rank">#{{ index + 1 }}</span>
            <span class="retrieval-score">Score {{ formatScore(item.score) }}</span>
            <span class="source-tag" :style="{ background: sourceColor(item) }">{{ sourceLabel(item) }}</span>
          </div>
          <div v-if="item.fileName" class="retrieval-card__title">{{ item.fileName }}</div>
          <div class="retrieval-card__content">{{ item.content || "（无正文片段）" }}</div>
          <div v-if="getGraphPath(item)" class="retrieval-graph-path">
            <a-icon type="share-alt" />
            <span>{{ getGraphPath(item).fact || formatGraphChain(getGraphPath(item)) }}</span>
          </div>
          <div v-if="item.raw" class="retrieval-meta-toggle">
            <a @click.prevent="toggleMeta(index)">
              <a-icon :type="metaOpen[index] ? 'up' : 'down'" />
              {{ metaOpen[index] ? "收起" : "查看" }}原始数据
            </a>
          </div>
          <pre v-show="metaOpen[index]" class="retrieval-meta-json">{{ item.raw ? formatMeta(parseRaw(item.raw)) : '' }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { retrievalTest } from "@/api/knowledge"

const props = defineProps<{ kbId: string | number }>()

const query = ref("")
const topK = ref(5)
const expandContext = ref(true)
const testing = ref(false)
const results = ref<any[]>([])
const hasSearched = ref(false)
const lastError = ref("")
const metaOpen = ref<Record<number, boolean>>({})
const showAdvanced = ref(false)
const advEnabled = ref(false)

// Advanced options
const adv = reactive({
  queryAssistEnabled: true,
  forceRewrite: false,
  rewriteMinWords: 50,
  exactFieldMaxChars: 80,
  routeQa: true,
  routeGraph: false,
  routeBm25: true,
  routeVector: true,
  routeStructured: false,
  routeSectionSummary: false,
  rerankEnabled: true,
  rerankTopN: 30,
  rerankScoreWeight: 0.55,
  parentContext: false,
  replaceChildContext: false,
  parentMaxChars: 4000,
  parentMinChars: 700,
  diversityPerSection: 0,
  diversityPerFile: 0,
  similarityThreshold: 0,
  docMatchBoost: 0.30,
  docMismatchPenalty: 0.55,
  graphContextPlanning: false,
  graphGlobal: false,
  graphSeedTopK: 8,
  graphMaxHops: 1,
  graphMaxNodesPerSeed: 8,
  graphMaxTotalNodes: 120,
  graphMinConfidence: 0,
  scopeAnchors: [] as string[],
  anchorFilter: false,
  strictMode: false,
  retryEnabled: true,
  retryLowConfidence: 0.12,
  retryMinChannels: 1,
  retryTopKMultiplier: 2,
})

const SOURCE_MAP: Record<string, string> = {
  chunk: "文本块", field: "字段", qa: "问答", graph: "图谱", graph_relation: "图关系",
  bm25: "关键词", vector: "向量", section_summary: "章节摘要",
  knowledge_unit: "知识单元", anchor: "锚点", structured: "结构化",
  none: "—"
}

const SOURCE_COLOR_MAP: Record<string, string> = {
  chunk: "#2563eb", field: "#7c3aed", qa: "#059669", graph: "#d97706", graph_relation: "#d97706",
  bm25: "#2563eb", vector: "#2563eb", section_summary: "#0891b2",
  knowledge_unit: "#7c3aed", anchor: "#d97706", structured: "#475569",
}

function sourceType(item: any): string {
  return item.hitType || item.retrieverType || "none"
}

function sourceLabel(item: any): string {
  const t = sourceType(item)
  return SOURCE_MAP[t] || t
}

function sourceColor(item: any): string {
  const t = sourceType(item)
  return SOURCE_COLOR_MAP[t] || "#64748b"
}

function formatScore(score: any) {
  const n = Number(score)
  return Number.isFinite(n) ? n.toFixed(4) : "-"
}

function formatMeta(meta: any) {
  try { return JSON.stringify(meta, null, 2) } catch { return String(meta) }
}

function parseRaw(raw: any) {
  if (!raw) return {}
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return {} }
}

function getGraphPath(item: any) {
  const raw = parseRaw(item?.raw)
  return raw?.graph_path || raw?.graphPath || null
}

function formatGraphChain(path: any) {
  const names = Array.isArray(path?.nodes) ? path.nodes.map((node: any) => node?.name).filter(Boolean) : []
  const relations = Array.isArray(path?.relationships) ? path.relationships : []
  if (!names.length) return "图关系命中"
  return names.reduce((text: string, name: string, index: number) => (
    index === 0 ? name : `${text} —${relations[index - 1] || "关联"}→ ${name}`
  ), "")
}

function toggleMeta(index: number) {
  metaOpen.value = { ...metaOpen.value, [index]: !metaOpen.value[index] }
}

function extractApiError(e: any): string {
  const d = e?.response?.data
  if (d && typeof d === "object") {
    const msg = d.resp_msg ?? d.message ?? d.detail?.message
    if (typeof msg === "string" && msg) return msg
  }
  if (e?.message) return e.message
  return "检索请求失败"
}

function selectAllRoutes() {
  adv.routeQa = true; adv.routeGraph = true; adv.routeBm25 = true;
  adv.routeVector = true; adv.routeStructured = true; adv.routeSectionSummary = true;
}

function invertRoutes() {
  adv.routeQa = !adv.routeQa; adv.routeGraph = !adv.routeGraph;
  adv.routeBm25 = !adv.routeBm25; adv.routeVector = !adv.routeVector;
  adv.routeStructured = !adv.routeStructured; adv.routeSectionSummary = !adv.routeSectionSummary;
}

function buildRetrievalOptions() {
  const options: Record<string, any> = {
    expand_context: expandContext.value,
  }

  // Query 优化
  options.query_assist = { enabled: adv.queryAssistEnabled }
  if (adv.forceRewrite) options.query_assist.force_rewrite = true
  if (adv.rewriteMinWords !== 50) options.query_assist.min_rewrite_words = adv.rewriteMinWords
  if (adv.exactFieldMaxChars !== 80) options.query_assist.exact_field_max_chars = adv.exactFieldMaxChars

  // 路由控制
  options.routes = {
    qa_enabled: adv.routeQa,
    graph_enabled: adv.routeGraph,
    bm25_enabled: adv.routeBm25,
    vector_enabled: adv.routeVector,
    structured_enabled: adv.routeStructured,
    section_summary_enabled: adv.routeSectionSummary,
  }

  // Rerank
  if (adv.rerankEnabled) {
    options.rerank = { enabled: true, top_n: adv.rerankTopN, score_weight: adv.rerankScoreWeight }
  }

  // 上下文扩展
  if (adv.parentContext) {
    options.parent_context = { enabled: true, max_chars: adv.parentMaxChars, min_chars: adv.parentMinChars }
    if (adv.replaceChildContext) options.parent_context.replace_child = true
  }

  // 多样性 & 阈值
  if (adv.diversityPerSection > 0) options.diversity_per_section = adv.diversityPerSection
  if (adv.diversityPerFile > 0) options.diversity_per_file = adv.diversityPerFile
  if (adv.similarityThreshold > 0) options.similarity_threshold = adv.similarityThreshold

  // 文档匹配
  if (adv.docMatchBoost !== 0.30) options.document_match_boost = adv.docMatchBoost
  if (adv.docMismatchPenalty !== 0.55) options.document_mismatch_penalty = adv.docMismatchPenalty
  if (adv.graphContextPlanning) options.graph_context_planning = true
  if (adv.routeGraph) {
    options.graph = true
    options.graph_seed_top_k = adv.graphSeedTopK
    options.graph_max_hops = adv.graphMaxHops
    options.graph_max_nodes_per_seed = adv.graphMaxNodesPerSeed
    options.graph_max_total_nodes = adv.graphMaxTotalNodes
    options.graph_min_confidence = adv.graphMinConfidence
    if (adv.graphGlobal) options.graph_global = true
  }

  // 范围锚点
  if (adv.scopeAnchors.length) {
    options.scope_anchors = adv.scopeAnchors
    if (adv.anchorFilter) options.anchor_filter = true
  }
  if (adv.strictMode) options.strict_mode = true

  // 检索重试
  if (adv.retryEnabled) {
    options.retry = {
      enabled: true,
      low_confidence_threshold: adv.retryLowConfidence,
      min_matched_channels: adv.retryMinChannels,
      top_k_multiplier: adv.retryTopKMultiplier,
    }
  }

  return options
}

async function onTest() {
  if (!query.value.trim()) {
    message.warning("请输入检索内容")
    return
  }
  lastError.value = ""
  testing.value = true
  hasSearched.value = true
  metaOpen.value = {}
  try {
    const payload: Record<string, any> = {
      query: query.value.trim(),
      topK: topK.value,
    }
    if (advEnabled.value) {
      payload.options = buildRetrievalOptions()
      payload.graph = adv.routeGraph
    }
    const res: any = await retrievalTest(props.kbId, payload)
    if (res && res.resp_code !== undefined && res.resp_code !== 0) {
      lastError.value = res.resp_msg || "检索失败"
      results.value = []
      message.warning(lastError.value)
      return
    }
    results.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e: any) {
    const msg = extractApiError(e)
    lastError.value = msg
    results.value = []
    message.error(msg)
  } finally {
    testing.value = false
  }
}

</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.retrieval-test { color: #17233d; }

.retrieval-hero {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  padding: 20px 22px; margin-bottom: 16px;
  background: radial-gradient(circle at 10% 20%, rgba(37,99,235,0.16), transparent 28%),
    linear-gradient(135deg, #f8fbff 0%, #eef6ff 100%);
  border: 1px solid rgba(37,99,235,0.12); border-radius: 18px;
}
.retrieval-hero__eyebrow { margin-bottom: 6px; font-size: 12px; font-weight: 800; color: #2563eb; letter-spacing: 0.08em; text-transform: uppercase; }
.retrieval-hero__title { font-size: 20px; font-weight: 800; }
.retrieval-hero__desc { margin-top: 6px; color: #667085; }

.retrieval-hero__metric {
  display: flex; flex-direction: column; align-items: center;
  min-width: 86px; padding: 12px 16px; background: #fff;
  border: 1px solid #dbeafe; border-radius: 16px;
}
.retrieval-hero__metric strong { font-size: 24px; color: #2563eb; }
.retrieval-hero__metric span { font-size: 12px; color: #64748b; }

.retrieval-graph-path {
  display: flex; align-items: flex-start; gap: 7px; margin-top: 10px; padding: 9px 11px;
  font-size: 12px; line-height: 1.6; color: #92400e; background: #fffbeb;
  border: 1px solid #fde68a; border-radius: 9px;
}
.retrieval-graph-path .anticon { margin-top: 3px; color: #d97706; }

.retrieval-console {
  display: grid; grid-template-columns: minmax(0,1fr) 132px 124px;
  gap: 12px; align-items: center; padding: 16px; margin-bottom: 16px;
  background: #fff; border: 1px solid #e7edf6; border-radius: 16px;
  box-shadow: 0 10px 28px rgba(15,23,42,0.05);
}

/* Route chips — 检索方式 chip 样式 */
.route-chips { display: flex; flex-wrap: wrap; gap: 6px; }

.route-chip {
  padding: 4px 14px; font-size: 12px; font-weight: 600;
  border: 1px solid #d1d5db; border-radius: 999px;
  cursor: pointer; transition: all 0.15s;
  background: #fff; color: #475569; user-select: none;
}
.route-chip:hover { border-color: #93c5fd; }
.route-chip.active { background: #2563eb; color: #fff; border-color: #2563eb; }

/* 路由控制标题行 */
.adv-section-label {
  display: flex; align-items: center; gap: 10px;
}

.route-actions {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; font-weight: 600; text-transform: none; letter-spacing: 0;
  color: #94a3b8;
}
.route-actions a { color: #2563eb; cursor: pointer; }
.route-actions a:hover { text-decoration: underline; }

/* Advanced panel */
.advanced-panel {
  background: #fff; border: 1px solid #edf1f7;
  border-radius: 12px; margin-bottom: 16px; overflow: hidden;
}

.advanced-toggle {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; cursor: pointer; user-select: none;
  background: #f8fafc; transition: background 0.15s;
}
.advanced-toggle:hover { background: #f1f5f9; }
.advanced-toggle.open { border-bottom: 1px solid #edf1f7; }
.advanced-toggle-left { display: flex; align-items: center; gap: 8px; }
.advanced-toggle-left span { font-size: 13px; font-weight: 700; color: #475569; }
.advanced-toggle-right { display: flex; align-items: center; gap: 8px; cursor: default; }
.advanced-enable-label { font-size: 12px; font-weight: 700; color: #64748b; }
.advanced-arrow { font-size: 12px; color: #94a3b8; cursor: pointer; }
.advanced-body { padding: 14px 16px; }
.advanced-body.disabled { opacity: 0.5; pointer-events: none; }
.adv-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px; }

.adv-section-label {
  grid-column: span 4; font-size: 11px; font-weight: 800; color: #2563eb;
  text-transform: uppercase; letter-spacing: 0.06em;
  padding: 4px 0 0; border-top: 1px solid #f1f5f9; margin-top: 4px;
}
.adv-section-label:first-child { border-top: none; margin-top: 0; padding-top: 0; }
.adv-opt { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.adv-opt > label { font-size: 11px; font-weight: 700; color: #64748b; }

.adv-opt :deep(.ant-input-number),
.adv-opt :deep(.ant-select) { width: 100%; }
.adv-opt--switch { flex-direction: row; justify-content: space-between; align-items: center; padding-top: 16px; }

.retrieval-search {
  display: flex; align-items: center; gap: 10px; min-width: 0; height: 48px;
  padding: 0 14px; background: linear-gradient(180deg, #fbfdff 0%, #f7faff 100%);
  border: 1px solid #dbe7f5; border-radius: 14px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.retrieval-search:hover { border-color: #b7d2ff; box-shadow: 0 0 0 3px rgba(37,99,235,0.07); }
.retrieval-search:focus-within { border-color: #2563eb; background: #fff; box-shadow: 0 0 0 4px rgba(37,99,235,0.12); }
.retrieval-search__icon { color: #94a3b8; flex: 0 0 auto; }

.retrieval-search__input {
  flex: 1; min-width: 0;
  ::v-deep(.ant-input) { height: 46px; padding: 0; color: #0f172a; background: transparent; border: none; box-shadow: none; }
  ::v-deep(.ant-input::placeholder) { color: #94a3b8; }
}
.retrieval-topk { display: flex; align-items: center; gap: 8px; color: #64748b; white-space: nowrap; }

.retrieval-topk__input {
  width: 100%;
  &.ant-input-number { width: 100%; height: 48px; border-radius: 12px; border-color: #dbe3ef; }
  &.ant-input-number ::v-deep(.ant-input-number-input) { height: 46px; padding-left: 12px; padding-right: 12px; color: #0f172a; }
}
.retrieval-submit { height: 48px; border-radius: 12px; box-shadow: 0 8px 16px rgba(37,99,235,0.16); }

.retrieval-error {
  display: flex; align-items: flex-start; gap: 8px; padding: 12px 14px; margin-bottom: 12px;
  color: #b45309; background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px;
}
.retrieval-state, .retrieval-empty { padding: 48px 16px; color: #94a3b8; text-align: center; }
.retrieval-state .anticon { margin-right: 8px; }

.retrieval-hint {
  display: flex; gap: 12px; padding: 20px 18px; color: #64748b;
  background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 14px;
}
.retrieval-hint .anticon { margin-top: 3px; color: #2563eb; font-size: 18px; }
.retrieval-hint strong { display: block; margin-bottom: 6px; color: #0f172a; }
.retrieval-hint p { margin: 0; font-size: 13px; line-height: 1.5; }

.retrieval-results { display: grid; gap: 12px; }

.retrieval-card {
  padding: 16px 18px; background: #fff; border: 1px solid #edf1f7; border-radius: 16px;
}
.retrieval-card__head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.retrieval-rank { font-weight: 800; color: #2563eb; }
.retrieval-score { padding: 3px 8px; font-size: 12px; color: #0f766e; background: #ecfdf5; border-radius: 999px; }

/* Source tag - colored by hit_type */
.source-tag { display: inline-block; padding: 1px 8px; font-size: 12px; color: #fff; border-radius: 4px; }

.retrieval-card__title { margin-bottom: 6px; font-size: 14px; font-weight: 700; color: #0f172a; }
.retrieval-card__content { overflow: auto; max-height: 200px; color: #334155; line-height: 1.7; white-space: pre-wrap; }
.retrieval-meta-toggle { margin-top: 10px; font-size: 12px; }
.retrieval-meta-toggle a { color: #2563eb; cursor: pointer; }

.retrieval-meta-json {
  margin-top: 8px; padding: 10px 12px; font-size: 11px; line-height: 1.4;
  color: #475569; background: #f1f5f9; border-radius: 8px; overflow: auto; max-height: 360px;
  font-family: 'SF Mono', 'Cascadia Code', Consolas, monospace;
}

@media (max-width: 900px) {
  .retrieval-console { grid-template-columns: 1fr; }
  .retrieval-submit { width: 100%; }
  .adv-grid { grid-template-columns: 1fr 1fr; }
  .adv-section-label { grid-column: span 2; }
}
</style>
