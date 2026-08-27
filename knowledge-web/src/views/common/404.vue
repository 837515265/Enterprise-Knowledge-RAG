<template>
  <a-result status="404" title="404" sub-title="抱歉，您访问的页面不存在。">
    <template #extra>
      <RouterLink :to="{ path: '/', replace: true }">
        <a-button type="primary"> 回到首页 </a-button>
      </RouterLink>
    </template>
  </a-result>
</template>
