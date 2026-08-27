<template>
  <div class="welcome-container">
    <div class="welcome-header">
      <img v-if="avatar" :src="avatar" class="avatar" alt="" />
      <div>
        <div class="welcome-title">欢迎回来，{{ name }}</div>
        <div class="welcome-info">
          <template v-if="userInfo && userInfo.roles && userInfo.roles.length">
            <div class="role-tag-list">
              <a-tag v-for="role in userInfo.roles" :key="role.roleId" color="blue" style="margin-bottom: 6px">
                {{ role.name }}
              </a-tag>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { storeToRefs } from "pinia"
import { useUserStore } from "@/store/modules/user"

const userStore = useUserStore()
const { name, avatar, userInfo } = storeToRefs(userStore)
</script>

<style scoped>
.welcome-container {
  padding: 24px;
  margin-bottom: 24px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px hsla(0deg, 0%, 0%, 0.05);
}

.welcome-header {
  display: flex;
  align-items: center;
}

.avatar {
  margin-right: 16px;
  width: 64px;
  height: 64px;
  background: #f5f5f5;
  border-radius: 50%;
  object-fit: cover;
}

.welcome-title {
  margin-bottom: 8px;
  font-size: 20px;
  font-weight: bold;
}

.welcome-info {
  margin-top: 8px;
}

.role-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 8px;
  margin-top: 4px;
}
</style>
