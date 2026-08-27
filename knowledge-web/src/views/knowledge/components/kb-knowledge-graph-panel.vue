<template>
  <section class="kb-graph-panel">
    <div class="kb-graph-head">
      <div>
        <span class="kb-graph-eyebrow">Knowledge Graph</span>
        <h2>{{ kbName }} · 全局知识图谱</h2>
        <p>聚合知识库内所有已解析文件、业务实体及其跨文档关系。</p>
      </div>
      <div class="kb-graph-actions">
        <button type="button" class="kb-graph-refresh" :disabled="auditLoading" @click="loadAudit">
          <a-icon type="safety-certificate" /> 图谱体检
        </button>
        <button type="button" class="kb-graph-refresh" :disabled="communityLoading" @click="rebuildCommunities">
          <a-icon type="cluster" /> 重建社区
        </button>
        <button type="button" class="kb-graph-refresh" :disabled="loading" @click="loadGraph(includeChunks)">
          <a-icon type="reload" /> 刷新
        </button>
      </div>
    </div>

    <div class="kb-graph-metrics">
      <article><a-icon type="file-text" /><span><strong>{{ stats.fileCount || 0 }}</strong><small>关联文件</small></span></article>
      <article><a-icon type="cluster" /><span><strong>{{ stats.nodeCount || 0 }}</strong><small>知识实体</small></span></article>
      <article><a-icon type="share-alt" /><span><strong>{{ stats.relationCount || 0 }}</strong><small>实体关系</small></span></article>
      <article><a-icon type="appstore" /><span><strong>{{ nodeTypeCount }}</strong><small>实体类型</small></span></article>
    </div>

    <section v-if="showAudit" class="kb-graph-audit">
      <header>
        <div><strong>图谱质量体检</strong><span :class="audit.status === 'healthy' ? 'healthy' : 'attention'">{{ audit.status === "healthy" ? "健康" : "需关注" }}</span></div>
        <button type="button" @click="showAudit = false"><a-icon type="close" /></button>
      </header>
      <div class="audit-metrics">
        <span>异常事实 <strong>{{ auditStats.surpriseCount || 0 }}</strong></span>
        <span>孤儿事实 <strong>{{ auditStats.orphanAssertionCount || 0 }}</strong></span>
        <span>Hub 节点 <strong>{{ auditStats.hubCount || 0 }}</strong></span>
        <span>歧义关系 <strong>{{ auditStats.confidenceLabels?.AMBIGUOUS || 0 }}</strong></span>
      </div>
      <div v-if="audit.surprises?.length" class="audit-list">
        <article v-for="item in audit.surprises.slice(0, 5)" :key="item.assertionKey">
          <strong>{{ item.subject }} —{{ item.predicate }}→ {{ item.object }}</strong>
          <small>surprise {{ item.surpriseScore }} · {{ (item.reasons || []).join(" / ") }}</small>
        </article>
      </div>
    </section>

    <a-spin :spinning="loading" class="kb-graph-body">
      <KnowledgeGraphView
        :graph="graph"
        :include-chunks="includeChunks"
        empty-description="当前知识库暂无图谱数据"
        @toggle-chunks="loadGraph"
      />
    </a-spin>
  </section>
</template>

<script setup lang="ts">
import { getKnowledgeBaseGraph, getKnowledgeBaseGraphAudit, rebuildKnowledgeBaseGraphCommunities } from "@/api/knowledge"
import KnowledgeGraphView from "./knowledge-graph-view.vue"

const props = defineProps<{ kbId: string | number; kbName?: string }>()
const loading = ref(false)
const auditLoading = ref(false)
const communityLoading = ref(false)
const includeChunks = ref(false)
const graph = ref<any>({ nodes: [], edges: [], stats: {} })
const audit = ref<any>({ stats: {}, surprises: [] })
const showAudit = ref(false)
const stats = computed(() => graph.value?.stats || {})
const auditStats = computed(() => audit.value?.stats || {})
const nodeTypeCount = computed(() => Object.keys(stats.value.nodeTypes || {}).length)

function resultData(res: any) {
  return res?.datas || res?.data || res || {}
}

async function loadAudit() {
  auditLoading.value = true
  try {
    const res = await getKnowledgeBaseGraphAudit(props.kbId, { hubDegree: 20, limit: 100 })
    audit.value = resultData(res)
    showAudit.value = true
  } catch (e) {
    console.error(e)
    message.error("图谱体检失败")
  } finally {
    auditLoading.value = false
  }
}

async function rebuildCommunities() {
  communityLoading.value = true
  try {
    await rebuildKnowledgeBaseGraphCommunities(props.kbId, { minSize: 2 })
    message.success("知识社区及全局摘要已重建")
    await loadGraph(includeChunks.value)
    if (showAudit.value) await loadAudit()
  } catch (e) {
    console.error(e)
    message.error("知识社区重建失败")
  } finally {
    communityLoading.value = false
  }
}

async function loadGraph(value = false) {
  includeChunks.value = Boolean(value)
  loading.value = true
  try {
    const res = await getKnowledgeBaseGraph(props.kbId, { includeChunks: includeChunks.value })
    graph.value = resultData(res)
  } catch (e) {
    console.error(e)
    graph.value = { nodes: [], edges: [], stats: {} }
    message.error("知识库图谱加载失败")
  } finally {
    loading.value = false
  }
}

watch(() => props.kbId, () => loadGraph(false), { immediate: true })
defineExpose({ refresh: loadGraph })
</script>

<style scoped lang="less">
.kb-graph-panel { display: flex; overflow: hidden; height: 100%; min-height: 0; color: #1e293b; background: #fff; flex-direction: column; }
.kb-graph-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; padding: 22px 24px 18px; border-bottom: 1px solid #e5eaf2; }
.kb-graph-eyebrow { font-size: 10px; font-weight: 800; letter-spacing: .1em; color: #2563eb; text-transform: uppercase; }
.kb-graph-head h2 { margin: 5px 0 4px; font-size: 20px; color: #0f172a; }
.kb-graph-head p { margin: 0; font-size: 13px; color: #64748b; }
.kb-graph-refresh { display: inline-flex; align-items: center; gap: 7px; padding: 8px 13px; font-size: 13px; color: #334155; background: #fff; border: 1px solid #dbe3ee; border-radius: 8px; cursor: pointer; }
.kb-graph-refresh:hover { color: #1d4ed8; border-color: #93c5fd; }
.kb-graph-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.kb-graph-metrics { display: grid; gap: 10px; padding: 14px 24px; background: #f8fafc; border-bottom: 1px solid #e5eaf2; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.kb-graph-metrics article { display: flex; align-items: center; gap: 11px; padding: 12px 14px; background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; }
.kb-graph-metrics article > i { font-size: 20px; color: #2563eb; }
.kb-graph-metrics span { display: grid; }
.kb-graph-metrics strong { font-size: 18px; line-height: 1.15; color: #0f172a; }
.kb-graph-metrics small { margin-top: 3px; font-size: 11px; color: #94a3b8; }
.kb-graph-body { overflow: hidden; min-height: 0; flex: 1; }
.kb-graph-body::v-deep .ant-spin-container { height: 100%; }
.kb-graph-body::v-deep .graph-canvas-wrap { height: calc(100% - 50px); min-height: 420px; }
.kb-graph-audit { padding: 12px 24px; background: #fff; border-bottom: 1px solid #e5eaf2; }
.kb-graph-audit header { display: flex; justify-content: space-between; align-items: center; }
.kb-graph-audit header > div { display: flex; align-items: center; gap: 9px; }
.kb-graph-audit header span { padding: 2px 8px; font-size: 11px; border-radius: 99px; }
.kb-graph-audit header span.healthy { color: #047857; background: #d1fae5; }
.kb-graph-audit header span.attention { color: #b45309; background: #fef3c7; }
.kb-graph-audit header button { color: #94a3b8; background: none; border: 0; cursor: pointer; }
.audit-metrics { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 9px; font-size: 12px; color: #64748b; }
.audit-metrics strong { margin-left: 4px; color: #0f172a; }
.audit-list { display: grid; gap: 6px; margin-top: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.audit-list article { display: grid; gap: 3px; padding: 8px 10px; background: #fff7ed; border: 1px solid #fed7aa; border-radius: 8px; }
.audit-list strong { overflow: hidden; font-size: 12px; color: #9a3412; text-overflow: ellipsis; white-space: nowrap; }
.audit-list small { font-size: 10px; color: #c2410c; }
@media (max-width: 1100px) {
  .kb-graph-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
