ARG PYTHON_BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/sdndopm/python:3.10-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV PIP_NO_CACHE_DIR=1
ENV PIP_INDEX_URL=https://mirrors.huaweicloud.com/repository/pypi/simple
ENV PIP_TRUSTED_HOST=mirrors.huaweicloud.com
ENV APP_PORT=20751
ENV LOG_DIR=/home/appuser/app/logs
# Nacos env vars are managed by application.yml profile config.
# APP_ENV selects the profile (dev/sit/prd), each with its own NACOS_SERVER_ADDR.

# LLM timeout overrides (knowledge extraction needs more time)
ENV KNOWLEDGE_TIMEOUT=300
ENV KNOWLEDGE_MAX_INPUT_CHARS=15000
ENV ANSWER_PREBUILD_TIMEOUT=300

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.110,<1" \
    "uvicorn[standard]>=0.27,<1" \
    "elasticsearch>=7.17,<8" \
    "neo4j>=5.26,<6" \
    "openpyxl>=3.1,<4" \
    "pandas>=2.2,<3" \
    "pyarrow>=15,<16" \
    "pymupdf>=1.24,<2" \
    "pymysql>=1.1,<2" \
    "PyYAML>=6,<7" \
    "python-docx>=1.1,<2" \
    "redis>=5,<6" \
    "requests>=2.31,<3" \
    "tenacity>=9,<10" \
    "python-multipart>=0.0.9,<1" \
    "jieba>=0.42"

COPY src ./src
COPY cypher ./cypher

RUN mkdir -p /app/data /home/appuser/app/logs

EXPOSE 20751

CMD ["sh", "-c", "mkdir -p ${LOG_DIR:-/home/appuser/app/logs} && uvicorn danbao_poc.api.app_service:app --host 0.0.0.0 --port ${APP_PORT:-20751} 2>&1 | tee -a ${LOG_DIR:-/home/appuser/app/logs}/app.log"]
