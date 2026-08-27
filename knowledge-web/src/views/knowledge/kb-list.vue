<template>
  <div class="kb-page kb-list-page">
    <div class="kb-page-inner kb-list-inner">
      <!-- 页头 -->
      <div class="list-header">
        <div class="list-header-main">
          <span class="list-eyebrow">知识库</span>
          <h1>我的知识库</h1>
          <p class="list-tagline">文档解析与问答检索的统一入口</p>
        </div>
        <div class="list-header-right">
          <div class="list-search">
            <a-icon type="search" />
            <input v-model="keyword" type="search" placeholder="按名称、描述搜索…" @keydown.enter="onSearch" />
          </div>
          <button type="button" class="list-create-btn" @click="showCreateModal = true">
            <a-icon type="plus" /> 新建知识库
          </button>
        </div>
      </div>

      <!-- Tab 筛选 -->
      <div class="list-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="list-tab"
          :class="{ 'is-active': activeTab === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- 卡片网格 -->
      <div class="list-grid">
        <div v-for="item in filteredList" :key="item.id" class="list-card" @click="goDetail(item)">
          <div class="list-card-icon">
            <a-icon :type="getKnowledgeTypeIcon(item.type)" />
          </div>
          <div class="list-card-body">
            <div class="list-card-top">
              <h3>{{ item.name }}</h3>
              <span class="list-card-vis" :class="item.visibility === 'public' ? 'is-public' : 'is-private'">
                {{ item.visibility === "public" ? "公开" : "私有" }}
              </span>
            </div>
            <p class="list-card-desc">{{ item.description || "暂无描述" }}</p>
            <div class="list-card-tags" :class="{ 'is-empty': !item.tags?.length }">
              <span v-for="tag in item.tags" :key="tag.id">{{ tag.name }}</span>
            </div>
            <div class="list-card-footer">
              <div class="list-card-meta">
                <span><a-icon type="file" /> {{ item.fileCount || 0 }} 个文件</span>
                <span v-if="item.pendingFileCount || item.pendingQaCount" class="list-card-pending">
                  待审核：文件 {{ item.pendingFileCount || 0 }} / 问答 {{ item.pendingQaCount || 0 }}
                </span>
              </div>
              <span>{{ typeLabel(item.type) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && filteredList.length === 0" class="list-empty">
        <a-icon type="inbox" style="font-size: 44px; color: #cbd5e1" />
        <p>暂无知识库</p>
        <button type="button" class="list-create-btn" @click="showCreateModal = true">
          <a-icon type="plus" /> 创建第一个知识库
        </button>
      </div>
    </div>

    <!-- 创建知识库弹窗（样式见底部非 scoped：Modal 挂载到 body） -->
    <a-modal
      v-model="showCreateModal"
      :width="860"
      centered
      :mask-closable="false"
      :footer="null"
      destroy-on-close
      wrap-class-name="kb-create-modal-wrap"
    >
      <template slot="title">
        <div class="kb-create-title">
          <div class="kb-create-title-icon" aria-hidden="true">
            <a-icon type="database" />
          </div>
          <div class="kb-create-title-text">
            <span class="kb-create-title-line">新建知识库</span>
            <span class="kb-create-title-sub">创建后将进入管理页，可随时上传文档与调整权限</span>
          </div>
        </div>
      </template>
      <div class="kb-create-body">
        <p class="kb-create-lead">仅需名称与类型即可创建；标签与审核可在设置中继续完善。</p>
        <KbBasicForm
          :form-model="createModel"
          :tags="createTags"
          :tag-suggestions="tagSuggestions"
          :submit-touched="createTouched"
          variant="modal"
          tag-hint="多个标签用于分类与筛选；可从预设选择或自定义，回车添加。"
          :description-auto-size="{ minRows: 2, maxRows: 4 }"
          @change-tags="updateCreateTags"
        />
      </div>
      <div class="kb-create-footer">
        <a-button size="large" @click="showCreateModal = false">取消</a-button>
        <a-button type="primary" size="large" :loading="createLoading" @click="onCreateSubmit">
          创建并进入管理
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { getKnowledgeBaseList, getTagList, createKnowledgeBase, createTag } from "@/api/knowledge"
import KbBasicForm from "./components/kb-basic-form.vue"
import { DEFAULT_KNOWLEDGE_TYPE, getKnowledgeTypeIcon, getKnowledgeTypeLabel } from "./constants"

const router = useRouter()

const keyword = ref("")
const activeTab = ref("all")
const loading = ref(false)
const allList = ref<any[]>([])
const tagList = ref<any[]>([])

function unwrapArrayResult(payload: any) {
  return Array.isArray(payload?.datas) ? payload.datas : []
}

function unwrapEntityResult(payload: any) {
  return payload?.datas && typeof payload.datas === "object" && !Array.isArray(payload.datas) ? payload.datas : {}
}

const tabs = [
  { key: "all", label: "全部" },
  { key: "created", label: "我创建的" },
  { key: "joined", label: "我加入的" }
]

const filteredList = computed(() => {
  let list = allList.value
  if (keyword.value) {
    const kw = keyword.value.toLowerCase()
    list = list.filter((item: any) => {
      const name = String(item.name || "").toLowerCase()
      const description = String(item.description || "").toLowerCase()
      return name.includes(kw) || description.includes(kw)
    })
  }
  // Tab 过滤逻辑：后端返回 role 字段区分 owner/member
  if (activeTab.value === "created") {
    list = list.filter((item: any) => item.role === "owner" || item.isOwner === true)
  } else if (activeTab.value === "joined") {
    list = list.filter((item: any) => item.role === "member")
  }
  return list
})

onMounted(() => {
  loadList()
  loadTags()
})

onActivated(() => {
  loadList()
})

async function loadList() {
  loading.value = true
  try {
    const res = await getKnowledgeBaseList({ pageSize: 200 })
    allList.value = Array.isArray(res?.data) ? res.data : []
    if (!Array.isArray(allList.value)) allList.value = []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

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
 * 将前端的标签名称转换成后端需要的 tagIds。
 * 已存在标签直接取 id；新标签先创建，再回填 id。
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

function switchTab(key: string) {
  activeTab.value = key
}

function onSearch() {
  // 前端过滤，不需要重新请求
}

function typeLabel(type: string) {
  return getKnowledgeTypeLabel(type)
}

function goDetail(item: any) {
  router.push({ name: "KbDetail", params: { kbId: item.id } })
}

/* ---- 创建弹窗 ---- */
const showCreateModal = ref(false)
const createLoading = ref(false)
const createTouched = ref(false)
const createTags = ref<string[]>([])
const createModel = reactive({
  name: "",
  type: DEFAULT_KNOWLEDGE_TYPE,
  description: "",
  visibility: "public",
  fileAuditEnabled: 0,
  qaAuditEnabled: 0
})

function resetCreateModel() {
  createModel.name = ""
  createModel.type = DEFAULT_KNOWLEDGE_TYPE
  createModel.description = ""
  createModel.visibility = "public"
  createModel.fileAuditEnabled = 0
  createModel.qaAuditEnabled = 0
  createTags.value = []
  createTouched.value = false
}

const tagSuggestions = computed(() => {
  const selected = new Set(createTags.value)
  return tagList.value.filter((tag: any) => tag?.name && !selected.has(tag.name)).slice(0, 8)
})

/**
 * 接收共享基础表单的标签变更，保持新建弹窗提交数据来源一致。
 */
function updateCreateTags(nextTags: string[]) {
  createTags.value = nextTags
}

async function onCreateSubmit() {
  createTouched.value = true
  if (!createModel.name?.trim()) {
    message.warning("请输入知识库名称")
    return
  }
  createLoading.value = true
  try {
    const tagIds = await resolveTagIds(createTags.value)
    const res = await createKnowledgeBase({ ...createModel, tagIds })
    message.success("创建成功")
    showCreateModal.value = false
    resetCreateModel()
    const createdKb = unwrapEntityResult(res)
    const newId = createdKb?.id
    if (newId) {
      router.push({ name: "KbDetail", params: { kbId: newId } })
    } else {
      loadList()
    }
  } catch (e) {
    message.error("创建失败")
  } finally {
    createLoading.value = false
  }
}
</script>

<style lang="less" scoped>
/* stylelint-disable order/properties-order, declaration-block-single-line-max-declarations, value-no-vendor-prefix */
@ink: #0c1222;
@muted: #64748b;
@primary: #1d4ed8;
@primary-hover: #1e40af;
@border: #e8ecf1;
@surface: #ffffff;
@page-bg: #f4f6f9;

.kb-list-page {
  position: relative;
  background-color: @page-bg;
  background-image: radial-gradient(ellipse 120% 80% at 100% -20%, rgba(29, 78, 216, 0.07), transparent 55%),
    radial-gradient(ellipse 80% 50% at 0% 100%, rgba(15, 118, 110, 0.05), transparent 50%);
}

.kb-list-inner {
  position: relative;
  max-width: 1120px;
}

.list-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px 24px;
  margin-bottom: 28px;
}

.list-header-main {
  min-width: 0;
}

.list-eyebrow {
  display: inline-block;
  margin-bottom: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(29, 78, 216, 0.08);
  color: @primary;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.list-header-main h1 {
  margin: 0 0 6px;
  color: @ink;
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
}

.list-tagline {
  margin: 0;
  max-width: 420px;
  color: @muted;
  font-size: 14px;
  line-height: 1.55;
}

.list-header-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.list-search {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  padding: 10px 16px;
  border: 1px solid @border;
  border-radius: 12px;
  background: @surface;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition: border-color 0.2s, box-shadow 0.2s;

  &:focus-within {
    border-color: rgba(29, 78, 216, 0.45);
    box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.12), 0 2px 8px rgba(15, 23, 42, 0.06);
  }

  .anticon {
    flex-shrink: 0;
    color: #94a3b8;
    font-size: 15px;
  }

  input {
    flex: 1;
    min-width: 0;
    border: none;
    outline: none;
    background: transparent;
    color: @ink;
    font-size: 14px;

    &::placeholder {
      color: #94a3b8;
    }
  }
}

.list-create-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(165deg, #2563eb 0%, @primary 45%, @primary-hover 100%);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(29, 78, 216, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  transition: transform 0.15s, box-shadow 0.15s;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(29, 78, 216, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  }

  &:active {
    transform: translateY(0);
  }
}

.list-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  padding: 4px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid @border;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  width: fit-content;
}

.list-tab {
  position: relative;
  padding: 9px 22px;
  border: none;
  border-radius: 11px;
  background: transparent;
  color: @muted;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;

  &:hover {
    color: #334155;
  }

  &.is-active {
    background: @surface;
    color: @primary;
    font-weight: 600;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
  }
}

.list-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 18px;
}

.list-card {
  position: relative;
  display: flex;
  gap: 16px;
  overflow: hidden;
  padding: 22px 22px 22px 20px;
  border: 1px solid @border;
  border-radius: 16px;
  background: @surface;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  transition: border-color 0.2s, box-shadow 0.25s, transform 0.2s;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: 3px;
    border-radius: 16px 0 0 16px;
    background: linear-gradient(180deg, #3b82f6, #1d4ed8);
    opacity: 0;
    transition: opacity 0.2s;
  }

  &:hover {
    border-color: rgba(59, 130, 246, 0.35);
    box-shadow: 0 12px 40px -12px rgba(15, 23, 42, 0.12), 0 4px 16px rgba(37, 99, 235, 0.08);
    transform: translateY(-2px);

    &::before {
      opacity: 1;
    }
  }
}

.list-card-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: linear-gradient(145deg, #f0f7ff 0%, #e0edff 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);

  .anticon {
    color: @primary;
    font-size: 22px;
  }
}

.list-card-body {
  flex: 1;
  min-width: 0;
}

.list-card-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;

  h3 {
    margin: 0;
    overflow: hidden;
    color: @ink;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.3;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.list-card-vis {
  flex-shrink: 0;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;

  &.is-public {
    background: #ecfdf5;
    color: #047857;
  }

  &.is-private {
    background: #fffbeb;
    color: #b45309;
  }
}

.list-card-desc {
  display: -webkit-box;
  margin: 0 0 10px;
  overflow: hidden;
  color: @muted;
  font-size: 13px;
  line-height: 1.55;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.list-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  margin-bottom: 10px;

  span {
    padding: 3px 9px;
    border-radius: 8px;
    background: #f1f5f9;
    color: #475569;
    font-size: 11px;
    font-weight: 500;
  }

  &.is-empty {
    visibility: hidden;
  }
}

.list-card-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
  color: #94a3b8;
  font-size: 12px;

  .anticon {
    margin-right: 4px;
    font-size: 12px;
    opacity: 0.85;
  }
}

.list-card-meta {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.list-card-pending {
  color: #b45309;
}

.list-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-top: 8px;
  padding: 72px 24px;
  border: 1px dashed @border;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.6);
  color: @muted;
  font-size: 14px;
}

@media (max-width: 768px) {
  .list-header {
    flex-direction: column;
    align-items: stretch;
  }

  .list-header-right {
    justify-content: stretch;
  }

  .list-search {
    flex: 1;
    min-width: 100%;
  }

  .list-grid {
    grid-template-columns: 1fr;
  }
}
/* stylelint-enable order/properties-order, declaration-block-single-line-max-declarations, value-no-vendor-prefix */
</style>

<!-- Modal 挂载到 document.body，须用非 scoped 样式 -->
<style lang="less">
/* stylelint-disable order/properties-order, declaration-block-single-line-max-declarations -- Ant Design Modal 覆盖样式 */
@kb-create-ink: #0c1222;
@kb-create-primary: #1d4ed8;
@kb-create-border: #e5e7eb;

.kb-create-modal-wrap {
  /* 遮罩略深，突出对话框层次 */
  &.ant-modal-wrap {
    backdrop-filter: blur(2px);
  }

  .ant-modal-mask {
    background-color: rgba(15, 23, 42, 0.48);
  }

  .ant-modal {
    padding-bottom: 0;
  }

  .ant-modal-content {
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.65);
    border-radius: 20px;
    box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.06), 0 32px 64px -16px rgba(15, 23, 42, 0.28),
      0 12px 24px -8px rgba(29, 78, 216, 0.12);
  }

  .ant-modal-header {
    padding: 16px 46px 12px 20px;
    background: #fafbfc;
    border-bottom: 1px solid #eef2f6;
  }

  .ant-modal-title {
    width: 100%;
    margin: 0;
    color: @kb-create-ink;
    font-size: 0;
    line-height: 0;
  }

  .kb-create-title {
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .kb-create-title-icon {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    border-radius: 12px;
    background: linear-gradient(145deg, #eff6ff, #dbeafe);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
    color: @kb-create-primary;
    font-size: 17px;
  }

  .kb-create-title-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    padding-top: 0;
  }

  .kb-create-title-line {
    display: block;
    color: @kb-create-ink;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.25;
  }

  .kb-create-title-sub {
    display: block;
    color: #64748b;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.45;
  }

  .ant-modal-close {
    top: 16px;
    right: 16px;
  }

  .ant-modal-close-x {
    display: flex;
    width: 32px;
    height: 32px;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    color: #64748b;
    font-size: 14px;
    line-height: 1;
    transition: background 0.15s, color 0.15s;
  }

  .ant-modal-close-x:hover {
    background: #e2e8f0;
    color: @kb-create-ink;
  }

  .ant-modal-body {
    padding: 0;
    background: #fff;
  }

  .kb-create-body {
    padding: 18px 24px 8px;
  }

  .kb-create-lead {
    margin: 0 0 16px;
    padding: 10px 14px;
    border: 1px solid #e8eef7;
    border-left: 3px solid @kb-create-primary;
    border-radius: 12px;
    background: linear-gradient(180deg, #f8fbff 0%, #f6f8fb 100%);
    color: #475569;
    font-size: 13px;
    line-height: 1.45;
  }

  .kb-create-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    padding: 14px 24px 16px;
    border-top: 1px solid #eef2f6;
    background: linear-gradient(180deg, #fafbfc, #f4f6f9);
  }

  .kb-create-footer .ant-btn {
    min-width: 92px;
    height: 36px;
    padding: 0 22px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 14px;
  }

  .kb-create-footer .ant-btn-default {
    border-color: #cbd5e1;
    color: #475569;
    background: #fff;
  }

  .kb-create-footer .ant-btn-default:hover {
    border-color: #94a3b8;
    color: @kb-create-ink;
  }

  .kb-create-footer .ant-btn-primary {
    border: none;
    background: linear-gradient(165deg, #2563eb, #1d4ed8);
    box-shadow: 0 2px 10px rgba(29, 78, 216, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  }

  .kb-create-footer .ant-btn-primary:hover {
    background: linear-gradient(165deg, #3b82f6, #1e40af);
    box-shadow: 0 6px 18px rgba(29, 78, 216, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  }
}
/* stylelint-enable order/properties-order, declaration-block-single-line-max-declarations */
</style>
