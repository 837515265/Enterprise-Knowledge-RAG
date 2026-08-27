<template>
  <div class="chunk-audit-review">
    <div class="chunk-audit-head">
      <div class="chunk-audit-title">{{ fileName }} - Chunk审核</div>
    </div>

    <div class="audit-sticky-panel">
      <div class="audit-sticky-main">
        <div class="audit-sticky-info">
          <div class="chunk-audit-meta">
            <span>待处理 {{ pendingChunks.length }}</span>
            <span>未选择 {{ pendingCount }}</span>
            <span class="is-approved">已选通过 {{ approvedIds.length }}</span>
            <span class="is-rejected">已选驳回 {{ rejectedIds.length }}</span>
            <span v-if="totalCount > pendingChunks.length">加载 {{ pendingChunks.length }}/{{ totalCount }}</span>
          </div>
          <div v-if="pendingChunks.length" class="audit-progress">
            <div class="audit-progress-bar">
              <span class="is-approved" :style="{ width: `${approvedPercent}%` }"></span>
              <span class="is-rejected" :style="{ width: `${rejectedPercent}%` }"></span>
            </div>
            <div class="audit-progress-text">全部选择状态后可提交</div>
          </div>
        </div>
        <div class="chunk-audit-actions">
          <a-button size="small" :disabled="!pendingChunks.length" @click="markAll('approved')">全部通过</a-button>
          <a-button size="small" :disabled="!pendingChunks.length" @click="markAll('rejected')">全部驳回</a-button>
          <a-button type="primary" size="small" :disabled="!canSubmit" :loading="submitLoading" @click="submitAudit">
            提交审核
          </a-button>
        </div>
      </div>
    </div>

    <a-spin :spinning="loading">
      <div class="audit-blocks">
        <article
          v-for="item in pendingChunks"
          :key="item.id"
          class="audit-block"
          :class="`is-${getDraft(item.id).status || 'pending'}`"
        >
          <button type="button" class="audit-icon-btn" title="编辑" @click="onEdit(item)">
            <a-icon type="edit" />
          </button>
          <pre class="audit-content">{{ item.content }}</pre>

          <footer class="audit-block-foot">
            <div class="audit-decision">
              <button
                type="button"
                :class="{ 'is-active': getDraft(item.id).status === '' }"
                @click="setDecision(item.id, '')"
              >
                待审核
              </button>
              <button
                type="button"
                class="approve"
                :class="{ 'is-active': getDraft(item.id).status === 'approved' }"
                @click="setDecision(item.id, 'approved')"
              >
                通过
              </button>
              <button
                type="button"
                class="reject"
                :class="{ 'is-active': getDraft(item.id).status === 'rejected' }"
                @click="setDecision(item.id, 'rejected')"
              >
                驳回
              </button>
            </div>

            <a-textarea
              class="audit-reason"
              :value="getDraft(item.id).reason"
              :auto-size="{ minRows: 2, maxRows: 4 }"
              placeholder="备注，可选"
              @change="setReason(item.id, $event.target.value)"
            />
          </footer>
        </article>

        <a-empty v-if="!loading && !pendingChunks.length" description="当前文件没有待审核 Chunk" />
      </div>
    </a-spin>

    <a-modal v-model="editVisible" title="编辑Chunk" width="700px" :confirm-loading="editLoading" @ok="onEditSubmit">
      <a-form-item label="内容">
        <a-textarea v-model="editForm.content" :auto-size="{ minRows: 6, maxRows: 15 }" />
      </a-form-item>
      <a-form-item label="编辑原因">
        <a-input v-model="editForm.editReason" placeholder="请输入编辑原因" />
      </a-form-item>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { getChunkList, submitFileAudit, updateChunk } from "@/api/knowledge"
import { buildChunkAuditReviewSummary } from "@/utils/logic/formatAuditReviewComment"

type AuditStatus = "" | "approved" | "rejected"
type AuditDraft = {
  status: AuditStatus
  reason: string
}

const props = defineProps<{
  kbId: string | number
  fileId: string | number
  fileName: string
}>()

const emit = defineEmits(["audited", "edited"])

const loading = ref(false)
const submitLoading = ref(false)
const pendingChunks = ref<any[]>([])
const totalCount = ref(0)
const draftMap = ref<Record<string, AuditDraft>>({})

const approvedIds = computed(() =>
  pendingChunks.value.filter((item: any) => getDraft(item.id).status === "approved").map((item: any) => item.id)
)
const rejectedIds = computed(() =>
  pendingChunks.value.filter((item: any) => getDraft(item.id).status === "rejected").map((item: any) => item.id)
)
const pendingCount = computed(() => pendingChunks.value.filter((item: any) => !getDraft(item.id).status).length)
const canSubmit = computed(() => pendingChunks.value.length > 0 && pendingCount.value === 0)
const approvedPercent = computed(() => getPercent(approvedIds.value.length))
const rejectedPercent = computed(() => getPercent(rejectedIds.value.length))

onMounted(() => {
  loadPendingChunks()
})

async function loadPendingChunks() {
  loading.value = true
  try {
    const res = await getChunkList(props.kbId, props.fileId, { auditStatus: "pending", pageNo: 1, pageSize: 1000 })
    pendingChunks.value = Array.isArray(res?.data) ? res.data : []
    totalCount.value = Number(res?.count || pendingChunks.value.length)
    pendingChunks.value.forEach((item: any) => {
      const key = String(item.id)
      if (!draftMap.value[key]) {
        draftMap.value = {
          ...draftMap.value,
          [key]: { status: "", reason: "" }
        }
      }
    })
  } catch (e) {
    message.error("获取待审核 Chunk 失败")
  } finally {
    loading.value = false
  }
}

function getDraft(id: string | number): AuditDraft {
  const key = String(id)
  return draftMap.value[key] || { status: "", reason: "" }
}

function setDecision(id: string | number, status: AuditStatus) {
  const key = String(id)
  const current = getDraft(id)
  draftMap.value = {
    ...draftMap.value,
    [key]: { ...current, status }
  }
}

function setReason(id: string | number, reason: string) {
  const key = String(id)
  const current = getDraft(id)
  draftMap.value = {
    ...draftMap.value,
    [key]: { ...current, reason }
  }
}

function markAll(status: AuditStatus) {
  const next = { ...draftMap.value }
  pendingChunks.value.forEach((item: any) => {
    const key = String(item.id)
    next[key] = { ...getDraft(item.id), status }
  })
  draftMap.value = next
}

function getPercent(count: number) {
  if (!pendingChunks.value.length) return 0
  return Math.round((count / pendingChunks.value.length) * 100)
}

function resetDraftMap() {
  const next: Record<string, AuditDraft> = {}
  pendingChunks.value.forEach((item: any) => {
    next[String(item.id)] = { status: "", reason: "" }
  })
  draftMap.value = next
}

async function submitAudit() {
  if (!canSubmit.value) {
    message.warning("请先为所有待审核 Chunk 选择通过或驳回")
    return
  }

  const auditDetails = pendingChunks.value.map((item: any) => ({
    chunkId: item.id,
    seqNo: item.seqNo,
    status: getDraft(item.id).status,
    reason: getDraft(item.id).reason.trim()
  }))
  const rejectedReasons = auditDetails
    .filter((item) => item.status === "rejected")
    .reduce((map: Record<string, string>, item) => {
      map[String(item.chunkId)] = item.reason
      return map
    }, {})

  submitLoading.value = true
  try {
    await submitFileAudit(props.kbId, props.fileId, {
      status:
        rejectedIds.value.length && approvedIds.value.length
          ? "partially_approved"
          : rejectedIds.value.length
          ? "rejected"
          : "approved",
      reviewComment: buildChunkAuditReviewSummary(auditDetails),
      approvedIds: approvedIds.value,
      rejectedIds: rejectedIds.value,
      rejectedReasons,
      auditDetails
    })
    message.success("审核已提交")
    emit("audited")
    resetDraftMap()
    await loadPendingChunks()
  } catch (e) {
    message.error("审核提交失败")
    resetDraftMap()
    await loadPendingChunks()
    emit("audited")
  } finally {
    submitLoading.value = false
  }
}

const editVisible = ref(false)
const editLoading = ref(false)
const editForm = reactive({ chunkId: null as any, content: "", editReason: "" })

function onEdit(record: any) {
  editForm.chunkId = record.id
  editForm.content = record.content
  editForm.editReason = ""
  editVisible.value = true
}

async function onEditSubmit() {
  editLoading.value = true
  try {
    await updateChunk(props.kbId, editForm.chunkId, {
      content: editForm.content,
      editReason: editForm.editReason
    })
    message.success("编辑成功")
    editVisible.value = false
    await loadPendingChunks()
    emit("edited")
  } catch (e) {
    message.error("编辑失败")
  } finally {
    editLoading.value = false
  }
}
</script>

<style lang="less" scoped>
.chunk-audit-review {
  color: #17233d;
}

.chunk-audit-head {
  margin-bottom: 8px;
}

.chunk-audit-title {
  font-size: 15px;
  font-weight: 800;
  line-height: 1.4;
}

.audit-sticky-panel {
  position: sticky;
  top: -16px;
  z-index: 10;
  padding: 16px 20px 10px;
  margin: 0 -20px 12px;
  background: #fafbfc;
  border-bottom: 1px solid #eef2f7;
}

.audit-sticky-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}

.audit-sticky-info {
  display: grid;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.chunk-audit-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.chunk-audit-meta .is-approved {
  color: #15803d;
}

.chunk-audit-meta .is-rejected {
  color: #b91c1c;
}

.chunk-audit-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.audit-progress {
  display: grid;
  grid-template-columns: minmax(80px, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.audit-progress-bar {
  display: flex;
  overflow: hidden;
  height: 5px;
  background: #e5eaf2;
  border-radius: 999px;
}

.audit-progress-bar span {
  display: block;
  height: 100%;
}

.audit-progress-bar .is-approved {
  background: #22c55e;
}

.audit-progress-bar .is-rejected {
  background: #ef4444;
}

.audit-progress-text {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.audit-blocks {
  display: grid;
  gap: 12px;
}

.audit-block {
  position: relative;
  overflow: hidden;
  background: #fff;
  border: 1px solid #e5eaf2;
  border-left: 4px solid #f59e0b;
  border-radius: 8px;
}

.audit-block.is-approved {
  border-left-color: #22c55e;
}

.audit-block.is-rejected {
  border-left-color: #ef4444;
}

.audit-icon-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 28px;
  height: 28px;
  color: #475569;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  cursor: pointer;
}

.audit-icon-btn:hover {
  color: #2563eb;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.audit-content {
  padding: 16px 50px 14px 16px;
  margin: 0;
  max-height: 280px;
  overflow: auto;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.75;
  color: #1f2937;
  white-space: pre-wrap;
}

.audit-block-foot {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
  background: #fbfdff;
  border-top: 1px solid #eef2f7;
}

.audit-decision {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.audit-decision button {
  height: 34px;
  font-weight: 700;
  color: #475569;
  background: #fff;
  border: 1px solid #d9e2ef;
  border-radius: 7px;
  cursor: pointer;
}

.audit-decision button.is-active {
  color: #b45309;
  background: #fff7ed;
  border-color: #f59e0b;
  box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.12);
}

.audit-decision button.approve.is-active {
  color: #15803d;
  background: #f0fdf4;
  border-color: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.12);
}

.audit-decision button.reject.is-active {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #ef4444;
  box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.12);
}

.audit-reason {
  font-size: 13px;
}

@media (max-width: 760px) {
  .audit-sticky-main {
    align-items: stretch;
    flex-direction: column;
  }

  .chunk-audit-actions {
    justify-content: flex-start;
  }

  .audit-decision {
    grid-template-columns: 1fr;
  }
}
</style>
