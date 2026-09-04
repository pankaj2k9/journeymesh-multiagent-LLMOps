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


# ---- Stage 3: the development image -----------------------------------------
# Local development only. It is `runtime` plus the test and lint tooling, so
# `make dev-test` and `make dev-migration` work inside the container instead of
# needing a virtualenv on the host.
#
# This stage is never built by CI or by the release workflow - both target
# `runtime` explicitly - so the published production image is byte-for-byte
# unaffected by anything below this line.
FROM runtime AS dev

USER root

# Build tooling is needed again: some dev dependencies have no wheel for this
# platform. It stays in this stage and never reaches `runtime`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

USER journeymesh

# The source is bind-mounted over this directory in docker-compose.dev.yml, so
# a code change needs no rebuild. Only a dependency change does.
ENV APP_ENV=development
