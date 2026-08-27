<template>
  <a-form layout="vertical" :class="formClasses">
    <div class="kb-basic-form-stack">
      <section class="kb-basic-panel">
        <div class="kb-basic-panel-head">
          <span class="kb-basic-panel-mark"></span>
          <div>
            <h4>基础信息</h4>
            <p>先确定知识库的识别信息，创建后仍可在设置中调整。</p>
          </div>
        </div>
        <div class="kb-basic-core-grid">
          <a-form-item
            class="kb-basic-form-item is-name"
            label="知识库名称"
            :validate-status="submitTouched && !formModel.name ? 'error' : ''"
            :help="submitTouched && !formModel.name ? '请输入知识库名称' : ''"
          >
            <a-input v-model="formModel.name" size="large" placeholder="例如：人力资源制度库" />
          </a-form-item>

          <a-form-item class="kb-basic-form-item is-type" label="知识库类型">
            <a-select v-model="formModel.type" size="large">
              <a-select-option v-for="item in KNOWLEDGE_TYPE_OPTIONS" :key="item.value" :value="item.value">
                {{ item.label }}
              </a-select-option>
            </a-select>
          </a-form-item>

          <a-form-item class="kb-basic-form-item is-visibility" label="可见范围">
            <a-select v-model="formModel.visibility" size="large">
              <a-select-option value="public">公开（出现在知识广场）</a-select-option>
              <a-select-option value="private">不公开（仅成员可见）</a-select-option>
            </a-select>
          </a-form-item>
        </div>
        <div>
          <a-form-item class="kb-basic-form-item is-description" label="描述（选填）">
            <a-textarea
              v-model="formModel.description"
              placeholder="简要说明用途，便于在列表中识别"
              :auto-size="descriptionAutoSize"
            />
          </a-form-item>
        </div>
      </section>

      <section class="kb-basic-panel">
        <div class="kb-basic-panel-head">
          <span class="kb-basic-panel-mark"></span>
          <div>
            <h4>标签</h4>
            <p>{{ tagHint }}</p>
          </div>
        </div>
        <div class="kb-basic-tag-editor">
          <div class="kb-basic-tag-box" @click="focusTagInput">
            <button v-for="tag in tags" :key="tag" type="button" class="kb-basic-tag-chip" @click.stop="removeTag(tag)">
              <span>{{ tag }}</span>
              <a-icon type="close" />
            </button>
            <input
              ref="tagInputRef"
              v-model="tagInput"
              class="kb-basic-tag-input"
              placeholder="输入标签后按回车添加"
              @keydown="handleTagInputKeydown"
              @blur="commitTagInput"
            />
          </div>
          <div v-if="tagSuggestions.length" class="kb-basic-tag-suggestions">
            <button
              v-for="tag in tagSuggestions"
              :key="tag.id || tag.name"
              type="button"
              class="kb-basic-tag-suggestion"
              @click="appendTag(tag.name)"
            >
              {{ tag.name }}
            </button>
          </div>
        </div>
      </section>

      <section class="kb-basic-panel">
        <div class="kb-basic-panel-head">
          <span class="kb-basic-panel-mark"></span>
          <div>
            <h4>内容审核</h4>
            <p>开启后，对应内容需审核通过才参与检索或对外展示。</p>
          </div>
        </div>
        <div class="kb-basic-review-row">
          <a-form-item label="文件解析结果" class="kb-basic-review-item">
            <a-select v-model="formModel.fileAuditEnabled" size="large">
              <a-select-option :value="0">不开启</a-select-option>
              <a-select-option :value="1">需审核</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="问答对" class="kb-basic-review-item">
            <a-select v-model="formModel.qaAuditEnabled" size="large">
              <a-select-option :value="0">不开启</a-select-option>
              <a-select-option :value="1">需审核</a-select-option>
            </a-select>
          </a-form-item>
        </div>
      </section>

      <slot></slot>
    </div>
  </a-form>
</template>

<script setup lang="ts">
import { KNOWLEDGE_TYPE_OPTIONS } from "../constants"

const props = withDefaults(
  defineProps<{
    formModel: any
    tags: string[]
    tagSuggestions: any[]
    submitTouched?: boolean
    card?: boolean
    variant?: "default" | "modal"
    tagHint?: string
    descriptionAutoSize?: { minRows: number; maxRows: number }
  }>(),
  {
    submitTouched: false,
    card: false,
    variant: "default",
    tagHint: "标签用于知识库分类、筛选与广场展示；支持选择已有标签或直接新建。",
    descriptionAutoSize: () => ({ minRows: 3, maxRows: 6 })
  }
)

const emit = defineEmits<{
  (event: "change-tags", tags: string[]): void
}>()

const tagInput = ref("")
const tagInputRef = ref<HTMLInputElement | null>(null)

const formClasses = computed(() => [
  "kb-basic-form",
  `is-${props.variant}`,
  {
    "is-card": props.card
  }
])

/**
 * 聚焦标签输入框，用于点击整个标签容器时延续输入体验。
 */
function focusTagInput() {
  tagInputRef.value?.focus()
}

/**
 * 添加标签并去重，新增结果通过事件交给父组件保存。
 */
function appendTag(rawValue: string) {
  const value = String(rawValue || "").trim()
  if (!value || props.tags.includes(value)) {
    tagInput.value = ""
    return
  }
  emit("change-tags", [...props.tags, value])
  tagInput.value = ""
}

/**
 * 移除指定标签，保持标签状态仍由父组件统一持有。
 */
function removeTag(tagName: string) {
  emit(
    "change-tags",
    props.tags.filter((item) => item !== tagName)
  )
}

/**
 * 提交当前输入框里的标签文本。
 */
function commitTagInput() {
  appendTag(tagInput.value)
}

/**
 * 处理标签输入快捷键：回车/逗号添加，空输入退格删除最后一个。
 */
function handleTagInputKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault()
    commitTagInput()
  }
  if (event.key === "Backspace" && !tagInput.value && props.tags.length) {
    emit("change-tags", props.tags.slice(0, -1))
  }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.kb-basic-form {
  --kb-basic-border: #e5e7eb;
  --kb-basic-primary: #1d4ed8;
  --kb-basic-ink: #0c1222;

  margin-bottom: 0;

  &.is-card {
    padding: 24px;
    background: #fff;
    border: 1px solid #e8ecf1;
    border-radius: 18px;
  }

  &.is-modal {
    --kb-basic-border: #e5e7eb;
  }
}

.kb-basic-form-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.is-full-row {
  width: 100%;
}

.kb-basic-panel {
  padding: 16px 18px;
  background: linear-gradient(180deg, #fbfcff 0%, #f8fafc 100%);
  border: 1px solid #e8eef7;
  border-radius: 16px;
}

.kb-basic-form.is-modal .kb-basic-panel {
  padding: 14px 16px;
}

.kb-basic-panel-head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.kb-basic-panel-head h4 {
  margin: 0;
  color: var(--kb-basic-ink);
  font-size: 14px;
  font-weight: 700;
}

.kb-basic-panel-head p {
  margin: 4px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.45;
}

.kb-basic-panel-mark {
  flex-shrink: 0;
  width: 4px;
  height: 16px;
  margin-top: 2px;
  background: linear-gradient(180deg, #3b82f6, #1d4ed8);
  border-radius: 999px;
}

.kb-basic-core-grid {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) 190px 240px;
  gap: 14px 16px;
}

.kb-basic-form.is-modal .kb-basic-core-grid {
  grid-template-columns: minmax(280px, 1fr) 200px 240px;
}

.kb-basic-form-item.is-description {
  grid-column: 1 / -1;
}

.kb-basic-form-item,
.kb-basic-review-item {
  margin-bottom: 0;
}

.kb-basic-form ::v-deep .ant-form-item-label {
  padding: 0 0 6px;
  line-height: 1.35;
}

.kb-basic-form ::v-deep .ant-form-item-label label {
  height: auto;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.kb-basic-form ::v-deep .ant-form-item-label label::after {
  display: none;
}

.kb-basic-tag-editor {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.kb-basic-tag-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 7px 10px;
  background: #fff;
  border: 1px solid var(--kb-basic-border);
  border-radius: 12px;
  cursor: text;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.kb-basic-tag-box:focus-within {
  border-color: var(--kb-basic-primary);
  box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.12);
}

.kb-basic-tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  color: var(--kb-basic-primary);
  font-size: 13px;
  font-weight: 600;
  background: #eaf2ff;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.kb-basic-tag-chip:hover {
  color: #1e40af;
  background: #dbeafe;
}

.kb-basic-tag-chip .anticon {
  font-size: 10px;
  opacity: 0.8;
}

.kb-basic-tag-input {
  flex: 1;
  min-width: 180px;
  height: 28px;
  padding: 0;
  color: var(--kb-basic-ink);
  font-size: 14px;
  line-height: 28px;
  background: transparent;
  border: 0;
  outline: none;
}

.kb-basic-tag-input::placeholder {
  color: #94a3b8;
}

.kb-basic-tag-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-basic-tag-suggestion {
  height: 28px;
  padding: 0 12px;
  color: #475569;
  font-size: 12px;
  font-weight: 500;
  background: #fff;
  border: 1px solid #dbe3ee;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.kb-basic-tag-suggestion:hover {
  color: var(--kb-basic-primary);
  background: #eff6ff;
  border-color: #93c5fd;
}

.kb-basic-form ::v-deep .ant-input,
.kb-basic-form ::v-deep .ant-input-affix-wrapper .ant-input {
  font-size: 14px;
  line-height: 1.5;
  border-color: var(--kb-basic-border);
  border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.kb-basic-form ::v-deep .ant-input:hover,
.kb-basic-form ::v-deep .ant-select-selection:hover {
  border-color: #cbd5e1;
}

.kb-basic-form ::v-deep .ant-input:focus {
  border-color: var(--kb-basic-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.kb-basic-form ::v-deep .ant-select {
  display: block;
  width: 100%;
}

.kb-basic-form ::v-deep .ant-select-selection {
  min-height: 40px;
  font-size: 14px;
  border-color: var(--kb-basic-border);
  border-radius: 12px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.kb-basic-form ::v-deep .ant-select-focused .ant-select-selection,
.kb-basic-form ::v-deep .ant-select-selection:focus,
.kb-basic-form ::v-deep .ant-select-selection:active {
  border-color: var(--kb-basic-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.kb-basic-form ::v-deep .ant-select-selection:not(.ant-select-selection--multiple) .ant-select-selection__rendered {
  margin-right: 30px;
  font-size: 14px;
  line-height: 38px;
}

.kb-basic-form ::v-deep .ant-select-selection-selected-value,
.kb-basic-form ::v-deep .ant-select-selection__placeholder {
  font-size: 14px;
  line-height: 38px;
}

.kb-basic-form ::v-deep .ant-select-arrow {
  color: #94a3b8;
  font-size: 12px;
}

.kb-basic-review-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

@media (max-width: 900px) {
  .kb-basic-core-grid,
  .kb-basic-form.is-modal .kb-basic-core-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kb-basic-form-item.is-name,
  .kb-basic-form-item.is-description {
    grid-column: 1 / -1;
  }
}

@media (max-width: 560px) {
  .kb-basic-core-grid,
  .kb-basic-form.is-modal .kb-basic-core-grid,
  .kb-basic-review-row {
    grid-template-columns: 1fr;
  }

  .kb-basic-form-item.is-name,
  .kb-basic-form-item.is-description {
    grid-column: 1;
  }
}
</style>
