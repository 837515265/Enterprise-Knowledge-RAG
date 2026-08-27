<template>
  <div class="chunk-list">
    <div class="chunk-list-head">
      <div>
        <div class="chunk-title">{{ fileName }} - 解析内容</div>
        <div class="chunk-metrics">
          <span>当前 {{ list.length }}</span>
          <span v-if="stats">总数 {{ stats.totalChunkCount }}</span>
          <span v-if="stats">有效 {{ stats.availableChunkCount }}</span>
        </div>
      </div>
      <div class="chunk-head-actions">
        <a-select v-model="auditFilter" size="small" class="chunk-status-select" @change="reset">
          <a-select-option value="">全部状态</a-select-option>
          <a-select-option value="pending">待审核</a-select-option>
          <a-select-option value="approved">已通过</a-select-option>
          <a-select-option value="rejected">已驳回</a-select-option>
        </a-select>
        <a-button v-if="!inline" size="small" @click="$emit('back')">
          <a-icon type="arrow-left" />返回
        </a-button>
      </div>
    </div>

    <div v-if="canAudit && pendingInList.length >= 2" class="chunk-batch-audit">
      <span>待审核 {{ pendingInList.length }} 条</span>
      <a-button size="small" @click="markAllPending('approved')">全部通过</a-button>
      <a-button size="small" @click="markAllPending('rejected')">全部驳回</a-button>
      <a-button type="primary" size="small" :disabled="!canSubmitBatch" :loading="batchSubmitLoading" @click="submitBatchAudit">
        提交审核
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <div class="chunk-blocks">
        <article
          v-for="item in list"
          :key="item.id"
          class="chunk-block"
          :class="[`is-${item.auditStatus || 'unknown'}`, { 'is-active': String(activeChunkId || '') === String(item.id) }]"
          @click="onSelectChunk(item)"
        >
          <div v-if="canEdit" class="chunk-tools">
            <button type="button" title="编辑" @click.stop="onEdit(item)">
              <a-icon type="edit" />
            </button>
            <a-checkbox
              class="chunk-enabled-check"
              :checked="item.enabled === 1"
              :title="item.enabled === 1 ? '禁用' : '启用'"
              @change="onToggleEnabled(item)"
              @click.native.stop
            />
            <a-popconfirm title="确定删除？" @confirm="onDelete(item)">
              <button type="button" title="删除" class="is-danger" @click.stop>
                <a-icon type="delete" />
              </button>
            </a-popconfirm>
          </div>

          <pre class="chunk-content">{{ item.content }}</pre>
          <div v-if="item.rejectReason" class="chunk-foot">
            <span class="is-reject">驳回原因：{{ item.rejectReason }}</span>
          </div>
          <footer v-if="canAudit && item.auditStatus === 'pending'" class="chunk-audit-foot" @click.stop>
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
              placeholder="驳回时请填写原因"
              @change="setReason(item.id, $event.target.value)"
            />
            <a-button
              type="primary"
              size="small"
              :loading="singleSubmitId === item.id"
              :disabled="!getDraft(item.id).status"
              @click="submitSingleAudit(item)"
            >
              提交本条审核
            </a-button>
          </footer>
        </article>

        <a-empty v-if="!loading && !list.length" description="暂无解析内容" />
      </div>
    </a-spin>

    <div v-if="pagination.total > pagination.pageSize" class="chunk-pager">
      <a-pagination
        size="small"
        :current="pagination.current"
        :page-size="pagination.pageSize"
        :total="pagination.total"
        @change="onPagerChange"
      />
    </div>

    <a-modal v-model="editVisible" title="编辑Chunk" width="700px" @ok="onEditSubmit" :confirm-loading="editLoading">
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
import { getChunkList, getChunkStats, updateChunk, toggleChunkEnabled, deleteChunk, submitFileAudit } from "@/api/knowledge"
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
  inline?: boolean
  initialAuditStatus?: string
  canEdit?: boolean
  canAudit?: boolean
  activeChunkId?: string | number | null
  contentOnly?: boolean
}>()

const emit = defineEmits(["back", "select-chunk", "edited", "audited"])

const stats = ref<any>(null)
const auditFilter = ref(props.initialAuditStatus || "")
const canEdit = computed(() => Boolean(props.canEdit))
const canAudit = computed(() => Boolean(props.canAudit))
const draftMap = ref<Record<string, AuditDraft>>({})
const batchSubmitLoading = ref(false)
const singleSubmitId = ref<string | number | null>(null)

const { list, loading, pagination, queryList, reset, onPageInfoChange } = usePageList(
  (params: any) => getChunkList(props.kbId, props.fileId, params),
  {
    extraParams: computed(() => ({
      auditStatus: auditFilter.value || undefined,
      contentOnly: props.contentOnly ? "true" : undefined
    })),
    defaultPageSize: props.inline ? 500 : 10,
    immediate: true,
    onSuccess: () => syncDraftMap()
  }
)

const pendingInList = computed(() => list.value.filter((item: any) => item.auditStatus === "pending"))
const canSubmitBatch = computed(
  () => pendingInList.value.length > 0 && pendingInList.value.every((item: any) => Boolean(getDraft(item.id).status))
)

function syncDraftMap() {
  const next: Record<string, AuditDraft> = { ...draftMap.value }
  list.value.forEach((item: any) => {
    if (item.auditStatus !== "pending") {
      return
    }
    const key = String(item.id)
    if (!next[key]) {
      next[key] = { status: "", reason: "" }
    }
  })
  draftMap.value = next
}

function getDraft(id: string | number): AuditDraft {
  return draftMap.value[String(id)] || { status: "", reason: "" }
}

function setDecision(id: string | number, status: AuditStatus) {
  const key = String(id)
  draftMap.value = {
    ...draftMap.value,
    [key]: { ...getDraft(id), status }
  }
}

function setReason(id: string | number, reason: string) {
  const key = String(id)
  draftMap.value = {
    ...draftMap.value,
    [key]: { ...getDraft(id), reason }
  }
}

function markAllPending(status: AuditStatus) {
  const next = { ...draftMap.value }
  pendingInList.value.forEach((item: any) => {
    next[String(item.id)] = { ...getDraft(item.id), status }
  })
  draftMap.value = next
}

function buildAuditPayload(items: any[]) {
  const auditDetails = items.map((item: any) => ({
    chunkId: item.id,
    seqNo: item.seqNo,
    status: getDraft(item.id).status,
    reason: getDraft(item.id).reason.trim()
  }))
  const approvedIds = auditDetails.filter((item) => item.status === "approved").map((item) => item.chunkId)
  const rejectedIds = auditDetails.filter((item) => item.status === "rejected").map((item) => item.chunkId)
  const rejectedReasons = auditDetails
    .filter((item) => item.status === "rejected")
    .reduce((map: Record<string, string>, item) => {
      map[String(item.chunkId)] = item.reason
      return map
    }, {})
  const missingRejectReason = auditDetails.some((item) => item.status === "rejected" && !item.reason)
  return { auditDetails, approvedIds, rejectedIds, rejectedReasons, missingRejectReason }
}

async function submitSingleAudit(item: any) {
  const draft = getDraft(item.id)
  if (!draft.status) {
    message.warning("请选择通过或驳回")
    return
  }
  if (draft.status === "rejected" && !draft.reason.trim()) {
    message.warning("请输入驳回原因")
    return
  }

  singleSubmitId.value = item.id
  try {
    const { auditDetails, approvedIds, rejectedIds, rejectedReasons } = buildAuditPayload([item])
    await submitFileAudit(props.kbId, props.fileId, {
      status: draft.status,
      reviewComment: buildChunkAuditReviewSummary(auditDetails),
      approvedIds,
      rejectedIds,
      rejectedReasons,
      auditDetails
    })
    message.success("审核已提交")
    emit("audited")
    await queryList()
  } catch (e) {
    message.error("审核提交失败")
  } finally {
    singleSubmitId.value = null
  }
}

async function submitBatchAudit() {
  if (!canSubmitBatch.value) {
    message.warning("请先为所有待审核 Chunk 选择通过或驳回")
    return
  }
  const { auditDetails, approvedIds, rejectedIds, rejectedReasons, missingRejectReason } =
    buildAuditPayload(pendingInList.value)
  if (missingRejectReason) {
    message.warning("驳回项请填写原因")
    return
  }

  batchSubmitLoading.value = true
  try {
    await submitFileAudit(props.kbId, props.fileId, {
      status:
        rejectedIds.length && approvedIds.length
          ? "partially_approved"
          : rejectedIds.length
          ? "rejected"
          : "approved",
      reviewComment: buildChunkAuditReviewSummary(auditDetails),
      approvedIds,
      rejectedIds,
      rejectedReasons,
      auditDetails
    })
    message.success("审核已提交")
    emit("audited")
    draftMap.value = {}
    await queryList()
  } catch (e) {
    message.error("审核提交失败")
  } finally {
    batchSubmitLoading.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getChunkStats(props.kbId, props.fileId)
    stats.value = res?.datas && !Array.isArray(res.datas) ? res.datas : null
  } catch (e) {
    console.error(e)
  }
})

function onPagerChange(pageNo: number, pageSize: number) {
  onPageInfoChange({ current: pageNo, pageSize })
}

function onSelectChunk(record: any) {
  emit("select-chunk", record)
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
    if (canAudit.value && auditFilter.value && auditFilter.value !== "pending") {
      auditFilter.value = ""
    }
    await reset()
    emit("edited")
  } catch (e) {
    message.error("编辑失败")
  } finally {
    editLoading.value = false
  }
}

async function onToggleEnabled(record: any) {
  try {
    await toggleChunkEnabled(props.kbId, record.id, { enabled: record.enabled !== 1 })
    message.success("操作成功")
    queryList()
  } catch (e) {
    message.error("操作失败")
  }
}

async function onDelete(record: any) {
  try {
    await deleteChunk(props.kbId, record.id)
    message.success("删除成功")
    queryList()
  } catch (e) {
    message.error("删除失败")
  }
}
</script>

<style lang="less" scoped>
.chunk-list {
  color: #17233d;
}

.chunk-list-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.chunk-title {
  overflow: hidden;
  font-size: 15px;
  font-weight: 800;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chunk-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

.chunk-head-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.chunk-status-select {
  width: 118px;
}

.chunk-blocks {
  display: grid;
  gap: 12px;
}

.chunk-block {
  position: relative;
  overflow: hidden;
  background: #fff;
  border: 1px solid #e5eaf2;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.chunk-block:hover {
  border-color: #bfdbfe;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08);
}

.chunk-block.is-active {
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12);
}

.chunk-block.is-approved {
  border-left-color: #22c55e;
}

.chunk-block.is-pending {
  border-left-color: #f59e0b;
}

.chunk-block.is-rejected {
  border-left-color: #ef4444;
}

.chunk-tools {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  display: inline-flex;
  gap: 4px;
}

.chunk-tools button {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 28px;
  height: 28px;
  color: #475569;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  cursor: pointer;
}

.chunk-tools button:hover {
  color: #2563eb;
  background: #eff6ff;
  border-color: #bfdbfe;
}

.chunk-tools button.is-danger:hover {
  color: #dc2626;
  background: #fef2f2;
  border-color: #fecaca;
}

.chunk-enabled-check {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 28px;
  height: 28px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  cursor: pointer;
}

.chunk-enabled-check:hover {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.chunk-content {
  padding: 16px 112px 16px 16px;
  margin: 0;
  max-height: 340px;
  overflow: auto;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.75;
  color: #1f2937;
  white-space: pre-wrap;
}

.chunk-foot {
  padding: 10px 16px;
  font-size: 12px;
  color: #64748b;
  background: #fbfdff;
  border-top: 1px solid #eef2f7;
}

.chunk-foot .is-reject {
  color: #b91c1c;
}

.chunk-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.chunk-batch-audit {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  font-size: 12px;
  color: #64748b;
  background: #fff;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
}

.chunk-audit-foot {
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
</style>
