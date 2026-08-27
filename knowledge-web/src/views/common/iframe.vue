<template>
  <div class="page-container">
    <div v-if="url" class="full-content">
      <iframe class="full-iframe" :src="url"></iframe>
    </div>
    <div v-else>请配置路由meta-> url 参数！</div>
  </div>
</template>

<script>
export default {
  name: "Iframe",
  components: {},
  data() {
    return {
      url: ""
    }
  },
  created() {
    this.url = this.$route.meta.url
  },
  watch: {
    // 如果路由有变化，会再次执行该方法
    $route: function () {
      this.url = this.$route.meta.url
    }
  }
}
</script>

<style lang="less" scoped>
.page-container {
  overflow: auto;
  padding: 16px;
  background: white;
}

.full-content {
  margin: -10px;
  height: calc(100vh - 120px);
}

.full-iframe {
  width: 100%;
  height: 100%;
  border-style: none;
}

.ant-pro-basicLayout-children-content-wrap .ant-pro-basicLayout-children-content-wrap {
  height: 900px !important;
}
</style>
