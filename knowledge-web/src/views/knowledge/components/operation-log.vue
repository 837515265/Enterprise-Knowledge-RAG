<template>
  <div class="operation-log">
    <div class="log-hero">
      <div>
        <div class="log-hero__eyebrow">Audit Trail</div>
        <div class="log-hero__title">操作日志</div>
        <div class="log-hero__desc">记录知识库配置、文件、问答、审核、成员等关键治理动作。</div>
      </div>
      <a-button :loading="loading" @click="onPageInfoChange({ current: 1, pageSize: pagination.pageSize })">
        <a-icon type="reload" />刷新
      </a-button>
    </div>

    <a-table
      class="log-table"
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="onPageInfoChange"
    >
      <template #action="text, record">
        <div class="log-action">
          <span class="log-action__icon" :class="`log-action__icon--${getActionMeta(text).tone}`">
            <a-icon :type="getActionMeta(text).icon" />
          </span>
          <div>
            <div class="log-action__label">{{ getActionMeta(text).label }}</div>
            <div class="log-action__code">{{ text }}</div>
          </div>
        </div>
      </template>
      <template #objectType="text">
        <a-tag :color="getObjectMeta(text).color">{{ getObjectMeta(text).label }}</a-tag>
      </template>
      <template #summary="text">
        <span class="log-summary">{{ text || "-" }}</span>
      </template>
      <template #createTime="text">
        <span class="log-time">{{ text || "-" }}</span>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { getOperationLogs } from "@/api/knowledge"

const props = defineProps<{
  kbId: string | number
}>()

const objectTypeMap: Record<string, string> = {
  kb: "知识库",
  file: "文件",
  chunk: "Chunk",
  qa: "问答对",
  member: "成员",
  tag: "标签"
}

const actionLabelMap: Record<string, string> = {
  "kb.create": "创建知识库",
  "kb.update": "更新知识库",
  "kb.delete": "删除知识库",
  "file.create": "新增文件/文件夹",
  "file.update": "更新文件",
  "file.delete": "删除文件",
  "file.audit": "文件审核",
  "chunk.update": "更新切片",
  "chunk.delete": "删除切片",
  "qa.create": "新增问答对",
  "qa.update": "更新问答对",
  "qa.delete": "删除问答对",
  "qa.audit": "问答审核",
  "member.create": "添加成员",
  "member.delete": "移除成员",
  "tag.create": "新增标签",
  "tag.delete": "删除标签"
}

const { list, loading, pagination, onPageInfoChange } = usePageList(
  (params: any) => getOperationLogs(props.kbId, params),
  { immediate: true }
)

const columns = [
  { title: "操作", dataIndex: "action", width: 160, scopedSlots: { customRender: "action" } },
  { title: "对象类型", dataIndex: "objectType", width: 100, scopedSlots: { customRender: "objectType" } },
  { title: "对象ID", dataIndex: "objectId", width: 140 },
  { title: "摘要", dataIndex: "summary", ellipsis: true, scopedSlots: { customRender: "summary" } },
  { title: "时间", dataIndex: "createTime", width: 170, scopedSlots: { customRender: "createTime" } }
]

function getObjectMeta(type: string) {
  const colorMap: Record<string, string> = {
    kb: "blue",
    file: "cyan",
    chunk: "purple",
    qa: "geekblue",
    member: "green",
    tag: "orange"
  }
  return {
    label: objectTypeMap[type] || type || "-",
    color: colorMap[type] || "default"
  }
}

function getActionMeta(action: string) {
  const verb = String(action || "")
    .split(".")
    .pop()
  const metaMap: Record<string, any> = {
    create: { icon: "plus", tone: "create" },
    update: { icon: "edit", tone: "update" },
    delete: { icon: "delete", tone: "delete" },
    audit: { icon: "audit", tone: "audit" }
  }
  const meta = metaMap[verb || ""] || { icon: "profile", tone: "default" }
  return {
    label: actionLabelMap[action] || action || "-",
    ...meta
  }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.operation-log {
  color: #17233d;
}

.log-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 20px 22px;
  margin-bottom: 16px;
  background: radial-gradient(circle at 10% 20%, rgba(24, 144, 255, 0.15), transparent 28%),
    linear-gradient(135deg, #f8fbff 0%, #eef7ff 100%);
  border: 1px solid rgba(24, 144, 255, 0.12);
  border-radius: 18px;
}

.log-hero__eyebrow {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #1677ff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.log-hero__title {
  font-size: 20px;
  font-weight: 800;
  color: #17233d;
}

.log-hero__desc {
  margin-top: 6px;
  color: #667085;
}

.log-table {
  padding: 8px;
  background: #fff;
  border: 1px solid #edf1f7;
  border-radius: 16px;
}

.log-action {
  display: flex;
  gap: 10px;
  align-items: center;
}

.log-action__icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
}

.log-action__icon--create {
  color: #16a34a;
  background: #ecfdf3;
}

.log-action__icon--update {
  color: #1677ff;
  background: #edf4ff;
}

.log-action__icon--delete {
  color: #ef4444;
  background: #fff1f2;
}

.log-action__icon--audit {
  color: #f59e0b;
  background: #fff7e6;
}

.log-action__icon--default {
  color: #64748b;
  background: #f1f5f9;
}

.log-action__label {
  font-weight: 700;
  color: #17233d;
}

.log-action__code {
  margin-top: 2px;
  font-size: 12px;
  color: #98a2b3;
}

.log-summary {
  color: #475569;
}

.log-time {
  color: #667085;
}
</style>
