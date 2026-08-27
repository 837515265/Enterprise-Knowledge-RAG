# SQL 问数知识 Profile 设计

## 1. 定位

Profile 代码：`sql_analytics`

展示名称：`智能问数/NL2SQL知识`

该 Profile 用于解析已经过治理的 SQL 问数知识对象，而不是普通自然语言文档。它适配：

- 单对象 Markdown：一个文件只包含一个稳定 `objectId`；
- 合并发布 TXT：使用 `BEGIN_KNOWLEDGE_CHUNK / END_KNOWLEDGE_CHUNK` 包围多个对象；
- 对象类型：`SCENE`、`SCHEMA`、`TABLE`、`FIELD`、`DIMENSION`、`ENUM`、`TERM`、`METRIC`、`TIME_RULE`、`VERIFIED_SQL`。

## 2. 核心边界

SQL 问数知识本身已经有稳定对象边界、对象类型和证据标识，因此解析时必须遵循：

1. 一个 `objectId` 生成一个原子 primary chunk；
2. 不使用 LLM 重新规划目录或拆分对象；
3. 不使用 LLM 改写指标公式、业务定义和 SQL；
4. 不生成自动 QA，不用 QA 文本替代原始知识对象；
5. 不构建通用知识图谱；
6. 检索以 BM25、向量、结构化对象字段为主；
7. `objectId`、`objectType`、`sceneCode` 必须进入 chunk metadata；
8. 未发布、未验证或禁止检索的对象不得进入可检索 chunk。

## 3. 与 SQL Planner 逻辑知识源的关系

`sql_analytics` 是解析策略，不取代 SQL Planner 的逻辑知识源隔离。

同一个知识库仍建议注册为三个逻辑知识源：

| 逻辑知识源 | objectType | 文件范围 |
| --- | --- | --- |
| `GUARANTEE_TERM` | `TERM` | 术语文件 fileId |
| `GUARANTEE_METRIC` | `METRIC` | 指标文件 fileId |
| `GUARANTEE_VERIFIED_SQL` | `VERIFIED_SQL` | 已验证 SQL 文件 fileId |

Profile 负责确保每个文件内部的对象边界和元数据正确；Planner 注册表负责按 fileId 隔离检索范围。

## 4. 确定性解析流程

```text
源文件
  -> 识别单对象 Markdown 或 BEGIN/END 合并格式
  -> 解析 objectId/objectType/sceneCode 等元数据
  -> 执行发布校验
  -> 每个对象生成一个 knowledge_object
  -> 生成一个 small_chunk 原始证据单元
  -> 写入 structured + BM25 + vector 索引
```

不会进入以下通用步骤：

- LLM catalog；
- LLM section summary；
- LLM knowledge extraction；
- LLM answer prebuild；
- graph builder。

## 5. 发布校验

所有对象至少需要：

- `objectId`；
- `objectType`；
- `sceneCode`。

不同类型的附加要求：

| 类型 | 必需字段 |
| --- | --- |
| `TERM` | `termCode`、定义 |
| `METRIC` | `metricCode`、业务定义、`aggregationType`、SQL 表达式、`reviewStatus=VERIFIED` |
| `VERIFIED_SQL` | `exampleCode`、用户问题、SQL、`reviewStatus=VERIFIED`、`retrievalEnabled=true` |
| `TABLE` | `tableName` |
| `FIELD` | `fieldName` |
| `DIMENSION` | `dimensionCode` |

`TERM/METRIC/VERIFIED_SQL` 的 `objectId` 前缀分别校验为：

- `term.`；
- `metric.`；
- `verified_sql.`。

不满足条件的对象写入 `catalog_artifact.rejected_objects`，不进入索引；整个文件没有任何可发布对象时，解析任务明确失败。

## 6. Chunk 元数据

每个 primary chunk 至少保留：

```json
{
  "profile": "sql_analytics",
  "object_id": "metric.METRIC_YEAR_NEW_BIZ_COUNT",
  "object_type": "METRIC",
  "scene_code": "GUARANTEE_BI",
  "metric_code": "METRIC_YEAR_NEW_BIZ_COUNT",
  "review_status": "VERIFIED",
  "catalog_source": "deterministic_sql_analytics",
  "content_role": "knowledge_object",
  "confidence": "VERIFIED"
}
```

向量文本优先使用名称、别名、示例问题、业务定义、指标口径和易错点；BM25 文本保留完整原文、对象编码、物理字段和 SQL。

## 7. Profile 选择

推荐上传时显式传递：

```json
{
  "profile": "sql_analytics"
}
```

兼容别名：`智能问数`、`SQL问数`、`经营问数`、`sql_planner`、`nl2sql`。

如果平台仍传 `general_document`，解析完成后检测到 `objectType: METRIC/TERM/VERIFIED_SQL` 或 `BEGIN_KNOWLEDGE_CHUNK` 标记，也会自动修正为 `sql_analytics`。

## 8. 上线验证顺序

1. 部署包含 fallback 参数修复和 `sql_analytics` Profile 的版本；
2. 只重试一个 `TERM`、一个 `METRIC`、一个 `VERIFIED_SQL` 文件；
3. 检查 `02_catalog_chunking.json`：`catalog_source` 应为 `deterministic_sql_analytics`；
4. 确认每个文件只有一个 primary object chunk，`objectId/objectType` 正确；
5. 确认没有 section-summary、knowledge-extraction、answer-prebuild 模型调用；
6. 使用检索接口分别按术语、指标、SQL 问题验证召回；
7. 再批量重试剩余失败任务；
8. 将新的成功 fileId 更新到 SQL Planner 知识源注册表。

## 9. 当前离线验证结果

使用现有发布包验证：

- 单对象 Markdown：`46 TERM + 41 METRIC + 60 VERIFIED_SQL = 147` 个文件全部解析通过；
- 三个合并 TXT：分别生成 `46`、`41`、`60` 个原子对象；
- 拒绝对象数：`0`；
- 对象跨 chunk 混合：`0`。
