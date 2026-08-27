<template>
  <basic-layout
    v-bind="settings"
    :menus="menus"
    :collapsed="collapsed"
    :mediaQuery="query"
    :openOnceKey="false"
    :isMobile="isMobile"
    :footer-render="false"
    :handleMediaQuery="handleMediaQuery"
    :handleCollapse="toggleCollapse"
  >
    <!--  菜单顶部header  -->
    <template #menuHeaderRender>
      <div class="flex size-full items-center px-[15px]">
        <img src="@/assets/img/logo-fold.jpg" class="" alt="" style="object-fit: contain" />
        <span
          v-show="!collapsed"
          class="ml-[15px] text-nowrap text-[18px] font-[600] text-white"
          style="font-family: Avenir, Arial, Helvetica, sans-serif"
        >
          {{ title }}
        </span>
      </div>
    </template>
    <!--  header左侧  -->
    <template #headerContentRender>
      <div>
        <a-tooltip title="清空所有缓存并刷新">
          <a-icon type="reload" style="font-size: 18px; cursor: pointer" @click="reload" />
        </a-tooltip>
      </div>
    </template>
    <!--  header右侧  -->
    <template #rightContentRender>
      <HeaderRightContent :top-menu="settings.layout === 'topmenu'" :is-mobile="isMobile" :theme="settings.theme" />
    </template>
    <SettingDrawer v-if="isDev" :settings="settings" @change="handleSettingChange"> </SettingDrawer>
    <transition name="fade-transform" mode="out-in">
      <keep-alive v-if="isKeepAlive">
        <router-view :key="$route.path" />
      </keep-alive>
      <router-view v-else :key="$route.path" />
    </transition>
  </basic-layout>
</template>

<script setup lang="ts">
import { CONTENT_WIDTH_TYPE } from "#/model/layout"
import { useLayoutStore } from "@/store/modules/layout"
import { useMenuStore } from "@/store/modules/menu"
import { storeToRefs } from "pinia"

const title = import.meta.env.VITE_APP_NAME

const layoutStore = useLayoutStore()
const menuStore = useMenuStore()

const { config: settings } = storeToRefs(layoutStore)
const { menus } = storeToRefs(menuStore)

const route = useRoute()
const isKeepAlive = computed(() => {
  return route.meta?.keepAlive !== false // 默认缓存
})

// 是否开发模式
const isDev: boolean = (import.meta.env.DEV as boolean) || import.meta.env.VUE_APP_PREVIEW === "true"
// 媒体查询
const query = ref({})
// 是否手机模式
const isMobile = ref(false)
// 菜单是否折叠
const [collapsed, toggleCollapse] = useToggle()

onMounted(() => {
  const userAgent = navigator.userAgent
  if (userAgent.indexOf("Edge") > -1) {
    nextTick(() => {
      toggleCollapse(!collapsed.value)
      setTimeout(() => {
        toggleCollapse(!collapsed.value)
      }, 16)
    })
  }
})

function handleMediaQuery(val: any) {
  query.value = val
  if (isMobile.value && !val["screen-xs"]) {
    isMobile.value = false
    return
  }
  if (!isMobile.value && val["screen-xs"]) {
    isMobile.value = true
    toggleCollapse(false)
    layoutStore.changeConfigItem("contentWidth", CONTENT_WIDTH_TYPE.Fluid)
    layoutStore.changeConfigItem("fixSiderbar", false)
  }
}

function handleSettingChange({ type, value }) {
  type && layoutStore.changeConfigItem(type, value)
  switch (type) {
    case "contentWidth":
      layoutStore.changeConfigItem(type, value)
      break
    case "layout":
      if (value === "sidemenu") {
        layoutStore.changeConfigItem("contentWidth", CONTENT_WIDTH_TYPE.Fluid)
        layoutStore.changeConfigItem("fixSiderbar", true)
      } else {
        layoutStore.changeConfigItem(type, value)
        layoutStore.changeConfigItem("fixSiderbar", false)
        layoutStore.changeConfigItem("contentWidth", CONTENT_WIDTH_TYPE.Fixed)
      }
      break
  }
}

// 清空缓存并刷新页面
function reload() {
  localStorage.clear()
  window.location.reload()
}
</script>

<style lang="less" scoped></style>
