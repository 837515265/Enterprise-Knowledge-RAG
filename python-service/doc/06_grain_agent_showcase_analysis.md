# grain_agent_showcase 项目分析报告

## 1. 项目概述

grain_agent_showcase 是一个**纯静态前端展示项目**（HTML/CSS/JS），包装 RAGFlow Agent 分享接口。为**山东省粮食和物资储备局**提供品牌化的政策法规问答界面。

**6 个文件**：
- `index.html` — 页面结构
- `styles.css` — 视觉设计（1026 行）
- `app.js` — RAGFlow API 集成 + 流式聊天（971 行）
- `config.js` — 配置和品牌文本
- `favicon.svg` — 图标
- `README.md`

**无后端代码、无 Python、无 RAG 管道**。所有智能能力委托给 RAGFlow 后端（`http://124.128.251.51:5002`）。

---

## 2. 文件处理

**本项目不处理文件**。从前端引用渲染代码可观察 RAGFlow 后端返回的引用元数据：

- `doc_name` / `document_name` — 源文档名
- `content_with_weight` / `content` — 加权 chunk 内容
- `dataset_name` / `kb_name` — 知识库名
- `document_id` — 文档 ID
- `page` — 页码
- `position` — 文档内位置

---

## 3. 文件解析

**本项目不解析文档**。仅处理 RAGFlow API 的 **SSE 流式响应**：

`processSseBlock`（`app.js`）：
- ReadableStream 读取字节
- 双换行 `\n\n` 分割 SSE 块
- 解析 `data:` 前缀行 → JSON
- 按 `event` 字段分发到 `handleAgentEvent`

事件类型：`node_started`（工作流节点）, `message`（增量文本）, `message_end`（含引用）, `workflow_finished`, `user_inputs`（中途参数收集）

---

## 4. Chunk 划分

**本项目不分块**。但有两种显示分段：

**思考/推理分离**（`splitThoughtSections`）：
- 扫描 `<think>`/`` 标签对
- 分为 `{type: "plain"}` 和 `{type: "think"}` 段
- 思考段渲染为可折叠 `<details>` 块

**纯文本结构渲染**（`renderPlainBlock`）：
- 按换行分割
- 分类为无序列表（`- `）、有序列表（`1. `）、段落
- 连续同类项分组为 `<ul>`/`<ol>`

---

## 5. 数据存储

**无数据库、无持久化、无服务端状态**。纯内存 JavaScript state：

```javascript
const state = {
  config, meta, sessionId, agentReady,
  isStreaming, messages[], beginFields[],
  beginValues{}, pendingStatusText, currentAssistantId
};
```

无 localStorage/IndexedDB/Cookie。重置会话时所有数据丢失。

---

## 6. 检索方法

**本项目不执行检索**。通过两个 API 端点与 RAGFlow 交互：

**GET `/api/v1/agentbots/{shared_id}/inputs`**：
获取 Agent 元数据（title, prologue, mode, inputs）

**POST `/api/v1/agentbots/{shared_id}/completions`**：
发送查询 + Begin 参数 + session_id
- `quote: true` → 返回引用
- `stream: true` → SSE 流式

引用渲染为卡片：文档名、chunk 内容、知识库名、文档 ID、页码、位置。

### 引用格式兼容（`normalizeReferenceList`）

处理 RAGFlow 不同版本的引用格式：
- 直接数组
- `reference.chunks`（数组或对象）
- `reference.doc_aggs`（对象）
- 通用对象 `Object.values(reference)`

---

## 7. 核心技术亮点

### 7.1 配置分层 + 品牌归一化

`buildConfig`：URL 参数 > `config.js` 默认值 > 解析 `share_url`

`normalizeBrandText`：将 "国家粮食和物资储备局" 统一替换为 "山东省粮食和物资储备局"。

### 7.2 Begin 参数输入类型推断

`normalizeInputType`：
- 有 `options` → `<select>`
- type 含 "bool" → 布尔 select
- type 含 "number" → `<input type="number">`
- 否则 → `<input type="text">`

### 7.3 中途用户输入收集

RAGFlow 工作流发出 `user_inputs` 事件时，前端动态渲染新参数输入字段。

### 7.4 SSE 缓冲策略

行缓冲：字节块解码累积 → `\n\n` 分割 → 最后不完整块保留到下次读取。

---

## 8. danbao-poc 可借鉴总结

grain_agent_showcase 是纯前端包装，无独立 RAG 管道。可借鉴的点有限：

| 优先级 | 借鉴点 | 预期收益 |
|--------|--------|---------|
| P3 | **SSE 流式响应格式** | danbao-poc API 可提供类似流式接口 |
| P3 | **引用格式兼容层** | 支持多版本引用格式 |
| P3 | **可折叠思考过程展示** | 前端展示 LLM 推理过程 |

**总结**：此项目主要价值在于展示 RAGFlow Agent 分享接口的使用方式，可作为 danbao-poc 前端集成的参考。
