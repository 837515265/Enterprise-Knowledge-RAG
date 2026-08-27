<template>
  <div
    :id="'tags-view-container'"
    class="tags-view-container"
    :class="{ 'tags-view-container--fixed': props.fixedWidth }"
  >
    <div class="tags-view-wrapper">
      <a-tabs
        :activeKey="$route.fullPath"
        type="editable-card"
        hide-add
        @change="onTabChange"
        @tabContextMenu="onTabContextMenu"
        @edit="onTabEdit"
      >
        <a-tab-pane v-for="tag in tags" :key="tag.fullPath" :closable="!tagsStore.isFixedTag(tag)">
          <template #tab>
            <div class="tags-view-item" :data-fullpath="tag.fullPath" @contextmenu.prevent="openMenu(tag, $event)">
              {{ tag.meta?.title || tag.path }}
            </div>
          </template>
        </a-tab-pane>
      </a-tabs>
      <ul v-if="menuVisible" :style="{ left: left + 'px', top: top + 'px', position: 'fixed' }" class="contextmenu">
        <li @click="handleMenuAction('refresh')"><a-icon type="reload" /> 刷新页面</li>
        <li v-if="!tagsStore.isFixedTag(selectedTag)" @click="handleMenuAction('close')">
          <a-icon type="close" /> 关闭当前
        </li>
        <li @click="handleMenuAction('closeOthers')"><a-icon type="minus-circle" /> 关闭其他</li>
        <li v-if="!tagsStore.isFirstTag(selectedTag)" @click="handleMenuAction('closeLeft')">
          <a-icon type="arrow-left" /> 关闭左侧
        </li>
        <li
          v-if="!tagsStore.isLastTag(selectedTag) && !tagsStore.isFixedTag(selectedTag)"
          @click="handleMenuAction('closeRight')"
        >
          <a-icon type="arrow-right" /> 关闭右侧
        </li>
        <li v-if="!tagsStore.isFixedTag(selectedTag)" @click="handleMenuAction('closeAll')">
          <a-icon type="close-circle" /> 全部关闭
        </li>
      </ul>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useTagsStore, TagView } from "@/store/modules/tags"
import { storeToRefs } from "pinia"
import { RouteConfig } from "vue-router"

// 组件props定义
const props = withDefaults(
  defineProps<{
    menus: RouteConfig[]
    fixedWidth: boolean
    fixedFirstRoute?: boolean
  }>(),
  {
    menus: () => [],
    fixedFirstRoute: false
  }
)

// 路由、store等初始化
const router = useRouter()
const route = useRoute()
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)

const [menuVisible, toggleMenuVisible] = useToggle()

const selectedTag = ref() as Ref<TagView>

// 右键菜单相关
const top = ref(0)
const left = ref(0)

// 初始化时设置 menus 和 fixedFirstRoute
onMounted(() => {
  tagsStore.setFixFirstTag(props.fixedFirstRoute ? props.menus : false)
})

// // 监听 props 变化时同步到 store
watch([() => props.menus, () => props.fixedFirstRoute], ([menus, fixed]) => {
  if (fixed) {
    tagsStore.setFixFirstTag(props.fixedFirstRoute ? menus : false)
  }
})

// 监听路由变化，自动添加标签
watch(
  () => route,
  () => {
    tagsStore.onChangeRoute(route)
  },
  { deep: true, immediate: true }
)

// 监听右键菜单显示/隐藏
watch(menuVisible, (value) => {
  if (value) {
    document.body.addEventListener("click", closeMenu)
  } else {
    document.body.removeEventListener("click", closeMenu)
  }
})

// 切换tab
function onTabChange(key: string) {
  const tag = tags.value.find((t) => t.fullPath === key)
  if (tag) {
    router.push({ path: tag.path, query: tag.query })
  }
}

// 右键菜单事件
function onTabContextMenu(e: MouseEvent) {
  // 通过事件委托获取tab的fullPath
  let target = e.target as HTMLElement | null
  while (target && !target.dataset.fullpath && target !== e.currentTarget) {
    target = target.parentNode as HTMLElement | null
  }
  const fullPath = target?.dataset?.fullpath
  if (fullPath) {
    const tag = tags.value.find((t) => t.fullPath === fullPath)
    if (tag) {
      openMenu(tag, e)
    }
  }
}

// 打开右键菜单
function openMenu(tag: TagView, e: MouseEvent) {
  left.value = e.clientX
  top.value = e.clientY
  toggleMenuVisible(true)
  selectedTag.value = tag
}

// 关闭右键菜单
function closeMenu() {
  toggleMenuVisible(false)
}

function handleMenuAction(action: string) {
  switch (action) {
    case "refresh":
      tagsStore.refreshTag(selectedTag.value, router)
      break
    case "close":
      tagsStore.closeTags("self", selectedTag.value!, router)
      break
    case "closeOthers":
      tagsStore.closeTags("others", selectedTag.value!, router)
      break
    case "closeLeft":
      tagsStore.closeTags("left", selectedTag.value!, router)
      break
    case "closeRight":
      tagsStore.closeTags("right", selectedTag.value!, router)
      break
    case "closeAll":
      tagsStore.closeTags("all", selectedTag.value!, router)
      break
  }
  closeMenu()
}

function onTabEdit(targetKey: string | number, action: "add" | "remove") {
  if (action === "remove") {
    const tag = tags.value.find((t) => t.fullPath === targetKey)
    if (tag) {
      tagsStore.closeTags("self", tag, router)
    }
  }
}
</script>

<style lang="less" scoped>
.tags-view-container {
  display: flex;
  justify-content: center;
  align-items: end;
  overflow-x: auto;
  padding-left: 20px;
  width: 100%;
  max-width: 100%;
  height: 48px;
  background: #fff;
  line-height: 1;
  border-bottom: 1px solid #dad9d98a;

  &&--fixed {
    .tags-view-wrapper {
      width: 1200px;
    }
  }

  .tags-view-wrapper {
    width: 100%;

    ::v-deep(.ant-tabs-tab-active .anticon-close) {
      color: var(--primary-color);

      &:hover {
        font-size: 14px;
        font-weight: bold;
        color: var(--primary-color);
      }
    }

    ::v-deep(.ant-tabs-bar) {
      margin: 0;
    }

    ::v-deep(.ant-tabs-nav .ant-tabs-tab) {
      padding-left: 0;

      .tags-view-item {
        display: inline-block;
        padding-left: 16px;
      }

      &:hover {
        @ligthen-color: color-mix(in srgb, var(--primary-color) 80%, white);

        color: @ligthen-color;

        .anticon-close {
          color: @ligthen-color;
        }
      }
    }
  }

  .contextmenu {
    position: fixed;
    z-index: 9999;
    padding: 5px 0;
    margin: 0;
    min-width: 104px;
    font-size: 13px;
    font-weight: 400;
    white-space: nowrap;
    color: #666;
    background: #fff;
    border: 1px solid #e5e6eb;
    border-radius: 4px;
    outline: 0;
    box-shadow: 0 2px 8px #00000026;
    transition: box-shadow 0.2s;
    list-style-type: none;

    li {
      display: flex;
      align-items: center;
      padding: 7px 8px;
      margin: 0;
      width: 100%;
      border-radius: 3px;
      transition: background 0.15s;
      cursor: pointer;

      & > .anticon {
        margin-right: 6px;
      }

      &:hover {
        color: var(--primary-color);
        background: #f2f3f5;
      }
    }
  }
}
</style>
