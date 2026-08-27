/** @type {import('eslint/lib/shared/types').ConfigData} */
module.exports = {
  globals: {
    defineProps: "readonly",
    defineEmits: "readonly",
    defineExpose: "readonly",
    withDefaults: "readonly"
  },
  extends: ["./node_modules/@ldsk/ld-eslint-config/vue2-ts.js", "./.eslintrc-auto-import.json"],
  // 覆盖规则
  rules: {
    // 允许添加console
    "no-console": "off",
    // 禁止使用debugger
    "no-debugger": "error"
  }
}
