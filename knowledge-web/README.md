### 项目简介

本项目是一套基于 Vite + Vue 2.7 + TypeScript + TailwindCSS + Pinia + Vue Router 的企业级后台管理系统模板。结合数科业务场景沉淀，内置完善的登录与权限体系、统一的表单/布局样式工具、丰富的业务组件与 hooks、mixin、低代码能力（vform）等，极大提升开发效率与团队协作体验。

完整文档请查看 [【鲁担数科开发者门户-技术组件-前端基础框架】]( http://hub.ludanshuke.com/#/tech-components/48)

### 环境要求

| 工具 | 版本要求     |
| ---- | ------------ |
| Node | **14.x**     |
| NPM  | **>= 8.3.0** |

> ⚠️ **提示：**
>
> 1. 本项目已添加环境校验，安装和打包时如未使用指定版本的 Node 和包管理器会直接报错，无法继续执行。
> 2. 本项目仅支持使用 `npm` 安装依赖，且建议使用 `npm >= 8.3.0`，以确保 `overrides` 等能力在处理间接依赖漂移时可以正常生效。
> 3. 如果使用错误的 Node 版本、过低版本的 `npm` 或其他包管理器，可能会导致依赖安装失败、项目无法运行或构建失败，请务必严格按照要求配置开发环境。

### 依赖安装说明

- 团队协作时请优先复用仓库中已验证可用的 `package-lock.json`，不要随意删除后重新生成。
- 本项目在 `Node 14` 下是否可正常启动，不仅取决于顶层依赖版本，也取决于锁文件中间接依赖的最终解析结果。
- 如启动时报错 `node:stream/promises`，通常优先排查间接依赖漂移问题，例如：`unplugin-icons` -> `@iconify/utils` -> `@antfu/install-pkg` -> `tinyexec`。
- 如确需通过 `overrides` 锁定间接依赖，请先确认本机 `npm` 版本满足 `>= 8.3.0`。

### 启动

1. 使用 nvm 切换 Node 版本为 14：

   ```bash
   nvm use  // .nvmrc文件已经设置 node版本，使用nvm use 即可切换到正确的版本
   ```

2. 安装依赖：

   ```bash
   npm install
   ```

3. 启动开发环境：

   ```bash
   npm run dev
   ```

### 常用命令

```bash
npm run dev           # 开发环境启动项目
npm run serve         # 启动开发环境（等同于 npm run dev，兼容部分习惯）
npm run build         # 生产环境打包项目
npm run lint          # 代码风格检查与自动修复（包括 eslint、stylelint、prettier）
npm run prepare       # husky 钩子安装（自动安装 git 钩子，保障代码规范）
npm run postinstall   # husky 钩子安装（自动安装 git 钩子，保障代码规范）
npm run lint-staged   # 手动执行 lint-staged 钩子（一般由 git 钩子自动触发）
npm run check:node    # 检查 Node 版本，确保环境符合要求
npm run predev        # dev 前自动执行 Node 版本校验
npm run prebuild      # build 前自动执行 Node 版本校验
npm run preinstall    # install 前自动执行 Node 版本校验
npm run check:ts      # TypeScript 类型检查（不生成文件）
```
