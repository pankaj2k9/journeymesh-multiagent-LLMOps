# =============================================================================
# JourneyMesh backend - FastAPI + LangGraph
# Every journey, intelligently connected.
#
#   docker build -t journeymesh-api ./backend
#   docker run --rm -p 8000:8000 --env-file backend/.env journeymesh-api
# =============================================================================

# ---- Stage 1: build the dependency tree in an isolated virtualenv -----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---- Stage 2: the runtime image --------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8000

# libpq for psycopg, curl for the health check. No build toolchain in runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 journeymesh

COPY --from=builder /opt/venv /opt/venv

WORKDIR /srv/journeymesh
COPY --chown=journeymesh:journeymesh . .

# The image must never carry a developer's environment file.
RUN rm -f .env && chown -R journeymesh:journeymesh /srv/journeymesh

USER journeymesh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/srv/journeymesh/docker-entrypoint.sh"]
CMD ["serve"]
