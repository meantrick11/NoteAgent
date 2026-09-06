FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
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

# Bake MiniLM so runtime can use EMBEDDING_LOCAL_FILES_ONLY=true.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', cache_folder='var/models')"

COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p notes var/logs chromadb_persist

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
