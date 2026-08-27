# 仓库级协作说明

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

---

## 作用范围

- 本文件作用于整个仓库。
- 修改任何文件前，都应先理解其所在目录职责，保持与现有架构一致。

## 项目定位

- 本项目是一个基于 `Vite 4 + Vue 2.7 + TypeScript` 的后台管理模板。
- 项目同时集成了 `Pinia`、`Vue Router 3`、`TailwindCSS`、`Less`、`Element UI`、`Ant Design Vue 1.x`。
- 项目既提供通用后台能力，也沉淀了数科业务常用能力，例如权限、动态菜单、字典、低代码表单、列表页与详情页包装、文件上传/预览等。

## 环境与安装要求

- 仅使用 `Node 14.x`。
- 仅使用 `npm`，不要使用 `yarn` 或 `pnpm`。
- `npm` 版本要求为 `>= 8.3.0`，以保证 `overrides` 等能力可用。
- 开始安装前优先执行 `nvm use`。
- 安装依赖使用 `npm install`。
- 启动开发环境使用 `npm run dev`。
- 生产构建使用 `npm run build`。
- 类型检查使用 `npm run check:ts`。
- 环境检查使用 `npm run check:node`。

## 仓库目录说明

### 根目录

- `build/`：Vite 构建配置、插件封装、环境脚本、依赖优化配置。
- `src/`：业务源码主目录，包含页面、组件、路由、状态、指令、工具和样式。
- `types/`：全局类型声明、路由类型、模型类型、自动生成的类型声明。
- `lib/`：仓库内置静态库资源，目前包含 `vform` 渲染器产物。
- `public/`：原样拷贝到构建产物的静态资源。
- `data/`：预留数据目录，如无明确任务不要随意塞业务逻辑。
- `dist/`：构建输出目录，不作为业务修改目标。
- `package.json`：脚本、依赖、校验命令、引擎限制、覆盖规则。
- `vite.config.ts`：Vite 总入口配置，依赖 `build/` 下封装能力。
- `tailwind.config.js`：Tailwind 主题配置，项目主题色通过 CSS 变量联动。
- `tsconfig.json`：TypeScript 编译约束、路径别名、类型范围。

### `src/` 目录

- `src/main.ts`：应用启动入口，负责注册路由、Pinia、VForm、ElementUI、指令、主题和额外 AntDV 组件。
- `src/api/`：接口定义层，应只负责调用请求方法并组织接口参数，不在此处放页面逻辑。
- `src/components/`：项目级通用组件。
- `src/config/`：页面、布局、字典等静态配置。
- `src/directives/`：全局自定义指令，当前以权限指令与全局 loading 指令为主。
- `src/hooks/`：可复用组合式逻辑，适合沉淀列表查询、字典、选项处理、双向绑定等通用行为。
- `src/layout/`：默认布局容器，承载菜单、标签页、头部、设置抽屉、`router-view`。
- `src/mixin/`：历史 mixin 能力，旧模块复用逻辑仍可能依赖这里。
- `src/router/`：路由实例、路由守卫、静态路由与动态菜单路由整合逻辑。
- `src/store/`：Pinia 状态管理入口与各模块 store。
- `src/style/`：全局样式入口、主题变量、基础样式、组件样式。
- `src/utils/`：工具层，包含鉴权、HTTP、主题、文件、总线、页面工具等。
- `src/views/`：页面层，按业务或示例模块分组。
- `src/assets/`：图片、样式资源等静态素材。

### `src/components/` 常见组件职责

- `page-wrapper/`：列表页、详情页包装组件，页面开发优先复用，不要重复造壳。
- `pro-layout/`：后台布局实现，包含基础布局、页头、内容包装等。
- `ld-vform/`：低代码表单相关封装。
- `upload/`：上传能力封装。
- `file-preview/`：文件预览弹窗或页面能力。
- `tags-view/`：多标签页导航。
- `select/`：带项目语义的选择类组件，如自定义单选、多选、下拉。
- `sourcecode-opener/`：结合调试插件的源码定位能力。

### `src/store/modules/` 状态职责

- `user.ts`：用户信息、token、权限等认证相关状态与动作。
- `menu.ts`：动态菜单、路由生成、路由注册、菜单权限过滤。
- `layout.ts`：布局配置、主题、折叠状态、展示策略。
- `dict.ts`：全局字典缓存。
- `tags.ts`：多标签页状态。

### `src/router/` 路由职责

- `index.ts`：创建 VueRouter 实例并注册路由守卫。
- `guard/permissionGuard.ts`：登录态校验、用户信息拉取、字典加载、动态路由注册、页面标题处理。
- `routes/routes.ts`：静态路由与布局路由定义；所有需要挂在默认布局下的页面，应优先放在布局路由或其动态合并链路中。

### `src/utils/` 工具职责

- `http/`：统一请求封装与 axios 拦截器配置。
- `auth/`：登录跳转、权限判断、菜单转路由、URL 解析。
- `theme/`：主题色切换与 CSS 变量处理。
- `logic/`：偏业务通用的逻辑工具，如额外组件注册、语言加载、编辑器打开源码等。
- 其他零散工具如 `bus.ts`、`fullLoading.ts`、`downloadBlob.ts`、`previewFile.ts` 应保持纯工具属性，避免塞页面状态。

## 关键架构约束

### 接口契约与用户身份

- 不要为了绕过前后端类型不一致而传 `0`、空字符串、`local-dev` 等默认值。
- 如果接口契约要求 `userId` 是字符串，就应端到端按字符串改造前端、后端实体、Service、SQL 字段。
- 如果当前后端字段类型不匹配，应同步修改后端和数据库，不要在前端做数字化转换或兜底。
- 缺少真实登录用户信息时，应明确提示或阻断操作，而不是静默使用默认用户。

### 入口与插件注册

- 应用启动入口是 `src/main.ts`。
- `src/main.ts` 中已统一完成路由、Pinia、VForm、ElementUI、指令、主题、AntDV 扩展组件注册。
- 涉及全局注册的能力，优先放在入口或对应注册函数中，不要在页面中重复注册。

### 请求层约束

- 项目统一通过 `src/utils/http/index.ts` 暴露的请求方法发起请求。
- `src/utils/http/instance.ts` 明确复用 axios 全局实例，而不是 `axios.create()`，目的是与 `vform` 共享同一套拦截器与默认配置。
- 不要绕过这层封装直接在业务代码里随意新建 axios 实例，除非任务明确要求并充分说明原因。

### 路由与权限约束

- 动态菜单与动态路由由 `menu` store 与权限守卫共同完成。
- 登录、用户信息获取、菜单拉取、字典初始化、页面标题设置都在路由守卫链路中。
- 新增页面时，先判断它属于：
  - 布局内静态路由
  - 动态菜单路由
  - 独立公共页（如 404、重定向、文件预览）
- 不要随意打散现有“菜单 -> 路由 -> 权限”的链路。

### 布局与主题约束

- 默认布局由 `src/layout/index.vue` 与 `src/components/pro-layout/` 共同实现。
- 布局配置统一由 `layout` store 与 `src/config/layout.ts` 管理。
- 主题色通过 CSS 变量与 `changeTheme` 联动，改主题相关逻辑时优先延续现有变量体系。

### 低代码与共享能力约束

- 项目内置 `@ldsk/vform` 与本地 `lib/vform` 资源。
- 涉及表单渲染、低代码能力、文件上传/预览等场景时，优先复用现有组件与工具，不要重复写一套新能力。

## 构建与插件说明

- `vite.config.ts` 是总配置入口，主要逻辑下沉到 `build/`。
- `build/createVitePlugin.ts` 统一注册以下能力：
  - `@vitejs/plugin-vue2`
  - `@vitejs/plugin-vue2-jsx`
  - `unplugin-icons`
  - `unplugin-vue-components`
  - `unplugin-auto-import`
  - `vite-plugin-vue-inspector`
  - `vite-plugin-commonjs`
  - `rollup-plugin-visualizer`
  - 自定义 `antd` 相关插件
- `src/components` 与 `src/directives` 会被自动扫描注册，改动这些目录时要考虑自动导入影响。
- `src/utils/*`、`src/hooks`、`src/mixin` 中部分导出会进入自动导入能力，新增方法时注意命名冲突与职责清晰。

## 自动导入与全局注册约定

- 本项目已配置组件自动注册、方法自动导入、图标自动解析与部分全局原型挂载；开发时应先判断是否已经自动可用，不要习惯性手动 `import`。

### 组件自动注册

- `src/components/` 下的组件会被自动扫描注册，模板中优先直接使用组件名，不必在页面中手动引入。
- `src/directives/` 相关能力也会参与自动扫描与注册；新增指令时要注意不要与现有命名冲突。
- `Ant Design Vue` 常用组件已通过解析器自动注册，模板中优先直接使用，如 `a-button`、`a-form`、`a-table`、`a-select` 等，无需再单独 `import`。
- 项目内常用公共组件也可直接在模板中使用，例如 `ListWrapper`、`DetailWrapper`、`CustomSelect`、`CustomUpload`、`FilePreview`、`FilePreviewModal`、`LdVform`、`SourcecodeOpener` 等。
- 如组件已经能通过自动注册直接使用，不要再在页面中重复手动引入同一个组件。

### Ant Design Vue 补充全局注册

- 对于自动解析不了的部分 `Ant Design Vue` 子组件与指令，项目已在 `src/main.ts` 中通过 `registerExtraAntdvComponents` 做了补充注册。
- 这类能力包括部分 `Option`、`OptGroup`、`TabPane`、`Descriptions.Item`、`RangePicker` 等子组件，以及 `v-ant-portal` 指令。
- 如果发现某个 `Ant Design Vue` 子组件仓库里已有全局补充注册，优先直接使用，不要在页面里重复 `Vue.use` 或手工二次注册。

### 方法自动导入

- `Vue`、`@vueuse/core`、项目内部分 `utils`、`hooks`、`mixin` 导出已通过自动导入插件接入。
- 常见如 `ref`、`reactive`、`computed`、`watch`、`useRoute`、`useRouter`、`message`、`notification`、`Modal`、`httpGet`、`httpPost`、`httpUpload`、`downloadBlob`、`previewFile`、`hasPermission`、`$page`、`eventBus` 等，可先按自动导入方式使用。
- 使用这些能力前，先参考 `types/auto-imports.d.ts` 与仓库现有写法；如果已经声明为全局可用，通常无需额外手动引入。
- 但需注意：自动导入主要面向脚本逻辑；模板中不要把自动导入的函数当成“全局模板函数”随意使用。

### 原型方法与历史写法兼容

- 项目已挂载 `this.$message`、`this.$notification`、`this.$info`、`this.$success`、`this.$error`、`this.$warning`、`this.$confirm`、`this.$destroyAll` 等原型方法，用于兼容部分选项式或历史代码。
- 在 `setup` 风格中，优先使用自动导入的 `message`、`notification`、`Modal`。
- 在历史 `this` 风格代码中，可沿用 `$message` 等实例方法，不要在同一个文件里混乱造出第三套提示调用方式。

### 图标使用约定

- 项目已启用 `unplugin-icons` 与图标解析器，图标组件优先按仓库现有命名方式直接在模板中使用，不要先手工引入再注册。
- `Ant Design Vue` 原生图标场景，优先沿用现有 `a-icon` 或已有菜单图标配置写法，保持和当前项目一致。
- 使用新图标前，优先确认现有图标库与现有命名规则能否覆盖，不要为了单个页面额外引入新的图标方案。

### 使用自动导入时的约束

- 如果某个组件、方法、指令、图标已经由项目自动导入或全局注册，就不要重复手动 `import`。
- 如果自动导入未覆盖某个能力，再补充手动引入；不要在不确认的情况下盲目重复导入。
- 排查“为什么这里没 import 也能用”时，优先查看：
  - `build/createVitePlugin.ts`
  - `types/auto-imports.d.ts`
  - `types/components.d.ts`
  - `src/utils/logic/loadAntdExtraComponnets.ts`

## 公共能力优先使用原则

- 任何新需求开始前，先判断仓库中是否已经存在可复用的组件、hook、工具方法、指令、store 或样式壳。
- 优先复用已有公共能力，只有在现有能力确实无法覆盖时，才新增新的公共实现。
- 新增公共能力前，应先确认是否只是现有组件、hook、工具缺少少量扩展；能扩展则优先扩展，不要并行再造一套。
- 新增页面代码时，应尽量减少重复的查询、分页、导出、上传、预览、权限判断、返回逻辑和样式结构。
- 新代码默认优先使用 `hooks`，新功能不要优先继续扩张 `mixin`；`mixin` 主要用于兼容历史写法。

## 具体场景应优先使用的公共能力

### hooks 使用约定

- `src/hooks/` 是组合式逻辑的首选沉淀位置；新逻辑若具备跨页面复用价值，应优先考虑抽成 hook。
- 新增业务代码时，先检查 `src/hooks/` 是否已有可直接使用或稍作扩展即可复用的能力。
- 组合式新逻辑优先继续沉淀到 `hooks`，不要优先往 `mixin` 里继续堆积。

#### `useQuery`

- 作用：统一处理一次请求型逻辑，封装 `loading`、`error`、`isSuccess`、`immediate`、参数监听、请求前拦截、结果转换等能力。
- 适用场景：详情查询、统计查询、下拉远程查询、单块数据加载、依赖参数自动触发的请求。
- 什么时候用：当页面需要“一个请求 + 一套标准请求状态”时，优先使用 `useQuery`。
- 不建议手写的内容：重复维护 `loading`、`error`、`watch`、立即执行与手动执行切换。
- 不适用场景：标准分页表格列表优先使用 `usePageList`，不要用 `useQuery` 再手搓一层分页。

#### `usePageList`

- 作用：在 `useQuery` 基础上封装分页列表查询，统一管理 `pageNum`、`pageSize`、`total`、`list`、分页变化、重置查询与 `pagination` 对象。
- 适用场景：所有标准后台列表页、搜索列表页、表格分页页。
- 什么时候用：只要接口返回的是“总数 + 列表”的分页结构，就优先用 `usePageList`。
- 配套建议：与 `list-wrapper`、`.c-search-form`、`a-table` 的分页联动一起使用，尽量参照 `demo/crud/list-hooks.vue` 模式。
- 不适用场景：非分页请求、一次性明细查询、纯本地列表处理，不必强行套 `usePageList`。

#### `useDict`

- 作用：按字典编码读取字典项，并提供 `list`、`getLabel`、`getCode`、`getItemByCode`、`getItemByLabel` 等快捷方法。
- 适用场景：状态展示、字典标签回显、根据字典生成下拉选项、根据 code 显示文本。
- 什么时候用：只要页面涉及全局字典值解析，就优先用 `useDict`，不要直接在页面里手写对 `dictStore` 的访问与转换。
- 配套建议：搭配 `custom-select`、表格列格式化、详情回显使用。

#### `useSelectOptions`

- 作用：把字典、接口返回或静态数组统一转换为选择器可用的 `options`。
- 适用场景：`custom-select`、单选/多选组件、下拉筛选、表单选项源统一处理。
- 什么时候用：当选项来源可能是 `dictCode`、`url` 或 `options` 三者之一时，优先使用它做统一映射。
- 不建议手写的内容：每个页面重复写 `label/value/key` 映射、接口结果数组判断、字典转 options 逻辑。

#### `useModelValue`

- 作用：为自定义组件统一封装 `v-model` 双向绑定行为，负责内部值与外部 `props.value` 同步，并触发 `input` 事件。
- 适用场景：封装自定义输入组件、下拉组件、单选多选组件、上传组件等需要兼容 `v-model` 的场景。
- 什么时候用：只要你在写一个自定义表单组件，并希望它能像原生组件一样支持 `v-model`，优先使用 `useModelValue`。
- 不建议手写的内容：每个自定义组件内重复写一套 `watch(props.value)` + `emit('input')`。

#### `useResettableRef`

- 作用：创建一个带“恢复初始值”能力的 `ref`，并通过 `reset` 方法回滚到默认值。
- 适用场景：查询条件默认值、表单初始值、副本编辑态、需要一键恢复初始状态的数据对象。
- 什么时候用：当某个响应式状态需要频繁“恢复初始值”时，优先使用 `useResettableRef`，不要手写一堆字段逐个回填。

#### 其他 hooks 使用原则

- 若已有 hook 只能覆盖 80% 场景，优先扩展现有 hook 的参数或配置项，不要复制一份 `useXxx2`、`useXxxNew`。
- hook 应聚焦“状态 + 行为”复用，不要把明显的页面私有 DOM 结构直接塞进 hook。
- hook 命名应直接体现职责，避免含糊命名。

### 公共组件使用约定

#### `ListWrapper`

- 作用：提供标准列表页外壳，统一搜索区、表格区、内容高度和加载态表现。
- 适用场景：标准后台列表页、查询页、带分页表格页。
- 什么时候用：只要页面主体是“查询 + 表格/列表”，优先使用 `ListWrapper`。
- 配套使用：通常与 `.c-search-form`、`usePageList`、`a-table` 一起使用。
- 不建议：不要每个列表页重新手写一套白底容器、内容高度计算和 loading 包裹。

#### `DetailWrapper`

- 作用：提供详情页 / 编辑页标准容器，统一页头、返回、内容滚动区和标题表现。
- 适用场景：新增页、编辑页、详情页、查看页。
- 什么时候用：页面以“详情内容 + 返回”为主时，优先使用 `DetailWrapper`。
- 配套使用：返回逻辑优先结合 `$page.goBackOpener()` 或组件内置 back 逻辑。

#### `CustomSelect`

- 作用：统一下拉组件的数据来源和 options 映射，支持 `dictCode`、`url`、`options` 三种来源。
- 适用场景：字典下拉、远程下拉、静态选项下拉。
- 什么时候用：只要是标准选择器且存在字典/接口/静态选项三类来源之一，优先使用 `CustomSelect`。
- 不建议：不要每个页面自己维护“请求接口转 options”“字典转 label/value” 的重复逻辑。

#### `CustomUpload`

- 作用：统一附件上传、类型/大小/数量校验、进度、回填、预览与删除逻辑。
- 适用场景：业务表单附件上传、图片上传、文件上传列表。
- 什么时候用：只要业务中有标准附件上传需求，优先使用 `CustomUpload`。
- 配套使用：文件预览逻辑优先沿用组件内置 `previewType` 与 `previewFile` 能力。
- 不建议：不要在业务页重新手写一套上传状态、校验和预览回填。

#### `FilePreview` / `FilePreviewModal`

- 作用：统一文件在线预览和下载操作。
- 适用场景：预览附件、合同、图片、文档等。
- 什么时候用：只要页面需要预览文件，优先使用 `FilePreview` 或 `FilePreviewModal`，不要自己再拼文件预览页。
- 选择建议：页面式预览优先走 `previewFile(id, 'page')`，弹窗式预览优先走 `FilePreviewModal` 或 `previewFile(id, 'modal')`。

#### `LdVform`

- 作用：承接低代码表单渲染能力。
- 适用场景：动态表单、低代码表单、函数编码驱动的表单页面。
- 什么时候用：业务已接入 vform 或功能由函数编码驱动时，优先使用 `LdVform`，不要在相邻场景重新造表单引擎。

#### `SourcecodeOpener`

- 作用：开发环境下快速定位当前示例或页面源码位置。
- 适用场景：示例页、调试页、开发说明页。
- 什么时候用：当页面需要明显提示“这里的代码在哪”时，可优先使用 `SourcecodeOpener`。

### 公共工具方法使用约定

#### `httpGet` / `httpPost` / `httpPut` / `httpDelete` / `httpUpload` / `httpDownload`

- 作用：统一请求入口，承接 token、拦截器、loading、mock、响应处理。
- 什么时候用：所有标准接口请求都应优先使用这组方法。
- 不建议：不要在页面里直接调用裸 `axios` 或创建新的请求实例。

#### `downloadBlob`

- 作用：统一处理二进制文件下载。
- 什么时候用：导出 Excel、模板下载、报表下载等返回 blob 的场景。
- 不建议：不要每个导出按钮都重新拼一套 `Blob` + `a` 标签下载逻辑。

#### `previewFile`

- 作用：统一打开文件预览页或预览弹窗。
- 什么时候用：只要业务里存在“点击附件进行预览”的行为，优先使用它。
- 不建议：不要在页面内自行拼接 `/file-preview/:id` 路由地址。

#### `$page.goBackOpener()`

- 作用：在启用页签体系时，优先返回到打开当前页的来源页，而不是简单 `router.back()`。
- 什么时候用：详情页、编辑页、弹出新页签再返回的业务页面。
- 不建议：不要在这类页面里直接写死 `router.go(-1)` 替代它。

#### `hasPermission`

- 作用：统一权限判断逻辑。
- 什么时候用：脚本逻辑中需要判断权限时优先使用；模板层优先仍使用 `v-action` / `v-actions`。
- 不建议：不要自行从 `store` 里反复拷贝权限数组再做重复判断。

#### `openFileInEditor`

- 作用：开发环境下直接唤起本地编辑器打开对应源码位置。
- 什么时候用：示例说明、调试辅助、插槽错误提示等开发体验场景。

### 列表页、查询页、表格页

- 列表页外层优先使用 `src/components/page-wrapper/list-wrapper.vue`。
- 列表查询区域优先使用 `a-form` + `.c-search-form`，保持搜索区间距、行高和布局一致。
- 分页列表数据优先使用 `src/hooks/usePageList.ts`，不要在页面里手写重复的 `pageNum`、`pageSize`、`total`、分页监听和重置逻辑。
- 非分页但具备统一请求生命周期的场景，优先使用 `src/hooks/useQuery.ts`，不要重复维护 `loading`、`error`、`success`、`immediate`、参数监听等逻辑。
- 列表页的查询参数、重置、分页联动、表格刷新，应尽量沿用 `demo/crud/list-hooks.vue` 展示的模式。
- 列表页如需“查询区 + 表格区 + 底部分页”的标准布局，应优先复用现有 `list-wrapper` 结构，不要自定义新的页面壳。

### 详情页、表单页、返回页

- 详情页或表单详情页外层优先使用 `src/components/page-wrapper/detail-wrapper.vue`。
- 返回上一个打开页签或来源页的逻辑，优先使用 `detail-wrapper` 内置能力或 `$page.goBackOpener()`，不要在页面中反复手写返回逻辑。
- 详情表单区域优先使用 `.c-detail-form`，保持表单项间距和帮助文案展示一致。

### 下拉、单选、多选、字典映射

- 下拉选项如来自字典、远程接口或静态选项，优先使用 `src/components/select/custom-select.vue`。
- 字典读取与字典值展示优先使用 `src/hooks/useDict.ts`，不要在页面中直接手写字典缓存访问和转换逻辑。
- 当页面只是需要“根据字典编码取 label/code/item”，优先用 `useDict` 返回的 `getLabel`、`getCode`、`getItemByCode` 等方法。
- 需要把接口返回值、静态数组或字典统一转为选择器 options 时，优先沿用 `src/hooks/useSelectOptions.ts`，不要重复写映射逻辑。

### 文件上传、下载、预览

- 上传能力优先使用 `src/components/upload/custom-upload.vue`，不要每个页面各写一套文件类型、大小、数量、预览和回填逻辑。
- 新页面只要涉及附件上传，优先复用 `custom-upload` 的 `fileTypes`、`fileMaxSize`、`limit`、`previewType` 等能力。
- 文件预览优先使用 `src/utils/previewFile.ts`、`src/components/file-preview/` 相关能力，不要自行拼接新页面预览链接。
- 下载二进制文件优先使用 `src/utils/downloadBlob.ts`，不要在页面里重复创建 `Blob`、`a` 标签和下载回收逻辑。
- 文件详情弹窗预览优先复用 `file-preview-modal.vue`，普通新开页预览优先走 `previewFile(id, 'page')`。

### 请求、接口、Loading

- 所有接口请求优先使用 `src/utils/http/` 下的统一封装，如 `request`、`httpGet`、`httpPost`、`httpPut`、`httpDelete`、`httpUpload`、`httpDownload`。
- 接口定义优先落在 `src/api/`，页面只负责调用，不直接堆叠请求配置和响应处理细节。
- 页面级或块级加载效果优先使用 `v-loading` 指令，不要在每个容器里重复写一套自定义 loading 遮罩。
- 需要全局 loading 效果时，优先走请求层支持的 `showLoading` 能力，不要再自己维护额外全局弹层。

### 权限、按钮显隐、菜单控制

- 按钮级权限优先使用 `v-action`。
- 一组权限或复合权限控制优先使用 `v-actions`。
- 不要在模板中大量手写 `v-if="hasPermission(...)"` 去替代现有权限指令，除非当前场景确实不适合使用指令。
- 路由、菜单、页面级权限应优先沿用 `menu store + permissionGuard + utils/auth` 既有链路，不要自行再发明一套权限来源。

### 自定义组件、双向绑定、源码定位

- 新建支持 `v-model` 的自定义表单组件时，优先复用 `src/hooks/useModelValue.ts`，不要每个组件手写一遍同步逻辑。
- 需要在开发环境快速打开源码位置时，优先使用 `src/components/sourcecode-opener/index.vue` 与 `openFileInEditor`，主要用于示例页、调试页和开发辅助场景。

### 低代码、布局、页签

- 低代码表单、动态表单渲染优先使用 `ld-vform` 相关能力，不要绕开现有 `vform` 体系重做一套表单引擎。
- 布局、主题、折叠、页签、菜单展示优先走 `layout store`、`tags store` 与 `pro-layout` 现有机制，不要在页面层自行维护布局状态。

## 样式使用约束

- 页面布局与基础排版优先复用现有全局样式类和页面壳，不要每个页面重新定义同类容器样式。
- 简单布局、间距、对齐、宽高、显隐、flex 排布等，优先使用现有 `TailwindCSS` 工具类。
- 组件级、页面级、结构性样式，以及对 Ant Design Vue / ElementUI 组件的定制覆盖，优先使用 `less`。
- 全局通用样式应放在 `src/style/`，不要把可复用样式长期散落在页面局部。
- 查询表单优先复用 `.c-search-form`，详情表单优先复用 `.c-detail-form`。
- 主题相关颜色优先使用 CSS 变量与现有主题体系，不要在大量页面中直接写死同一主题色。
- 只有非常轻量、动态、一次性的展示需求才考虑少量内联样式；常规场景优先类名或 `less`。
- `scoped less` 是页面和组件局部样式的默认选择；只有确需影响第三方子组件时，才谨慎使用 `::v-deep`。
- 修改样式前，先确认是否已有类似页面、类似组件或 `demo` 示例可复用其结构与 class 组织方式。

## 代码编写方式约束

- 先查公共能力，再写业务实现；先组装已有能力，再考虑新增代码。
- 新页面优先参考 `src/views/demo/` 中的示例写法，尤其是 `demo/crud`、`demo/request`、`demo/vform`。
- 同类页面应保持类似结构：查询区、操作区、表格区、分页区、详情区的代码组织尽量统一。
- 公共逻辑优先抽到 `hooks/`、`utils/`、`components/`，不要把同一逻辑复制到多个页面。
- 对外部依赖或公共组件的使用方式，应先和仓库已有写法保持一致，再考虑新风格。
- 如果一个业务场景已经有明确公共能力，新增代码时默认必须使用该公共能力；如不使用，应有明确理由。

## 类型与路径约定

- 使用 `@/` 指向 `src/`，使用 `#/` 指向 `types/`。
- 全局类型、模型类型、shim、自动导入声明统一放在 `types/`。
- 涉及公共模型时优先补充到 `types/model/`，不要把跨模块类型散落在页面文件中。

## 编码风格与实现约束

- 保持现有风格：双引号、无分号、注释精简。
- 尽量延续当前文件写法，不做无必要的格式重构。
- Vue 页面优先遵循现有目录组织与命名方式，不随意改目录层级。
- 优先复用已有组件、hooks、utils、store，而不是新起一套并行实现。
- 页面层只保留页面编排逻辑；通用能力应沉淀到 `components/`、`hooks/`、`utils/`、`store/`。
- 接口调用应进入 `api/` 或统一请求层，不要在视图文件里散写请求细节。
- 权限判断优先走现有权限工具和权限指令，不要在模板中堆大量重复判断。
- 涉及列表页、详情页、查询区、分页区时，优先参考 `demo/crud` 与 `page-wrapper` 现有模式。

## 代码规范与格式化要求

- 本项目默认以 `ESLint`、`Prettier`、`Stylelint` 作为代码规范和格式化约束。
- JavaScript、TypeScript、Vue 脚本部分改动后，应至少通过 `ESLint` 规则校验。
- 文本格式、引号、缩进、换行等风格问题，以 `Prettier` 结果为准。
- `less`、`css`、`vue` 中的样式改动，除格式化外还应遵循 `Stylelint` 规则。
- 只要修改了代码，就必须对改动文件进行格式化，不能只改逻辑不整理格式。
- 不要在一次任务中顺手大面积重排无关文件；格式化范围应优先控制在当前改动文件。
- 如无特殊原因，优先使用项目现有命令进行修复，而不是手工调整到“看起来差不多”。

## 改动后的校验要求

- 修改 `src/**/*.{js,ts}` 后，至少对改动文件执行 `eslint --fix` 或等效校验。
- 修改 `src/**/*.vue` 后，至少保证对应文件经过 `eslint --fix`、`prettier --write`，涉及样式时还应满足 `stylelint --fix`。
- 修改 `src/**/*.{less,css}` 后，至少保证对应文件经过 `stylelint --fix` 与 `prettier --write`。
- 修改文档、JSON 等文本文件后，至少执行 `prettier --write` 保持格式统一。
- 如果任务范围允许，优先执行 `npm run lint`；如果只涉及少量文件，也应至少保证改动文件被正确格式化和校验。

## 修改时的目录选择建议

- 改接口：优先看 `src/api/` 与 `src/utils/http/`。
- 改登录、权限、菜单：优先看 `src/router/guard/`、`src/store/modules/user.ts`、`src/store/modules/menu.ts`、`src/utils/auth/`。
- 改布局、主题、侧边栏、标签页：优先看 `src/layout/`、`src/components/pro-layout/`、`src/store/modules/layout.ts`、`src/store/modules/tags.ts`、`src/utils/theme/`。
- 改全局组件或表单包装：优先看 `src/components/`。
- 改公共逻辑复用：优先看 `src/hooks/`、`src/utils/`、`src/mixin/`。
- 改构建、自动导入、组件自动注册：优先看 `build/`、`vite.config.ts`、`types/auto-imports.d.ts`、`types/components.d.ts`。
- 改样式体系：优先看 `src/style/` 与相关组件局部样式。

## 依赖与锁文件要求

- `package-lock.json` 是项目环境稳定性的一部分，不要随意删除重建。
- 团队协作时优先共享已验证可用的 `package-lock.json`。
- 如遇到安装后启动失败，优先检查锁文件变化、间接依赖漂移和 `npm` 版本，而不是先怀疑业务代码。
- `package.json` 中如存在 `overrides`，变更前要确认团队最低 `npm` 版本是否支持。

## 验证要求

- 涉及环境、依赖、脚本改动时，优先执行 `npm run check:node`。
- 涉及 TypeScript、路由、store、hooks、工具或配置改动时，按需执行 `npm run check:ts`。
- 涉及构建、插件、样式打包、资源加载时，按需执行 `npm run build`。
- 未经验证，不要宣称构建通过、环境兼容或问题已修复。

## 知识库 V1.0.1 测试文档（跨仓库）

- 测试资产在 Obsidian `ProjectsRoot/projects/知识库管理平台/tests测试/V1.0.1/`。
- 在本仓库用 Cursor 创建 TC 用例/执行实例时，可说 **按 `create-v101-tc-test-suite` skill**，或 @ 该目录下的 `AI-Agent-创建TC测试套件.md`。
- 项目级 Skill 路径：`.cursor/skills/create-v101-tc-test-suite/SKILL.md`。

## 不建议的做法

- 不要绕开统一请求层直接到处创建请求实例。
- 不要把公共逻辑直接写死在页面组件里。
- 不要随意替换布局体系、权限链路、动态菜单注册方式。
- 不要因为一个页面需求就升级核心栈或替换主插件。
- 不要只看顶层依赖版本判断问题，构建与启动失败常常与间接依赖、锁文件和本地环境有关。

## 平台版本与发布文档

- 知识库管理平台版本历史由后端仓库统一维护：`../app-knowledge-service/docs/versions/版本历史.md`。
- 每次上线的配置单及 SQL 等附件统一维护在：`../app-knowledge-service/docs/releases/V{版本号}/`。
- 前端变更必须登记到同一平台版本，不在本仓库另建一套版本历史。
- 版本内容必须以 Git 提交、Tag、代码和现有文档为依据；未生成的 Tag、镜像号和生产配置必须标记为“待确认”。
