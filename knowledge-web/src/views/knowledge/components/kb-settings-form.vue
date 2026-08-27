<template>
  <div class="kb-settings">
    <div class="kb-settings-hero">
      <div>
        <div class="kb-settings-hero__eyebrow">Basic Settings</div>
        <h3 class="kb-settings-hero__title">知识库基础设置</h3>
        <p class="kb-settings-hero__desc">维护名称、分类、标签与内容审核，解析/检索/模型请在「策略配置」页签中设置。</p>
      </div>
      <a-button type="primary" size="large" :loading="saving" @click="onSave">
        <a-icon type="save" />保存设置
      </a-button>
    </div>

    <KbBasicForm
      :form-model="formModel"
      :tags="selectedTags"
      :tag-suggestions="tagSuggestions"
      :submit-touched="submitTouched"
      card
      @change-tags="updateSelectedTags"
    />

    <div class="kb-settings-danger">
      <div>
        <h4>危险操作</h4>
        <p>删除知识库后，所有文件、问答、审核数据将不可恢复。</p>
      </div>
      <a-popconfirm title="确定要删除此知识库？此操作不可撤销" @confirm="onDeleteKb">
        <a-button type="danger" ghost>删除知识库</a-button>
      </a-popconfirm>
    </div>
  </div>
</template>

<script setup lang="ts">
import { updateKnowledgeBase, deleteKnowledgeBase, getTagList, createTag } from "@/api/knowledge"
import KbBasicForm from "./kb-basic-form.vue"
import { DEFAULT_KNOWLEDGE_TYPE, normalizeKnowledgeTypeForForm } from "../constants"

const props = defineProps<{
  kbId: string | number
  kbInfo: any
}>()

const emit = defineEmits(["saved"])
const router = useRouter()

const saving = ref(false)
const submitTouched = ref(false)
const tagList = ref<any[]>([])
const selectedTags = ref<string[]>([])

const formModel = reactive({
  name: "",
  type: DEFAULT_KNOWLEDGE_TYPE,
  description: "",
  visibility: "public",
  fileAuditEnabled: 0,
  qaAuditEnabled: 0
})

const tagSuggestions = computed(() => {
  const selected = new Set(selectedTags.value)
  return tagList.value.filter((tag: any) => tag?.name && !selected.has(tag.name)).slice(0, 8)
})

onMounted(() => {
  loadTags()
})

watch(
  () => props.kbInfo,
  (info) => {
    if (info) {
      formModel.name = info.name || ""
      formModel.type = normalizeKnowledgeTypeForForm(info.type)
      formModel.description = info.description || ""
      formModel.visibility = info.visibility || "public"
      formModel.fileAuditEnabled = info.fileAuditEnabled || 0
      formModel.qaAuditEnabled = info.qaAuditEnabled || 0
      selectedTags.value = (info.tags || []).map((tag: any) => tag.name || tag).filter(Boolean)
    }
  },
  { immediate: true }
)

/**
 * 拉取已有标签，用于设置页标签建议。
 */
async function loadTags() {
  try {
    const res = await getTagList()
    tagList.value = unwrapArrayResult(res)
  } catch (e) {
    console.error(e)
    tagList.value = []
  }
}

/**
 * 将标签名称转换为后端需要的 tagIds，不存在的标签先自动创建。
 */
async function resolveTagIds(tagNames: string[]) {
  const normalizedNames = Array.from(new Set((tagNames || []).map((item) => String(item || "").trim()).filter(Boolean)))
  if (!normalizedNames.length) {
    return []
  }

  const tagMap = new Map(tagList.value.map((tag: any) => [String(tag.name || "").trim(), tag]))
  const tagIds: Array<string | number> = []

  for (const name of normalizedNames) {
    let tag = tagMap.get(name)
    if (!tag?.id) {
      try {
        const res = await createTag({ name })
        tag = unwrapEntityResult(res)
        if (tag?.id) {
          tagList.value = [...tagList.value, tag]
          tagMap.set(name, tag)
        }
      } catch (error) {
        await loadTags()
        tag = (tagList.value || []).find((item: any) => String(item.name || "").trim() === name)
        if (!tag?.id) {
          throw error
        }
      }
    }
    if (tag?.id) {
      tagIds.push(tag.id)
    }
  }

  return tagIds
}

function unwrapArrayResult(payload: any) {
  return Array.isArray(payload?.datas) ? payload.datas : []
}

function unwrapEntityResult(payload: any) {
  return payload?.datas && typeof payload.datas === "object" && !Array.isArray(payload.datas) ? payload.datas : {}
}

/**
 * 接收共享基础表单的标签变更，保存时统一转换成后端 tagIds。
 */
function updateSelectedTags(nextTags: string[]) {
  selectedTags.value = nextTags
}

/**
 * 保存基础设置，保持和新建知识库提交结构一致。
 */
async function onSave() {
  submitTouched.value = true
  if (!formModel.name?.trim()) {
    message.warning("请输入知识库名称")
    return
  }
  saving.value = true
  try {
    const tagIds = await resolveTagIds(selectedTags.value)
    await updateKnowledgeBase(props.kbId, { ...formModel, tagIds })
    message.success("保存成功")
    emit("saved")
  } catch (e) {
    message.error("保存失败")
  } finally {
    saving.value = false
  }
}

/**
 * 删除当前知识库，删除后回到知识库列表。
 */
async function onDeleteKb() {
  try {
    await deleteKnowledgeBase(props.kbId)
    message.success("知识库已删除")
    router.push({ name: "KbList" })
  } catch (e) {
    message.error("删除失败")
  }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order */
.kb-settings {
  color: #0f172a;
}

.kb-settings-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 22px 24px;
  margin-bottom: 18px;
  background: radial-gradient(circle at 12% 20%, rgba(29, 78, 216, 0.16), transparent 28%),
    linear-gradient(135deg, #f8fbff 0%, #edf4ff 100%);
  border: 1px solid rgba(29, 78, 216, 0.12);
  border-radius: 20px;
}

.kb-settings-hero__eyebrow {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #1d4ed8;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.kb-settings-hero__title {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #0c1222;
}

.kb-settings-hero__desc {
  margin: 8px 0 0;
  color: #64748b;
}

.kb-settings-danger {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  padding: 18px 20px;
  margin-top: 18px;
  background: #fff7f7;
  border: 1px solid #fecaca;
  border-radius: 16px;
}

.kb-settings-danger h4 {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 700;
  color: #991b1b;
}

.kb-settings-danger p {
  margin: 0;
  color: #64748b;
}

@media (max-width: 900px) {
  .kb-settings-hero,
  .kb-settings-danger {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
