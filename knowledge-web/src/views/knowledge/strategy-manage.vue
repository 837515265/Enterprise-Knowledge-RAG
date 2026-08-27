<template>
  <div class="strategy-page">
    <div class="strategy-head">
      <div>
        <h1 class="strategy-title">{{ pageMeta.title }}</h1>
        <p class="strategy-desc">{{ pageMeta.desc }}</p>
      </div>
      <a-button type="primary" @click="openCreate">
        <a-icon type="plus" />新增策略
      </a-button>
    </div>

    <div class="strategy-toolbar">
      <a-input-search
        v-model="keyword"
        class="strategy-search"
        placeholder="搜索名称、编码或备注"
        allow-clear
        @search="loadList"
      />
      <a-select v-model="statusFilter" class="strategy-filter" @change="loadList">
        <a-select-option value="">全部状态</a-select-option>
        <a-select-option value="active">启用</a-select-option>
        <a-select-option value="disabled">停用</a-select-option>
      </a-select>
      <a-button @click="loadList">
        <a-icon type="reload" />刷新
      </a-button>
    </div>

    <a-table
      row-key="id"
      :columns="columns"
      :data-source="filteredList"
      :loading="loading"
      :pagination="{ pageSize: 10, showTotal: (total) => `共${total}条` }"
      class="strategy-table"
    >
      <template #name="text, record">
        <div class="strategy-name-cell">
          <strong>{{ record.name }}</strong>
          <span>{{ record.code || "未设置编码" }}</span>
        </div>
      </template>

      <template #scopeType="text">
        <a-tag :color="text === 'template' ? 'blue' : 'purple'">{{ text === "template" ? "系统预设" : "知识库自定义" }}</a-tag>
      </template>

      <template #status="text">
        <a-badge :status="text === 'active' ? 'success' : 'default'" :text="text === 'active' ? '启用' : '停用'" />
      </template>

      <template #remark="text">
        <span class="strategy-remark">{{ text || "暂无备注" }}</span>
      </template>

      <template #action="text, record">
        <div class="strategy-actions">
          <a-button size="small" @click="openEdit(record)">编辑</a-button>
          <a-button size="small" @click="toggleStatus(record)">
            {{ record.status === "active" ? "停用" : "启用" }}
          </a-button>
          <a-popconfirm title="确定删除该策略？已被知识库引用时不建议删除。" @confirm="onDelete(record)">
            <a-button size="small" type="danger" ghost>删除</a-button>
          </a-popconfirm>
        </div>
      </template>
    </a-table>

    <a-drawer
      :title="editingId ? `编辑${pageMeta.shortTitle}` : `新增${pageMeta.shortTitle}`"
      :visible="drawerVisible"
      width="720"
      destroy-on-close
      @close="closeDrawer"
    >
      <a-form layout="vertical" class="strategy-form">
        <div class="strategy-form-grid">
          <a-form-item label="策略名称" :validate-status="submitTouched && !formModel.name ? 'error' : ''" help="">
            <a-input v-model="formModel.name" placeholder="例如：通用文档解析" />
          </a-form-item>
          <a-form-item label="策略编码">
            <a-input v-model="formModel.code" placeholder="例如：general_doc_parse" />
          </a-form-item>
          <a-form-item label="作用域">
            <a-select v-model="formModel.scopeType">
              <a-select-option value="template">系统预设</a-select-option>
              <a-select-option value="kb">知识库自定义</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="状态">
            <a-radio-group v-model="formModel.status">
              <a-radio value="active">启用</a-radio>
              <a-radio value="disabled">停用</a-radio>
            </a-radio-group>
          </a-form-item>
        </div>

        <template v-if="isParse">
          <div class="strategy-section-title">解析参数</div>
          <div class="strategy-form-grid">
            <a-form-item label="分段方式">
              <a-select v-model="parseForm.splitMode" @change="syncConfigFromFields">
                <a-select-option value="auto">自动识别</a-select-option>
                <a-select-option value="heading">按标题</a-select-option>
                <a-select-option value="paragraph">按段落</a-select-option>
                <a-select-option value="fixed">固定长度</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="Chunk 大小">
              <a-input-number v-model="parseForm.chunkSize" :min="128" :max="8000" :step="128" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="重叠长度">
              <a-input-number v-model="parseForm.chunkOverlap" :min="0" :max="2000" :step="32" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="OCR">
              <a-switch v-model="parseForm.ocrEnabled" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="表格抽取">
              <a-switch v-model="parseForm.tableExtraction" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="图片抽取">
              <a-switch v-model="parseForm.imageExtraction" @change="syncConfigFromFields" />
            </a-form-item>
          </div>
        </template>

        <template v-else>
          <div class="strategy-section-title">检索参数</div>
          <div class="strategy-form-grid">
            <a-form-item label="检索模式">
              <a-select v-model="retrievalForm.mode" @change="syncConfigFromFields">
                <a-select-option value="hybrid">混合检索</a-select-option>
                <a-select-option value="vector">向量检索</a-select-option>
                <a-select-option value="bm25">关键词检索</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item label="TopK">
              <a-input-number v-model="retrievalForm.topK" :min="1" :max="50" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="相似度阈值">
              <a-input-number v-model="retrievalForm.scoreThreshold" :min="0" :max="1" :step="0.01" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="向量权重">
              <a-input-number v-model="retrievalForm.vectorWeight" :min="0" :max="1" :step="0.05" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="BM25 权重">
              <a-input-number v-model="retrievalForm.bm25Weight" :min="0" :max="1" :step="0.05" @change="syncConfigFromFields" />
            </a-form-item>
            <a-form-item label="Rerank">
              <a-switch v-model="retrievalForm.rerankEnabled" @change="syncConfigFromFields" />
            </a-form-item>
          </div>
        </template>

        <a-form-item label="策略 JSON" :validate-status="configJsonError ? 'error' : ''" :help="configJsonError">
          <a-textarea v-model="formModel.configJson" :auto-size="{ minRows: 8, maxRows: 14 }" @blur="syncFieldsFromConfig" />
        </a-form-item>
        <a-form-item label="备注">
          <a-textarea v-model="formModel.remark" :auto-size="{ minRows: 2, maxRows: 4 }" placeholder="说明适用场景、注意事项" />
        </a-form-item>
      </a-form>

      <div class="strategy-drawer-footer">
        <a-button @click="closeDrawer">取消</a-button>
        <a-button type="primary" :loading="saving" @click="onSave">保存</a-button>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import {
  createParseStrategyConfig,
  createRetrievalStrategyConfig,
  deleteParseStrategyConfig,
  deleteRetrievalStrategyConfig,
  getParseStrategyConfigs,
  getRetrievalStrategyConfigs,
  updateParseStrategyConfig,
  updateRetrievalStrategyConfig
} from "@/api/knowledge"

const props = defineProps<{
  strategyType: "parse" | "retrieval"
}>()

const isParse = computed(() => props.strategyType === "parse")
const pageMeta = computed(() =>
  isParse.value
    ? {
        title: "解析策略管理",
        shortTitle: "解析策略",
        desc: "维护文档入库时的解析、分段、OCR 与结构化抽取预设，供知识库设置选择。"
      }
    : {
        title: "检索策略管理",
        shortTitle: "检索策略",
        desc: "维护问答召回时的向量、关键词、混合检索与重排预设，供知识库设置选择。"
      }
)

const loading = ref(false)
const saving = ref(false)
const drawerVisible = ref(false)
const submitTouched = ref(false)
const editingId = ref("")
const keyword = ref("")
const statusFilter = ref("")
const list = ref<any[]>([])
const configJsonError = ref("")

const formModel = reactive({
  name: "",
  code: "",
  scopeType: "template",
  status: "active",
  configJson: "",
  remark: ""
})

const parseForm = reactive({
  splitMode: "auto",
  chunkSize: 800,
  chunkOverlap: 100,
  ocrEnabled: true,
  tableExtraction: true,
  imageExtraction: false
})

const retrievalForm = reactive({
  mode: "hybrid",
  topK: 5,
  scoreThreshold: 0.3,
  vectorWeight: 0.7,
  bm25Weight: 0.3,
  rerankEnabled: true,
  rerankTopN: 10
})

const columns = [
  { title: "名称", dataIndex: "name", scopedSlots: { customRender: "name" }, width: 220 },
  { title: "作用域", dataIndex: "scopeType", scopedSlots: { customRender: "scopeType" }, width: 110 },
  { title: "状态", dataIndex: "status", scopedSlots: { customRender: "status" }, width: 100 },
  { title: "备注", dataIndex: "remark", scopedSlots: { customRender: "remark" } },
  { title: "更新时间", dataIndex: "updateTime", width: 170 },
  { title: "操作", key: "action", scopedSlots: { customRender: "action" }, width: 210 }
]

const filteredList = computed(() => {
  const word = keyword.value.trim().toLowerCase()
  return list.value.filter((item) => {
    const matchStatus = !statusFilter.value || item.status === statusFilter.value
    if (!word) {
      return matchStatus
    }
    const haystack = [item.name, item.code, item.remark].join(" ").toLowerCase()
    return matchStatus && haystack.includes(word)
  })
})

watch(
  () => props.strategyType,
  () => {
    closeDrawer()
    loadList()
  }
)

onMounted(loadList)

async function loadList() {
  loading.value = true
  try {
    const res = isParse.value
      ? await getParseStrategyConfigs({ scopeType: "template" })
      : await getRetrievalStrategyConfigs({ scopeType: "template" })
    list.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    console.error(e)
    message.error("策略列表加载失败")
  } finally {
    loading.value = false
  }
}

function openCreate() {
  resetForm()
  syncConfigFromFields()
  drawerVisible.value = true
}

function openEdit(record: any) {
  resetForm()
  editingId.value = record.id
  formModel.name = record.name || ""
  formModel.code = record.code || ""
  formModel.scopeType = record.scopeType || "template"
  formModel.status = record.status || "active"
  formModel.configJson = formatJson(record.configJson || "{}")
  formModel.remark = record.remark || ""
  syncFieldsFromConfig()
  drawerVisible.value = true
}

function closeDrawer() {
  drawerVisible.value = false
  resetForm()
}

function resetForm() {
  editingId.value = ""
  submitTouched.value = false
  configJsonError.value = ""
  formModel.name = ""
  formModel.code = ""
  formModel.scopeType = "template"
  formModel.status = "active"
  formModel.configJson = ""
  formModel.remark = ""
  parseForm.splitMode = "auto"
  parseForm.chunkSize = 800
  parseForm.chunkOverlap = 100
  parseForm.ocrEnabled = true
  parseForm.tableExtraction = true
  parseForm.imageExtraction = false
  retrievalForm.mode = "hybrid"
  retrievalForm.topK = 5
  retrievalForm.scoreThreshold = 0.3
  retrievalForm.vectorWeight = 0.7
  retrievalForm.bm25Weight = 0.3
  retrievalForm.rerankEnabled = true
  retrievalForm.rerankTopN = 10
}

function syncConfigFromFields() {
  const config = isParse.value
    ? {
        splitMode: parseForm.splitMode,
        chunkSize: Number(parseForm.chunkSize),
        chunkOverlap: Number(parseForm.chunkOverlap),
        ocrEnabled: Boolean(parseForm.ocrEnabled),
        tableExtraction: Boolean(parseForm.tableExtraction),
        imageExtraction: Boolean(parseForm.imageExtraction)
      }
    : {
        mode: retrievalForm.mode,
        topK: Number(retrievalForm.topK),
        scoreThreshold: Number(retrievalForm.scoreThreshold),
        vectorWeight: Number(retrievalForm.vectorWeight),
        bm25Weight: Number(retrievalForm.bm25Weight),
        rerank: {
          enabled: Boolean(retrievalForm.rerankEnabled),
          topN: Number(retrievalForm.rerankTopN)
        }
      }
  formModel.configJson = JSON.stringify(config, null, 2)
  configJsonError.value = ""
}

function syncFieldsFromConfig() {
  try {
    const config = JSON.parse(formModel.configJson || "{}")
    if (isParse.value) {
      parseForm.splitMode = config.splitMode || parseForm.splitMode
      parseForm.chunkSize = Number(config.chunkSize || parseForm.chunkSize)
      parseForm.chunkOverlap = Number(config.chunkOverlap ?? parseForm.chunkOverlap)
      parseForm.ocrEnabled = Boolean(config.ocrEnabled)
      parseForm.tableExtraction = Boolean(config.tableExtraction)
      parseForm.imageExtraction = Boolean(config.imageExtraction)
    } else {
      retrievalForm.mode = config.mode || retrievalForm.mode
      retrievalForm.topK = Number(config.topK || retrievalForm.topK)
      retrievalForm.scoreThreshold = Number(config.scoreThreshold ?? retrievalForm.scoreThreshold)
      retrievalForm.vectorWeight = Number(config.vectorWeight ?? retrievalForm.vectorWeight)
      retrievalForm.bm25Weight = Number(config.bm25Weight ?? retrievalForm.bm25Weight)
      retrievalForm.rerankEnabled = Boolean(config.rerank?.enabled)
      retrievalForm.rerankTopN = Number(config.rerank?.topN || retrievalForm.rerankTopN)
    }
    formModel.configJson = formatJson(formModel.configJson)
    configJsonError.value = ""
  } catch (e) {
    configJsonError.value = "JSON 格式不正确"
  }
}

async function onSave() {
  submitTouched.value = true
  syncFieldsFromConfig()
  if (!formModel.name.trim()) {
    message.warning("请输入策略名称")
    return
  }
  if (configJsonError.value) {
    message.warning("请先修正策略 JSON")
    return
  }
  saving.value = true
  try {
    const payload = {
      name: formModel.name.trim(),
      code: formModel.code.trim(),
      scopeType: formModel.scopeType,
      status: formModel.status,
      configJson: formModel.configJson,
      remark: formModel.remark
    }
    if (editingId.value) {
      if (isParse.value) {
        await updateParseStrategyConfig(editingId.value, payload)
      } else {
        await updateRetrievalStrategyConfig(editingId.value, payload)
      }
      message.success("策略已更新")
    } else {
      if (isParse.value) {
        await createParseStrategyConfig(payload)
      } else {
        await createRetrievalStrategyConfig(payload)
      }
      message.success("策略已创建")
    }
    closeDrawer()
    loadList()
  } catch (e) {
    console.error(e)
    message.error("保存失败")
  } finally {
    saving.value = false
  }
}

async function toggleStatus(record: any) {
  const nextStatus = record.status === "active" ? "disabled" : "active"
  try {
    const payload = { ...record, status: nextStatus }
    if (isParse.value) {
      await updateParseStrategyConfig(record.id, payload)
    } else {
      await updateRetrievalStrategyConfig(record.id, payload)
    }
    message.success(nextStatus === "active" ? "已启用" : "已停用")
    loadList()
  } catch (e) {
    message.error("状态更新失败")
  }
}

async function onDelete(record: any) {
  try {
    if (isParse.value) {
      await deleteParseStrategyConfig(record.id)
    } else {
      await deleteRetrievalStrategyConfig(record.id)
    }
    message.success("已删除")
    loadList()
  } catch (e) {
    message.error("删除失败")
  }
}

function formatJson(value: string) {
  try {
    return JSON.stringify(JSON.parse(value || "{}"), null, 2)
  } catch (e) {
    return value || ""
  }
}

</script>

<style lang="less" scoped>
.strategy-page {
  padding: 20px 24px 32px;
  color: #0f172a;
}

.strategy-head,
.strategy-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.strategy-head {
  margin-bottom: 16px;
}

.strategy-title {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
}

.strategy-desc {
  margin: 6px 0 0;
  color: #64748b;
}

.strategy-toolbar {
  justify-content: flex-start;
  padding: 14px;
  margin-bottom: 14px;
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 8px;
}

.strategy-search {
  width: 320px;
}

.strategy-filter {
  width: 140px;
}

.strategy-table {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 8px;
}

.strategy-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.strategy-name-cell span {
  font-size: 12px;
  color: #94a3b8;
}

.strategy-remark {
  display: block;
  overflow: hidden;
  max-width: 420px;
  font-size: 13px;
  color: #475569;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strategy-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.strategy-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}

.strategy-section-title {
  margin: 6px 0 14px;
  padding-bottom: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #1d4ed8;
  border-bottom: 1px solid #e5e7eb;
}

.strategy-drawer-footer {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 24px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}

.strategy-form {
  padding-bottom: 64px;
}

@media (max-width: 900px) {
  .strategy-head,
  .strategy-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .strategy-search,
  .strategy-filter {
    width: 100%;
  }

  .strategy-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
