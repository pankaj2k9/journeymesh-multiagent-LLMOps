# =============================================================================
# JourneyMesh frontend - React + TypeScript + Vite
# Every journey, intelligently connected.
#
#   Production image (static build served by nginx):
#     docker build -t journeymesh-web ./frontend
#     docker run --rm -p 5173:80 journeymesh-web
#
#   Development image (Vite dev server with hot reload):
#     docker build --target dev -t journeymesh-web-dev ./frontend
#
# VITE_* values are compiled into the bundle, so the API URL is a build
# argument, not a runtime one. Leave it empty to use the same-origin /api
# proxy in nginx.conf.template, which is what the compose stack does; set it
# to the backend's public URL for a split deployment where the browser talks
# to the backend directly.
#
# Nothing secret may go into a VITE_* value: it is compiled into a file the
# browser downloads.
# =============================================================================

# ---- Stage 1: dependencies --------------------------------------------------
FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund


# ---- Stage 2: development server -------------------------------------------
FROM node:22-alpine AS dev

ENV NODE_ENV=development
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]


# ---- Stage 3: production build ----------------------------------------------
FROM node:22-alpine AS builder

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Type-check and bundle. A type error fails the build, by design.
RUN npm run build


# ---- Stage 4: runtime -------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Only these three variables are substituted into the template. Without the
# filter, envsubst would also eat nginx's own $host and $remote_addr.
ENV NGINX_ENVSUBST_FILTER=JOURNEYMESH_ \
    JOURNEYMESH_API_UPSTREAM=http://backend:8000 \
    JOURNEYMESH_RESOLVER=127.0.0.11 \
    JOURNEYMESH_CONNECT_SRC="'self'"

RUN apk add --no-cache curl gettext \
    && rm -rf /usr/share/nginx/html/*

# The official image renders every template in this directory into
# /etc/nginx/conf.d at start-up, so the upstream is a deployment decision
# rather than something baked into the image.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
