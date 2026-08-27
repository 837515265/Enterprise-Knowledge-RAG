<template>
  <section class="knowledge-panel">
    <div class="panel-head">
      <div>
        <span class="eyebrow">知识工作区</span>
        <strong>{{ fileName }}</strong>
      </div>
      <a-tooltip title="刷新解析数据"><button class="icon-button" @click="loadAll"><a-icon type="reload" /></button></a-tooltip>
    </div>

    <nav class="primary-tabs">
      <button v-for="tab in availableTabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        <a-icon :type="tab.icon" />{{ tab.label }}
        <span v-if="tab.count !== undefined">{{ tab.count }}</span>
      </button>
    </nav>

    <a-spin :spinning="loading" class="panel-body-spin">
      <div v-show="activeTab === 'content'" class="panel-scroll content-view">
        <section class="insight-card summary-card">
          <div class="insight-head">
            <div><span class="section-icon"><a-icon type="read" /></span><strong>章节摘要</strong><em v-if="activeSummary?.summarySource === 'llm'">AI</em></div>
            <span v-if="activeSummary?.confidence" class="confidence-tag">{{ confidenceLabel(activeSummary.confidence) }}</span>
          </div>
          <p v-if="activeSummary?.nodeSummary" :class="{ expanded: summaryExpanded }">{{ activeSummary.nodeSummary }}</p>
          <a-empty v-else description="当前解析代际暂无章节摘要" />
          <button v-if="activeSummary?.nodeSummary?.length > 130" class="text-action" @click="summaryExpanded = !summaryExpanded">
            {{ summaryExpanded ? "收起摘要" : "查看完整摘要" }} <a-icon :type="summaryExpanded ? 'up' : 'down'" />
          </button>
        </section>

        <section v-if="processSteps.length" class="insight-card process-card">
          <div class="insight-head">
            <div><span class="section-icon"><a-icon type="branches" /></span><strong>业务流程</strong></div>
            <span>{{ processSteps.length }} 个环节</span>
          </div>
          <div class="process-track">
            <button v-for="(step, index) in processSteps" :key="step.unitId" @click="locateKnowledgeUnit(step)">
              <i>{{ index + 1 }}</i><span><strong>{{ step.subjectText }}</strong><small>{{ step.objectText }}</small></span>
            </button>
          </div>
        </section>

        <section class="insight-card">
          <div class="insight-head">
            <div><span class="section-icon"><a-icon type="key" /></span><strong>关键字段 / 实体</strong></div>
            <span>{{ keyFields.length + anchors.length }} 项</span>
          </div>
          <div v-if="keyFields.length" class="field-grid">
            <div v-for="field in keyFields" :key="`${field.label}-${field.value}`"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div>
          </div>
          <div v-if="anchors.length" class="entity-cloud">
            <button v-for="anchor in anchors" :key="anchor.anchorId" @click="locateAnchor(anchor)">
              <a-icon type="tag" />{{ anchor.anchorName }}<small>{{ anchorTypeLabel(anchor.anchorType) }}</small>
            </button>
          </div>
          <a-empty v-if="!keyFields.length && !anchors.length" description="暂无关键字段或实体" />
        </section>

        <section class="insight-card">
          <div class="insight-head">
            <div><span class="section-icon"><a-icon type="ordered-list" /></span><strong>目录层级</strong></div>
            <span>{{ sections.length }} 个章节</span>
          </div>
          <div v-if="sections.length" class="outline-list">
            <button v-for="section in sections" :key="section.sectionId" :style="{ paddingLeft: `${12 + Math.max(0, Number(section.sectionLevel || 1) - 1) * 16}px` }" @click="locateSection(section)">
              <i>{{ Number(section.sectionLevel || 1) }}</i><span><strong>{{ section.sectionTitle || section.sectionPath }}</strong><small>{{ sectionTypeLabel(section.sectionType) }}</small></span>
              <em v-if="section.pageStart">第 {{ section.pageStart }} 页</em><a-icon type="right" />
            </button>
          </div>
          <a-empty v-else description="暂无目录层级" />
        </section>

        <section v-if="knowledgeUnits.length" class="insight-card knowledge-card">
          <div class="insight-head">
            <div><span class="section-icon"><a-icon type="highlight" /></span><strong>规则与知识条目</strong></div>
            <button class="text-action" @click="showAllUnits = !showAllUnits">{{ showAllUnits ? "收起" : `查看全部 ${knowledgeUnits.length} 项` }}</button>
          </div>
          <button v-for="unit in visibleKnowledgeUnits" :key="unit.unitId" class="knowledge-row" @click="locateKnowledgeUnit(unit)">
            <span class="unit-type">{{ unitTypeLabel(unit.unitType) }}</span>
            <span><strong>{{ unit.subjectText }} · {{ unit.predicateText }}</strong><small>{{ unit.objectText }}</small></span>
            <a-icon type="aim" />
          </button>
        </section>

        <section class="insight-card raw-chunk-card">
          <button class="raw-chunk-trigger" @click="showRawChunks = !showRawChunks">
            <span><a-icon type="file-text" /><strong>内容片段与证据</strong><small>{{ overview.chunkCount }} 个 Chunk · 可编辑、审核和定位原文</small></span>
            <a-icon :type="showRawChunks ? 'up' : 'down'" />
          </button>
          <ChunkList
            v-if="showRawChunks"
            :key="`content-${fileId}`"
            :kb-id="kbId"
            :file-id="fileId"
            :file-name="fileName"
            :inline="true"
            :content-only="true"
            :can-edit="canEdit"
            :can-audit="canAudit"
            :active-chunk-id="activeChunkId"
            @select-chunk="$emit('locate', $event)"
            @edited="$emit('edited')"
            @audited="$emit('audited')"
          />
        </section>
      </div>

      <div v-if="activeTab === 'multimodal'" class="multimodal-view">
        <div class="secondary-tabs">
          <button :class="{ active: multimodalMode === 'flows' }" @click="multimodalMode = 'flows'">流程 {{ flows.length }}</button>
          <button :class="{ active: multimodalMode === 'images' }" @click="multimodalMode = 'images'">图片 {{ images.length }}</button>
          <button :class="{ active: multimodalMode === 'relations' }" @click="multimodalMode = 'relations'">图片关系</button>
        </div>

        <div v-if="multimodalMode === 'flows'" class="flow-layout">
          <aside class="flow-list">
            <button v-for="(flow, index) in flows" :key="flow.id" :class="{ active: selectedFlowIndex === index }" @click="selectedFlowIndex = index">
              <span>流程 {{ String(index + 1).padStart(2, '0') }}</span>
              <strong>{{ flow.topic || flow.title || `业务流程 ${index + 1}` }}</strong>
              <small>{{ flow.steps.length }} 个步骤 · {{ flow.imageCount }} 张证据图</small>
            </button>
          </aside>
          <div class="step-timeline">
            <template v-if="selectedFlow">
              <div class="flow-heading"><span class="eyebrow">流程解析</span><h3>{{ selectedFlow.topic || selectedFlow.title }}</h3></div>
              <article v-for="(step, index) in selectedFlow.steps" :key="`${selectedFlow.id}-${index}`" class="step-card">
                <div class="step-index">{{ step.step_no || index + 1 }}</div>
                <div class="step-main">
                  <strong>{{ step.step_name || `步骤 ${index + 1}` }}</strong>
                  <p>{{ step.description || "已从文档图片中识别该操作步骤" }}</p>
                  <div class="evidence-row">
                    <button v-for="evidence in step.evidence_images || []" :key="evidence.image_id" @click="openEvidence(evidence)">
                      <KnowledgeImageThumb :file-id="evidence.image_file_id" :alt="step.step_name" />
                      <span>{{ evidence.role === 'primary' ? '主证据' : '辅助证据' }}</span>
                    </button>
                  </div>
                </div>
              </article>
            </template>
            <a-empty v-else description="暂无流程解析结果" />
          </div>
        </div>

        <div v-else-if="multimodalMode === 'images'" class="image-grid panel-scroll">
          <button v-for="image in images" :key="image.id" @click="openImage(image)">
            <KnowledgeImageThumb :file-id="image.fileId" :alt="image.title" />
            <span><strong>{{ image.title }}</strong><small>第 {{ image.pageStart || '-' }} 页 · {{ image.visualType || '文档图片' }}</small></span>
          </button>
        </div>

        <div v-else class="image-relations panel-scroll">
          <div class="relation-note"><a-icon type="info-circle" />图片关系根据流程步骤和主辅证据自动归纳。</div>
          <article v-for="relation in imageRelations" :key="relation.id">
            <span>{{ relation.source }}</span><i>{{ relation.type }}</i><span>{{ relation.target }}</span>
          </article>
          <a-empty v-if="!imageRelations.length" description="暂无图片关系" />
        </div>
      </div>

      <KnowledgeGraphView
        v-if="activeTab === 'graph'"
        :graph="displayGraph"
        :include-chunks="includeChunks"
        @toggle-chunks="loadGraph"
        @locate="$emit('locate', $event)"
      />
    </a-spin>

    <aside v-if="selectedEvidence" class="evidence-drawer">
      <div class="evidence-head"><div><span class="eyebrow">证据详情</span><strong>{{ selectedEvidence.title }}</strong></div><button @click="selectedEvidence = null"><a-icon type="close" /></button></div>
      <div class="evidence-preview"><KnowledgeImageThumb :file-id="selectedEvidence.fileId" :alt="selectedEvidence.title" natural /></div>
      <dl>
        <template v-if="selectedEvidence.visualType"><dt>图片类型</dt><dd>{{ selectedEvidence.visualType }}</dd></template>
        <template v-if="selectedEvidence.keyFacts.length"><dt>关键信息</dt><dd><ul><li v-for="fact in selectedEvidence.keyFacts" :key="fact">{{ fact }}</li></ul></dd></template>
        <template v-if="selectedEvidence.entities.length"><dt>识别实体</dt><dd class="tag-list"><span v-for="entity in selectedEvidence.entities" :key="entity">{{ entity }}</span></dd></template>
      </dl>
      <a-button type="primary" block @click="$emit('locate', selectedEvidence.raw)"><a-icon type="aim" />定位原文</a-button>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { getChunkList, getFileAnalysis, getFileKnowledgeGraph } from "@/api/knowledge"
import ChunkList from "./chunk-list.vue"
import KnowledgeGraphView from "./knowledge-graph-view.vue"
import KnowledgeImageThumb from "./knowledge-image-thumb.vue"

const props = defineProps<{
  kbId: string | number
  fileId: string | number
  fileName: string
  canEdit?: boolean
  canAudit?: boolean
  activeChunkId?: string | number | null
}>()
const emit = defineEmits(["locate", "overview", "edited", "audited"])
const activeTab = ref("content")
const multimodalMode = ref("flows")
const loading = ref(false)
const chunks = ref<any[]>([])
const analysis = ref<any>({ sections: [], summaries: [], knowledgeUnits: [], anchors: [], relations: [], chunkTypeStats: [] })
const graph = ref<any>({ nodes: [], edges: [], stats: {} })
const includeChunks = ref(false)
const selectedFlowIndex = ref(0)
const selectedEvidence = ref<any>(null)
const summaryExpanded = ref(false)
const showAllUnits = ref(false)
const showRawChunks = ref(false)

function parseJson(value: any) {
  if (!value) return {}
  if (typeof value === "object") return value
  try { return JSON.parse(value) } catch (e) { return {} }
}
function responseData(res: any): any[] {
  const value = res?.data || res?.datas || res?.records || []
  return Array.isArray(value) ? value : value?.records || []
}
function resultData(res: any) { return res?.datas || res?.data || res || {} }

function uniqueBy(items: any[], key: string) {
  const seen = new Set<string>()
  return (items || []).filter((item) => {
    const value = String(item?.[key] || "")
    if (!value || seen.has(value)) return false
    seen.add(value)
    return true
  })
}

const sections = computed(() => uniqueBy(analysis.value?.sections || [], "sectionId"))
const summaries = computed(() => uniqueBy(analysis.value?.summaries || [], "sectionId"))
const knowledgeUnits = computed(() => uniqueBy(analysis.value?.knowledgeUnits || [], "unitId"))
const anchors = computed(() => uniqueBy(analysis.value?.anchors || [], "anchorId"))
const activeSummary = computed(() => summaries.value.find((item) => Number(item.sectionLevel || 1) === 1) || summaries.value[0] || null)
const structuredSummary = computed(() => parseJson(activeSummary.value?.structuredSummaryJson))
const processSteps = computed(() => {
  const units = knowledgeUnits.value.filter((item) => item.unitType === "process_step")
  if (units.length) return units
  const summaryChunkIds = parseJson(activeSummary.value?.coveredChunkIdsJson)
  const primaryChunkId = Array.isArray(summaryChunkIds) ? summaryChunkIds[0] : null
  return (structuredSummary.value?.process_steps || []).map((value: string, index: number) => {
    const [subjectText, ...rest] = String(value).split(/[：:]/)
    return { unitId: `summary-step-${index}`, subjectText, objectText: rest.join("："), primaryChunkId, pageStart: structuredSummary.value?.page_start }
  })
})

const displayGraph = computed(() => ({
  ...graph.value,
  nodes: (graph.value?.nodes || []).map((node: any) => {
    const unit = knowledgeUnits.value.find((item) => item.subjectText === node.name)
    const anchor = anchors.value.find((item) => item.anchorName === node.name)
    const chunkId = node.chunkId || unit?.primaryChunkId || anchor?.sourceChunkId
    const chunk = chunks.value.find((item) => String(item.id) === String(chunkId))
    return {
      ...node,
      chunkId,
      pageStart: node.pageStart || chunk?.pageStart,
      pageEnd: node.pageEnd || chunk?.pageEnd,
      blockIds: node.blockIds || chunk?.blockIds,
      description: node.description || unit?.objectText || anchor?.evidenceQuote,
      properties: {
        ...parseJson(node.properties),
        ...(unit ? {
          subjectText: unit.subjectText,
          predicateText: unit.predicateText,
          objectText: unit.objectText,
          unitType: unit.unitType,
          unitSubtype: unit.unitSubtype,
          sourceSectionId: unit.sourceSectionId,
          sourceChunkId: unit.primaryChunkId,
          evidenceQuote: unit.evidenceQuote,
          confidence: unit.confidence
        } : {}),
        ...(anchor ? { anchorType: anchor.anchorType, aliases: parseJson(anchor.aliasesJson), sourceChunkId: anchor.sourceChunkId, evidenceQuote: anchor.evidenceQuote, confidence: anchor.confidence } : {})
      }
    }
  })
}))

const fieldLabels: Record<string, string> = {
  channel: "申请渠道", channels: "申请渠道", product: "适用产品", categories: "产品类型",
  condition: "触发条件", timing: "生效时点", action: "执行动作", actions: "执行动作",
  actor: "责任主体", actors: "责任主体", supported_methods: "认证方式", recovery_path: "恢复路径",
  option: "可选操作", feature: "功能支持", target: "作用对象"
}
const keyFields = computed(() => {
  const result: any[] = []
  const seen = new Set<string>()
  for (const unit of knowledgeUnits.value) {
    const normalized = parseJson(unit.normalizedJson)
    for (const [key, rawValue] of Object.entries(normalized)) {
      const label = fieldLabels[key]
      if (!label || rawValue === undefined || rawValue === null || rawValue === "") continue
      const value = Array.isArray(rawValue) ? rawValue.join("、") : typeof rawValue === "object" ? JSON.stringify(rawValue) : String(rawValue)
      const signature = `${label}:${value}`
      if (!seen.has(signature)) {
        seen.add(signature)
        result.push({ label, value })
      }
      if (result.length >= 8) return result
    }
  }
  return result
})
const visibleKnowledgeUnits = computed(() => showAllUnits.value ? knowledgeUnits.value : knowledgeUnits.value.slice(0, 5))

const images = computed(() => chunks.value.filter((item) => item.chunkType === "image").map((item, index) => {
  const meta = parseJson(item.metadataJson)
  return {
    id: item.id,
    imageId: meta.image_id || meta.imageId || String(item.id),
    fileId: meta.file_center_file_id || meta.image_file_id || meta.fileId,
    title: meta.title || meta.caption || item.title || `图片 ${String(index + 1).padStart(2, "0")}`,
    visualType: meta.visual_type || meta.visualType,
    keyFacts: meta.key_facts || meta.keyFacts || [],
    entities: (meta.entities || []).map((entity: any) => typeof entity === "string" ? entity : entity.name || entity.value).filter(Boolean),
    pageStart: item.pageStart,
    raw: item
  }
}))
const imageMap = computed(() => Object.fromEntries(images.value.map((item) => [String(item.imageId), item])))
const flows = computed(() => chunks.value.filter((item) => item.chunkType === "image_group").map((item) => {
  const meta = parseJson(item.metadataJson)
  const steps = Array.isArray(meta.steps) ? meta.steps : []
  return { id: item.id, topic: meta.topic, title: item.title, steps, imageCount: steps.reduce((sum: number, step: any) => sum + (step.evidence_images || []).length, 0), raw: item }
}))
const selectedFlow = computed(() => flows.value[selectedFlowIndex.value] || null)
const imageRelations = computed(() => {
  const relations: any[] = []
  flows.value.forEach((flow) => {
    flow.steps.forEach((step: any, index: number) => {
      const ids = (step.evidence_images || []).map((item: any) => item.image_id).filter(Boolean)
      for (let i = 1; i < ids.length; i++) relations.push({ id: `${flow.id}-${index}-support-${i}`, source: ids[0], type: "辅助说明", target: ids[i] })
      const next = flow.steps[index + 1]
      const nextId = next?.evidence_images?.[0]?.image_id
      if (ids[0] && nextId) relations.push({ id: `${flow.id}-${index}-next`, source: ids[0], type: "下一步骤", target: nextId })
    })
  })
  return relations
})
const overview = computed(() => ({
  chunkCount: chunks.value.length,
  contentCount: chunks.value.filter((item) => !["image", "image_group"].includes(item.chunkType)).length,
  imageCount: images.value.length,
  flowCount: flows.value.length,
  entityCount: Number(graph.value?.stats?.nodeCount || graph.value?.nodes?.length || 0),
  relationCount: Number(graph.value?.stats?.relationCount || graph.value?.edges?.length || 0),
  sectionCount: sections.value.length,
  knowledgeUnitCount: knowledgeUnits.value.length,
  anchorCount: anchors.value.length
}))
const availableTabs = computed(() => [
  { key: "content", label: "内容解析", icon: "file-text", count: overview.value.knowledgeUnitCount || overview.value.contentCount },
  ...(overview.value.imageCount || overview.value.flowCount ? [{ key: "multimodal", label: "多模态", icon: "picture", count: overview.value.imageCount }] : []),
  ...(overview.value.entityCount ? [{ key: "graph", label: "知识图谱", icon: "share-alt", count: overview.value.entityCount }] : [])
])

function openImage(image: any) { selectedEvidence.value = image }
function confidenceLabel(value: string) { return { high: "高置信", medium: "中置信", low: "低置信" }[value] || value }
function anchorTypeLabel(value: string) { return { rule_document: "规则文档", subject: "业务对象", organization: "组织", product: "产品" }[value] || value || "实体" }
function sectionTypeLabel(value: string) { return { procedure_clause: "流程章节", policy_clause: "制度条款", form: "表单", table: "表格" }[value] || value || "内容章节" }
function unitTypeLabel(value: string) { return { process_step: "流程", rule: "规则", condition: "条件", responsibility: "职责", scope: "范围", field: "字段" }[value] || value || "知识" }

function locateSection(section: any) {
  const chunkIds = parseJson(section.coveredChunkIdsJson)
  emit("locate", { id: Array.isArray(chunkIds) ? chunkIds[0] : null, chunkId: Array.isArray(chunkIds) ? chunkIds[0] : null, pageStart: section.pageStart, blockIds: section.blockIds })
}
function locateKnowledgeUnit(unit: any) {
  if (!unit?.primaryChunkId && !unit?.pageStart) return
  emit("locate", { id: unit.primaryChunkId, chunkId: unit.primaryChunkId, pageStart: unit.pageStart, blockIds: parseJson(unit.metadataJson)?.block_ids })
}
function locateAnchor(anchor: any) {
  if (!anchor?.sourceChunkId) return
  emit("locate", { id: anchor.sourceChunkId, chunkId: anchor.sourceChunkId, pageStart: parseJson(anchor.metadataJson)?.page_start })
}
function openEvidence(evidence: any) {
  const image = imageMap.value[String(evidence.image_id)] || {}
  selectedEvidence.value = {
    ...image,
    fileId: evidence.image_file_id || image.fileId,
    title: image.title || evidence.image_id || "流程证据",
    keyFacts: image.keyFacts || [],
    entities: image.entities || [],
    raw: image.raw || { pageStart: image.pageStart }
  }
}

async function loadGraph(value = false) {
  includeChunks.value = Boolean(value)
  try {
    const res = await getFileKnowledgeGraph(props.kbId, props.fileId, { includeChunks: includeChunks.value })
    graph.value = resultData(res)
  } catch (e) {
    console.error(e)
    graph.value = { nodes: [], edges: [], stats: {} }
  }
  emit("overview", overview.value)
}

async function loadAll() {
  loading.value = true
  try {
    const [chunkRes, analysisRes] = await Promise.all([
      getChunkList(props.kbId, props.fileId, { pageNo: 1, pageSize: 500 }),
      getFileAnalysis(props.kbId, props.fileId).catch((e: any) => {
        console.error(e)
        return null
      }),
      loadGraph(false)
    ])
    chunks.value = responseData(chunkRes)
    analysis.value = analysisRes ? resultData(analysisRes) : { sections: [], summaries: [], knowledgeUnits: [], anchors: [], relations: [], chunkTypeStats: [] }
    selectedFlowIndex.value = 0
    summaryExpanded.value = false
    showAllUnits.value = false
    showRawChunks.value = false
    if (!availableTabs.value.some((tab) => tab.key === activeTab.value)) activeTab.value = "content"
  } finally {
    loading.value = false
    emit("overview", overview.value)
  }
}

function openTab(tab: string) {
  if (availableTabs.value.some((item) => item.key === tab)) activeTab.value = tab
}
defineExpose({ openTab, refresh: loadAll })
watch(() => props.fileId, loadAll, { immediate: true })
watch(overview, (value) => emit("overview", value), { deep: true, immediate: true })
</script>

<style scoped lang="less">
.knowledge-panel { position: relative; display: flex; overflow: hidden; height: 100%; min-width: 0; color: #1e293b; background: #fff; flex-direction: column; }
.panel-head { display: flex; justify-content: space-between; align-items: center; padding: 13px 16px 10px; border-bottom: 1px solid #edf1f6; }
.panel-head > div { display: grid; min-width: 0; gap: 2px; }
.panel-head strong { overflow: hidden; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.eyebrow { font-size: 10px; font-weight: 700; letter-spacing: .08em; color: #2563eb; text-transform: uppercase; }
.icon-button, .evidence-head button { display: inline-flex; justify-content: center; align-items: center; width: 28px; height: 28px; color: #64748b; background: #fff; border: 1px solid #e2e8f0; border-radius: 7px; cursor: pointer; }
.primary-tabs { display: grid; padding: 0 12px; min-height: 46px; border-bottom: 1px solid #dbe4f0; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.primary-tabs button { position: relative; display: inline-flex; justify-content: center; align-items: center; gap: 5px; font-size: 12px; white-space: nowrap; color: #64748b; background: transparent; border: 0; cursor: pointer; }
.primary-tabs button::after { position: absolute; right: 20%; bottom: 0; left: 20%; height: 2px; background: transparent; content: ""; }
.primary-tabs button.active { font-weight: 700; color: #1d4ed8; }
.primary-tabs button.active::after { background: #2563eb; }
.primary-tabs button span { padding: 1px 6px; font-size: 10px; background: #eff6ff; border-radius: 99px; }
.panel-body-spin { overflow: hidden; min-height: 0; flex: 1; }
.panel-body-spin::v-deep .ant-spin-container { height: 100%; }
.panel-scroll { overflow: auto; height: 100%; }
.content-view { padding: 14px 16px 24px; background: #fafbfc; }
.insight-card { padding: 13px; margin-bottom: 10px; background: #fff; border: 1px solid #e5eaf2; border-radius: 10px; }
.insight-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 10px; font-size: 11px; color: #94a3b8; }
.insight-head > div { display: flex; align-items: center; gap: 7px; min-width: 0; }
.insight-head strong { font-size: 12px; color: #1e293b; }
.insight-head em { padding: 1px 5px; font-size: 9px; font-style: normal; font-weight: 700; color: #2563eb; background: #eff6ff; border-radius: 4px; }
.section-icon { display: inline-flex; justify-content: center; align-items: center; width: 24px; height: 24px; color: #2563eb; background: #eff6ff; border-radius: 6px; flex: none; }
.confidence-tag { padding: 2px 7px; color: #059669; background: #ecfdf5; border-radius: 99px; }
.summary-card p { display: -webkit-box; overflow: hidden; margin: 0; font-size: 12px; line-height: 1.75; color: #475569; -webkit-box-orient: vertical; -webkit-line-clamp: 4; }
.summary-card p.expanded { display: block; overflow: visible; }
.text-action { padding: 0; margin-top: 8px; font-size: 11px; color: #2563eb; background: none; border: 0; cursor: pointer; }
.insight-head > .text-action { margin-top: 0; }
.process-track { display: grid; }
.process-track button { position: relative; display: grid; align-items: start; gap: 9px; padding: 5px 0 11px; text-align: left; background: none; border: 0; cursor: pointer; grid-template-columns: 24px minmax(0, 1fr); }
.process-track button:not(:last-child)::after { position: absolute; top: 27px; bottom: 0; left: 11px; width: 1px; background: #bfdbfe; content: ""; }
.process-track button > i { z-index: 1; display: inline-flex; justify-content: center; align-items: center; width: 24px; height: 24px; font-size: 10px; font-style: normal; font-weight: 800; color: #fff; background: #2563eb; border-radius: 50%; }
.process-track button > span { display: grid; gap: 3px; padding-top: 2px; min-width: 0; }
.process-track strong { font-size: 11px; color: #1e293b; }
.process-track small { display: -webkit-box; overflow: hidden; font-size: 10px; line-height: 1.55; color: #64748b; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.field-grid { display: grid; overflow: hidden; margin-bottom: 9px; border: 1px solid #edf1f6; border-radius: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.field-grid > div { display: grid; gap: 3px; padding: 8px 9px; min-width: 0; border-bottom: 1px solid #edf1f6; }
.field-grid > div:nth-child(odd) { border-right: 1px solid #edf1f6; }
.field-grid > div:nth-last-child(-n+2) { border-bottom: 0; }
.field-grid span { font-size: 9px; color: #94a3b8; }
.field-grid strong { overflow: hidden; font-size: 10px; line-height: 1.45; color: #334155; text-overflow: ellipsis; white-space: nowrap; }
.entity-cloud { display: flex; flex-wrap: wrap; gap: 6px; }
.entity-cloud button { display: inline-flex; align-items: center; gap: 4px; padding: 4px 7px; font-size: 10px; color: #334155; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; cursor: pointer; }
.entity-cloud button:hover { color: #1d4ed8; border-color: #93c5fd; }
.entity-cloud small { padding-left: 4px; color: #94a3b8; border-left: 1px solid #cbd5e1; }
.outline-list { overflow: hidden; border: 1px solid #edf1f6; border-radius: 8px; }
.outline-list button { display: grid; align-items: center; gap: 8px; padding: 9px 10px; width: 100%; text-align: left; background: #fff; border: 0; border-bottom: 1px solid #edf1f6; cursor: pointer; grid-template-columns: 20px minmax(0, 1fr) auto 12px; }
.outline-list button:last-child { border-bottom: 0; }
.outline-list button:hover { background: #f8fbff; }
.outline-list button > i { display: inline-flex; justify-content: center; align-items: center; width: 18px; height: 18px; font-size: 9px; font-style: normal; color: #2563eb; background: #eff6ff; border-radius: 5px; }
.outline-list button > span { display: grid; min-width: 0; }
.outline-list strong { overflow: hidden; font-size: 11px; color: #334155; text-overflow: ellipsis; white-space: nowrap; }
.outline-list small { margin-top: 2px; font-size: 9px; color: #94a3b8; }
.outline-list em { font-size: 9px; font-style: normal; white-space: nowrap; color: #94a3b8; }
.knowledge-card { padding-bottom: 6px; }
.knowledge-row { display: grid; align-items: start; gap: 8px; padding: 9px 0; width: 100%; text-align: left; background: none; border: 0; border-top: 1px solid #edf1f6; cursor: pointer; grid-template-columns: 36px minmax(0, 1fr) 14px; }
.knowledge-row > span:nth-child(2) { display: grid; gap: 3px; min-width: 0; }
.knowledge-row strong { overflow: hidden; font-size: 10px; color: #334155; text-overflow: ellipsis; white-space: nowrap; }
.knowledge-row small { display: -webkit-box; overflow: hidden; font-size: 10px; line-height: 1.5; color: #64748b; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.knowledge-row > i { margin-top: 3px; color: #94a3b8; }
.unit-type { padding: 2px 5px; text-align: center; font-size: 9px; color: #1d4ed8; background: #eff6ff; border-radius: 4px; }
.raw-chunk-card { padding: 0; overflow: hidden; }
.raw-chunk-trigger { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 13px; width: 100%; text-align: left; background: #fff; border: 0; cursor: pointer; }
.raw-chunk-trigger > span { display: grid; gap: 2px; padding-left: 27px; position: relative; }
.raw-chunk-trigger > span > i { position: absolute; top: 2px; left: 0; color: #2563eb; }
.raw-chunk-trigger strong { font-size: 11px; color: #334155; }
.raw-chunk-trigger small { font-size: 9px; color: #94a3b8; }
.raw-chunk-card::v-deep .chunk-list { border-top: 1px solid #edf1f6; }
.capability-summary { display: grid; gap: 8px; margin-bottom: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.capability-summary article { display: flex; align-items: center; gap: 9px; padding: 10px; background: #fff; border: 1px solid #e5eaf2; border-radius: 9px; }
.capability-summary article > i { font-size: 18px; color: #2563eb; }
.capability-summary span { display: grid; }
.capability-summary strong { font-size: 16px; line-height: 1.1; }
.capability-summary small { margin-top: 3px; color: #94a3b8; }
.multimodal-view { display: flex; overflow: hidden; height: 100%; flex-direction: column; }
.secondary-tabs { display: flex; gap: 4px; padding: 10px 14px; background: #fafbfc; border-bottom: 1px solid #edf1f6; }
.secondary-tabs button { padding: 5px 11px; font-size: 12px; color: #64748b; background: transparent; border: 1px solid transparent; border-radius: 7px; cursor: pointer; }
.secondary-tabs button.active { font-weight: 700; color: #1d4ed8; background: #fff; border-color: #bfdbfe; }
.flow-layout { display: grid; overflow: hidden; min-height: 0; flex: 1; grid-template-columns: 150px minmax(0, 1fr); }
.flow-list { overflow: auto; padding: 10px 8px; background: #f8fafc; border-right: 1px solid #e5eaf2; }
.flow-list button { display: grid; gap: 4px; padding: 10px; margin-bottom: 7px; width: 100%; text-align: left; background: #fff; border: 1px solid #e5eaf2; border-radius: 8px; cursor: pointer; }
.flow-list button.active { border-color: #60a5fa; box-shadow: 0 0 0 2px rgba(37,99,235,.08); }
.flow-list span, .flow-list small { font-size: 10px; color: #94a3b8; }
.flow-list strong { overflow: hidden; font-size: 11px; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.step-timeline { overflow: auto; padding: 16px; background: #fff; }
.flow-heading h3 { margin: 4px 0 14px; font-size: 15px; }
.step-card { position: relative; display: grid; gap: 10px; padding-bottom: 16px; grid-template-columns: 28px minmax(0, 1fr); }
.step-card:not(:last-child)::before { position: absolute; top: 28px; bottom: 0; left: 13px; width: 1px; background: #bfdbfe; content: ""; }
.step-index { z-index: 1; display: flex; justify-content: center; align-items: center; width: 28px; height: 28px; font-size: 11px; font-weight: 800; color: #fff; background: #2563eb; border-radius: 50%; }
.step-main { padding: 10px 12px; background: #f8fafc; border: 1px solid #e5eaf2; border-radius: 9px; }
.step-main strong { font-size: 12px; }
.step-main p { margin: 5px 0 8px; font-size: 11px; line-height: 1.65; color: #64748b; }
.evidence-row { display: flex; flex-wrap: wrap; gap: 7px; }
.evidence-row button { position: relative; overflow: hidden; padding: 0; width: 82px; height: 58px; background: #fff; border: 1px solid #dbe4f0; border-radius: 7px; cursor: pointer; }
.evidence-row button span { position: absolute; right: 3px; bottom: 3px; padding: 1px 4px; font-size: 9px; color: #fff; background: rgba(15,23,42,.72); border-radius: 3px; }
.image-grid { display: grid; align-content: start; gap: 12px; padding: 14px; background: #fafbfc; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
.image-grid > button { display: grid; overflow: hidden; padding: 0; min-height: 154px; text-align: left; background: #fff; border: 1px solid #e5eaf2; border-radius: 9px; cursor: pointer; grid-template-rows: 104px auto; }
.image-grid > button:hover { border-color: #60a5fa; box-shadow: 0 6px 18px rgba(37,99,235,.1); }
.image-grid .knowledge-image-thumb { height: 104px; }
.image-grid > button > span { display: grid; gap: 3px; padding: 8px 9px; }
.image-grid strong { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.image-grid small { font-size: 10px; color: #94a3b8; }
.image-relations { padding: 14px; background: #fafbfc; }
.relation-note { padding: 9px 10px; margin-bottom: 10px; font-size: 11px; color: #475569; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; }
.relation-note i { margin-right: 6px; color: #2563eb; }
.image-relations article { display: grid; align-items: center; gap: 8px; padding: 10px; margin-bottom: 7px; font-size: 11px; background: #fff; border: 1px solid #e5eaf2; border-radius: 8px; grid-template-columns: minmax(0,1fr) auto minmax(0,1fr); }
.image-relations article i { padding: 2px 6px; font-style: normal; color: #1d4ed8; background: #eff6ff; border-radius: 99px; }
.evidence-drawer { position: absolute; z-index: 5; top: 0; right: 0; bottom: 0; overflow: auto; padding: 16px; width: ~"min(330px, 82%)"; background: #fff; border-left: 1px solid #dbe4f0; box-shadow: -18px 0 38px rgba(15,23,42,.14); }
.evidence-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.evidence-head > div { display: grid; gap: 4px; }
.evidence-preview { overflow: hidden; margin: 14px 0; background: #f8fafc; border: 1px solid #e5eaf2; border-radius: 10px; }
.evidence-drawer dl { font-size: 12px; }
.evidence-drawer dt { margin-top: 12px; font-weight: 700; color: #334155; }
.evidence-drawer dd { margin: 5px 0 0; line-height: 1.7; color: #64748b; }
.evidence-drawer ul { padding-left: 18px; margin: 0; }
.tag-list { display: flex; flex-wrap: wrap; gap: 5px; }
.tag-list span { padding: 2px 7px; color: #475569; background: #f1f5f9; border-radius: 99px; }
</style>
