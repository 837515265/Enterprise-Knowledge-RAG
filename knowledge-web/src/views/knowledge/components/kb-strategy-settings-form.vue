<template>
  <div class="kb-strategy-settings">
    <div class="kb-strategy-hero">
      <div>
        <div class="kb-strategy-hero__eyebrow">Strategy</div>
        <h3 class="kb-strategy-hero__title">策略配置</h3>
        <p class="kb-strategy-hero__desc">配置默认解析、检索与模型；上传文件时仍可临时覆盖解析策略。</p>
      </div>
      <a-button type="primary" size="large" :loading="saving" @click="onSave">
        <a-icon type="save" />保存策略
      </a-button>
    </div>

    <a-form layout="vertical" class="kb-strategy-form">
      <div class="kb-strategy-section">
        <span class="kb-strategy-section__title">解析与检索</span>
        <p class="kb-strategy-section__desc">与知识库默认行为绑定；检索测试后续会读取这里的检索策略。</p>
        <div class="kb-strategy-row">
          <a-form-item label="默认解析策略" class="kb-strategy-item">
            <a-select v-model="formModel.parseStrategyConfigId" size="large" allow-clear placeholder="使用系统默认">
              <a-select-option v-for="item in parseStrategyOptions" :key="item.id" :value="item.id">
                {{ item.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="默认检索策略" class="kb-strategy-item">
            <a-select v-model="formModel.retrievalConfigId" size="large" allow-clear placeholder="使用系统默认">
              <a-select-option v-for="item in retrievalStrategyOptions" :key="item.id" :value="item.id">
                {{ item.name }}
              </a-select-option>
            </a-select>
          </a-form-item>
        </div>
      </div>

      <div class="kb-strategy-section">
        <span class="kb-strategy-section__title">模型策略</span>
        <p class="kb-strategy-section__desc">按知识库保存，底层以 model_profile JSON 写入；问 AI 会优先使用对话模型配置。</p>
        <div class="kb-strategy-model-grid">
          <a-form-item label="对话模型">
            <a-input v-model="modelForm.chatModel" size="large" placeholder="Qwen/Qwen3.6-27B" />
          </a-form-item>
          <a-form-item label="Embedding 模型">
            <a-input v-model="modelForm.embeddingModel" size="large" placeholder="bge-m3" />
          </a-form-item>
          <a-form-item label="Rerank 模型">
            <a-input v-model="modelForm.rerankModel" size="large" placeholder="bge-reranker-v2-m3" />
          </a-form-item>
          <a-form-item label="OCR 模型">
            <a-input v-model="modelForm.ocrModel" size="large" placeholder="default-ocr" />
          </a-form-item>
          <a-form-item label="Temperature">
            <a-input-number v-model="modelForm.temperature" :min="0" :max="2" :step="0.1" size="large" />
          </a-form-item>
          <a-form-item label="Max Tokens">
            <a-input-number v-model="modelForm.maxTokens" :min="256" :max="32768" :step="256" size="large" />
          </a-form-item>
        </div>
      </div>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { getParseStrategyConfigs, getRetrievalStrategyConfigs, updateKnowledgeBase } from "@/api/knowledge"

const props = defineProps<{
  kbId: string | number
  kbInfo: any
}>()

const emit = defineEmits(["saved"])

const saving = ref(false)
const parseStrategyOptions = ref<any[]>([])
const retrievalStrategyOptions = ref<any[]>([])

const formModel = reactive({
  parseStrategyConfigId: "",
  retrievalConfigId: ""
})

const modelForm = reactive({
  chatModel: "Qwen/Qwen3.6-27B",
  embeddingModel: "bge-m3",
  rerankModel: "bge-reranker-v2-m3",
  ocrModel: "default-ocr",
  temperature: 0.3,
  maxTokens: 2048
})

onMounted(() => {
  loadStrategyOptions()
})

watch(
  () => props.kbInfo,
  (info) => {
    if (info) {
      formModel.parseStrategyConfigId = info.parseStrategyConfigId || ""
      formModel.retrievalConfigId = info.retrievalConfigId || ""
      applyModelProfile(info.modelProfile)
    }
  },
  { immediate: true }
)

/**
 * 拉取解析与检索策略配置列表。
 */
async function loadStrategyOptions() {
  const params = { kbId: props.kbId, status: "active" }
  try {
    const [parseRes, retrievalRes] = await Promise.all([
      getParseStrategyConfigs(params),
      getRetrievalStrategyConfigs(params)
    ])
    parseStrategyOptions.value = Array.isArray((parseRes as any)?.datas) ? (parseRes as any).datas : []
    retrievalStrategyOptions.value = Array.isArray((retrievalRes as any)?.datas) ? (retrievalRes as any).datas : []
  } catch (e) {
    console.error(e)
    parseStrategyOptions.value = []
    retrievalStrategyOptions.value = []
  }
}

function applyModelProfile(modelProfile: string) {
  resetModelForm()
  if (!modelProfile) {
    return
  }
  try {
    const profile = JSON.parse(modelProfile)
    modelForm.chatModel = profile?.chat?.model || modelForm.chatModel
    modelForm.embeddingModel = profile?.embedding?.model || modelForm.embeddingModel
    modelForm.rerankModel = profile?.rerank?.model || modelForm.rerankModel
    modelForm.ocrModel = profile?.parse?.ocrModel || modelForm.ocrModel
    modelForm.temperature = Number(profile?.chat?.temperature ?? modelForm.temperature)
    modelForm.maxTokens = Number(profile?.chat?.maxTokens ?? modelForm.maxTokens)
  } catch (e) {
    console.error(e)
    message.warning("当前知识库模型配置格式异常，请重新保存")
  }
}

function resetModelForm() {
  modelForm.chatModel = "Qwen/Qwen3.6-27B"
  modelForm.embeddingModel = "bge-m3"
  modelForm.rerankModel = "bge-reranker-v2-m3"
  modelForm.ocrModel = "default-ocr"
  modelForm.temperature = 0.3
  modelForm.maxTokens = 2048
}

function buildModelProfile() {
  return JSON.stringify({
    version: "1.0",
    embedding: {
      provider: "default",
      model: modelForm.embeddingModel,
      dimension: 1024,
      batchSize: 32
    },
    rerank: {
      enabled: true,
      provider: "default",
      model: modelForm.rerankModel,
      topN: 10
    },
    chat: {
      provider: "default",
      model: modelForm.chatModel,
      temperature: Number(modelForm.temperature),
      maxTokens: Number(modelForm.maxTokens)
    },
    parse: {
      ocrModel: modelForm.ocrModel,
      layoutModel: "default-layout",
      tableModel: "default-table"
    }
  })
}

/**
 * 仅更新解析、检索、模型策略相关字段。
 */
async function onSave() {
  saving.value = true
  try {
    await updateKnowledgeBase(props.kbId, {
      parseStrategyConfigId: formModel.parseStrategyConfigId || "",
      retrievalConfigId: formModel.retrievalConfigId || "",
      modelProfile: buildModelProfile()
    })
    message.success("策略已保存")
    emit("saved")
  } catch (e) {
    message.error("保存失败")
  } finally {
    saving.value = false
  }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.kb-strategy-settings {
  color: #0f172a;
}

.kb-strategy-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 22px 24px;
  margin-bottom: 18px;
  background: radial-gradient(circle at 12% 20%, rgba(16, 185, 129, 0.12), transparent 30%),
    linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: 20px;
}

.kb-strategy-hero__eyebrow {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #059669;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.kb-strategy-hero__title {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #0c1222;
}

.kb-strategy-hero__desc {
  margin: 8px 0 0;
  color: #64748b;
}

.kb-strategy-form {
  padding: 24px;
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 18px;
}

.kb-strategy-section {
  margin-bottom: 24px;
  padding: 18px;
  background: #f8fafc;
  border: 1px solid #e8ecf1;
  border-radius: 16px;
}

.kb-strategy-section:last-of-type {
  margin-bottom: 0;
}

.kb-strategy-section__title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.kb-strategy-section__desc {
  margin: 6px 0 16px;
  color: #64748b;
}

.kb-strategy-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.kb-strategy-item {
  margin-bottom: 0;
}

.kb-strategy-model-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.kb-strategy-model-grid ::v-deep .ant-input-number {
  width: 100%;
}

@media (max-width: 900px) {
  .kb-strategy-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .kb-strategy-row,
  .kb-strategy-model-grid {
    grid-template-columns: 1fr;
  }
}
</style>
