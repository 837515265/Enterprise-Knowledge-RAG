<template>
  <div></div>
</template>
<script setup lang="ts">
const route = useRoute()
const router = useRouter()

const { query } = route
// 还原原始路径
const realPath = route.params.path as string
router.replace({ path: `/${realPath}`, query })
</script>
