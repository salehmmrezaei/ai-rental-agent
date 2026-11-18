# Connected Neon database and local verification

On 18 November 2026, Casa was connected to the existing Neon project
`casa-ai-rental-agent` (`solitary-dust-40694354`), organization
`org-noisy-violet-85423256`, branch `production`.
`neon deploy` confirmed that PostgreSQL is the only utilized service and that the
branch already matched `neon.ts`. No plan upgrade, other service, Vercel deployment,
or DNS change was requested or performed.

The database was verified empty before running the existing Alembic migrations and
synthetic seed. Migration head is `0010_shared_demo_state`; `btree_gist` is installed.
The seed created 301 synthetic users, 300 properties, 900 rental units/listings,
750 applications, 550 contracts, 100 visits, 50 conversations, 150 messages,
200 saved listings and 1,200 image metadata records. The actual photos remain
bundled WebP assets, with no storage service required. Database size immediately
after setup was approximately 12 MiB.

## Private files on the setup computer

These files are ignored by Git and excluded from Vercel uploads. Secret files have
permissions `600`; none of their credentials are included in this document.

| File | Purpose |
| --- | --- |
| `.neon` | CLI project/branch context; no database password |
| `.env.neon` | Direct owner URL and private seed password for operator commands only |
| `.env.neon-demo` | Pooled `casa_runtime` URL, independent JWT secret, public-demo settings; no owner URL or model API key |
| `.env.before-neon` | Private backup of the original development `.env` |
| `.env` | Original development/Docker configuration, restored byte-for-byte after setup |

`casa_runtime` has rental-table reads and writes only to `demo_visitors` and
`demo_rate_buckets`. Direct SQL attempts to update users were denied with SQLSTATE
`42501`. Runtime connections use the existing SQLAlchemy/psycopg 3 driver, `NullPool`,
disabled named prepared statements and Neon's transaction pooler. Client-to-pooler
TLS was verified using libpq's `ssl_in_use`; `pg_stat_ssl` behind a pooler describes
the separate internal connection. See [Neon's connection-method guide](https://neon.com/docs/connect/choose-connection).

Do not use `.env.neon` for the web runtime or upload it to Vercel. For the eventual
Vercel deployment, enter the runtime settings from `.env.neon-demo` privately,
using `.env.vercel.example` as the key checklist and the exact public origin for
`CORS_ORIGINS`. Do not add `DATABASE_URL_UNPOOLED`, `DATABASE_DIRECT_URL` or
`DEMO_PASSWORD` to the Vercel runtime.

## Run the connected app locally

From the repository root, using Node 24 and the existing Python 3.12+ virtualenv:

```sh
npm ci
npm --prefix frontend ci
npm run build
```

In one terminal, start FastAPI with the private Neon runtime file:

```sh
npm run dev:neon:api
```

In another terminal, start the frontend:

```sh
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI on port 8000, so the
browser never receives a database connection string. The API script uses the same
entrypoint as Vercel, which enforces public demo mode, shared PostgreSQL session/chat
state, read-only rental operations and no external LLM integration. If Python
dependencies need reinstalling, follow the virtualenv commands in
[the deployment guide](vercel-neon.md#3-migrate-and-seed-once-from-your-computer).

To inspect the production build instead of the development frontend:

```sh
API_PROXY_TARGET=http://127.0.0.1:8000 npm --prefix frontend run preview -- --host 127.0.0.1 --port 5175 --strictPort
E2E_PUBLIC_DEMO=1 E2E_BASE_URL=http://127.0.0.1:5175 npm --prefix frontend run test:e2e
```

Do not run the ordinary backend database suite against Neon production. Those tests
require a disposable database ending in `_test` and truncate fixture tables.
The public-demo browser suite skips fixture creation and only writes disposable
visitor/session/chat state.

## CLI and operator commands

Global CLI installation initially failed because npm registry DNS was unavailable;
the requested `npx` fallback installed Neon CLI 9.6.3. Browser login succeeded.
The first `init` hit npm's `EALLOWSCRIPTS` error while installing dependencies.
Installing `@neon/config` and `@neon/env` directly fixed initialization; both are
recorded in the root lockfile. The CLI also installed Neon agent tooling. GitHub
Copilot CLI itself was unavailable; Neon used its skills/MCP fallback.
That fallback also created an account-scoped API key for the local Copilot MCP
configuration. Casa does not use it; it can be managed in Neon's account API-key
settings independently of Casa's runtime database credentials.

The completed setup commands were:

```sh
npx --yes neon@latest init -y --org-id org-noisy-violet-85423256 --project-id solitary-dust-40694354 --branch production --services postgres
npx --yes neon@latest config plan
npx --yes neon@latest deploy
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.seed --demo --non-interactive
```

The checked-in runtime grants were then applied with an independently generated
private password. No schema changes or seeding run on app startup or build.

`init` and `deploy` automatically pull owner connection variables into an existing
root `.env`. Preserve local configuration before rerunning either command. To
refresh connection information separately without touching the restored Docker
environment or overwriting the restricted runtime URL, use:

```sh
npx --yes neon@latest env pull --service postgres --file .env.neon-pulled
chmod 600 .env.neon-pulled
```

Treat that new file as privileged operator credentials. It is not a substitute
for `.env.neon-demo`. The backend now recognizes `DATABASE_URL_UNPOOLED` for Alembic;
an explicit `DATABASE_DIRECT_URL` takes precedence.

For future migrations or safe expired-state cleanup:

```sh
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.demo_state --cleanup
```

Reapply `deploy/neon-runtime-role.sql` after migrations that add tables, using the
existing operator helper described in the deployment guide. Do not reseed on a
schedule or keep the database awake with periodic readiness requests.

## Verification completed

The production frontend was served locally on port 5175, with FastAPI connected
to the real Neon database using `casa_runtime`.

```text
npm run build
  1962 modules transformed.
  built in 356ms

npm test
  Test Files  12 passed (12)
  Tests       94 passed (94)

Targeted backend configuration/serverless tests
  6 passed in 1.09s

Deployment configuration and preflight checks
  4 tests OK + 5 tests OK

E2E_PUBLIC_DEMO=1 E2E_BASE_URL=http://127.0.0.1:5175 npm --prefix frontend run test:e2e
  5 passed (50.5s)
```

Browser checks covered images/deep links, all three roles, read-only controls,
simulated chat with listing cards and Blu, denied direct writes, separate visitor
histories, accessibility and no external browser requests. A separate HTTP check
against two independent FastAPI processes verified that sessions/chat and logout
propagate through Neon, while another visitor's session stays isolated. Targeted
backend checks also verified that the Vercel entrypoint imports no OpenAI/Agents
SDK or Faker. Database grants, client TLS and the synthetic dataset guard passed.
The full destructive backend suite was not run against production.

The remaining hosting steps are Vercel environment configuration, a reviewed
deployment, then subdomain/DNS configuration and hosted HTTPS smoke tests. Follow
[the Vercel/Neon guide](vercel-neon.md); those actions are still pending review.
