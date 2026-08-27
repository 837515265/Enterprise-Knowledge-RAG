<template>
  <div class="example-list-container">
    <h1 class="text-[23px]">
      示例
      <span class="text-[12px] text-red-400">（仅开发环境显示）</span>
    </h1>
    <div class="columns">
      <div v-for="col in mainColumns" :key="col.path" class="column">
        <div class="column-title">{{ col.meta.title }}</div>
        <div class="card-list-wrap">
          <div v-for="item in col.children" :key="item.path" class="example-card" @click="goDemo(item.path)">
            <div class="card-title">{{ item.meta.title }}</div>
            <div class="card-desc">
              <a-icon type="arrow-right" class="arrow" />
              <span class="desc-text">点击跳转到{{ item.meta.title }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { layoutRoute } from "@/router/routes/routes"

const router = useRouter()

// 只取一级children中ldsk和demo
const mainColumns = ref(
  (layoutRoute.children ?? [])
    .filter((col: any) => ["/ldsk", "/demo"].includes(col.path) && Array.isArray(col.children))
    .map((col: any) => ({
      ...col,
      children: col.children || []
    }))
)

function goDemo(path: string) {
  router.push(path)
}
</script>

<style lang="less" scoped>
.example-list-container {
  padding: 24px;
  background: #fff;
  border-radius: 8px;
  transition: box-shadow 0.2s, transform 0.2s;
}

.columns {
  display: flex;
  gap: 32px;
  margin-top: 16px;
}

.column {
  flex: 1;
  min-width: 260px;
}

.column-title {
  padding-left: 2px;
  margin-bottom: 12px;
  font-size: 18px;
  font-weight: bold;
  color: #1a1a1a;
}

.card-list-wrap {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.example-card {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 10px 16px 12px;
  min-width: 0;
  height: 90px;
  background-color: var(--primary-color-100);
  border-radius: 10px;
  box-shadow: #e9e8e8 1.95px 1.95px 2.6px;
  transition: transform 0.2s ease-in-out;
  flex-direction: column;
  cursor: pointer;
}

.example-card:hover {
  box-shadow: #e9e8e8 1.95px 1.95px 2.6px;
  transform: translateY(-2px) scale(1.03);
}

.card-title {
  margin-bottom: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-color-500);
}

.card-desc {
  position: relative;
  display: flex;
  align-items: center;
  height: 20px;
  font-size: 13px;
  color: #666;
}

.card-desc .arrow {
  vertical-align: middle;
}

.desc-text {
  transform: translateX(-20px);
  transition: transform 0.2s;
  line-height: 16px;
}

.arrow {
  margin-right: 4px;
  font-size: 16px;
  color: var(--primary-color-500);
  opacity: 0;
  transition: opacity 0.2s, transform 0.2s;
  transform: translateX(-10px);
  vertical-align: middle;
}

.example-card:hover .arrow {
  opacity: 1;
  transform: translateX(0);
}

.example-card:hover .desc-text {
  transform: translateX(4px);
}
</style>
