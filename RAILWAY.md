# Deploying JourneyMesh to Railway

Production runs on Railway as **three services in one project**. Railway does
not execute `docker-compose.yml`: Compose is the local orchestrator, Railway is
the production one, and each Compose service becomes a Railway service with the
Compose-specific parts replaced by Railway's own equivalents.

```
LOCAL                                  PRODUCTION
docker-compose.yml                     Railway project
  ├── frontend container                 ├── frontend service   (public)
  ├── backend  container                 ├── backend  service   (public)
  └── db       container                 └── Postgres service   (private)
        db:5432                                DATABASE_URL reference
```

| Compose concept | Railway equivalent |
| --- | --- |
| `depends_on: service_healthy` | Health check path + deploy ordering |
| `./db/postgres-data` bind mount | The Postgres service's own managed volume |
| `db:5432` on the container network | `DATABASE_URL` reference variable, private networking |
| `docker compose up --build` | A deploy per service, from this repository |
| `migrate` one-shot service | The backend's **pre-deploy command** |

---

## 1. Create the project and the database

1. Create a Railway project called **JourneyMesh**.
2. **+ New → Database → PostgreSQL**. Railway provisions it with its own
   volume and generates `DATABASE_URL`, `PGHOST`, `PGUSER` and the rest.
3. Leave the database **private**. It needs no public TCP proxy: only the
   backend talks to it, over Railway's private network. Enable a public proxy
   only if you genuinely need remote administration, and disable it after.

## 2. Backend service

**+ New → GitHub Repo →** this repository.

| Setting | Value |
| --- | --- |
| Root directory | `/backend` |
| Builder | Dockerfile (`backend/railway.json` declares it) |
| Health check path | `/health` |
| Pre-deploy command | `./docker-entrypoint.sh migrate` |
| Networking | Generate a public domain — the browser calls this API |

Variables:

```
DATABASE_URL      = ${{ Postgres.DATABASE_URL }}     <- a reference, not a copy
DB_REQUIRE_SSL    = true
APP_ENV           = production
DEBUG             = false
LOG_FORMAT        = json
WEB_CONCURRENCY   = 2
RUN_MIGRATIONS    = false                            <- pre-deploy already did
FRONTEND_URL      = https://<your-frontend>.up.railway.app
CORS_ORIGINS      = https://<your-frontend>.up.railway.app
GROQ_API_KEY      = ...
GROQ_MODEL        = ...
TAVILY_API_KEY    = ...
AVIATIONSTACK_API_KEY = ...
OPENWEATHER_API_KEY   = ...
LANGSMITH_TRACING = true
LANGSMITH_API_KEY = ...
LANGSMITH_PROJECT = JourneyMesh
```

`${{ Postgres.DATABASE_URL }}` is a **reference variable**. Railway resolves it
at deploy time from the Postgres service, so the credentials are never typed,
copied or committed, and rotating them needs no change here.

Do **not** set `PORT`. Railway assigns it; the entrypoint reads it and binds
`0.0.0.0`.

## 3. Frontend service

**+ New → GitHub Repo →** the same repository.

| Setting | Value |
| --- | --- |
| Root directory | `/frontend` |
| Builder | Dockerfile (`frontend/railway.json` declares it) |
| Health check path | `/healthz` |
| Networking | Generate a public domain |

Build argument — this is compiled into the bundle, so it is a **build** value,
not a runtime one:

```
VITE_API_BASE_URL = https://<your-backend>.up.railway.app
```

Runtime variable, so the page's content security policy allows the browser to
reach that origin:

```
JOURNEYMESH_CONNECT_SRC = 'self' https://<your-backend>.up.railway.app
```

Nothing secret may go in a `VITE_*` value: it is compiled into a file the
browser downloads. The frontend never connects to PostgreSQL — only the backend
does.

## 4. Disable automatic deployment

In each service: **Settings → Source → disable "Auto Deploy" / check suites**,
or set the deployment trigger to manual. Production is released by running the
**Deploy to Railway** GitHub Action, not by pushing to `main`, so that nothing
unverified reaches production.

## 5. GitHub Actions credentials

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

```
RAILWAY_TOKEN     a project token, scoped to this project and environment
```

**Variables** (the same page → Variables) — none of these is sensitive:

```
RAILWAY_PROJECT_ID        the project's id
RAILWAY_ENVIRONMENT       production
RAILWAY_BACKEND_SERVICE   backend
RAILWAY_FRONTEND_SERVICE  frontend
RAILWAY_BACKEND_URL       https://<your-backend>.up.railway.app
RAILWAY_FRONTEND_URL      https://<your-frontend>.up.railway.app
```

Prefer a **project token** over an account token: it can deploy this project's
services and nothing else.

## 6. Release

```
push / merge to main  ->  CI runs  ->  CI passes
                                          |
                    Actions -> "Deploy to Railway" -> Run workflow
                                          |
                          backend deploys (pre-deploy migration runs)
                                          |
                                  /health returns 200
                                          |
                                  frontend deploys
                                          |
                                  /healthz returns 200
```

A failed migration fails the pre-deploy step, and Railway keeps the previous
deployment serving traffic rather than starting a backend against a schema it
does not expect.

---

## Notes

- **Deploying never touches the database.** The Postgres service has its own
  lifecycle and its own volume; redeploying the backend or the frontend does
  not recreate, reset or seed it.
- **Migrations are additive.** `alembic upgrade head` applies revisions. Nothing
  in the deployment path drops tables.
- **`*.railway.internal`** is Railway's private DNS. Services in a project
  reach each other at `<service>.railway.internal` without crossing the public
  internet. The backend reaches PostgreSQL this way through the reference
  variable; you never construct the address by hand.
