<template>
  <div class="kb-page">
    <div class="kb-page-inner">
      <!-- 页头 -->
      <div class="kb-page-head">
        <div>
          <h1 class="kb-page-title">知识库工作台</h1>
          <p class="kb-page-desc">总览指标、待办事项与快捷入口</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <router-link to="/knowledge/list" class="kb-btn-sm primary" style="text-decoration: none">创建知识库</router-link>
          <router-link to="/knowledge/ask-ai" class="kb-btn-sm" style="text-decoration: none">去问 AI</router-link>
        </div>
      </div>

      <!-- 指标卡片 -->
      <section class="wb-metrics">
        <div class="wb-metric">
          <strong>{{ stats.myKbCount }}</strong>
          <span>我的知识库</span>
          <small>公开库 {{ stats.publicCount }} 个</small>
        </div>
        <div class="wb-metric">
          <strong>{{ stats.pendingAudit }}</strong>
          <span>待审核事项</span>
          <small>文件 {{ stats.pendingFile }} · 问答 {{ stats.pendingQa }}</small>
        </div>
        <div class="wb-metric">
          <strong>{{ stats.parseFailed }}</strong>
          <span>解析失败</span>
          <small>需要人工处理</small>
        </div>
        <div class="wb-metric">
          <strong>{{ stats.todayUpload }}</strong>
          <span>今日上传</span>
          <small>新增 {{ stats.todayChunks }} 个 chunk</small>
        </div>
      </section>

      <!-- 两栏：待办 + 快捷入口 -->
      <section class="wb-grid">
        <div class="wb-panel">
          <div class="wb-panel-head">
            <h3>待办事项</h3>
            <router-link to="/knowledge/list">查看全部</router-link>
          </div>
          <div class="wb-list">
            <div v-if="todos.length === 0" class="kb-empty" style="padding: 24px">暂无待办事项</div>
            <div v-for="(item, i) in todos" :key="i" class="wb-item" @click="goDetail(item)">
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </div>
          </div>
        </div>

        <div class="wb-panel">
          <div class="wb-panel-head">
            <h3>快捷入口</h3>
          </div>
          <div class="wb-actions">
            <router-link to="/knowledge/list" class="wb-action">我的知识库</router-link>
            <router-link to="/knowledge/plaza" class="wb-action">知识广场</router-link>
            <router-link to="/knowledge/ask-ai" class="wb-action">问 AI</router-link>
            <router-link to="/knowledge/search-files" class="wb-action">搜文件</router-link>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getKnowledgeBaseList } from "@/api/knowledge"

const router = useRouter()

const stats = reactive({
  myKbCount: 0,
  publicCount: 0,
  pendingAudit: 0,
  pendingFile: 0,
  pendingQa: 0,
  parseFailed: 0,
  todayUpload: 0,
  todayChunks: 0
})

const todos = ref<any[]>([])

onMounted(async () => {
  try {
    const res = await getKnowledgeBaseList({ pageSize: 100 })
    const list = Array.isArray(res?.data) ? res.data : []
    stats.myKbCount = list.length
    stats.publicCount = list.filter((k: any) => k.visibility === "public").length
  } catch (e) {
    console.error(e)
  }
})

function goDetail(item: any) {
  if (item.kbId) {
    router.push({ name: "KbDetail", params: { kbId: item.kbId } })
  }
}
</script>

<style lang="less" scoped>
@border: #e5e7eb;
@primary: #2563eb;

.wb-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}

.wb-metric {
  padding: 18px 18px 16px;
  border: 1px solid @border;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);

  strong {
    display: block;
    margin-bottom: 6px;
    font-size: 28px;
    line-height: 1;
    color: #0f172a;
  }
  span {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #334155;
  }
  small {
    display: block;
    margin-top: 6px;
    font-size: 12px;
    color: #64748b;
  }
}

.wb-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.9fr);
  gap: 16px;
}

.wb-panel {
  border: 1px solid @border;
  border-radius: 16px;
  background: #fff;
  padding: 16px;
}

.wb-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;

  h3 { margin: 0; font-size: 16px; }
  a { color: @primary; font-weight: 600; font-size: 13px; text-decoration: none; }
}

.wb-list {
  display: grid;
  gap: 10px;
}

.wb-item {
  display: block;
  padding: 12px 14px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  transition: border-color 0.12s;

  &:hover { border-color: #93c5fd; }

  strong { display: block; margin-bottom: 6px; font-size: 14px; color: #0f172a; }
  span { font-size: 12px; color: #64748b; }
}

.wb-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.wb-action {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 76px;
  padding: 12px;
  border-radius: 12px;
  border: 1px dashed #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.12s;

  &:hover { background: #dbeafe; border-color: @primary; }
}

@media (max-width: 900px) {
  .wb-metrics, .wb-grid { grid-template-columns: 1fr; }
}
</style>
