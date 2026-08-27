# Enterprise Knowledge RAG

企业知识库 RAG 平台：从文档解析 → 结构化切块 → 知识图谱 → 混合检索 → 可溯源问答的完整链路。

## 系统组成

| 目录 | 说明 | 技术栈 |
|------|------|--------|
| [`python-service/`](python-service/) | 解析 / 检索 AI 引擎服务 | Python (FastAPI) |
| [`java-service/`](java-service/) | 知识库平台后端（知识库 / 文件 / 图谱 / QA / 审计） | Java (Spring Cloud, MyBatis-Plus) |
| [`knowledge-web/`](knowledge-web/) | 知识库管理前端（含知识图谱可视化） | Vue 3 + Ant Design Vue + G6 |

## 核心链路

```
文件中心 ──► python-service 解析（OCR / 多模态 / docx / pdf）
                  │
                  ├─► Middle Document ──► Catalog / AST / Container 切块
                  │         └─► Chunk ──► 结构化字段抽取 ──► MySQL
                  ├─► 知识图谱构建 ──► Neo4j（实体 / 关系 / 社区 / 治理）
                  └─► 向量化 ──► Elasticsearch（embedding + bm25 混合检索）
                          │
java-service 请求检索 ──► python-service（query 理解 / 图谱检索 / 证据对齐 / 置信度）
                          └─► 答案预构建 + 引用溯源 ──► 前端展示
```

## 核心能力

- **文档解析**：PDF（Paddle 版面 / 千帆 VLM 多模态 OCR）、docx、txt、图片；分层多图解析 + 图片字节剥离
- **切块**：目录（Catalog）切块、AST 切块、容器切块；章节摘要、锚点单元
- **知识图谱**：业务字段 / 实体关系抽取 → Neo4j 建图 → GraphRAG 社区 + 治理 + 受限扩散检索
- **混合检索**：query 理解 → ES 向量 + BM25 → 图谱检索 → 重排 → 证据对齐 → 置信度打分
- **溯源问答**：答案预构建、引用格式化、多轮上下文、审计留痕

## 模块结构

- **python-service**：`src/danbao_poc/` 为解析/检索引擎核心包，入口在 `src/danbao_poc/api/`（parse-service、retrieve-service）；`doc/` 为方案与设计文档；`deploy/` 为部署配置模板
- **java-service**：Maven 多模块（`app-knowledge-service` 服务端 + `app-knowledge-api` 接口/DTO），SQL 脚本在 `src/main/resources/sql/`，数据库设计见 `docs/`
- **knowledge-web**：Vue 3 + Vite，`src/views/knowledge/` 为知识库业务页面

## 快速开始

各子项目分别有 README 与配置模板（`.env.example`、`application-local.yml.example`）。运行依赖 MySQL、Elasticsearch、Neo4j、Redis 与文件中心，配置模板中已注明所需字段。

> ⚠️ 本仓库仅含代码与脱敏配置示例。真实密钥、数据库密码、API Key 一律不入库。
