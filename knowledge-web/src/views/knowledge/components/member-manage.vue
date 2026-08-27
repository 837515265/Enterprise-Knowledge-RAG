<template>
  <div class="member-manage">
    <div class="member-hero">
      <div>
        <div class="member-hero__eyebrow">Knowledge Access</div>
        <div class="member-hero__title">成员权限</div>
        <div class="member-hero__desc">从用户中心选择用户、部门或角色，统一授予知识库访问权限。</div>
      </div>
      <a-button type="primary" class="member-hero__button" @click="openAddModal">
        <a-icon type="usergroup-add" />添加成员
      </a-button>
    </div>

    <div class="member-summary">
      <div v-for="item in summaryCards" :key="item.type" class="member-summary__item">
        <span class="member-summary__icon" :class="`member-summary__icon--${item.type}`">
          <a-icon :type="item.icon" />
        </span>
        <div>
          <div class="member-summary__num">{{ item.count }}</div>
          <div class="member-summary__label">{{ item.label }}</div>
        </div>
      </div>
    </div>

    <a-alert
      class="member-tip"
      type="info"
      show-icon
      message="成员来源于用户中心，知识库仅保存授权对象 ID 和权限级别。"
    />

    <a-table :columns="columns" :data-source="viewMemberList" :loading="loading" :pagination="false" row-key="id">
      <template #target="text, record">
        <div class="member-target">
          <span class="member-target__avatar" :class="`member-target__avatar--${record.ruleType}`">
            <a-icon v-if="record.ruleType !== 'user'" :type="getRuleMeta(record.ruleType).icon" />
            <span v-else>{{ getInitial(record.displayName) }}</span>
          </span>
          <div class="member-target__content">
            <div class="member-target__name">{{ record.displayName }}</div>
            <div class="member-target__meta">
              <a-tag :color="getRuleMeta(record.ruleType).color">{{ getRuleMeta(record.ruleType).label }}</a-tag>
            </div>
          </div>
        </div>
      </template>
      <template #grantRole="text">
        <a-tag :color="getRoleMeta(text).color">{{ getRoleMeta(text).label }}</a-tag>
      </template>
      <template #createTime="text">
        <span class="member-time">{{ text || "-" }}</span>
      </template>
      <template #action="text, record">
        <span v-if="record.locked" class="member-locked">不可更改</span>
        <a-popconfirm v-else title="确定移除？" @confirm="onRemove(record)">
          <a class="member-remove">移除</a>
        </a-popconfirm>
      </template>
    </a-table>

    <a-empty
      v-if="!loading && viewMemberList.length === 0"
      class="member-empty"
      description="还没有成员权限，点击右上角添加成员"
    />

    <a-modal
      v-model="showAdd"
      title="添加成员权限"
      width="640px"
      :confirm-loading="addLoading"
      @ok="onAddSubmit"
      @cancel="resetAddForm"
    >
      <div class="member-add">
        <a-radio-group
          v-model="addForm.ruleType"
          button-style="solid"
          class="member-type-switch"
          @change="onRuleTypeChange"
        >
          <a-radio-button value="user"><a-icon type="user" /> 用户</a-radio-button>
          <a-radio-button value="dept"><a-icon type="apartment" /> 部门</a-radio-button>
          <a-radio-button value="role"><a-icon type="team" /> 角色</a-radio-button>
        </a-radio-group>

        <a-form-item :label="`选择${getRuleMeta(addForm.ruleType).label}`" class="member-add__form-item">
          <a-tree-select
            v-if="addForm.ruleType === 'dept'"
            v-model="deptSelectedIds"
            show-search
            tree-checkable
            allow-clear
            class="member-target-select"
            dropdown-class-name="member-target-dropdown"
            placeholder="请选择部门"
            :tree-data="deptTreeData"
            :loading="deptTreeLoading"
            :show-checked-strategy="SHOW_PARENT"
            tree-node-filter-prop="title"
            :load-data="loadDeptChildren"
            :get-popup-container="getMemberPopupContainer"
            @focus="ensureDeptTree"
          />
          <a-select
            v-else
            v-model="addForm.targetId"
            show-search
            allow-clear
            :filter-option="false"
            :placeholder="`请输入${getRuleMeta(addForm.ruleType).label}名称搜索`"
            :loading="memberSearchLoading"
            class="member-target-select"
            dropdown-class-name="member-target-dropdown"
            option-label-prop="title"
            :get-popup-container="getMemberPopupContainer"
            @search="onSearchMember"
            @focus="ensureCandidateOptions"
            @change="onCandidateChange"
          >
            <a-select-option v-for="option in candidateOptions" :key="option.id" :value="option.id" :title="option.name">
              <div class="member-option">
                <span class="member-option__name">{{ option.name }}</span>
                <span class="member-option__sub">{{ option.subTitle }}</span>
              </div>
            </a-select-option>
          </a-select>
        </a-form-item>

        <div v-if="addForm.ruleType === 'dept' && selectedDeptCandidates.length" class="member-selected member-selected--multi">
          <a-icon type="check-circle" />
          <span>已选择：</span>
          <a-tag v-for="dept in selectedDeptCandidates" :key="dept.id" color="blue">{{ dept.name }}</a-tag>
        </div>

        <div v-else-if="selectedCandidate" class="member-selected">
          <a-icon type="check-circle" />
          已选择：{{ selectedCandidate.name }}
          <span v-if="selectedCandidate.subTitle">（{{ selectedCandidate.subTitle }}）</span>
        </div>

        <a-form-item label="授予权限" class="member-add__form-item">
          <a-radio-group v-model="addForm.grantRole" class="member-role-group" :disabled="isCreatorCandidate">
            <a-radio-button v-for="role in grantRoleOptions" :key="role.value" :value="role.value">
              {{ role.label }}
            </a-radio-button>
          </a-radio-group>
        </a-form-item>

        <div class="member-role-desc">
          <a-icon type="safety-certificate" />
          {{ getRoleMeta(addForm.grantRole).desc }}
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import {
  getDeptTree,
  getDeptsByIds,
  getRoleById,
  getUsersByIds,
  searchRoleMembers,
  searchUserMembers
} from "@/api/common-user"
import { getKbMembers, addKbMember, removeKbMember } from "@/api/knowledge"
import { TreeSelect } from "ant-design-vue"

const props = defineProps<{
  kbId: string | number
  kbInfo?: Record<string, any> | null
}>()

type MemberRuleType = "user" | "dept" | "role"

type CandidateOption = {
  id: string
  name: string
  subTitle: string
  raw: Record<string, any>
}

const loading = ref(false)
const memberList = ref<any[]>([])
const displayNameMap = ref<Record<string, string>>({})

onMounted(() => loadMembers())

/**
 * 加载知识库成员，并从用户中心补齐展示名称。
 */
async function loadMembers() {
  loading.value = true
  try {
    const res = await getKbMembers(props.kbId)
    memberList.value = Array.isArray(res?.datas) ? res.datas : []
    await enrichMemberNames()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const columns = [
  { title: "成员", dataIndex: "targetId", scopedSlots: { customRender: "target" } },
  { title: "角色", dataIndex: "grantRole", width: 100, scopedSlots: { customRender: "grantRole" } },
  { title: "添加时间", dataIndex: "createTime", width: 180, scopedSlots: { customRender: "createTime" } },
  { title: "操作", width: 80, scopedSlots: { customRender: "action" } }
]

const showAdd = ref(false)
const addLoading = ref(false)
const memberSearchLoading = ref(false)
const deptTreeLoading = ref(false)
const deptLoadingNodeIds = ref<Record<string, boolean>>({})
const candidateOptions = ref<CandidateOption[]>([])
const deptTreeData = ref<any[]>([])
const deptOptionMap = ref<Record<string, CandidateOption>>({})
const deptSelectedIds = ref<string[]>([])
const addForm = reactive<{ ruleType: MemberRuleType; targetId: string; grantRole: string }>({
  ruleType: "user",
  targetId: "",
  grantRole: "readonly"
})
let searchTimer: ReturnType<typeof setTimeout> | null = null
const SHOW_PARENT = TreeSelect.SHOW_PARENT

const ruleTypeMeta = {
  user: { label: "用户", color: "blue", icon: "user" },
  dept: { label: "部门", color: "green", icon: "apartment" },
  role: { label: "角色", color: "orange", icon: "team" }
}

const grantRoleOptions = [
  { value: "admin", label: "管理员", color: "red", desc: "可管理知识库配置、成员、文件与解析任务。" },
  { value: "reviewer", label: "审核员", color: "orange", desc: "可查看内容并参与审核类操作。" },
  { value: "editor", label: "编辑", color: "blue", desc: "可维护知识库文件与内容。" },
  { value: "readonly", label: "只读", color: "default", desc: "仅可查看和检索知识库内容。" }
]

const viewMemberList = computed(() => {
  const list = memberList.value.map((item) => ({
    ...item,
    displayName: displayNameMap.value[getMemberKey(item.ruleType, item.targetId)] || item.targetId || "-"
  }))
  if (props.kbInfo?.createName) {
    const hasCreator = list.some(
      (item) => item.ruleType === "user" && item.displayName === props.kbInfo?.createName && item.grantRole === "admin"
    )
    if (!hasCreator) {
      list.unshift({
        id: `creator-${props.kbInfo.createName}`,
        ruleType: "user",
        targetId: "creator",
        grantRole: "admin",
        displayName: props.kbInfo.createName,
        createTime: props.kbInfo.createTime,
        locked: true
      })
    }
  }
  return list
})

const summaryCards = computed(() => {
  return [
    { type: "user", label: "用户", icon: "user", count: countByRuleType("user") },
    { type: "dept", label: "部门", icon: "apartment", count: countByRuleType("dept") },
    { type: "role", label: "角色", icon: "team", count: countByRuleType("role") }
  ]
})

const selectedCandidate = computed(() => {
  return candidateOptions.value.find((item) => item.id === addForm.targetId)
})
const selectedDeptCandidates = computed(() => {
  return deptSelectedIds.value.map((id) => deptOptionMap.value[id]).filter(Boolean)
})
const isCreatorCandidate = computed(() => {
  return addForm.ruleType === "user" && selectedCandidate.value?.name && selectedCandidate.value.name === props.kbInfo?.createName
})

watch(isCreatorCandidate, (isCreator) => {
  if (isCreator) {
    addForm.grantRole = "admin"
  }
})

/**
 * 打开添加成员弹窗，并预加载当前类型候选项。
 */
function openAddModal() {
  showAdd.value = true
  ensureCandidateOptions()
}

/**
 * 切换授权对象类型后清空旧选择，避免把用户 ID 当成部门 ID 使用。
 */
function onRuleTypeChange() {
  addForm.targetId = ""
  deptSelectedIds.value = []
  candidateOptions.value = []
  ensureCandidateOptions()
}

/**
 * 远程搜索用户中心候选对象。
 */
function onSearchMember(keyword: string) {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
  searchTimer = setTimeout(() => {
    searchCandidates(keyword)
  }, 300)
}

/**
 * 保证下拉打开时有一组默认候选项。
 */
function ensureCandidateOptions() {
  if (addForm.ruleType === "dept") {
    ensureDeptTree()
  } else if (!candidateOptions.value.length) {
    searchCandidates("")
  }
}

/**
 * 候选项变更时仅保留 ID，展示信息通过候选列表和成员列表动态补齐。
 */
function onCandidateChange(value: string) {
  addForm.targetId = value || ""
  if (isCreatorCandidate.value) {
    addForm.grantRole = "admin"
  }
}

async function onAddSubmit() {
  const targetIds = addForm.ruleType === "dept" ? deptSelectedIds.value : addForm.targetId ? [addForm.targetId] : []
  if (!targetIds.length) {
    message.warning(`请先选择${getRuleMeta(addForm.ruleType).label}`)
    return
  }

  const existed = targetIds.some((targetId) =>
    memberList.value.some((item) => item.ruleType === addForm.ruleType && String(item.targetId) === String(targetId))
  )
  if (existed) {
    message.warning("该对象已在成员列表中，如需变更权限请先移除原记录")
    return
  }

  addLoading.value = true
  try {
    await Promise.all(
      targetIds.map((targetId) =>
        addKbMember(props.kbId, {
          ruleType: addForm.ruleType,
          targetId,
          grantRole: addForm.grantRole
        })
      )
    )
    message.success("添加成功")
    showAdd.value = false
    resetAddForm()
    loadMembers()
  } catch (e) {
    message.error("添加失败")
  } finally {
    addLoading.value = false
  }
}

/**
 * 移除指定知识库成员授权。
 */
async function onRemove(record: any) {
  try {
    await removeKbMember(props.kbId, record.id)
    message.success("移除成功")
    loadMembers()
  } catch (e) {
    message.error("移除失败")
  }
}

/**
 * 从用户中心批量补齐成员名称。
 */
async function enrichMemberNames() {
  const nameMap: Record<string, string> = {}
  const userIds = getTargetIds("user")
  const deptIds = getTargetIds("dept")
  const roleIds = getTargetIds("role")

  if (userIds.length) {
    try {
      const res = await getUsersByIds(userIds)
      const users = res?.datas && typeof res.datas === "object" ? res.datas : {}
      Object.keys(users).forEach((id) => {
        nameMap[getMemberKey("user", id)] = getUserName(users[id])
      })
    } catch (e) {
      console.error(e)
    }
  }

  if (deptIds.length) {
    try {
      const res = await getDeptsByIds(deptIds)
      const depts = res?.datas && typeof res.datas === "object" ? res.datas : {}
      Object.keys(depts).forEach((id) => {
        nameMap[getMemberKey("dept", id)] = depts[id]
      })
    } catch (e) {
      console.error(e)
    }
  }

  if (roleIds.length) {
    await Promise.all(
      roleIds.map(async (id) => {
        try {
          const res = await getRoleById(id)
          const role = res?.datas || {}
          nameMap[getMemberKey("role", id)] = role.roleName || role.name || id
        } catch (e) {
          console.error(e)
        }
      })
    )
  }

  displayNameMap.value = nameMap
}

/**
 * 搜索并归一化用户中心候选对象。
 */
async function searchCandidates(keyword: string) {
  if (addForm.ruleType === "dept") {
    await ensureDeptTree()
    return
  }
  memberSearchLoading.value = true
  try {
    const res =
      addForm.ruleType === "user"
        ? await searchUserMembers(keyword)
        : addForm.ruleType === "dept"
        ? await searchDeptMembers(keyword)
        : await searchRoleMembers(keyword)

    candidateOptions.value = normalizeCandidateOptions(res)
  } catch (e) {
    console.error(e)
    candidateOptions.value = []
  } finally {
    memberSearchLoading.value = false
  }
}

/**
 * 按当前授权对象类型归一化用户中心返回值，供 Select 统一展示。
 */
function normalizeCandidateOptions(payload: any): CandidateOption[] {
  const list = extractList(payload)
  const mapper = {
    user: mapUserOption,
    dept: mapDeptOption,
    role: mapRoleOption
  }[addForm.ruleType]

  const options = list.map(mapper).filter((item) => item.id)
  return options.filter((item, index, array) => array.findIndex((candidate) => candidate.id === item.id) === index)
}

function extractList(payload: any) {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.datas)) {
    return payload.datas
  }
  if (Array.isArray(payload?.data)) {
    return payload.data
  }
  if (payload?.datas && typeof payload.datas === "object") {
    return Object.values(payload.datas)
  }
  return []
}

function mapUserOption(user: any): CandidateOption {
  return {
    id: user.userId,
    name: getUserName(user),
    subTitle: [user.userName, user.phoneNumber, user.dept?.deptName].filter(Boolean).join(" / "),
    raw: user
  }
}

function mapDeptOption(dept: any): CandidateOption {
  return {
    id: String(dept.deptId || dept.id || dept.key || dept.value || ""),
    name: dept.deptName || dept.label || dept.title || dept.name || dept.deptId,
    subTitle: "",
    raw: dept
  }
}

function mapRoleOption(role: any): CandidateOption {
  return {
    id: role.roleId,
    name: role.roleName || role.name || role.roleId,
    subTitle: role.roleCode ? `编码：${role.roleCode}` : "",
    raw: role
  }
}

function getUserName(user: any) {
  return user?.realName || user?.nickName || user?.userName || user?.userId || "-"
}

function getTargetIds(ruleType: MemberRuleType) {
  return Array.from(
    new Set(
      memberList.value
        .filter((item) => item.ruleType === ruleType && item.targetId)
        .map((item) => String(item.targetId))
    )
  )
}

function getMemberKey(ruleType: string, targetId: string) {
  return `${ruleType}:${targetId}`
}

function countByRuleType(ruleType: MemberRuleType) {
  return memberList.value.filter((item) => item.ruleType === ruleType).length
}

function getRuleMeta(ruleType: MemberRuleType) {
  return ruleTypeMeta[ruleType] || ruleTypeMeta.user
}

function getRoleMeta(role: string) {
  return grantRoleOptions.find((item) => item.value === role) || grantRoleOptions[3]
}

function getInitial(name: string) {
  return (name || "U").slice(0, 1).toUpperCase()
}

/**
 * 重置添加成员表单。
 */
function resetAddForm() {
  addForm.ruleType = "user"
  addForm.targetId = ""
  deptSelectedIds.value = []
  addForm.grantRole = "readonly"
  candidateOptions.value = []
}

async function ensureDeptTree() {
  if (deptTreeData.value.length || deptTreeLoading.value) {
    return
  }
  deptTreeLoading.value = true
  try {
    const res = await getDeptTree("")
    const tree = extractList(res)
    const optionMap: Record<string, CandidateOption> = {}
    deptTreeData.value = normalizeDeptTree(tree, optionMap, false)
    deptOptionMap.value = optionMap
  } catch (e) {
    console.error(e)
    message.error("获取部门树失败")
  } finally {
    deptTreeLoading.value = false
  }
}

async function loadDeptChildren(treeNode: any) {
  const nodeId = String(treeNode?.value || treeNode?.eventKey || treeNode?.dataRef?.value || "")
  if (!nodeId || deptLoadingNodeIds.value[nodeId]) {
    return
  }
  const dataRef = treeNode?.dataRef || findDeptTreeNode(deptTreeData.value, nodeId)
  if (dataRef?.children?.length) {
    return
  }

  deptLoadingNodeIds.value = { ...deptLoadingNodeIds.value, [nodeId]: true }
  try {
    const res = await getDeptTree(nodeId)
    const optionMap = { ...deptOptionMap.value }
    const children = normalizeDeptTree(extractList(res), optionMap, false)
    deptOptionMap.value = optionMap
    deptTreeData.value = updateDeptTreeChildren(deptTreeData.value, nodeId, children)
  } catch (e) {
    console.error(e)
    message.error("加载下级部门失败")
  } finally {
    const nextLoading = { ...deptLoadingNodeIds.value }
    delete nextLoading[nodeId]
    deptLoadingNodeIds.value = nextLoading
  }
}

function normalizeDeptTree(nodes: any[], optionMap: Record<string, CandidateOption>, includeChildren: boolean) {
  return (nodes || [])
    .map((node) => {
      const id = String(node.deptId || node.id || node.key || node.value || "")
      if (!id) {
        return null
      }
      const title = node.deptName || node.label || node.title || node.name || id
      optionMap[id] = {
        id,
        name: title,
        subTitle: "",
        raw: node
      }
      const children = includeChildren ? normalizeDeptTree(node.children || [], optionMap, includeChildren) : []
      const hasChildren = Array.isArray(node.children) && node.children.length > 0
      const isLeaf = node.isLeaf === true || node.leaf === true || node.hasChild === false || node.hasChildren === false
      return {
        title,
        key: id,
        value: id,
        children: children.length ? children : undefined,
        isLeaf: isLeaf && !hasChildren
      }
    })
    .filter(Boolean)
}

function findDeptTreeNode(nodes: any[], nodeId: string): any {
  for (const node of nodes || []) {
    if (String(node.value) === nodeId) {
      return node
    }
    const found = findDeptTreeNode(node.children || [], nodeId)
    if (found) {
      return found
    }
  }
  return null
}

function updateDeptTreeChildren(nodes: any[], nodeId: string, children: any[]): any[] {
  return (nodes || []).map((node) => {
    if (String(node.value) === nodeId) {
      return {
        ...node,
        children: children.length ? children : undefined,
        isLeaf: !children.length
      }
    }
    if (node.children?.length) {
      return {
        ...node,
        children: updateDeptTreeChildren(node.children, nodeId, children)
      }
    }
    return node
  })
}

function getMemberPopupContainer() {
  return document.body
}
</script>

<style lang="less" scoped>
.member-manage {
  color: #1f2a44;
}

.member-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  overflow: hidden;
  padding: 20px 22px;
  margin-bottom: 16px;
  background: radial-gradient(circle at 8% 20%, rgba(51, 112, 255, 0.16), transparent 28%),
    linear-gradient(135deg, #f8fbff 0%, #eef5ff 100%);
  border: 1px solid rgba(51, 112, 255, 0.12);
  border-radius: 18px;
}

.member-hero__eyebrow {
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #3370ff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.member-hero__title {
  font-size: 20px;
  font-weight: 700;
  color: #17233d;
}

.member-hero__desc {
  margin-top: 6px;
  color: #667085;
}

.member-hero__button {
  padding: 0 18px;
  height: 38px;
  border-radius: 999px;
  box-shadow: 0 10px 20px rgba(51, 112, 255, 0.22);
}

.member-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.member-summary__item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px;
  background: #fff;
  border: 1px solid #edf1f7;
  border-radius: 14px;
}

.member-summary__icon {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 38px;
  height: 38px;
  border-radius: 12px;
}

.member-summary__icon--user {
  color: #3370ff;
  background: #edf4ff;
}

.member-summary__icon--dept {
  color: #16a34a;
  background: #ecfdf3;
}

.member-summary__icon--role {
  color: #f59e0b;
  background: #fff7e6;
}

.member-summary__num {
  font-size: 20px;
  font-weight: 700;
  color: #17233d;
}

.member-summary__label {
  color: #667085;
}

.member-tip {
  margin-bottom: 14px;
  border-radius: 12px;
}

.member-target {
  display: flex;
  gap: 12px;
  align-items: center;
}

.member-target__avatar {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 36px;
  height: 36px;
  font-weight: 700;
  border-radius: 12px;
  flex: 0 0 auto;
}

.member-target__avatar--user {
  color: #fff;
  background: linear-gradient(135deg, #3370ff, #5b8cff);
}

.member-target__avatar--dept {
  color: #16a34a;
  background: #ecfdf3;
}

.member-target__avatar--role {
  color: #f59e0b;
  background: #fff7e6;
}

.member-target__name {
  font-weight: 600;
  color: #1f2a44;
}

.member-target__meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  color: #98a2b3;
}

.member-time {
  color: #667085;
}

.member-remove {
  color: #ef4444;
}

.member-locked {
  font-size: 12px;
  color: #98a2b3;
}

.member-empty {
  margin-top: 20px;
}

.member-add {
  padding-top: 4px;
}

.member-type-switch {
  display: flex;
  margin-bottom: 18px;

  ::v-deep .ant-radio-button-wrapper {
    flex: 1;
    height: 40px;
    line-height: 38px;
    text-align: center;
  }
}

.member-add__form-item {
  margin-bottom: 18px;
}

.member-target-select {
  width: 100%;

  ::v-deep .ant-select-selection-selected-value {
    max-width: calc(100% - 20px);
    overflow: hidden;
    line-height: 30px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.member-option {
  display: flex;
  flex-direction: column;
  line-height: 1.5;
}

.member-option__name {
  font-weight: 600;
  color: #1f2a44;
}

.member-option__sub {
  font-size: 12px;
  color: #98a2b3;
}

.member-selected {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 10px 12px;
  margin: -4px 0 18px;
  color: #1677ff;
  background: #f0f7ff;
  border: 1px solid #d6e8ff;
  border-radius: 12px;
}

.member-role-group {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));

  ::v-deep .ant-radio-button-wrapper {
    text-align: center;
  }
}

.member-role-desc {
  padding: 12px 14px;
  color: #667085;
  background: #fafbff;
  border: 1px dashed #d9e3f0;
  border-radius: 12px;
}
</style>

<style lang="less">
.member-target-dropdown {
  min-width: 360px !important;
}
</style>
