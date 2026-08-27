<template>
  <a-modal
    v-model="visible"
    title="修改密码"
    :confirm-loading="confirmLoading"
    :footer="null"
    destroyOnClose
    @ok="handleSubmit"
    @cancel="handleCancel"
  >
    <a-form-model ref="form" :model="model" :rules="rules" @submit.prevent="handleSubmit">
      <a-form-model-item label="用户账号" :labelCol="labelCol" :wrapperCol="wrapperCol" prop="userName" :hidden="true">
        <a-input v-model="model.userName" placeholder="请输入用户账号" :readOnly="true" />
      </a-form-model-item>
      <a-form-model-item label="新密码" :labelCol="labelCol" :wrapperCol="wrapperCol" prop="newPassword" hasFeedback>
        <a-input-password
          v-model="model.newPassword"
          type="password"
          :visibility-toggle="true"
          placeholder="请输入新密码"
        />
      </a-form-model-item>
      <a-form-model-item
        label="确认密码"
        :labelCol="labelCol"
        :wrapperCol="wrapperCol"
        prop="confirmPassword"
        hasFeedback
      >
        <a-input-password
          v-model="model.confirmPassword"
          type="password"
          :visibility-toggle="true"
          placeholder="请再次输入新密码"
          @blur="handleConfirmBlur"
        />
      </a-form-model-item>
      <a-form-model-item :wrapperCol="{ span: 24 }" style="text-align: center">
        <a-button htmlType="submit" type="primary" :loading="confirmLoading">提交</a-button>
      </a-form-model-item>
    </a-form-model>
  </a-modal>
</template>

<script setup lang="ts">
import { changePassword } from "@/api/common-user"
import { useUserStore } from "@/store/modules/user"

const userStore = useUserStore()

const visible = ref(false)
const confirmLoading = ref(false)
const confirmDirty = ref(false)
const model = ref({
  userName: "",
  newPassword: "",
  confirmPassword: ""
})
const form = ref<any>(null)
const labelCol = { xs: { span: 24 }, sm: { span: 8 } }
const wrapperCol = { xs: { span: 24 }, sm: { span: 15 } }

const rules = {
  newPassword: [{ required: true, message: "请输入登陆密码!" }, { validator: validatePasswordSuit }],
  confirmPassword: [{ required: true, message: "请重新输入登陆密码!" }, { validator: compareToFirstPassword }]
}

// 密码复杂度校验
function validatePasswordSuit(rule: any, value: any, callback: any) {
  if (!value) {
    callback()
    return
  }
  if (value.length < 8 || !/[A-Za-z]/.test(value) || !/[0-9]/.test(value) || !/[^A-Za-z0-9]/.test(value)) {
    callback(new Error("密码长度不低于八位，必须为数字、字母、特殊字符的组合"))
    return
  }
  callback()
}

// 两次密码一致性校验
function compareToFirstPassword(rule: any, value: any, callback: any) {
  if (value !== model.value.newPassword) {
    callback(new Error("两次输入的密码不一样！"))
  } else {
    callback()
  }
}

function show(username: string) {
  if (form.value) {
    form.value.resetFields()
  }
  visible.value = true
  model.value.userName = username
  setTimeout(() => {
    if (form.value) {
      model.value.userName = username
    }
  }, 0)
}

function close() {
  visible.value = false
}

function handleSubmit() {
  if (!form.value) {
    return
  }
  form.value.validate((valid: boolean) => {
    if (valid) {
      confirmLoading.value = true
      changePassword(model.value)
        .then((res: any) => {
          if (res.resp_code === 0) {
            message.success({
              content: "修改成功，请重新登录系统!"
            })
            userStore.logoutAction()
          } else {
            message.error(res.resp_msg || "修改失败，请稍候重新尝试！")
          }
        })
        .finally(() => {
          confirmLoading.value = false
        })
    }
  })
}

function handleCancel() {
  close()
}

function handleConfirmBlur(e: any) {
  const value = e.target.value
  confirmDirty.value = confirmDirty.value || !!value
}

defineExpose({
  show,
  close
})
</script>

<style lang="less" scoped>
#tips span:not(:last-child) {
  float: left;
  margin-right: 2px;
  width: 30px;
  height: 20px;
  font-size: 15px;
  text-align: center;
  border: 1px solid transparent;
  line-height: 20px;
}

.flexCenter,
#tips /deep/.ant-form-item-children {
  display: flex;
  align-items: center;
}

.left5 {
  margin-left: 5px;
}

.colorRed {
  background-color: red;
}

.colorOrange {
  background-color: orange;
}

.colorGreen {
  background-color: #54ec51;
}

.colorSafe {
  background-color: #52c41a;
}

.colorInit {
  background: #eee;
}
</style>
