<template>
  <div class="graph-view">
    <div class="graph-toolbar">
      <div class="graph-mode-tabs">
        <button v-for="item in modes" :key="item.key" :class="{ active: mode === item.key }" @click="mode = item.key">
          {{ item.label }}
        </button>
      </div>
      <label class="chunk-switch">
        <a-switch size="small" :checked="includeChunks" @change="$emit('toggle-chunks', $event)" />
        <span>显示证据片段</span>
      </label>
    </div>

    <template v-if="mode === 'graph'">
      <div v-if="!graph.nodes.length" class="graph-empty"><a-empty :description="emptyDescription" /></div>
      <div v-else class="graph-canvas-wrap">
        <div ref="canvasRef" class="graph-canvas"></div>
        <div class="graph-legend">
          <span v-for="item in legend" :key="item.type"><i :style="{ background: item.color }"></i>{{ item.label }}</span>
        </div>
      </div>
    </template>

    <div v-else-if="mode === 'entities'" class="graph-list">
      <button v-for="node in graph.nodes" :key="node.id" :class="{ selected: selectedNode?.id === node.id }" @click="selectNode(node)">
        <span class="entity-dot" :style="{ background: typeColor(node.type) }"></span>
        <span class="list-main"><strong>{{ node.name }}</strong><small>{{ nodeTypeLabel(node.type) }}</small></span>
        <a-icon type="right" />
      </button>
    </div>

    <div v-else class="graph-list relation-list">
      <button v-for="edge in graph.edges" :key="edge.id" @click="selectNodeById(edge.source)">
        <span class="list-main"><strong>{{ nodeName(edge.source) }} → {{ nodeName(edge.target) }}</strong><small>{{ relationLabel(edge.type) }}</small></span>
        <a-icon type="right" />
      </button>
    </div>

    <aside v-if="selectedNode" class="node-detail-drawer">
      <div class="detail-head">
        <div><span class="node-type">{{ nodeTypeLabel(selectedNode.type) }}</span><strong>{{ selectedNode.name }}</strong></div>
        <button aria-label="关闭节点详情" @click="closeNodeDetail"><a-icon type="close" /></button>
      </div>

      <section v-if="selectedNode.description" class="detail-section node-description">
        <h4>节点说明</h4><p>{{ selectedNode.description }}</p>
      </section>

      <section v-if="selectedNodeProperties.length" class="detail-section">
        <h4>节点属性 <span>{{ selectedNodeProperties.length }}</span></h4>
        <dl class="property-list">
          <div v-for="item in selectedNodeProperties" :key="item.key" class="property-row">
            <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="detail-section relation-section">
        <h4>关联关系 <span>{{ relatedRelations.length }}</span></h4>
        <div v-if="relatedRelations.length" class="related-list">
          <button v-for="item in relatedRelations" :key="item.edge.id" @click="selectNode(item.node)">
            <i :style="{ background: typeColor(item.node.type) }"></i>
            <span><small>{{ item.direction }} · {{ relationLabel(item.edge.type) }}</small><strong>{{ item.node.name }}</strong></span>
            <a-icon type="right" />
          </button>
        </div>
        <a-empty v-else description="暂无关联关系" />
      </section>

      <div class="detail-actions">
        <span v-if="selectedNodePage">来源：第 {{ selectedNodePage }} 页</span><span v-else-if="selectedNodeChunkId">已关联原文证据</span><span v-else>当前节点无原文定位信息</span>
        <a-button :disabled="!canLocateSelectedNode" type="primary" @click="locateSelectedNode"><a-icon type="aim" />定位原文</a-button>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import G6 from "@antv/g6"

const props = withDefaults(defineProps<{ graph?: any; includeChunks?: boolean; emptyDescription?: string }>(), {
  graph: () => ({ nodes: [], edges: [], stats: {} }),
  includeChunks: false,
  emptyDescription: "暂无知识图谱"
})
const emit = defineEmits(["toggle-chunks", "locate"])
const canvasRef = ref<HTMLElement | null>(null)
const mode = ref("graph")
const selectedNode = ref<any>(null)
let graphInstance: any = null
const modes = [
  { key: "graph", label: "图谱" },
  { key: "entities", label: "实体列表" },
  { key: "relations", label: "关系列表" }
]
const palette: Record<string, string> = {
  File: "#2563eb",
  Document: "#0ea5e9",
  Requirement: "#6366f1",
  Concept: "#8b5cf6",
  Condition: "#10b981",
  Attribute: "#f59e0b",
  Metric: "#f97316",
  Entity: "#64748b",
  Assertion: "#e11d48",
  GraphCommunity: "#7c3aed",
  Chunk: "#94a3b8"
}
const labels: Record<string, string> = {
  File: "文件", Document: "文档", Requirement: "制度条款", Concept: "概念", Condition: "条件",
  Attribute: "属性", Metric: "指标", Entity: "实体", Assertion: "事实", GraphCommunity: "知识社区", Chunk: "证据片段"
}
const relationLabels: Record<string, string> = {
  EVIDENCED_BY: "证据来源", RELATED_TO: "关联", REQUIRES: "要求", APPROVES: "审批",
  HAS_ATTRIBUTE: "具有属性", CONSTRAINS: "约束", PARSED_AS: "解析为", ASSERTS: "声明事实",
  MEMBER_OF_COMMUNITY: "属于社区"
}

const legend = computed(() => {
  const types = Array.from(new Set((props.graph.nodes || []).map((node: any) => node.type))).slice(0, 6)
  return types.map((type: any) => ({ type, color: typeColor(type), label: nodeTypeLabel(type) }))
})

const propertyLabels: Record<string, string> = {
  pageStart: "起始页", page_start: "起始页", pageEnd: "结束页", page_end: "结束页",
  chunkId: "证据片段", chunk_id: "证据片段", sourceChunkId: "来源片段", fileNodeId: "文件节点",
  subjectText: "主体", predicateText: "关系/属性", objectText: "取值", confidence: "置信度",
  status: "状态", sourceSectionId: "来源章节", aliases: "别名", anchorType: "锚点类型",
  unitType: "知识类型", unitSubtype: "知识子类", evidenceQuote: "证据原文",
  domain_type: "业务类型", parse_generation: "解析代际", node_key: "节点标识", profile: "解析画像",
  index_generation: "索引代际", created_at: "创建时间", file_node_id: "文件节点", name_cn: "中文名称",
  value_text: "知识内容", kb_id: "知识库"
}
const hiddenPropertyKeys = new Set(["id", "name", "description", "type", "properties", "kbId", "kb_id", "labels"])
const selectedNodeProperties = computed(() => {
  if (!selectedNode.value) return []
  const rawProperties = parseProperties(selectedNode.value.properties)
  const merged = { ...rawProperties, ...selectedNode.value }
  return Object.entries(merged)
    .filter(([key, value]) => !hiddenPropertyKeys.has(key) && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({ key, label: propertyLabels[key] || humanizeKey(key), value: formatPropertyValue(value) }))
    .filter((item) => item.value)
    .slice(0, 20)
})
const relatedRelations = computed(() => {
  if (!selectedNode.value) return []
  const id = String(selectedNode.value.id)
  return (props.graph.edges || []).flatMap((edge: any) => {
    const source = String(edge.source)
    const target = String(edge.target)
    if (source !== id && target !== id) return []
    const relatedId = source === id ? target : source
    const node = (props.graph.nodes || []).find((item: any) => String(item.id) === relatedId)
    return node ? [{ edge, node, direction: source === id ? "指向" : "来源" }] : []
  }).slice(0, 30)
})
const selectedNodePage = computed(() => {
  const propsValue = parseProperties(selectedNode.value?.properties)
  return selectedNode.value?.pageStart || selectedNode.value?.page_start || propsValue.pageStart || propsValue.page_start || null
})
const selectedNodeChunkId = computed(() => {
  const propsValue = parseProperties(selectedNode.value?.properties)
  return selectedNode.value?.chunkId || selectedNode.value?.chunk_id || propsValue.chunkId || propsValue.chunk_id || propsValue.sourceChunkId || null
})
const canLocateSelectedNode = computed(() => Boolean(selectedNodePage.value || selectedNodeChunkId.value))

function typeColor(type: string) { return palette[type] || palette.Entity }
function nodeTypeLabel(type: string) { return labels[type] || type || "实体" }
function relationLabel(type: string) { return relationLabels[type] || type }
function nodeName(id: string) { return props.graph.nodes.find((node: any) => node.id === id)?.name || id }
function parseProperties(value: any) {
  if (!value) return {}
  if (typeof value === "object") return value
  try { return JSON.parse(value) } catch (e) { return {} }
}
function humanizeKey(key: string) {
  return key.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2")
}
function formatPropertyValue(value: any) {
  let text = ""
  if (Array.isArray(value)) text = value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join("、")
  else if (typeof value === "object") text = JSON.stringify(value)
  else if (typeof value === "number" && value > 0 && value < 1) text = `${Math.round(value * 100)}%`
  else text = String(value)
  return text.length > 280 ? `${text.slice(0, 280)}…` : text
}
function selectNode(node: any) {
  if (!node) return
  selectedNode.value = node
  nextTick(() => {
    const item = graphInstance?.findById?.(node.id)
    if (!item) return
    graphInstance.getNodes().forEach((graphNode: any) => graphInstance.clearItemStates(graphNode))
    graphInstance.setItemState(item, "selected", true)
    graphInstance.focusItem(item, true, { easing: "easeCubic", duration: 300 })
  })
}
function selectNodeById(id: string) {
  selectNode((props.graph.nodes || []).find((node: any) => String(node.id) === String(id)))
}
function closeNodeDetail() {
  selectedNode.value = null
  graphInstance?.getNodes?.().forEach((item: any) => graphInstance.clearItemStates(item))
}
function locateSelectedNode() {
  if (!canLocateSelectedNode.value) return
  const properties = parseProperties(selectedNode.value?.properties)
  emit("locate", {
    ...selectedNode.value,
    id: selectedNodeChunkId.value,
    chunkId: selectedNodeChunkId.value,
    pageStart: selectedNodePage.value,
    blockIds: selectedNode.value?.blockIds || properties.blockIds || properties.block_ids
  })
}

function renderGraph() {
  if (!canvasRef.value || mode.value !== "graph") return
  if (graphInstance) {
    graphInstance.destroy()
    graphInstance = null
  }
  const width = canvasRef.value.clientWidth || 520
  const height = canvasRef.value.clientHeight || 430
  graphInstance = new G6.Graph({
    container: canvasRef.value,
    width,
    height,
    fitView: true,
    fitViewPadding: 36,
    animate: true,
    modes: { default: ["drag-canvas", "zoom-canvas", "drag-node"] },
    layout: { type: "force", preventOverlap: true, linkDistance: 100, nodeStrength: -80 },
    defaultNode: { type: "circle", size: 42, style: { lineWidth: 2, stroke: "#fff", shadowColor: "rgba(15,23,42,.14)", shadowBlur: 10 } },
    defaultEdge: { style: { stroke: "#cbd5e1", lineWidth: 1.2, endArrow: { path: G6.Arrow.triangle(5, 7, 0), fill: "#cbd5e1" } } },
    nodeStateStyles: { selected: { lineWidth: 4, stroke: "#1d4ed8", shadowBlur: 16 } }
  })
  graphInstance.data({
    nodes: props.graph.nodes.map((node: any) => ({
      ...node,
      label: String(node.name || "").slice(0, 10),
      style: { fill: typeColor(node.type) },
      labelCfg: { position: "bottom", offset: 8, style: { fill: "#334155", fontSize: 11 } }
    })),
    edges: props.graph.edges.map((edge: any) => ({ ...edge }))
  })
  graphInstance.render()
  graphInstance.on("node:click", (event: any) => {
    const id = event.item?.getID()
    selectNode(props.graph.nodes.find((node: any) => node.id === id) || null)
  })
}

watch(() => props.graph, () => {
  if (selectedNode.value && !(props.graph.nodes || []).some((node: any) => node.id === selectedNode.value.id)) selectedNode.value = null
  nextTick(renderGraph)
})
watch(mode, () => nextTick(renderGraph))
onMounted(() => nextTick(renderGraph))
onBeforeUnmount(() => graphInstance?.destroy())
</script>

<style scoped lang="less">
.graph-view { position: relative; overflow: hidden; height: 100%; color: #1e293b; }
.graph-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid #e5eaf2; }
.graph-mode-tabs { display: inline-flex; padding: 3px; background: #f1f5f9; border-radius: 8px; }
.graph-mode-tabs button { padding: 5px 12px; font-size: 12px; color: #64748b; background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.graph-mode-tabs button.active { font-weight: 700; color: #1d4ed8; background: #fff; box-shadow: 0 1px 4px rgba(15, 23, 42, .08); }
.chunk-switch { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #64748b; }
.graph-canvas-wrap { position: relative; height: calc(100% - 52px); min-height: 360px; background: #f8fafc; }
.graph-canvas { width: 100%; height: 100%; }
.graph-legend { position: absolute; top: 12px; left: 12px; display: flex; flex-wrap: wrap; gap: 8px 12px; padding: 7px 10px; max-width: calc(100% - 24px); font-size: 11px; color: #64748b; background: rgba(255,255,255,.9); border: 1px solid #e5eaf2; border-radius: 8px; }
.graph-legend span { display: inline-flex; align-items: center; gap: 5px; }
.graph-legend i, .entity-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.node-inspector { padding: 14px 16px; background: #fff; border-top: 1px solid #dbe4f0; box-shadow: 0 -10px 24px rgba(15, 23, 42, .05); }
.inspector-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.inspector-head > div { display: grid; gap: 5px; }
.inspector-head button { color: #94a3b8; background: none; border: 0; cursor: pointer; }
.node-type { width: max-content; padding: 2px 7px; font-size: 11px; color: #1d4ed8; background: #eff6ff; border-radius: 99px; }
.node-inspector p { margin: 10px 0; font-size: 12px; line-height: 1.7; color: #64748b; }
.node-actions { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #94a3b8; }
.graph-list { overflow: auto; height: calc(100% - 55px); padding: 10px; }
.graph-list button { display: flex; align-items: center; gap: 10px; padding: 11px 12px; margin-bottom: 7px; width: 100%; text-align: left; background: #fff; border: 1px solid #e5eaf2; border-radius: 8px; cursor: pointer; }
.graph-list button:hover { border-color: #93c5fd; }
.graph-list button.selected { color: #1d4ed8; background: #f8fbff; border-color: #60a5fa; box-shadow: 0 0 0 2px rgba(37, 99, 235, .06); }
.list-main { display: grid; min-width: 0; flex: 1; }
.list-main strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.list-main small { margin-top: 3px; color: #94a3b8; }
.graph-empty { padding-top: 90px; }
.node-detail-drawer { position: absolute; z-index: 8; top: 53px; right: 0; bottom: 0; display: flex; overflow: hidden; width: ~"min(360px, 88%)"; background: #fff; border-left: 1px solid #dbe4f0; box-shadow: -14px 0 34px rgba(15, 23, 42, .13); flex-direction: column; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 16px; border-bottom: 1px solid #edf1f6; }
.detail-head > div { display: grid; gap: 6px; min-width: 0; }
.detail-head strong { overflow: hidden; font-size: 15px; line-height: 1.35; color: #0f172a; text-overflow: ellipsis; }
.detail-head > button { display: inline-flex; justify-content: center; align-items: center; width: 28px; height: 28px; color: #64748b; background: #fff; border: 1px solid #e2e8f0; border-radius: 7px; cursor: pointer; flex: none; }
.detail-section { overflow: auto; padding: 14px 16px 0; flex: none; }
.relation-section { min-height: 0; flex: 1; }
.detail-section h4 { display: flex; align-items: center; gap: 6px; margin: 0 0 9px; font-size: 11px; color: #334155; }
.detail-section h4 span { padding: 1px 5px; font-size: 9px; color: #2563eb; background: #eff6ff; border-radius: 99px; }
.node-description p { padding: 10px; margin: 0; font-size: 11px; line-height: 1.7; color: #475569; background: #f8fafc; border-radius: 8px; }
.property-list { overflow: hidden; margin: 0; border: 1px solid #edf1f6; border-radius: 8px; }
.property-row { display: grid; grid-template-columns: 86px minmax(0, 1fr); }
.property-list dt, .property-list dd { padding: 7px 8px; margin: 0; font-size: 10px; line-height: 1.5; border-bottom: 1px solid #edf1f6; }
.property-list dt { color: #64748b; background: #f8fafc; border-right: 1px solid #edf1f6; }
.property-list dd { overflow-wrap: anywhere; color: #334155; }
.property-row:last-child dt, .property-row:last-child dd { border-bottom: 0; }
.related-list { overflow: auto; padding-bottom: 8px; }
.related-list button { display: grid; align-items: center; gap: 8px; padding: 8px; margin-bottom: 6px; width: 100%; text-align: left; background: #fff; border: 1px solid #e5eaf2; border-radius: 8px; cursor: pointer; grid-template-columns: 8px minmax(0, 1fr) 12px; }
.related-list button:hover { border-color: #93c5fd; }
.related-list button > i { width: 8px; height: 8px; border-radius: 50%; }
.related-list button > span { display: grid; min-width: 0; }
.related-list small { font-size: 9px; color: #94a3b8; }
.related-list strong { overflow: hidden; margin-top: 2px; font-size: 10px; color: #334155; text-overflow: ellipsis; white-space: nowrap; }
.detail-actions { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 16px; font-size: 10px; color: #94a3b8; background: #fff; border-top: 1px solid #dbe4f0; }
</style>
