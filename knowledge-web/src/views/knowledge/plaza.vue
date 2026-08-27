<template>
  <div class="kb-page">
    <div class="kb-page-inner">
      <div class="plaza-header">
        <div class="plaza-title-row">
          <h1>知识广场</h1>
          <div class="plaza-search">
            <a-icon type="search" />
            <input v-model="keyword" type="search" placeholder="搜索公开知识库…" @keydown.enter="onSearch" />
          </div>
        </div>
        <div class="plaza-tabs">
          <button type="button" class="plaza-tab is-active">全部</button>
        </div>
      </div>

      <div class="plaza-grid">
        <div v-for="item in filteredList" :key="item.id" class="plaza-card" @click="goDetail(item)">
          <div class="plaza-card-icon">
            <a-icon :type="getKnowledgeTypeIcon(item.type)" />
          </div>
          <div class="plaza-card-body">
            <div class="plaza-card-top">
              <h3>{{ item.name }}</h3>
              <span v-if="item.joined" class="plaza-badge">已加入</span>
            </div>
            <p class="plaza-card-desc">{{ item.description || "暂无描述" }}</p>
            <div class="plaza-card-footer">
              <span class="plaza-card-stat"> <a-icon type="file" /> {{ item.fileCount || 0 }} 个文件 </span>
              <span class="plaza-card-type">{{ typeLabel(item.type) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!loading && filteredList.length === 0" class="plaza-empty">
        <a-icon type="inbox" style="font-size: 40px; color: #cbd5e1" />
        <p>暂无公开知识库</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getPlazaList } from "@/api/knowledge"
import { getKnowledgeTypeIcon, getKnowledgeTypeLabel } from "./constants"

const router = useRouter()
const keyword = ref("")
const loading = ref(false)
const allList = ref<any[]>([])

const filteredList = computed(() => {
  if (!keyword.value) return allList.value
  const kw = keyword.value.toLowerCase()
  return allList.value.filter((item: any) => item.name?.toLowerCase().includes(kw))
})

onMounted(() => loadList())

async function loadList() {
  loading.value = true
  try {
    const res = await getPlazaList({ pageSize: 200 })
    allList.value = Array.isArray(res?.data) ? res.data : []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function onSearch() {
  /* 前端过滤 */
}

function typeLabel(type: string) {
  return getKnowledgeTypeLabel(type)
}

function goDetail(item: any) {
  router.push({ name: "KbDetail", params: { kbId: item.id } })
}
</script>

<style lang="less" scoped>
@primary: #2563eb;
@border: #e5e7eb;

.plaza-header {
  margin-bottom: 24px;
}

.plaza-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  gap: 16px;

  h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
  }
}

.plaza-search {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  min-width: 240px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 10px;
  transition: border-color 0.2s;
  gap: 8px;

  &:focus-within {
    border-color: @primary;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
  }

  .anticon {
    font-size: 14px;
    color: #94a3b8;
  }

  input {
    font-size: 14px;
    color: #334155;
    background: transparent;
    border: none;
    outline: none;
    flex: 1;
  }
}

.plaza-tabs {
  display: flex;
  gap: 6px;
}

.plaza-tab {
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
  background: #fff;
  border: 1px solid @border;
  border-radius: 8px;
  transition: all 0.15s;
  cursor: pointer;

  &.is-active {
    color: #fff;
    background: @primary;
    border-color: @primary;
  }
}

.plaza-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.plaza-card {
  display: flex;
  padding: 20px;
  background: #fff;
  border: 1px solid @border;
  border-radius: 14px;
  transition: all 0.2s;
  gap: 14px;
  cursor: pointer;

  &:hover {
    border-color: #93c5fd;
    box-shadow: 0 8px 24px rgba(37, 99, 235, 0.08);
    transform: translateY(-1px);
  }
}

.plaza-card-icon {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 44px;
  height: 44px;
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border-radius: 12px;
  flex-shrink: 0;

  .anticon {
    font-size: 20px;
    color: @primary;
  }
}

.plaza-card-body {
  flex: 1;
  min-width: 0;
}

.plaza-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;

  h3 {
    overflow: hidden;
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #0f172a;
  }
}

.plaza-badge {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #16a34a;
  background: #dcfce7;
  border-radius: 6px;
  flex-shrink: 0;
}

.plaza-card-desc {
  display: box;
  overflow: hidden;
  margin: 0 0 10px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.plaza-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.plaza-card-stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #94a3b8;

  .anticon {
    font-size: 12px;
  }
}

.plaza-card-type {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 6px;
}

.plaza-empty {
  display: flex;
  align-items: center;
  padding: 60px 20px;
  font-size: 14px;
  color: #94a3b8;
  flex-direction: column;
  gap: 12px;
}

@media (max-width: 768px) {
  .plaza-grid {
    grid-template-columns: 1fr;
  }

  .plaza-title-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .plaza-search {
    width: 100%;
    min-width: unset;
  }
}
</style>
