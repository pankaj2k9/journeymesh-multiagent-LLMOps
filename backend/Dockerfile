# =============================================================================
# JourneyMesh backend - FastAPI + LangGraph
# Every journey, intelligently connected.
#
#   docker build -t journeymesh-api ./backend
#   docker run --rm -p 8000:8000 --env-file backend/.env journeymesh-api
# =============================================================================

# ---- Stage 1: build the dependency tree in an isolated virtualenv -----------
FROM python:3.14-slim AS builder

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
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    PORT=8000

# libpq for psycopg, curl for the health check. No build toolchain in runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 journeymesh

# ---- uv / uvx ----------------------------------------------------------------
# The AviationStack MCP server is published as a Python package and is launched
# with `uvx aviationstack-mcp` as a stdio subprocess. `uvx` fetches it into an
# isolated environment on first use, so it is not a dependency of this
# application and cannot conflict with one.
#
# It is installed INTO THE IMAGE rather than onto the VPS: the deployment ships
# a container, and a host that needs manual setup is a host that drifts.
#
# Copied from the official distroless image at a pinned version - no curl|sh,
# and nothing added to the build that is not needed at runtime.
COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

# uv writes into three places, and all three are given explicit, shared paths
# so the unprivileged runtime user can read them and nothing depends on $HOME.
ENV UV_CACHE_DIR=/opt/uv/cache \
    UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_LINK_MODE=copy

# The AviationStack MCP package requires Python >= 3.13, while this application
# runs on 3.11. That is fine - the MCP server is a separate process, not an
# import - but it means uv needs a 3.13 interpreter to run it with.
#
# Both the interpreter and the package are installed AT BUILD TIME so that a
# call on the VPS is a local process start, not a download. Without this the
# first flight lookup after every deployment would stall fetching ~50 MB, and
# would fail outright on a host with no outbound access to the index.
#
# `mcp<2` is pinned because aviationstack-mcp imports mcp.server.fastmcp.FastMCP,
# which mcp 2.x renamed to MCPServer. Left unpinned, uv resolves mcp 2.x into
# the tool's isolated environment and the server dies on import. The pin is
# scoped to that environment and has no effect on this application's own mcp
# version. Remove it when the package supports mcp 2.x.
RUN install -d -m 0755 /opt/uv \
    && uv python install 3.13 \
    && uv tool install --python 3.13 --with "mcp<2" aviationstack-mcp \
    && uv cache prune --ci \
    && chmod -R a+rX /opt/uv \
    && chown -R journeymesh:journeymesh /opt/uv/cache

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
