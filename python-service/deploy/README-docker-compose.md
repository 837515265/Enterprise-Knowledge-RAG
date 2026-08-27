# Docker Compose 部署说明

适用场景：把 `danbao-poc` 部署到另一台开发环境服务器，由 Docker Compose 启动单个 `app-rag-doc` 容器，并注册到 Nacos。

Compose 不部署 MySQL、Redis、Elasticsearch、Neo4j、Nacos、文件中心或 Java 端服务。这些都按外部既有服务处理，通过 `.env.deploy` 配置连接地址。

容器内只监听一个端口 `20751`，同一端口提供解析、索引、检索接口：

- `/api/v1/parse/**`
- `/api/v1/index/**`
- `/api/v1/retrieve/**`
- `/api/v1/review/**`

## 1. 准备文件

把整个 `danbao-poc` 目录复制到目标服务器，或只复制以下内容：

- `Dockerfile`
- `docker-compose.yml`
- `pyproject.toml`
- `uv.lock`
- `src/`
- `scripts/`
- `cypher/`
- `deploy/docker-compose.env.template`

目标服务器需要已安装 Docker 和 Docker Compose v2。

## 2. 准备环境变量

在项目根目录执行：

```bash
cp deploy/docker-compose.env.template .env.deploy
```

然后编辑 `.env.deploy`：

- 填写现有 MySQL、Redis、ES、Neo4j 的连接信息。
- 填写 `NACOS_PASSWORD`。
- 如果目标服务器有多块网卡，必须设置 `NACOS_REGISTER_IP` 为 Java 服务能访问到的服务器 IP。
- 确认 `JAVA_PLATFORM_SERVICE_NAME=app-knowledge-service`。
- 确认 `FILE_CENTER_SERVICE_NAME=common-file-center`。
- 填写 OCR、LLM、Embedding、Rerank 的 URL 和 API Key。

`APP_PORT` 是宿主机发布端口，也是注册到 Nacos 的端口。默认：

```bash
APP_PORT=20751
PARSE_PORT=20751
RETRIEVE_PORT=20751
```

## 3. 构建并启动

```bash
docker compose --env-file .env.deploy up -d --build
```

查看日志：

```bash
docker compose logs -f parse-service
docker compose logs -f retrieve-service
```

这里必须带 `--env-file .env.deploy`，这样 `PARSE_PORT`、`RETRIEVE_PORT` 等 Compose 变量和容器内环境变量会使用同一份配置。

## 4. 健康检查

```bash
curl http://127.0.0.1:20751/health
curl http://127.0.0.1:20751/ready
```

`/ready` 中应能看到：

- `mysql.status=ok`
- `redis.status=ok`
- `file_center.status=ok`
- `java_platform.status=ok`
- retrieve-service 还应看到 `elasticsearch.status=ok`

## 5. 验证 Nacos 注册

在目标服务器进入容器检查服务自身视角：

```bash
docker compose exec parse-service python - <<'PY'
from danbao_poc.nacos_client import resolve_service_base_url
for name in ["app-knowledge-service", "common-file-center", "danbao-parse-service", "danbao-retrieve-service"]:
    print(name, "=>", resolve_service_base_url(name))
PY
```

也可以在 Nacos 控制台确认：

- `danbao-parse-service`
- `danbao-retrieve-service`

实例 IP 应是目标服务器可被 Java 访问的 IP，端口应是 `20751`。

## 6. 停止和重启

```bash
docker compose down
docker compose --env-file .env.deploy up -d --build
```

## 7. 常见问题

1. Nacos 中注册成了容器 IP，Java 访问不到：
   设置 `.env.deploy` 中的 `NACOS_REGISTER_IP` 为宿主机业务网卡 IP。

2. Nacos 中注册端口不对：
   确认 `.env.deploy` 中 `APP_PORT`、`PARSE_PORT`、`RETRIEVE_PORT`、`NACOS_PARSE_REGISTER_PORT`、`NACOS_RETRIEVE_REGISTER_PORT` 都是 `20751`。

3. 文件中心发现失败：
   确认 `FILE_CENTER_SERVICE_NAME=common-file-center`，并检查 Nacos namespace/group 是否一致。

4. Java 回调失败：
   确认 `JAVA_PLATFORM_SERVICE_NAME=app-knowledge-service`，`JAVA_PARSE_CALLBACK_PATH=/internal/platform/parse-callback`，以及服务鉴权头 `SERVICE_AUTH_HEADER/SERVICE_AUTH_TOKEN`。
