# Casa on Vercel Hobby and Neon Free

This is the zero-additional-hosting-cost option for the personal, fictional portfolio demo at `https://casa.salehmmrezaei.com`. It uses your existing Vercel Hobby account and a separate Neon **Free** project. No VPS, Redis, object-storage subscription, OpenAI key, paid inference, background worker or paid add-on is required. Keep both accounts on their free plans: this is a quota-limited demo, not unlimited free production hosting. Your existing portfolio and Casa share Vercel account allowances. No deployment, account creation or DNS change is performed by these files.

The existing Docker configurations remain available. See [the VPS/Docker guide](deployment.md) for that alternative.

## Design and current provider support

The root `vercel.json` declares a static Vite frontend service and a Python FastAPI service. `/api/*` is routed first, preserving `/api/v1`; other paths enter the frontend, whose filesystem-first fallback supports React refresh/deep links. Both services share one domain and deployment. Vercel currently documents [Services as Beta on all plans](https://vercel.com/docs/services), with [service-specific build/routing configuration](https://vercel.com/docs/services/config-reference). This avoids separate API domains and permissive CORS. Native service support is preferable to legacy custom builders or running a Vite development server in production.

The ASGI entrypoint is `backend/vercel_entry.py`. It always enables public demo mode, PostgreSQL state, hidden API docs and the simulated assistant, and clears any accidentally supplied OpenAI key. It does not connect, migrate, seed or create tables at import time. OpenAI/Faker are optional installation extras and are not imported by this entrypoint. The existing locked local/Docker installation still includes both for normal development.

Migration `0010_shared_demo_state` adds only operational `demo_visitors` and `demo_rate_buckets` tables and a read-only dataset validation function. Rental models and workflows are unchanged. Sessions and chat survive cold starts, different instances and deployment restarts. Every lookup verifies the visitor session, seeded user and role. Chat updates lock that visitor's row; logout deletes it, so an in-flight reply cannot recreate deleted state. Threads and server-owned search filters are stored together in JSONB. No public endpoint can modify rental records or live assistant tables.

Session expiry defaults to 30 minutes, and chat history expires within 30 minutes independently. A visitor has at most three threads, 12 turns per thread and 128 KiB of serialized history. The recommended 64 active sessions bound history payload to about 8 MiB, excluding database/index overhead. There are at most 4,096 rate buckets. Keys are HMAC digests, not plaintext visitor IPs. Expired data is inaccessible immediately and removed opportunistically during subsequent traffic; if there is no traffic, expired rows may remain physically stored until cleanup. No paid TTL service or scheduled keepalive is needed.

Public status/liveness and rejected business writes do not wake the database. Data reads validate the reserved synthetic footprint with one SQL function call instead of transferring 1,200 image records for validation. Runtime connections use SQLAlchemy `NullPool` and disable named prepared statements; Neon owns the actual [transaction pool](https://neon.com/docs/connect/connection-pooling). Transaction-scoped advisory locks and row locks remain valid with that pooler. Bundled image files are read from the deployed package; no upload directory or persistent local writes are needed. Public published image responses can be CDN-cached; authenticated/private image responses remain `no-store`.

## 1. Review first

Review this branch/PR, migration, Vercel configuration and tests before executing the account or hosting steps below. None of these steps require sharing credentials in chat. Do not modify the Vercel project hosting your existing portfolio; Casa will be a new project in the same Hobby account.

Ensure this remains a personal portfolio demonstration consistent with the providers' current terms, rather than a real commercial rental service. No payments or real people/data should be introduced.

## 2. Create a dedicated Neon Free database

1. In Neon, explicitly select **Free**, without a paid Marketplace integration, trial upgrade or paid compute. Create a new project for Casa; use PostgreSQL 18 when offered (17 also supports the features used here).
2. Choose a region near the Vercel function region shown in your project settings. Retain scale-to-zero. Do not enable always-on compute or run periodic uptime queries against database readiness.
3. Use a dedicated database/branch containing only Casa's synthetic seed. Do not reuse a development database containing extra test accounts or unrelated data: the demo deliberately rejects mixed datasets.
4. From Neon's Connect panel, retain the **direct owner** connection string privately for migrations/seeding. Keep its TLS parameters. The runtime will use a different role and the **pooled** host containing `-pooler`.
5. Neon supports the required [`btree_gist` extension](https://neon.com/docs/extensions/btree_gist); migration `0004` creates it. No pgvector, pg_cron or external vector store is needed.

## 3. Migrate and seed once, from your computer

Use the reviewed checkout and Python 3.12+ (Vercel is pinned to 3.13). Install the existing full local dependency lock; this includes Faker and the operator tools:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
```

Create an ignored `.env.neon` in a private editor, with permissions `600`. Put the **direct owner URL** in `DATABASE_URL`, and an independently generated private 12–128 character seed password in `DEMO_PASSWORD`. Use ordinary dotenv syntax; do not source the file as shell code. No JWT or OpenAI key is required for migrations/seed. Example keys (replace locally, never commit):

```dotenv
DATABASE_URL=postgresql://OWNER:ENCODED_PASSWORD@DIRECT_NEON_HOST/neondb?sslmode=require
DEMO_PASSWORD=YOUR_PRIVATE_SEED_PASSWORD
PUBLIC_DEMO_MODE=false
```

```sh
chmod 600 .env.neon
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.seed --demo --non-interactive
```

Alembic also accepts `DATABASE_DIRECT_URL` when a pooled `DATABASE_URL` is otherwise configured, and recognizes Neon's CLI-generated `DATABASE_URL_UNPOOLED` as a fallback. The explicit `DATABASE_DIRECT_URL` takes precedence. Use the direct URL for schema changes. Never run migrations/seeding in a Vercel request, startup hook or every preview build. The seed is transactional/idempotent, preserves original IDs/dates/password hashes and attaches the same bundled fictional photos. It never deletes unrelated data or silently repairs a partial seed. Initial hashing is done on your computer, not in a serverless request.

## 4. Create the restricted runtime role

After migrations, run the private operator helper:

```sh
backend/.venv/bin/python deploy/neon_role.py --env-file .env.neon --set-password
```

It creates `casa_runtime`, rejects privileged/inherited existing roles, grants domain reads plus writes only to the two temporary state tables, and asks for the runtime password locally without printing it. Generate a separate 64-character hex password privately to avoid URL-encoding mistakes. It must differ from the owner, seed and JWT secrets. Store it in your password manager. SQL is reviewable in `deploy/neon-runtime-role.sql`; rerun grants after future migrations that add tables. Use the `casa_runtime` user and its password with Neon's **pooled** host for Vercel. Never put the owner/direct URL or seed password into Vercel.

## 5. Configure the new Casa Vercel project

After review, import `salehmmrezaei/ai-rental-agent` into a **new** Casa project in the existing Hobby account. Choose the reviewed production branch (normally `main` after merge). Repository root must remain the project root, not `frontend/` or `backend/`; the root configuration owns both services. Use the service build settings from the repository, Node 24 and Python 3.13. Do not select a paid container runtime or add-on.

Copy the keys from `.env.vercel.example` into that project's **Production** environment settings:

- `DATABASE_URL`: TLS pooled Neon URL, user `casa_runtime`.
- `JWT_SECRET`: independently generated random secret of at least 32 bytes (64 hex characters recommended).
- `CORS_ORIGINS`: `["https://casa.salehmmrezaei.com"]`.
- Recommended bounds: `DEMO_MAX_SESSIONS=64`, `DEMO_SESSION_MINUTES=30`, and the supplied request/chat limits.
- Keep `OPENAI_API_KEY` empty and `ASSISTANT_ENABLED=false`. The entrypoint also enforces these, even if configuration is accidentally changed.

No `VITE_` secret is needed: the frontend already uses `/api/v1`. Do not set `DATABASE_DIRECT_URL` or `DEMO_PASSWORD` in Vercel. Do not copy secrets into build commands or the repository. The API filesystem is disposable; uploads are rejected before parsing and images come from the bundled package.

For Preview environments, either leave database variables unset (API intentionally unavailable) or provision an explicitly isolated synthetic Neon branch/database, migrate/seed it privately and use a separate JWT secret. Do not let untrusted preview code access production database credentials. Free branch/storage quotas still apply. GitHub import/merge may trigger deployment automatically, so set up the database/environment before activating production deployment.

Only after your review, allow the first deployment. Inspect build logs to verify both services and package size, without dumping environment variables. The Vercel CLI recognized the checked-in services locally, but an actual hosted Vercel build requires your project and remains a live acceptance step.

## 6. Attach the subdomain after deployment review

In the new Casa project's Domains panel, add `casa.salehmmrezaei.com`. At your DNS provider, add the exact CNAME target Vercel displays for name `casa`; do not guess a generic CNAME. Remove only conflicting records for that subdomain after reviewing them. Leave your main portfolio domain/project unchanged. Vercel verifies the domain and provisions HTTPS automatically. No registrar credentials or DNS API token need to be shared with this assistant.

## 7. Verify the deployed website

```sh
python3 deploy/smoke.py https://casa.salehmmrezaei.com
```

The non-destructive script checks static assets/security headers, same-origin API, deep links, bundled photos, all three roles, cross-role denial, blocked registration/uploads/writes, simulated chat, visitor isolation and logout. Also run the browser suite against the deployed origin:

```sh
cd frontend
npm ci
E2E_PUBLIC_DEMO=1 E2E_BASE_URL=https://casa.salehmmrezaei.com npm run test:e2e
```

Verify HTTP redirects to HTTPS, certificate trust, desktop/mobile layouts and Blu. Use two independent browser contexts: chats must stay separate. Keep one session open, allow Neon to suspend naturally or roll out a new function version, and verify the unexpired session/chat still works. Expired sessions must require role re-entry. Check unsupported mutation requests explain read-only behavior, without configuration/API-key errors or external model requests. Confirm no runtime filesystem writes or persistent process are required. A redeploy must not reset rental data or automatically reseed.

## Expiry, reset, backup and recovery

Expired state is denied by database time immediately; chat also has its own lifetime. Subsequent API traffic prunes expired session/rate rows. To remove expired rows manually, or explicitly sign out all visitors, use the private operator file:

```sh
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.demo_state --cleanup
# Optional complete visitor reset, affecting no rental records:
backend/.venv/bin/python -m dotenv -f .env.neon run -- backend/.venv/bin/python -m app.demo_state --reset
```

Restarting/redeploying a Vercel function is **not** a reset now. Rotating JWT_SECRET invalidates tokens after deployment; reset the state tables too if immediate physical history removal is needed. SQL data and bundled photos remain preserved. Dataset date refresh still uses a new dedicated database/branch and seed, never `TRUNCATE` against an existing environment.

Use Neon's free restore window only within its current limits. For an independent backup, use [Neon's pg_dump guidance](https://neon.com/docs/manage/backup-pg-dump) with your private direct owner connection and `--format=custom --no-owner --no-acl`. Keep the dump encrypted on your existing computer/storage, separate from the repository; no paid backup product is required. Dumps contain hashes and possibly temporary chat. Restore to a fresh isolated Neon database, migrate as necessary, reapply runtime grants, verify synthetic guards and acceptance tests, then switch Vercel's pooled runtime URL and redeploy. Never overwrite unrelated data. Bundled images are recoverable from the reviewed Git commit and need no object-store backup.

## Free-tier budget and operating limits

As checked on 18 November 2026, [Neon Free](https://neon.com/docs/introduction/plans) lists 100 CU-hours/project, 1 GB storage/project, 5 GB public transfer and scale-to-zero after five minutes. [Vercel Hobby](https://vercel.com/docs/plans/hobby) lists included invocation/transfer/CPU allowances and can pause usage when limits are reached. Check your own consoles for current/grandfathered limits and combined portfolio usage. Do not upgrade to Launch/Pro or enable metered extras if zero additional bill is the requirement. Free limits may make the demo temporarily unavailable; uninterrupted hosting cannot be guaranteed for unlimited traffic at zero cost.

Avoid scheduled readiness probes, background cleanup loops, warmers and automatic migration/seed jobs. They can keep Neon awake. Review provider usage manually, use the free firewall controls for abuse if needed, and keep conservative caps. Lower session capacity if storage grows. The hashed limiter rows and bounded JSON histories limit application storage; PostgreSQL indexes/WAL/dead tuples still require monitoring. Inspect `pg_database_size(current_database())` privately. No paid tracing, analytics, remote LLM or file storage is configured.

When Neon wakes slowly, the API returns a sanitized 503/Retry-After instead of connection details; retry after a short delay. Persistent 503s need private inspection of database plan/compute availability, pooled URL/TLS, runtime grants, migration head and synthetic dataset. A 401 after expiry is expected. A 429 or capacity response protects shared/free resources. Missing images indicate incomplete package assets or seed metadata. Existing development/Docker behavior remains unchanged unless PostgreSQL demo state is explicitly selected.
