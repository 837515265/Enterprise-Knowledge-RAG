# 企业知识问答解析检索服务

当前实现聚焦 `guarantee_plan`，分为两个应用服务：

- `parse-service`：根据 `kb_id + file_node_id` 从文件中心取文件，调用 OCR，生成 middle document、chunk、结构化字段、业务图谱输入，并直接写入 MySQL。执行单位始终是“单文件任务”。
- `retrieve-service`：根据 `kb_id + file_node_id` 从 MySQL 读取当前解析结果，写入 Elasticsearch 和 Neo4j，并提供查询接口。

开发联调时也支持跳过文件中心，但仍然仿照正式链路：为每个本地 PDF 生成稳定 `file_node_id`，再提交单文件任务。

当前解析路由策略：

- `txt / md`：直接读取文本，不走 OCR
- `docx`：直接提取段落文本，不走 OCR
- `pdf`：统一走 OCR，因为正式方案需要版面结构
- 图片：统一走 OCR
- 其他类型：当前 P0 直接报不支持

当前 OCR 有两种后端：

- `paddle_layout`：默认主链路。整 PDF 或图片直接送 Paddle，返回版面结构 JSON，再归一化成 `middle_document`
- `qianfan_vlm`：PDF 先逐页渲染成图片，再逐页调用 OpenAI 兼容多模态 OCR，输出页级 Markdown，再归一化成 `middle_document`

数据库、Elasticsearch、Neo4j、Redis 默认使用现网已有实例，不由本项目 `docker compose` 拉起。

## 一、配置

复制配置模板：

```powershell
copy .env.example .env
```

你需要填写的配置都在：

- [D:\pyproject\bisheng\danbao-poc\.env.example](D:/pyproject/bisheng/danbao-poc/.env.example)

重点字段：

- `MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE`
- `ELASTICSEARCH_URL`
- `REDIS_URL`
- `NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD`
- `FILE_CENTER_BASE_URL`
- `NACOS_* / FILE_CENTER_SERVICE_NAME`（需要注册发现时填写）
- `OCR_BACKEND`
- `PADDLE_OCR_WEB_URL` 或 `PADDLE_OCR_PREDICT_URL`
- `QIANFAN_OCR_BASE_URL / QIANFAN_OCR_MODEL / QIANFAN_OCR_API_KEY`
- `DEFAULT_MODEL_*`
- `QUERY_UNDERSTANDING_*`
- `EMBEDDING_*`
- `RERANK_*`
- `FALLBACK_MODEL_*`

文件中心有两种配置方式：

- 固定地址：填写 `FILE_CENTER_BASE_URL`，例如 `http://10.0.0.8:8080/api-ai-center`
- Nacos 发现：设置 `NACOS_ENABLED=true`、`NACOS_SERVER_ADDR`、`FILE_CENTER_SERVICE_NAME`，必要时补 `FILE_CENTER_CONTEXT_PATH`

开启 Nacos 后，`parse-service` 会以 `NACOS_PARSE_SERVICE_NAME` 注册，`retrieve-service` 会以 `NACOS_RETRIEVE_SERVICE_NAME` 注册。默认服务名分别是 `danbao-parse-service` 和 `danbao-retrieve-service`。

Docker 部署时容器内服务端口是 `8000`，因此 compose 默认用 `NACOS_PARSE_REGISTER_PORT=8000`、`NACOS_RETRIEVE_REGISTER_PORT=8000` 注册到 Nacos。若调用方不在同一 Docker 网络里，需要在 `.env` 中把 `NACOS_REGISTER_IP` 改成宿主机 IP，并把两个注册端口改成宿主机映射端口，例如 `21084`、`21085`。

## 二、启动

当前 `docker-compose.yml` 只起两个应用容器：

- `parse-service`
- `retrieve-service`

启动：

```powershell
docker compose up -d --build
```

默认对外端口：

- `parse-service`: `21084`
- `retrieve-service`: `21085`

## 二点一、本地无 Docker 启动

如果本地没有 Docker，可以直接用 `uv` 起两个服务。

1. 复制本地开发环境模板：

```powershell
copy deploy\local.dev.env.template .env.local
```

2. 填写 `.env.local` 里缺失的配置，尤其是：

- `MYSQL_*`
- `REDIS_URL`
- `FILE_CENTER_BASE_URL`
- 如需走 Nacos：`NACOS_ENABLED / NACOS_SERVER_ADDR / FILE_CENTER_SERVICE_NAME`
- `OCR_BACKEND`
- `PADDLE_OCR_WEB_URL` 或 `PADDLE_OCR_PREDICT_URL`
- `QIANFAN_OCR_*`
- `DEFAULT_MODEL_* / EMBEDDING_* / RERANK_*`

说明：

- `OCR_BACKEND=paddle_layout` 时：
  - `PADDLE_OCR_WEB_URL` 可以直接填 `http://124.128.251.51:8118`
  - 代码会自动补成 `http://124.128.251.51:8118/api/ocr`
  - 也可以手工写完整接口
- `OCR_BACKEND=qianfan_vlm` 时：
  - `QIANFAN_OCR_BASE_URL` 建议填 OpenAI 兼容根地址，例如 `http://host:port/v1`
  - 如果你只填根地址，代码会自动补 `/v1`
  - PDF 会逐页渲染成图片，再逐页调用多模态 OCR

3. 启动服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

4. 只做健康检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1 -HealthOnly
```

5. 停止服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-local.ps1
```

## 三、接口

### 1. 解析

`POST /api/v1/parse/files`

```json
{
  "kb_id": 1024,
  "file_node_id": 889001,
  "profile": "guarantee_plan",
  "async_mode": false,
  "return_payload": false
}
```

说明：

- `async_mode=false`：同步执行当前文件，接口返回最终解析结果
- `async_mode=true`：只提交单文件任务，立即返回 `task_id`

任务状态接口：

`GET /api/v1/parse/tasks/{task_id}`

批量提交接口：

`POST /api/v1/parse/files:batch-submit`

```json
{
  "kb_id": 1024,
  "items": [
    {
      "file_node_id": 100000000000001,
      "profile": "guarantee_plan",
      "local_file_path": "D:\\pyproject\\bisheng\\data\\danbaofangan\\按揭农业贷—邹城市草莓产业集群担保服务方案.pdf"
    },
    {
      "file_node_id": 100000000000002,
      "profile": "guarantee_plan",
      "local_file_path": "D:\\pyproject\\bisheng\\data\\danbaofangan\\另一个文件.pdf"
    }
  ]
}
```

这个接口只负责**批量提交多个单文件任务到 Redis 队列**，不会在一个 HTTP 请求里串行把所有文件 OCR/LLM 跑完。

### 1.1 本地目录开发模式

开发阶段不走文件中心时，仍然建议按正式方式提交单文件任务，只是额外传入 `local_file_path`：

```json
{
  "kb_id": 1024,
  "file_node_id": 100000000000001,
  "profile": "guarantee_plan",
  "local_file_path": "D:\\pyproject\\bisheng\\data\\danbaofangan\\按揭农业贷—邹城市草莓产业集群担保服务方案.pdf",
  "return_payload": false
}
```

测试脚本已支持扫描目录、生成稳定 `file_node_id`，并批量提交单文件任务，再轮询每个任务状态：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1 -RunParseDirectory -KbId 1024 -DirectoryPath "D:\pyproject\bisheng\data\danbaofangan"
```

也可以单独测试一个异步单文件任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-local.ps1 -RunParseAsync -KbId 1024 -FileNodeId 889001
```

### 2. 索引

`POST /api/v1/index/files`

```json
{
  "kb_id": 1024,
  "file_node_id": 889001,
  "operation": "rebuild"
}
```

### 2.1 Chunk 局部索引

`POST /api/v1/index/chunks`

```json
{
  "kb_id": 1024,
  "file_node_id": 889001,
  "chunk_ids": [10001, 10002],
  "operation": "upsert"
}
```

### 2.2 QA 索引

`POST /api/v1/index/qas`

```json
{
  "kb_id": 1024,
  "qa_ids": [20001, 20002],
  "operation": "upsert"
}
```

### 3. 检索

`POST /api/v1/retrieve/query`

```json
{
  "kb_id": 1024,
  "query": "邹城草莓最高额度是多少",
  "top_k": 5
}
```

## 四、当前范围

已实现：

- 文件中心下载
- OCR 标准化
- Paddle / Qianfan VLM 双 OCR 后端路由
- Redis 单文件任务状态与并发控制
- 担保方案章节切分
- 核心字段抽取
- 业务图谱输入生成
- MySQL 入库
- Elasticsearch 索引
- Elasticsearch 向量索引
- Neo4j 图谱导入
- QueryUnderstanding
- QA / 图谱 / BM25 / 向量 四路召回
- rerank 重排
- EvidenceGroup 聚合返回
- 文件全量索引、Chunk 局部索引、QA 局部索引

未实现：

- 多 Profile 扩展
- 业务审核流联调
