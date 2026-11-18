# Vercel and Neon deployment

Public demo: **[casa.salehmmrezaei.com](https://casa.salehmmrezaei.com)**.

The configuration serves React and FastAPI from one Vercel project, with Neon PostgreSQL for rental data and temporary visitor state. It needs no VPS or model API key. Use Hobby/Free plans and check their current quotas. [Docker deployment](deployment.md) remains available as an alternative.

## Architecture

`vercel.json` routes `/api/*` to FastAPI and other paths to the built frontend, including SPA deep links. `backend/vercel_entry.py` enforces demo mode, PostgreSQL session/chat storage, hidden API docs and a disabled live assistant. Bundled images need no persistent filesystem.

Runtime uses SQLAlchemy/psycopg with `NullPool` and Neon's [transaction pooler](https://neon.com/docs/connect/connection-pooling). See [architecture](architecture.md) for role isolation and state limits.

## 1. Database and private configuration

Use a dedicated Neon Free database containing only Casa's synthetic dataset. Choose a region near the Vercel function region and retain scale-to-zero. Preserve TLS parameters in connection URLs.

Keep two separate private files, ignored by Git and protected with `chmod 600`:

| File | Contents |
| --- | --- |
| `.env.neon` | Direct owner URL and private seed password, for operator commands |
| `.env.neon-demo` | Pooled `casa_runtime` URL, independent JWT secret and settings from `.env.vercel.example`, for local preview |

Keep your ordinary Docker `.env` separate. `neon.ts` declares PostgreSQL only; the local `.neon` file selects the project/branch. CLI `init` and `deploy` can overwrite database variables in the root `.env`. To refresh credentials into a separate operator file:

```sh
npx --yes neon@latest env pull --service postgres --file .env.neon-pulled
chmod 600 .env.neon-pulled
```

## 2. Migrate and seed once

Install the Python dependencies using the [development guide](development.md#native-development). In `.env.neon`, set the direct owner `DATABASE_URL`, a private 12–128 character `DEMO_PASSWORD`, and `PUBLIC_DEMO_MODE=false`.

```sh
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.seed --demo --non-interactive
```

Migrations install the required `btree_gist` extension. Alembic accepts `DATABASE_DIRECT_URL`, then `DATABASE_URL_UNPOOLED`, falling back to `DATABASE_URL`. Use a direct connection for schema changes. Migrations and seeding are operator actions, never build/startup/request hooks.

The seed preserves existing IDs, passwords and dates; a partial or mixed dataset is not silently replaced. A fresh database is required to reset the rental dataset safely.

## 3. Restricted runtime role

After migrating:

```sh
backend/.venv/bin/python deploy/neon_role.py --env-file .env.neon --set-password
```

The helper prompts privately for a separate password and applies `deploy/neon-runtime-role.sql`. The role reads rental tables and writes only `demo_visitors` and `demo_rate_buckets`. Use a 64-character random hex password and the `-pooler` hostname for runtime. Reapply grants after migrations that add tables.

## 4. Vercel configuration

Import the repository into a separate Casa Vercel project. Use the repository root, Node 24, Python 3.13 and the checked-in service settings. Keep the existing portfolio project separate.

Configure Production variables using `.env.vercel.example`:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | TLS pooled connection with the restricted `casa_runtime` role |
| `JWT_SECRET` | Independent random secret, at least 32 bytes |
| `CORS_ORIGINS` | `["https://casa.salehmmrezaei.com"]` |
| `DEMO_MAX_SESSIONS` | `64` |
| `DEMO_SESSION_MINUTES` | `30` |
| `OPENAI_API_KEY` | Empty |
| `ASSISTANT_ENABLED` | `false` |

Include the request/chat bounds from the template. Owner/direct URLs, seed passwords and `VITE_` secrets do not belong in the runtime. Preview deployments need separate synthetic databases and JWT secrets, or no database access.

## 5. Domain and verification

In Casa's Vercel Domains settings, add `casa.salehmmrezaei.com`, then use the exact DNS target Vercel provides. Preserve the main portfolio's DNS. Verify HTTPS, API routing and deep links after deployment:

```sh
python3 deploy/smoke.py https://casa.salehmmrezaei.com
E2E_PUBLIC_DEMO=1 E2E_BASE_URL=https://casa.salehmmrezaei.com npm --prefix frontend run test:e2e
```

These checks cover assets, role access, blocked writes, simulated chat and visitor isolation. Check desktop/mobile rendering and Blu, then verify unexpired sessions survive a function restart. Expired sessions require fresh role entry. Build and automated-test commands are in the [development guide](development.md#tests).

## Maintenance and recovery

Sessions/chat expire within 30 minutes; subsequent traffic prunes expired rows. To clean expired state, or explicitly sign out all visitors:

```sh
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.demo_state --cleanup
# Optional: remove all disposable visitor state, preserving rental data.
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.demo_state --reset
```

Redeployment preserves rental data and shared visitor state. Rotating `JWT_SECRET` invalidates tokens after deployment; resetting temporary state removes stored chat immediately.

Use [pg_dump](https://neon.com/docs/manage/backup-pg-dump) with the direct owner connection and `--format=custom --no-owner --no-acl` for a private backup. Encrypt it outside the repository. Restore into a fresh database, migrate, reapply grants, verify the synthetic guard and smoke checks, then update the pooled runtime URL. Bundled photos remain recoverable from Git.

Review usage in the Neon and Vercel dashboards. Free-tier limits can temporarily suspend the demo. Avoid scheduled readiness probes, keepalive requests and background cleanup loops that keep Neon awake.

| Symptom | Check |
| --- | --- |
| 503 after inactivity | Allow a short retry; then check connection/TLS, migration head, seed and grants |
| `demo_dataset_required` | Complete dedicated synthetic seed; keep unrelated data separate |
| 401 | Session expiry; re-enter a demo role |
| 429 or capacity response | Request/session limits and available free-tier resources |
| Missing photos | Bundled assets, image metadata and API routing |
