<template>
  <ChatPanel
    :embedded="embedded"
    :fixed-kb-id="fixedKbId"
    :fixed-kb-name="fixedKbName"
    :initial-question="initialQuestion"
    :initial-kb-id="initialKbId"
  />
</template>

<script setup lang="ts">
import ChatPanel from "../chat.vue"

withDefaults(
  defineProps<{
    embedded?: boolean
    fixedKbId?: string | number
    fixedKbName?: string
    initialQuestion?: string
    initialKbId?: string | number
  }>(),
  {
    embedded: false,
    fixedKbId: "",
    fixedKbName: "",
    initialQuestion: "",
    initialKbId: ""
  }
)
</script>
