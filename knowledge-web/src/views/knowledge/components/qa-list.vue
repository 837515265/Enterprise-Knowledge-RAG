<template>
  <div class="qa-wrap">
    <!-- 工具栏 -->
    <div class="qa-toolbar">
      <div class="qa-toolbar-left">
        <div class="qa-search">
          <a-icon type="search" />
          <input v-model="keyword" placeholder="搜索问答对…" @keydown.enter="reset" />
        </div>
        <div class="qa-status-filter">
          <button
            v-for="item in auditFilterOptions"
            :key="item.value"
            type="button"
            :class="{ 'is-active': auditFilter === item.value }"
            @click="setAuditFilter(item.value)"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <div class="qa-toolbar-right">
        <button type="button" class="qa-action-btn" :disabled="templateLoading" @click="onDownloadTemplate">
          <a-icon :type="templateLoading ? 'loading' : 'download'" /> 模板
        </button>
        <button type="button" class="qa-action-btn" @click="onImport"><a-icon type="upload" /> 导入</button>
        <button type="button" class="qa-action-btn is-primary" @click="onAdd"><a-icon type="plus" /> 新建</button>
        <button v-if="canManage" type="button" class="qa-action-btn" @click="onReindexAllQas" :disabled="reindexing">
          <a-icon :type="reindexing ? 'loading' : 'database'" /> 全部索引
        </button>
      </div>
    </div>

    <!-- 列表 -->
    <div class="qa-body">
      <div v-if="loading" class="qa-loading"><a-icon type="loading" /> 加载中…</div>

      <div v-else-if="!list || list.length === 0" class="qa-empty">
        <a-icon type="inbox" style="font-size: 36px; color: #d1d5db" />
        <p>暂无问答对</p>
        <button type="button" class="qa-action-btn is-primary" @click="onAdd"><a-icon type="plus" /> 新建问答对</button>
      </div>

      <div v-else class="qa-items">
        <div v-for="item in list" :key="item.id" class="qa-card">
          <div class="qa-card-q">
            <span class="qa-label">Q</span>
            <span class="qa-text">{{ item.question }}</span>
          </div>
          <div class="qa-card-a">
            <span class="qa-label qa-label--a">A</span>
            <span class="qa-text">{{ item.answer }}</span>
          </div>
          <div class="qa-card-footer">
            <span class="qa-status" :class="'qa-status--' + (item.auditStatus || 'pending')">
              {{ statusLabel(item.auditStatus) }}
            </span>
            <span v-if="item.updateTime" class="qa-time">{{ item.updateTime }}</span>
            <div class="qa-card-actions">
              <a @click="onEdit(item)"><a-icon type="edit" /> 编辑</a>
              <template v-if="canAudit && item.auditStatus === 'pending'">
                <a @click="openAudit(item, 'approved')"><a-icon type="check" /> 通过</a>
                <a class="qa-del" @click="openAudit(item, 'rejected')"><a-icon type="close" /> 驳回</a>
              </template>
              <a-popconfirm title="确定删除该问答对？" @confirm="onDelete(item)">
                <a class="qa-del"><a-icon type="delete" /> 删除</a>
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div v-if="list && list.length > 0" class="qa-pagination">
        <a-pagination
          size="small"
          :current="pagination.current"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          show-size-changer
          show-quick-jumper
          @change="(page, size) => onPageInfoChange({ current: page, pageSize: size })"
          @showSizeChange="(_, size) => onPageInfoChange({ current: 1, pageSize: size })"
        />
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <a-modal
      v-model="editVisible"
      :title="editForm.id ? '编辑问答对' : '新建问答对'"
      :confirm-loading="editLoading"
      @ok="onEditSubmit"
    >
      <a-form :label-col="{ span: 4 }" :wrapper-col="{ span: 19 }">
        <a-form-item label="问题">
          <a-textarea v-model="editForm.question" :auto-size="{ minRows: 2, maxRows: 5 }" placeholder="请输入问题" />
        </a-form-item>
        <a-form-item label="答案">
          <a-textarea v-model="editForm.answer" :auto-size="{ minRows: 3, maxRows: 8 }" placeholder="请输入答案" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model="auditVisible"
      :title="auditForm.status === 'approved' ? '通过问答对审核' : '驳回问答对审核'"
      :confirm-loading="auditLoading"
      ok-text="提交"
      cancel-text="取消"
      @ok="submitAudit"
    >
      <a-form layout="vertical">
        <a-form-item label="审核意见">
          <a-textarea
            v-model="auditForm.reviewComment"
            :auto-size="{ minRows: 3, maxRows: 6 }"
            :placeholder="auditForm.status === 'approved' ? '可填写通过说明' : '请输入驳回原因'"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- CSV导入弹窗 -->
    <a-modal
      v-model="importVisible"
      title="CSV 批量导入"
      :confirm-loading="importLoading"
      ok-text="开始导入"
      cancel-text="取消"
      destroy-on-close
      @ok="submitImport"
      @cancel="resetImportModal"
    >
      <div class="qa-import-guide">
        <div>
          <div class="qa-import-guide__title">先下载模板，再按格式填写</div>
          <div class="qa-import-guide__desc">CSV 第一行为表头：question, answer；从第二行开始填写问题和答案。</div>
        </div>
        <a-button size="small" :loading="templateLoading" @click="onDownloadTemplate">
          <a-icon type="download" />下载模板
        </a-button>
      </div>
      <a-upload-dragger :before-upload="handleImportBefore" :show-upload-list="false" accept=".csv">
        <p class="ant-upload-drag-icon"><a-icon type="inbox" /></p>
        <p class="ant-upload-text">点击或拖拽 CSV 文件到此处</p>
        <p class="ant-upload-hint">选择文件后请点击「开始导入」确认提交，避免误操作。</p>
      </a-upload-dragger>
      <div v-if="importDraftFile" class="qa-import-selected">
        <div class="qa-import-selected__meta">
          <a-icon type="file" />
          <span class="qa-import-selected__name">{{ importDraftFile.name }}</span>
        </div>
        <a class="qa-import-selected__remove" @click="clearImportDraft">移除</a>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import {
  getQaPairList,
  createQaPair,
  updateQaPair,
  deleteQaPair,
  importQaPairs,
  downloadQaTemplate,
  submitQaAudit,
  reindexQas
} from "@/api/knowledge"
import { message } from "ant-design-vue"

const props = defineProps<{
  kbId: string | number
  compact?: boolean
  canAudit?: boolean
  canManage?: boolean
  initialAuditStatus?: string
}>()
const emit = defineEmits(["audited"])

const keyword = ref("")
const reindexing = ref(false)
const auditFilter = ref<string | undefined>(props.initialAuditStatus || undefined)
const canAudit = computed(() => Boolean(props.canAudit))
const auditFilterOptions = [
  { label: "全部", value: undefined },
  { label: "待审核", value: "pending" },
  { label: "已通过", value: "approved" },
  { label: "已驳回", value: "rejected" }
]

const { list, loading, pagination, queryList, reset, onPageInfoChange } = usePageList(
  (params: any) => getQaPairList(props.kbId, params),
  {
    extraParams: computed(() => ({
      keyword: keyword.value || undefined,
      auditStatus: auditFilter.value || undefined
    })),
    immediate: true
  }
)

function statusLabel(status: string) {
  const map: Record<string, string> = { approved: "已通过", pending: "待审核", rejected: "已驳回" }
  return map[status] || "待审核"
}

function setAuditFilter(value?: string) {
  auditFilter.value = value
  reset()
}

const editVisible = ref(false)
const editLoading = ref(false)
const editForm = reactive({ id: null as any, question: "", answer: "" })

function onAdd() {
  editForm.id = null
  editForm.question = ""
  editForm.answer = ""
  editVisible.value = true
}

function onEdit(record: any) {
  editForm.id = record.id
  editForm.question = record.question
  editForm.answer = record.answer
  editVisible.value = true
}

async function onEditSubmit() {
  editLoading.value = true
  try {
    if (editForm.id) {
      await updateQaPair(props.kbId, editForm.id, { question: editForm.question, answer: editForm.answer })
      message.success("更新成功")
    } else {
      await createQaPair(props.kbId, { question: editForm.question, answer: editForm.answer })
      message.success("创建成功")
    }
    editVisible.value = false
    queryList()
  } catch (e) {
    message.error("操作失败")
  } finally {
    editLoading.value = false
  }
}

async function onDelete(record: any) {
  try {
    await deleteQaPair(props.kbId, record.id)
    message.success("删除成功")
    queryList()
  } catch (e) {
    message.error("删除失败")
  }
}

async function onReindexAllQas() {
  reindexing.value = true
  try {
    await reindexQas(props.kbId)
    message.success("已提交全部重新索引任务")
    queryList()
  } catch (e) {
    message.error("重新索引失败")
  } finally {
    reindexing.value = false
  }
}

const auditVisible = ref(false)
const auditLoading = ref(false)
const auditForm = reactive({ qaId: null as any, status: "approved", reviewComment: "" })

function openAudit(record: any, status: string) {
  auditForm.qaId = record.id
  auditForm.status = status
  auditForm.reviewComment = ""
  auditVisible.value = true
}

async function submitAudit() {
  if (auditForm.status === "rejected" && !auditForm.reviewComment.trim()) {
    message.warning("请输入驳回原因")
    return
  }
  auditLoading.value = true
  try {
    await submitQaAudit(props.kbId, auditForm.qaId, {
      status: auditForm.status,
      reviewComment: auditForm.reviewComment
    })
    message.success("审核已提交")
    auditVisible.value = false
    emit("audited")
    queryList()
  } catch (e) {
    message.error("审核失败")
  } finally {
    auditLoading.value = false
  }
}

const importVisible = ref(false)
const importLoading = ref(false)
const importDraftFile = ref<File | null>(null)
const templateLoading = ref(false)

function onImport() {
  resetImportModal()
  importVisible.value = true
}

function handleImportBefore(file: File) {
  importDraftFile.value = file
  return false
}

function clearImportDraft() {
  importDraftFile.value = null
}

function resetImportModal() {
  importVisible.value = false
  importLoading.value = false
  importDraftFile.value = null
}

/**
 * 下载问答对导入模板，帮助用户按后端要求准备 CSV。
 */
async function onDownloadTemplate() {
  templateLoading.value = true
  try {
    const res = await downloadQaTemplate(props.kbId)
    downloadBlob(res, "问答对导入模板.csv")
  } catch (e) {
    message.error("模板下载失败")
  } finally {
    templateLoading.value = false
  }
}

async function submitImport() {
  if (!importDraftFile.value) {
    message.warning("请先选择 CSV 文件")
    return
  }
  importLoading.value = true
  try {
    const formData = new FormData()
    formData.append("file", importDraftFile.value)
    await importQaPairs(props.kbId, formData)
    message.success("导入成功")
    resetImportModal()
    queryList()
  } catch (e) {
    message.error("导入失败")
  } finally {
    importLoading.value = false
  }
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@border: #e5e7eb;

.qa-wrap {
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  height: 100%;
}

.qa-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid #f1f5f9;
}

.qa-toolbar-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.qa-status-filter {
  display: inline-flex;
  padding: 3px;
  background: #f8fafc;
  border: 1px solid @border;
  border-radius: 10px;
  gap: 2px;

  button {
    padding: 4px 10px;
    font-size: 12px;
    color: #64748b;
    background: transparent;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.16s;

    &.is-active {
      color: @primary;
      background: #fff;
      box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
    }
  }
}

.qa-toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.qa-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  min-width: 200px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 8px;
  transition: border-color 0.2s;

  &:focus-within {
    border-color: @primary;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08);
  }

  .anticon {
    font-size: 13px;
    color: #94a3b8;
  }

  input {
    flex: 1;
    font-size: 13px;
    background: transparent;
    border: none;
    outline: none;
  }
}

.qa-action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  background: #fff;
  border: 1px solid @border;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;

  &:disabled {
    color: #94a3b8;
    background: #f8fafc;
    cursor: not-allowed;
  }

  &:hover {
    color: @primary;
    border-color: #93c5fd;
  }

  &.is-primary {
    color: #fff;
    background: @primary;
    border-color: @primary;

    &:hover {
      background: #1d4ed8;
    }
  }
}

.qa-import-guide {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  margin-bottom: 14px;
  background: #f8fbff;
  border: 1px solid #dbeafe;
  border-radius: 12px;
}

.qa-import-guide__title {
  font-size: 14px;
  font-weight: 700;
  color: #1e3a8a;
}

.qa-import-guide__desc {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.qa-import-selected {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-top: 12px;
  background: #f8fafc;
  border: 1px solid @border;
  border-radius: 10px;
}

.qa-import-selected__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 13px;
  color: #334155;
}

.qa-import-selected__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qa-import-selected__remove {
  flex-shrink: 0;
  font-size: 12px;
  color: #dc2626;
  cursor: pointer;
}

.qa-body {
  flex: 1;
  overflow: auto;
  min-height: 0;
}

.qa-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  padding: 48px 16px;
  font-size: 14px;
  color: #94a3b8;
}

.qa-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 48px 16px;
  font-size: 14px;
  color: #94a3b8;

  p {
    margin: 0;
  }
}

.qa-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.qa-card {
  padding: 16px 20px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 12px;
  transition: all 0.2s;

  &:hover {
    border-color: #93c5fd;
    box-shadow: 0 2px 12px rgba(37, 99, 235, 0.06);
  }
}

.qa-card-q,
.qa-card-a {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.qa-card-q {
  margin-bottom: 8px;
}

.qa-label {
  display: flex;
  flex-shrink: 0;
  justify-content: center;
  align-items: center;
  margin-top: 1px;
  width: 22px;
  height: 22px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: @primary;
  border-radius: 6px;
}

.qa-label--a {
  background: #16a34a;
}

.qa-text {
  /* stylelint-disable-next-line value-no-vendor-prefix */
  display: -webkit-box;
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.55;
  color: #334155;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.qa-card-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px solid #f1f5f9;
}

.qa-status {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;

  &--approved {
    color: #16a34a;
    background: #dcfce7;
  }

  &--pending {
    color: #d97706;
    background: #fef3c7;
  }

  &--rejected {
    color: #dc2626;
    background: #fee2e2;
  }
}

.qa-time {
  font-size: 12px;
  color: #94a3b8;
}

.qa-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-left: auto;

  a {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 12px;
    color: @primary;
    cursor: pointer;
    transition: opacity 0.15s;

    &:hover {
      opacity: 0.8;
    }
  }

  .qa-del {
    color: #dc2626;
  }
}

.qa-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
