<template>
  <div v-loading="loading" class="file-preview-container">
    <div v-if="!hideDownloadButton" class="preview-operation flex justify-between">
      <div class="ml-[10px] text-[20px] font-[800]">{{ fileName }}</div>
      <a-button type="primary" :loading="downloadLoading" icon="download" @click="downloadReport"> 下载文件 </a-button>
    </div>
    <div v-if="url" class="iframe-wrapper">
      <iframe ref="previewIframe" class="preview-iframe" :src="url" @load="onIframeLoad" />
    </div>
  </div>
</template>

<script>
import { downLoadByFileId } from "@/api/common"
import { getPreviewUrlByFileId } from "@/utils/logic/file"

export default {
  props: {
    fileId: {
      type: String,
      default: ""
    },
    hideDownloadButton: {
      type: Boolean,
      default: false
    },
    highlightBlockIds: {
      type: Array,
      default: () => []
    },
    highlightPage: {
      type: Number,
      default: null
    }
  },
  data() {
    return {
      url: "",
      fileName: "",
      loading: false,
      downloadLoading: false,
      pdfNavSeq: 0,
      lastPdfNavigatedPage: null
    }
  },
  async mounted() {
    this.loading = true
    try {
      const { name, url } = await getPreviewUrlByFileId(this.fileId)
      this.url = this.withPdfPageHash(url)
      this.fileName = name || "文件预览"
    } catch (e) {
      console.error(e)
      this.$message.warning("文件预览加载失败")
    } finally {
      this.loading = false
    }
  },
  watch: {
    highlightBlockIds() {
      this.highlightPreviewBlocks()
    },
    highlightPage() {
      this.updatePdfPageHash()
    }
  },
  methods: {
    onIframeLoad() {
      this.highlightPreviewBlocks()
    },
    highlightPreviewBlocks() {
      const blockIds = (this.highlightBlockIds || []).map((id) => String(id).trim()).filter(Boolean)
      const iframe = this.$refs.previewIframe
      if (!iframe || !blockIds.length) {
        return
      }

      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document
        if (!doc) {
          this.postHighlightMessage(blockIds)
          return
        }

        doc.querySelectorAll(".kb-preview-block-highlight").forEach((node) => {
          node.classList.remove("kb-preview-block-highlight")
        })

        this.ensureHighlightStyle(doc)
        const matchedNodes = blockIds.flatMap((id) => Array.from(doc.querySelectorAll(this.buildBlockSelector(id))))
        matchedNodes.forEach((node) => node.classList.add("kb-preview-block-highlight"))
        if (matchedNodes[0]) {
          matchedNodes[0].scrollIntoView({ behavior: "smooth", block: "center" })
        }
      } catch (e) {
        this.postHighlightMessage(blockIds)
      }
    },
    updatePdfPageHash() {
      const page = Number(this.highlightPage)
      if (this.lastPdfNavigatedPage === page && this.getPdfHashPage(this.url) === page) {
        return
      }

      const nextUrl = this.withPdfPageHash(this.url, true)
      if (nextUrl && nextUrl !== this.url) {
        this.lastPdfNavigatedPage = page
        this.url = nextUrl
        this.$nextTick(() => {
          const iframe = this.$refs.previewIframe
          if (iframe) {
            iframe.setAttribute("src", nextUrl)
          }
        })
      }
    },
    withPdfPageHash(url, forcePdfNavigation = false) {
      const page = Number(this.highlightPage)
      if (!url || !Number.isFinite(page) || page <= 0 || !this.isPdfUrl(url)) {
        return url
      }
      let [baseUrl] = url.split("#")
      if (forcePdfNavigation) {
        this.pdfNavSeq += 1
        baseUrl = this.withQueryParam(baseUrl, "_kb_pdf_nav", `${Date.now()}_${this.pdfNavSeq}`)
      }
      return baseUrl + `#page=${page}`
    },
    getPdfHashPage(url) {
      const match = String(url || "").match(/#page=(\d+)/i)
      return match ? Number(match[1]) : null
    },
    isPdfUrl(url) {
      return /\.pdf(?:[?#]|$)/i.test(url)
    },
    withQueryParam(url, key, value) {
      const [base, query = ""] = url.split("?")
      const params = new URLSearchParams(query)
      params.set(key, value)
      return `${base}?${params.toString()}`
    },
    postHighlightMessage(blockIds) {
      const iframe = this.$refs.previewIframe
      iframe?.contentWindow?.postMessage(
        {
          type: "KB_PREVIEW_HIGHLIGHT_BLOCKS",
          blockIds
        },
        "*"
      )
    },
    buildBlockSelector(blockId) {
      const escaped = this.escapeCss(blockId)
      return [`#${escaped}`, `[data-block-id="${blockId}"]`, `[data-block-ids*="${blockId}"]`].join(",")
    },
    escapeCss(value) {
      if (window.CSS?.escape) {
        return window.CSS.escape(value)
      }
      return value.replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1")
    },
    ensureHighlightStyle(doc) {
      if (doc.getElementById("kb-preview-block-highlight-style")) {
        return
      }
      const style = doc.createElement("style")
      style.id = "kb-preview-block-highlight-style"
      style.textContent = `
        .kb-preview-block-highlight {
          background: rgba(37, 99, 235, 0.14) !important;
          outline: 2px solid rgba(37, 99, 235, 0.55) !important;
          outline-offset: 2px !important;
          border-radius: 4px !important;
          transition: background 0.18s ease, outline-color 0.18s ease;
        }
      `
      doc.head?.appendChild(style)
    },
    async downloadReport() {
      this.downloadLoading = true
      try {
        const res = await downLoadByFileId(this.fileId)
        if (res.data.type) {
          const url = window.URL.createObjectURL(new Blob([res.data]))
          const link = document.createElement("a")
          link.href = url
          // 获取文件名
          const contentDisposition = res.headers["content-disposition"]
          let fileName = this.fileName || "unknown"
          const utf8Match = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)
          const plainMatch = contentDisposition?.match(/filename="?([^";]+)"?/i)
          if (utf8Match?.[1] || plainMatch?.[1]) {
            fileName = decodeURIComponent(utf8Match?.[1] || plainMatch?.[1])
          }
          link.setAttribute("download", fileName)
          document.body.appendChild(link)
          link.click()
          link.remove()
          window.URL.revokeObjectURL(url)
        } else {
          this.$message.warning(res.data.msg)
        }
      } catch (e) {
        this.$message.warning("下载失败，请稍候尝试")
      } finally {
        this.downloadLoading = false
      }
    }
  }
}
</script>

<style scoped lang="less">
.file-preview-container {
  display: flex;
  height: 100%;
  min-height: 400px;
  background: #fff;
  border-radius: 12px;
  flex-direction: column;

  .preview-operation {
    padding: 10px;
    box-shadow: 0 2px 6px hsla(0deg, 0%, 87%, 0.08);
  }

  .iframe-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 10px;
    min-height: 0;
    flex: 1;

    .preview-iframe {
      width: 100%;
      height: 100%;
      background: #f8f9fa;
      border: none !important;
    }
  }
}
</style>
