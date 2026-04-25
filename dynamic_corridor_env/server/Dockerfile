ARG BASE_IMAGE=ghcr.io/meta-pytorch/openenv-base:latest
FROM ${BASE_IMAGE}

WORKDIR /app/env

RUN if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh && \
        mv /root/.local/bin/uv /usr/local/bin/uv && \
        mv /root/.local/bin/uvx /usr/local/bin/uvx; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    libatomic1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libglu1-mesa \
    libsm6 \
    libice6 \
    libxrandr2 \
    libxi6 \
    libxfixes3 \
    libxcursor1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-editable; \
    else \
        uv sync --no-install-project --no-editable; \
    fi

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --find-links https://sumo.dlr.de/daily/wheels/ eclipse-sumo

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-editable; \
    else \
        uv sync --no-editable; \
    fi

ENV PATH="/app/env/.venv/bin:$PATH"
ENV PYTHONPATH="/app/env:$PYTHONPATH"
ENV SUMO_BINARY=sumo
ENV DYNAMIC_CORRIDOR_NET_FILE=/app/env/nets/pune-5/pune-5.net.xml
ENV DYNAMIC_CORRIDOR_ROUTE_FILE=/app/env/nets/pune-5/pune-5.rou.xml
ENV DYNAMIC_CORRIDOR_DELTA_TIME=5
ENV DYNAMIC_CORRIDOR_MAX_SECONDS=900
ENV DYNAMIC_CORRIDOR_SEED=42
ENV ENABLE_WEB_INTERFACE=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "cd /app/env && uvicorn server.app:app --host 0.0.0.0 --port 8000"]
