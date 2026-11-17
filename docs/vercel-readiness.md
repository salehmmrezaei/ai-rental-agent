# Vercel / Neon preparation and verification

Prepared on 18 November 2026. No Vercel/Neon account was accessed, no cloud database was provisioned, no hosting deployment was created and no DNS was changed. Follow [the deployment guide](vercel-neon.md) after review.

## Implementation

- Native Vercel Services: Vite static frontend and FastAPI ASGI backend, same-origin `/api/v1`, filesystem-first SPA fallback, security headers and a 30-second API function cap. Node 24 and Python 3.13 are selected. Provider Services support is currently Beta on all plans; hosted build verification is still required.
- `backend/vercel_entry.py` forces restricted demo mode and PostgreSQL state, clears provider keys and disables live AI/docs. Default runtime dependencies exclude OpenAI Agents SDK and Faker; core runtime versions match the existing tested lock. Normal local/Docker lock installation retains optional live and seed functionality.
- Additive migration `0010_shared_demo_state` creates only two operational state tables and a read-only reserved-dataset validation function. Existing rental models and constraints are retained. Readiness now expects this migration.
- `shared_demo.py` stores expiring visitor sessions and bounded shared throttle buckets, with transaction-scoped locks and HMAC keys. `shared_simulated_assistant.py` reuses existing authorized deterministic queries/cards, storing bounded per-visitor JSONB histories with row-locked updates. Logout/expiry never modify shared rental data. No process lifetime, local cache or background task is required for correctness.
- Neon runtime uses its pooled URL, SQLAlchemy NullPool and disabled named prepared statements. Alembic can use a separate direct URL. Runtime-role grants allow domain reads and temporary-state writes only; direct domain updates are denied by PostgreSQL as well as the API policy.
- Existing bundled image bytes remain package data. Anonymous published-image responses may be CDN-cached; private image responses are not. No persistent uploads or object store are needed in public mode.
- `app.demo_state --cleanup/--reset` touches only operational state. Expiry denial is immediate; physical cleanup is opportunistic or a private operator action. Redeploying a function preserves SQL state.
- The existing Docker Compose files are unchanged. CI adds a PostgreSQL-state browser matrix and offline Vercel configuration checks; migration/seeding is never run in public requests or Vercel builds.

## Actual local results

| Check | Result |
| --- | --- |
| Full backend suite | 331 passed on migrated disposable PostgreSQL 18. |
| New shared-state tests | 12 tests, included above: independent app instances, fresh Python process, concurrency, capacity, shared throttles, role isolation, independent chat expiry, no model runner, restricted database role, packaging/import behavior. |
| Frontend optimized build and unit tests | Build passed; 94 tests passed. |
| Chrome public-demo suite | All five scenarios passed against the hardened Vercel ASGI entrypoint with PostgreSQL state and no API key, including a repeat against the minimal runtime without OpenAI/Agents/Faker installed. |
| Chrome normal-mode suite | All seven existing rental workflows passed. |
| Offline Vercel configuration tests | Four passed. |
| Existing environment preflight tests | Five passed. |
| Minimal runtime installation | Fresh temporary environment installed default backend dependencies; entrypoint imported successfully with no OpenAI, Agents SDK or Faker installed. All six bundled images were available. |
| Wheel/package | Built successfully; all six image assets present and no env/upload files. Compressed application wheel about 1.2 MB, excluding dependencies; this is not a measured Vercel function bundle size. |
| Docker alternative | Both production images built; fresh PostgreSQL bootstrap, migrations, seed, API/Caddy health and complete non-destructive HTTP acceptance passed using isolated volumes and loopback-only HTTP. |
| Native Vercel CLI | Official CLI 65.17.0 recognized both service frameworks and accepted routing configuration. Local launch then failed in the environment's npm installer with EALLOWSCRIPTS. No login/deployment was attempted. Direct ASGI/Vite browser checks above passed; native local service startup and actual hosted build remain unverified. |
| Real Neon / Vercel / domain | Not executed: pooled Neon TLS behavior, real provider build size/runtime, suspension/resume, project limits, HTTPS/DNS and production URL need owner-run acceptance after review. |

Hosted CI is configured to run these regression suites after branch publication. Its status is visible on the PR and must be checked for the reviewed commit. Earlier initial failures during development were fixed; the results above are the completed local runs.

## Remaining limits

Zero additional monthly cost depends on keeping Vercel Hobby and Neon Free, staying within their allowances and not enabling paid extras. Your existing portfolio shares Vercel quotas. Exhaustion or provider suspension can make the demo unavailable; this is not an unlimited-capacity or SLA promise. No readiness cron/warmers are configured. The recommended 64 sessions, three threads per visitor, 12 turns per thread, 128 KiB history per session and 4,096 throttle rows bound application state; monitor database storage and transfer as described in the guide.

Vercel has outbound network access, unlike the optional Docker private network. The public entrypoint therefore enforces no live model code/key, and the minimal runtime omits the SDK. Runtime SQL credentials must remain private and restricted, previews must use an isolated synthetic database or no DB, and owner credentials must stay off Vercel. Do not expose any real data in the reserved synthetic records.

Existing development-only Picomatch advisory notes in the original report still apply to build/test tools, which are not a public Vite server. Provider-dependent deployment and public acceptance are deliberately left for review, not represented as completed deployment.
