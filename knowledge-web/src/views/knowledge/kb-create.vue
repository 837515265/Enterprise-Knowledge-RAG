<template>
  <div class="kb-page">
    <div class="kb-page-inner" style="max-width: 720px">
      <div class="kb-page-head">
        <div>
          <h1 class="kb-page-title">{{ isEdit ? "编辑知识库" : "创建知识库" }}</h1>
          <p class="kb-page-desc">{{ isEdit ? "修改知识库的基本信息与设置" : "填写知识库基本信息并创建" }}</p>
        </div>
        <button class="kb-btn-sm" @click="goBack">← 返回</button>
      </div>

      <div class="kb-form-card">
        <a-form :label-col="{ span: 5 }" :wrapper-col="{ span: 17 }">
          <a-form-item
            label="知识库名称"
            :validate-status="submitTouched && !formModel.name ? 'error' : ''"
            :help="submitTouched && !formModel.name ? '请输入知识库名称' : ''"
          >
            <a-input v-model="formModel.name" placeholder="请输入知识库名称" />
          </a-form-item>
          <a-form-item label="知识库类型">
            <a-select v-model="formModel.type">
              <a-select-option v-for="item in KNOWLEDGE_TYPE_OPTIONS" :key="item.value" :value="item.value">
                {{ item.label }}
              </a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="描述">
            <a-textarea
              v-model="formModel.description"
              placeholder="请输入知识库描述"
              :auto-size="{ minRows: 3, maxRows: 6 }"
            />
          </a-form-item>
          <a-form-item label="可见性">
            <a-radio-group v-model="formModel.visibility">
              <a-radio value="public">公开</a-radio>
              <a-radio value="private">不公开</a-radio>
            </a-radio-group>
          </a-form-item>
          <a-form-item label="标签">
            <a-select
              v-model="selectedTags"
              mode="tags"
              style="width: 100%"
              placeholder="输入标签后回车添加"
              allow-clear
              :token-separators="[',']"
            >
              <a-select-option v-for="tag in tagList" :key="tag.id" :value="tag.name">{{ tag.name }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="文件审核">
            <a-switch :checked="formModel.fileAuditEnabled === 1" @change="onFileAuditChange" />
            <span class="ml-2 text-xs text-gray-400">开启后，解析结果需审核才能参与检索</span>
          </a-form-item>
          <a-form-item label="问答审核">
            <a-switch :checked="formModel.qaAuditEnabled === 1" @change="onQaAuditChange" />
            <span class="ml-2 text-xs text-gray-400">开启后，新增问答对需审核通过</span>
          </a-form-item>
          <a-form-item :wrapper-col="{ span: 17, offset: 5 }">
            <a-button type="primary" :loading="submitLoading" @click="onSubmit">
              {{ isEdit ? "保存修改" : "创建" }}
            </a-button>
            <a-button class="ml-3" @click="goBack">取消</a-button>
          </a-form-item>
        </a-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  createKnowledgeBase,
  updateKnowledgeBase,
  getKnowledgeBaseDetail,
  getTagList,
  createTag
} from "@/api/knowledge"
import { DEFAULT_KNOWLEDGE_TYPE, KNOWLEDGE_TYPE_OPTIONS, normalizeKnowledgeTypeForForm } from "./constants"

const props = defineProps<{ kbId?: string | number }>()

const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!props.kbId || !!route.params.kbId)
const editKbId = computed(() => props.kbId || route.params.kbId)

const submitLoading = ref(false)
const submitTouched = ref(false)
const tagList = ref<any[]>([])

function unwrapArrayResult(payload: any) {
  return Array.isArray(payload?.datas) ? payload.datas : []
}

function unwrapEntityResult(payload: any) {
  return payload?.datas && typeof payload.datas === "object" && !Array.isArray(payload.datas) ? payload.datas : {}
}

const selectedTags = ref<string[]>([])

const formModel = reactive({
  name: "",
  type: DEFAULT_KNOWLEDGE_TYPE,
  description: "",
  visibility: "public",
  fileAuditEnabled: 0,
  qaAuditEnabled: 0
})

onMounted(async () => {
  await loadTags()
  if (isEdit.value && editKbId.value) {
    await loadDetail()
  }
})

async function loadTags() {
  try {
    const res = await getTagList()
    tagList.value = unwrapArrayResult(res)
  } catch (e) {
    console.error(e)
    tagList.value = []
  }
}

async function loadDetail() {
  try {
    const res = await getKnowledgeBaseDetail(editKbId.value)
    const detail = unwrapEntityResult(res)
    if (detail) {
      formModel.name = detail.name || ""
      formModel.type = normalizeKnowledgeTypeForForm(detail.type)
      formModel.description = detail.description || ""
      formModel.visibility = detail.visibility || "public"
      formModel.fileAuditEnabled = detail.fileAuditEnabled || 0
      formModel.qaAuditEnabled = detail.qaAuditEnabled || 0
      selectedTags.value = (detail.tags || []).map((t: any) => t.name || t)
    }
  } catch (e) {
    message.error("获取知识库详情失败")
  }
}

/**
 * 将标签名称转换为后端要求的 tagIds。
 * 不存在的标签先创建，再提交知识库创建/更新请求。
 */
async function resolveTagIds(tagNames: string[]) {
  const normalizedNames = Array.from(new Set((tagNames || []).map((item) => item?.trim()).filter(Boolean)))
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

function onFileAuditChange(checked: boolean) {
  formModel.fileAuditEnabled = checked ? 1 : 0
}

function onQaAuditChange(checked: boolean) {
  formModel.qaAuditEnabled = checked ? 1 : 0
}

async function onSubmit() {
  submitTouched.value = true
  if (!formModel.name?.trim()) {
    message.warning("请输入知识库名称")
    return
  }
  submitLoading.value = true
  try {
    const tagIds = await resolveTagIds(selectedTags.value)
    const data = { ...formModel, tagIds }
    if (isEdit.value) {
      await updateKnowledgeBase(editKbId.value, data)
      message.success("更新成功")
    } else {
      await createKnowledgeBase(data)
      message.success("创建成功")
    }
    goBack()
  } catch (e) {
    message.error(isEdit.value ? "更新失败" : "创建失败")
  } finally {
    submitLoading.value = false
  }
}

function goBack() {
  router.push({ name: "KbList" })
}
</script>

<style lang="less" scoped>
.kb-form-card {
  padding: 24px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
}
</style>
