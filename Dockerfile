# ---------- 前端构建阶段 ----------
# 只用官方 Node 镜像把 Vue 产物编译出来；运行容器里没有 Node，也没有新的端口。
# 用 Node 24（Vite 7 的 engines 是 ^20.19 || >=22.12，24 在范围内）。
FROM node:24-bookworm-slim AS frontend-build

WORKDIR /build/frontend
# 先只拷依赖清单，package.json 没变时这一层可以复用。
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts 把产物写到 ../src/NoteAgent/HttpApi/WebFrontend/dist，
# 即 /build/src/NoteAgent/HttpApi/WebFrontend/dist，下面直接从这里取。
RUN npm run build


FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HUB_DISABLE_TELEMETRY=1

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY main.py alembic.ini ./
COPY alembic ./alembic

# 前端产物放进包目录：项目是 editable 安装，运行时就从这个路径读 index.html。
# 必须放在 COPY src 之后，否则会被源码那一层覆盖掉。
COPY --from=frontend-build /build/src/NoteAgent/HttpApi/WebFrontend/dist ./src/NoteAgent/HttpApi/WebFrontend/dist

# Lock resolves CUDA torch on Linux. Skip those packages and install the CPU wheel.
RUN uv sync --frozen --no-dev \
        --no-install-package torch \
        --no-install-package cuda-bindings \
        --no-install-package cuda-toolkit \
        --no-install-package nvidia-cublas \
        --no-install-package nvidia-cudnn-cu13 \
        --no-install-package nvidia-cusparselt-cu13 \
        --no-install-package nvidia-nccl-cu13 \
        --no-install-package nvidia-nvshmem-cu13 \
        --no-install-package triton \
    && uv pip install --python .venv/bin/python "torch==2.12.1" \
        --index-url https://download.pytorch.org/whl/cpu

# Bake the evaluated default model so runtime can use EMBEDDING_LOCAL_FILES_ONLY=true.
# 换模型时必须同时改这一行，否则镜像里没有权重、启动会失败。
ARG HF_ENDPOINT=https://hf-mirror.com
ENV HF_ENDPOINT=${HF_ENDPOINT}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small', cache_folder='var/models')"

COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p notes var/logs chromadb_persist

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
