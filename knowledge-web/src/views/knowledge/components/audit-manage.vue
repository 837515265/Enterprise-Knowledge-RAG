<template>
  <div class="audit-manage">
    <div class="audit-hero">
      <div>
        <div class="audit-hero__eyebrow">Review History</div>
        <div class="audit-hero__title">审核管理</div>
        <div class="audit-hero__desc">集中查看文件切片与问答对的审核裁决、审核人和意见。</div>
      </div>
      <div class="audit-hero__metric">
        <strong>{{ pagination.total || 0 }}</strong>
        <span>条记录</span>
      </div>
    </div>

    <div class="audit-filter">
      <div class="audit-filter__item">
        <span>对象类型</span>
        <a-select v-model="bizTypeFilter" placeholder="全部类型" allow-clear @change="reset">
          <a-select-option value="chunk">Chunk</a-select-option>
          <a-select-option value="qa">问答对</a-select-option>
        </a-select>
      </div>
      <div class="audit-filter__item">
        <span>审核状态</span>
        <a-select v-model="statusFilter" placeholder="全部状态" allow-clear @change="reset">
          <a-select-option value="approved">已通过</a-select-option>
          <a-select-option value="rejected">已驳回</a-select-option>
          <a-select-option value="partially_approved">部分通过</a-select-option>
        </a-select>
      </div>
      <a-button type="primary" class="audit-filter__btn" @click="reset"> <a-icon type="search" />查询 </a-button>
    </div>

    <a-table
      class="audit-table"
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="onPageInfoChange"
    >
      <template #bizType="text">
        <a-tag v-if="text === 'chunk'" color="blue">Chunk</a-tag>
        <a-tag v-else color="purple">问答对</a-tag>
      </template>
      <template #status="text">
        <a-tag :color="getStatusMeta(text).color">{{ getStatusMeta(text).label }}</a-tag>
      </template>
      <template #reviewerName="text">
        <span class="audit-reviewer">{{ text || "系统" }}</span>
      </template>
      <template #reviewComment="text">
        <span class="audit-comment" :title="formatAuditReviewCommentDisplay(text)">
          {{ formatAuditReviewCommentDisplay(text) }}
        </span>
      </template>
      <template #reviewedAt="text">
        <span class="audit-time">{{ text || "-" }}</span>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { getAuditHistory } from "@/api/knowledge"
import { formatAuditReviewCommentDisplay } from "@/utils/logic/formatAuditReviewComment"

const props = defineProps<{
  kbId: string | number
}>()

const bizTypeFilter = ref(undefined)
const statusFilter = ref(undefined)

const { list, loading, pagination, reset, onPageInfoChange } = usePageList(
  (params: any) => getAuditHistory(props.kbId, params),
  {
    extraParams: computed(() => ({
      bizType: bizTypeFilter.value || undefined,
      status: statusFilter.value || undefined
    })),
    immediate: true
  }
)

const columns = [
  { title: "类型", dataIndex: "bizType", width: 80, scopedSlots: { customRender: "bizType" } },
  { title: "裁决", dataIndex: "status", width: 100, scopedSlots: { customRender: "status" } },
  { title: "审核人", dataIndex: "reviewerName", width: 120, scopedSlots: { customRender: "reviewerName" } },
  { title: "审核意见", dataIndex: "reviewComment", ellipsis: true, scopedSlots: { customRender: "reviewComment" } },
  { title: "审核时间", dataIndex: "reviewedAt", width: 170, scopedSlots: { customRender: "reviewedAt" } }
]

function getStatusMeta(status: string) {
  const map: Record<string, any> = {
    approved: { label: "已通过", color: "green" },
    rejected: { label: "已驳回", color: "red" },
    partially_approved: { label: "部分通过", color: "orange" }
  }
  return map[status] || { label: status || "-", color: "default" }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.audit-manage {
  color: #17233d;
}

.audit-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  margin-bottom: 16px;
  background: radial-gradient(circle at 10% 20%, rgba(245, 158, 11, 0.16), transparent 28%),
    linear-gradient(135deg, #fffdf8 0%, #fff7ed 100%);
  border: 1px solid rgba(245, 158, 11, 0.16);
  border-radius: 18px;
}

.audit-hero__eyebrow {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #d97706;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.audit-hero__title {
  font-size: 20px;
  font-weight: 800;
}

.audit-hero__desc {
  margin-top: 6px;
  color: #667085;
}

.audit-hero__metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 86px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #fed7aa;
  border-radius: 16px;
}

.audit-hero__metric strong {
  font-size: 24px;
  color: #d97706;
}

.audit-hero__metric span {
  font-size: 12px;
  color: #64748b;
}

.audit-filter {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 14px;
  margin-bottom: 16px;
  background: #fff;
  border: 1px solid #edf1f7;
  border-radius: 16px;
}

.audit-filter__item {
  display: flex;
  flex: 0 0 180px;
  flex-direction: column;
  gap: 6px;
}

.audit-filter__item span {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.audit-filter__btn {
  height: 32px;
}

.audit-table {
  padding: 8px;
  background: #fff;
  border: 1px solid #edf1f7;
  border-radius: 16px;
}

.audit-reviewer {
  font-weight: 600;
  color: #334155;
}

.audit-comment {
  color: #475569;
}

.audit-time {
  color: #667085;
}

@media (max-width: 900px) {
  .audit-filter {
    align-items: stretch;
    flex-direction: column;
  }

  .audit-filter__item {
    flex: 1;
  }
}
</style>
