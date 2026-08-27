<template>
  <div class="file-manage">
    <div class="mb-3 flex items-center justify-between">
      <span class="font-medium">文件列表</span>
      <div>
        <a-button size="small" @click="onCreateFolder">
          <a-icon type="folder-add" />新建文件夹
        </a-button>
        <a-button type="primary" size="small" class="ml-2" @click="showUpload = true">
          <a-icon type="upload" />上传文件
        </a-button>
      </div>
    </div>

    <a-table
      :columns="columns"
      :data-source="fileList"
      :loading="loading"
      :pagination="false"
      row-key="id"
      size="small"
      :default-expand-all-rows="true"
    >
      <template #name="text, record">
        <a-icon :type="record.nodeType === 'folder' ? 'folder' : 'file'" class="mr-1" />
        <a v-if="record.nodeType === 'file'" @click="onClickFile(record)">{{ text }}</a>
        <span v-else>{{ text }}</span>
      </template>

      <template #parseStatus="text">
        <a-badge v-if="text === 'parsed'" status="success" text="已解析" />
        <a-badge v-else-if="text === 'parsing'" status="processing" text="解析中" />
        <a-badge v-else-if="text === 'failed'" status="error" text="解析失败" />
        <a-badge v-else status="default" text="未解析" />
      </template>

      <template #fileSize="text">
        <span v-if="text">{{ formatFileSize(text) }}</span>
        <span v-else class="text-gray-400">-</span>
      </template>

      <template #action="text, record">
        <template v-if="record.nodeType === 'folder'">
          <a @click="onCreateFolder(record.id)">新建子目录</a>
          <a-divider type="vertical" />
        </template>
        <template v-if="record.nodeType === 'file'">
          <a @click="onReparse(record)">重新解析</a>
          <a-divider type="vertical" />
        </template>
        <a-popconfirm title="确定删除？" @confirm="onDelete(record)">
          <a class="text-red-500">删除</a>
        </a-popconfirm>
      </template>
    </a-table>

    <!-- 上传弹窗 -->
    <a-modal v-model="showUpload" title="上传文件" :footer="null" destroy-on-close>
      <a-upload-dragger
        :multiple="true"
        :before-upload="beforeUpload"
        :custom-request="handleCustomUpload"
        accept=".pdf,.doc,.docx,.txt,.md,.xlsx"
      >
        <p class="ant-upload-drag-icon">
          <a-icon type="inbox" />
        </p>
        <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p class="ant-upload-hint">支持 PDF、Word、TXT、Markdown、Excel</p>
      </a-upload-dragger>
    </a-modal>

    <a-modal
      v-model="showCreateFolder"
      title="新建文件夹"
      ok-text="创建"
      cancel-text="取消"
      :confirm-loading="createFolderSubmitting"
      destroy-on-close
      @ok="submitCreateFolder"
      @cancel="resetCreateFolder"
    >
      <a-input
        v-model="folderName"
        placeholder="请输入文件夹名称"
        :max-length="64"
        allow-clear
        @pressEnter="submitCreateFolder"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { getFileTree, createFolder, deleteFile, reparseFile, uploadFile as uploadFileApi } from "@/api/knowledge"

const props = defineProps<{
  kbId: string | number
}>()

const emit = defineEmits(["select-file"])

const loading = ref(false)
const fileList = ref<any[]>([])
const showUpload = ref(false)
const showCreateFolder = ref(false)
const createFolderSubmitting = ref(false)
const folderName = ref("")
const folderParentId = ref<string | number | null>(null)

onMounted(() => {
  loadFiles()
})

async function loadFiles() {
  loading.value = true
  try {
    const res = await getFileTree(props.kbId)
    fileList.value = Array.isArray(res?.datas) ? res.datas : []
  } catch (e) {
    console.error("获取文件列表失败", e)
  } finally {
    loading.value = false
  }
}

const columns = [
  { title: "名称", dataIndex: "name", scopedSlots: { customRender: "name" } },
  { title: "大小", dataIndex: "fileSize", width: 100, scopedSlots: { customRender: "fileSize" } },
  { title: "解析状态", dataIndex: "parseStatus", width: 110, scopedSlots: { customRender: "parseStatus" } },
  { title: "操作", width: 140, scopedSlots: { customRender: "action" } }
]

function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + " B"
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB"
  return (bytes / 1024 / 1024).toFixed(1) + " MB"
}

function onClickFile(record: any) {
  emit("select-file", record)
}

/**
 * 打开新建文件夹弹窗。
 */
function onCreateFolder(parentId: string | number | null = null) {
  folderParentId.value = parentId
  showCreateFolder.value = true
}

/**
 * 提交新建文件夹请求并刷新文件列表。
 */
async function submitCreateFolder() {
  const name = folderName.value.trim()
  if (!name) {
    message.warning("请输入文件夹名称")
    return
  }

  createFolderSubmitting.value = true
  try {
    await createFolder(props.kbId, { name, parentId: folderParentId.value })
    message.success("创建成功")
    resetCreateFolder()
    loadFiles()
  } catch (e) {
    message.error("创建失败")
  } finally {
    createFolderSubmitting.value = false
  }
}

/**
 * 重置新建文件夹弹窗状态。
 */
function resetCreateFolder() {
  showCreateFolder.value = false
  folderName.value = ""
  folderParentId.value = null
}

function beforeUpload() {
  return true
}

async function handleCustomUpload(options: any) {
  const { file, onSuccess, onError } = options
  try {
    const formData = new FormData()
    formData.append("file", file)
    await uploadFileApi(props.kbId, formData)
    message.success(`${file.name} 上传成功`)
    onSuccess?.({}, file)
    loadFiles()
  } catch (e) {
    message.error(`${file.name} 上传失败`)
    onError?.(e)
  }
}

async function onReparse(record: any) {
  try {
    await reparseFile(props.kbId, record.id)
    message.success("已触发重新解析")
    loadFiles()
  } catch (e) {
    message.error("触发重解析失败")
  }
}

async function onDelete(record: any) {
  try {
    await deleteFile(props.kbId, record.id)
    message.success("删除成功")
    loadFiles()
  } catch (e) {
    message.error("删除失败")
  }
}

defineExpose({ loadFiles })
</script>

<style lang="less" scoped></style>
