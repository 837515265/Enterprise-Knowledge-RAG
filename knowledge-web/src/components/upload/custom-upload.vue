<template>
  <div>
    <a-upload
      v-bind="$attrs"
      :headers="{
        Authorization: `Bearer ${userStore.token}`,
        ...headers
      }"
      :file-list="fileList"
      name="file"
      :disabled="disabled"
      :action="action"
      :list-type="listType"
      :show-upload-list="showUploadList"
      :custom-request="customUpload"
      :remove="handleRemove"
      :class="[disabled && listType === 'picture-card' && limit !== 1 && 'custom-upload--disabled']"
      v-on="$listeners"
      @preview="customPreview"
    >
      <!-- 上传图片 -->
      <!-- listType = picture-card -->
      <template v-if="listType === 'picture-card'">
        <div
          v-if="singleImageMode && fileList[0]?.status === 'done' && fileList[0]?.url"
          class="upload-image-wrapper"
          style="position: relative; width: 100%; height: 100%"
          @click.stop
        >
          <img width="100%" height="100%" :src="fileList[0].url" style="object-fit: contain" alt="avatar" />
          <div class="upload-image-mask">
            <a-icon type="eye" class="mask-icon" title="预览" @click.stop="customPreview(fileList[0])" />
            <a-icon
              v-show="!disabled"
              type="delete"
              class="mask-icon"
              title="删除"
              @click.stop="handleRemove(fileList[0])"
            />
          </div>
        </div>
        <a-icon
          v-else-if="singleImageMode && fileList[0]?.status === 'uploading'"
          type="loading"
          class="text-[30px] text-[#999]"
        />
        <a-icon v-else type="plus" class="text-[30px] text-[#999]" />
      </template>
      <!-- listType = picture / text -->
      <a-button v-else-if="!disabled"> <a-icon type="upload" />点击上传</a-button>
    </a-upload>
    <!-- 上传提示放在外层 -->
    <div v-if="showUploadTip" class="ant-upload-hint">
      {{ uploadTipText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { getFileByFileId, uploadFile } from "@/api/common"
import { useUserStore } from "@/store/modules/user"
import type { FileListItem, FileResponseData } from "#/model/model"

/**
 * 上传组件参数，全部作为props暴露
 */
const props = withDefaults(
  defineProps<{
    /** v-model 绑定的文件列表 */
    value?: FileResponseData[]
    /** 点击预览时的打开方式，page-新页面打开/ modal-弹窗打开/ auto-图片使用弹窗，其他使用新页面打开 */
    previewType?: "page" | "modal" | "auto"
    /** 上传地址 */
    action?: string
    /** headers对象 */
    headers?: Recordable
    // text, picture 和 picture-card
    listType?: "text" | "picture" | "picture-card"
    /** 允许上传的文件类型（如 ['jpg', 'png']） */
    fileTypes?: string[]
    /** 单个文件最大体积（MB） */
    fileMaxSize?: number
    /** 最多上传文件数量 */
    limit?: number
    /** 是否显示文件列表 */
    showFileList?: boolean
    /** 是否禁用上传 */
    disabled?: boolean
    /** 上传按钮下方的提示 */
    uploadTip?: boolean | string
  }>(),
  {
    value: () => [],
    previewType: "auto",
    action: "/api-file/files/upload",
    headers: undefined,
    listType: "text",
    fileTypes: undefined,
    fileMaxSize: undefined,
    limit: undefined,
    showFileList: true,
    disabled: false,
    uploadTip: true
  }
)

const emit = defineEmits(["input"])

const userStore = useUserStore()

const fileList = ref<FileListItem[]>([])

// listType 为picture-card 且 limt =1 时，只展示单个图片
const singleImageMode = computed(() => {
  return props.limit === 1 && props.listType === "picture-card"
})

// 是否展示文件上传列表
const showUploadList = computed(() => {
  return !singleImageMode.value && props.showFileList
})

// 生成默认的上传提示
const defaultUploadTip = computed(() => {
  let tip = "只允许上传"
  if (props.fileTypes && props.fileTypes.length > 0) {
    tip += ` ${props.fileTypes.join("、")} 类型的文件`
  } else {
    tip += "任意类型的文件"
  }
  if (props.limit) {
    tip += `，最多上传 ${props.limit} 个文件`
  }
  if (props.fileMaxSize) {
    tip += `，单个文件最大为 ${props.fileMaxSize}MB`
  }
  return tip
})

// 控制上传提示的显示和内容
const showUploadTip = computed(() => {
  return !props.disabled && (props.uploadTip === true || typeof props.uploadTip === "string")
})
const uploadTipText = computed(() => {
  return typeof props.uploadTip === "string" ? props.uploadTip : defaultUploadTip.value
})

// 校验文件类型
function checkFileType(file: File) {
  if (!props.fileTypes || props.fileTypes.length === 0) {
    return true
  }
  const ext = file.name.split(".").pop()?.toLowerCase()
  return props.fileTypes.includes(ext || "")
}

// 校验文件大小
function checkFileSize(file: File) {
  if (!props.fileMaxSize) {
    return true
  }
  return file.size / 1024 / 1024 <= props.fileMaxSize
}

// 校验文件数量
function checkFileLimit() {
  if (!props.limit) {
    return true
  }
  return fileList.value.length < props.limit
}

async function customUpload({ file }) {
  // 校验文件类型
  if (!checkFileType(file)) {
    return message.error(
      `文件类型不支持${
        props.fileTypes && props.fileTypes.length > 0 ? `，只允许上传：${props.fileTypes.join("、")}` : ""
      }`
    )
  }
  // 校验文件大小
  if (!checkFileSize(file)) {
    return message.error(`文件大小超出限制${props.fileMaxSize ? `，单个文件最大为 ${props.fileMaxSize}MB` : ""}`)
  }
  // 校验文件数量
  if (!checkFileLimit()) {
    return message.error(`最多只能上传${props.limit}个文件`)
  }

  const uid = file.uid

  const fileItem = {
    uid: uid,
    name: file.name,
    status: "uploading",
    percent: 0 // 新增进度字段
  } as unknown as FileListItem

  fileList.value.push(fileItem)

  // 模拟进度
  let progress = 0
  const interval = setInterval(() => {
    progress += Math.floor(Math.random() * 10) + 5 // 每次增加5-15
    if (progress > 95) {
      progress = 95
    } // 上传完成前最多到95%
    fileItem.percent = progress
    fileList.value = [...fileList.value]
  }, 200)

  try {
    const res = await uploadFile(file)

    Object.assign(fileItem, {
      uid: uid,
      name: res.name,
      status: "uploading",
      responeseData: res
    })
  } catch {
    clearInterval(interval)
    fileItem.status = "error"
    fileList.value = [...fileList.value]
    return message.error("上传失败，请稍后重试！")
  }

  // 如果展示图片，则获取真正的文件路径
  if (["picture", "picture-card"].includes(props.listType)) {
    const path = await getFileByFileId(fileItem.responeseData.id)
    const url = resolveFileUrl(path, false)
    fileItem.url = url
    fileItem.responeseData.url = url
    fileItem.status = "done"
  } else {
    fileItem.url = fileItem.responeseData.url
    fileItem.status = "done"
  }

  clearInterval(interval)
  fileItem.percent = 100 // 上传完成
  fileList.value = [...fileList.value]
  emitFileList()
}

// 自定义上传
function customPreview(file: FileListItem) {
  // 判断 file.url 是否为图片格式
  const isImg = /\.(jpg|jpeg|png|gif|webp)$/i.test(file.url || "")
  // 文件预览打开类型
  const type = props.previewType === "auto" ? (isImg ? "modal" : "page") : props.previewType
  return previewFile(file.responeseData.id, type)
}

// 处理删除逻辑
function handleRemove(file: FileListItem) {
  // 删除 fileList 中对应的文件
  fileList.value = fileList.value.filter((item) => item.uid !== file.uid)
  // 如果有回调
  emitFileList()
}

watch(
  () => props.value,
  (list = []) => {
    fileList.value = list.map((item) => {
      return {
        uid: item.id,
        name: item.name,
        status: "done",
        url: item.url || "",
        responeseData: item
      }
    })
  },
  { immediate: true }
)

// 在 customUpload、handleRemove 这些地方，操作 fileList 后 emit
function emitFileList() {
  emit(
    "input",
    fileList.value.map((item) => item.responeseData)
  )
}
</script>

<style scoped lang="less">
.custom-upload--disabled {
  ::v-deep .ant-upload {
    display: none;
  }
}

.ant-upload-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}

.upload-image-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
}

.upload-image-mask {
  position: absolute;
  top: 0;
  left: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: hsla(0deg, 0%, 0%, 0.45);
  opacity: 0;
  transition: opacity 0.2s;
  gap: 16px;
}

.upload-image-wrapper:hover .upload-image-mask {
  opacity: 1;
}

.mask-icon {
  font-size: 16px;
  color: #fff;
  transition: color 0.2s;
  cursor: pointer;
}

.mask-icon:hover {
  color: #1890ff;
}
</style>
