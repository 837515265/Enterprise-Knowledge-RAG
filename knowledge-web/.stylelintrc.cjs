module.exports = {
  extends: [
      './node_modules/@ldsk/ld-eslint-config/.stylelintrc.js',
  ],
  rules: {
    'selector-max-type': 10,
    "number-leading-zero": "always"
  }
}