# =============================================================================
# JourneyMesh - single production image
# Every journey, intelligently connected.
#
# One container serves both halves, which is what the Render deployment runs:
#
#   /                  the React application
#   /trip/:tripId      the React application (client-side route)
#   /api/v1/*          FastAPI
#
#   docker build -t journeymesh .
#   docker run --rm -p 8000:8000 -e DATABASE_URL=... journeymesh
#
# The container binds 0.0.0.0 on $PORT, so Render's assigned port is used
# without any code change. Locally it falls back to 8000.
# =============================================================================

# ---- Stage 1: build the React bundle ----------------------------------------
FROM node:22-alpine AS frontend-builder

# Baked into the bundle. Empty is correct here: the browser calls /api on the
# same origin, which FastAPI serves.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

WORKDIR /build/frontend

# Dependencies first, so a source-only change reuses this layer.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY frontend/ ./

# `npm run build` type-checks before bundling, so a type error fails the image.
# Unit tests are the CI pipeline's job and are not repeated here.
RUN npm run build


# ---- Stage 2: build the Python environment ----------------------------------
FROM python:3.14-slim AS backend-builder

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
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---- Stage 3: the application ------------------------------------------------
FROM python:3.14-slim AS application

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8000 \
    SERVE_FRONTEND=true \
    FRONTEND_DIST_DIR=/srv/journeymesh/static

# libpq for psycopg, curl for the health check. No compiler, no npm, no source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 journeymesh

COPY --from=backend-builder /opt/venv /opt/venv

WORKDIR /srv/journeymesh

# The backend application. .dockerignore keeps caches, the local virtualenv and
# any .env out of the build context.
COPY --chown=journeymesh:journeymesh backend/ ./

# Only the built React assets travel into the final image - no node_modules, no
# frontend source, no build cache.
COPY --from=frontend-builder --chown=journeymesh:journeymesh /build/frontend/dist ./static

# Belt and braces: no developer environment file, no test caches, no VCS data.
RUN rm -rf .env .env.* .git .pytest_cache .ruff_cache .venv htmlcov evals/reports \
    && find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true \
    && chmod +x docker-entrypoint.sh \
    && chown -R journeymesh:journeymesh /srv/journeymesh

USER journeymesh

EXPOSE 8000

# Matches the Render health check path. Cheap by design: no LLM, no graph, no
# MCP call, no database round trip.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

ENTRYPOINT ["/srv/journeymesh/docker-entrypoint.sh"]
CMD ["serve"]
