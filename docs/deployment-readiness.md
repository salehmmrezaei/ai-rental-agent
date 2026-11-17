# Deployment readiness and security review

Prepared for `https://casa.salehmmrezaei.com`. **The public site has not been deployed or verified by this implementation.** DNS changes, VPS provisioning, public HTTPS/firewall checks and owner acceptance remain required.

## Architecture assessment

Casa already has a substantial working rental domain rather than a visual-only prototype: React/TypeScript routing and role workspaces; FastAPI routers, schemas, services and repositories; SQLAlchemy/PostgreSQL models with nine Alembic revisions; tenant applications, contracts, visits, saves and tenant–agency messaging; landlord inventory/occupancy; agency moderation and administration. PostgreSQL triggers, foreign keys and exclusion constraints protect state transitions, apartment/room booking conflicts and scheduling even under concurrent transactions. Existing tests exercise authorization and concurrency as well as UI behavior.

The original deployable pieces were development-focused: Vite dev server, localhost-exposed API/database, no HTTPS production reverse proxy, no explicit public-demo policy, shared password sign-in, and live assistant chat unavailable without an OpenAI key. Publishing that stack with shared administrator credentials would grant visitors normal business mutations and allow one shared-account logout/password change to affect other visitors.

The implementation preserves that normal application path while adding a separate read-only public-demo path and a production Compose deployment. It introduces no external service, LLM key or paid dependency for public visitors, no business model changes and no new migration.

## Changes and reasons

| Area / files | Change and purpose |
| --- | --- |
| Backend config, security, dependencies, app/auth/assistant routers; new `backend/app/public_demo.py` | Explicit public-demo setting; expiring per-visitor JWTs over seeded tenant/landlord/admin personas; default-deny write middleware; dedicated synthetic-data guard; isolated visitor logout; API docs hidden; bounded global/per-IP/session throttles. |
| New `backend/app/services/simulated_assistant.py`, assistant schemas | Deterministic role-scoped offline reads, useful property/listing/visit responses and guided limitations; private bounded memory history instead of shared DB chat/actions. Normal live SDK path remains available. |
| Frontend `src/demo/`, auth/API session handling, role layouts/pages, assistant/Blu components | Fictional-demo banner, passwordless role guide/switcher, clear read-only controls, simulated assistant label/examples, and sessionStorage for temporary demo tokens. Existing Blu assets and animation design retained. |
| New `docker-compose.prod.yml` | Separate production stack, migration→seed→API startup, no public DB/API ports, private app network, one worker, empty live key, restart/health/resource/log limits and persistent DB/uploads/certificates. |
| New `frontend/Dockerfile.prod`, `deploy/Caddyfile` | Build React once and serve static assets with Caddy HTTPS; same-origin API proxy, SPA refreshes, request limits/timeouts, CSP/security headers. No Node/Vite runtime in the final image. |
| New `deploy/init-db.sh` | First-start creation of a separate non-superuser application DB role; bootstrap `btree_gist` required by visit constraints. |
| New `.env.production.example`, `deploy/check_env.py`, `deploy/test_preflight.py` | Safe configuration template and tested validation of secret format, independence, permissions, identifier/limit bounds and disabled live keys. |
| New `deploy/compose.sh`, `deploy/backup.sh`, `deploy/smoke.py` | Consistent production commands, private logical DB/upload/certificate backups and non-destructive HTTP acceptance checks. |
| New `.dockerignore`; `.gitignore` | Exclude secrets, host modules, Git metadata, caches/uploads/backups from builds; track only the safe env example. |
| New `.github/workflows/verify.yml` | Backend tests on disposable PostgreSQL 18; frontend tests/build; normal and demo Playwright; production-container first-start and restart smoke. No deployment automation or deployment credentials. |
| New backend/frontend/browser demo tests | Direct API bypass denial, role/session/data isolation, no live agent calls, safe offline output, role switching/read-only UI and real image/deep-link behavior. |
| `frontend/package-lock.json` | Compatible transitive Undici development dependency security update. |
| README, this report and `docs/deployment.md` | Explain operating policy, credentials/DNS review, step-by-step deployment, recovery, reset, monitoring, costs and live acceptance. |

## Security review results

| Concern | Assessment / implemented control |
| --- | --- |
| Public writes and shared admin abuse | Backend denies all mutations by default except visitor access/logout and simulated chat. This covers registration, profile/password/account changes, messaging/read receipts, uploads, business operations and assistant confirmations, including future unknown write endpoints. Demo tokens do not enable normal-mode authentication. |
| Role isolation | Roles come from the authenticated seeded DB user. Tenant reads remain scoped to that tenant; landlord reads remain owner-scoped; agency reads are allowed only on the complete dedicated synthetic dataset. Cross-visitor chat/history access is denied. |
| Synthetic-only data | Demo queries validate reserved seeded entity IDs/counts, synthetic property flag, fictional account addresses and exact bundled image metadata. Unrelated/mixed datasets fail closed. Operators must still avoid inserting real personal text into reserved sample records. |
| JWT/browser storage | Existing issuer/audience/algorithm/expiry/token-version checks remain. Public visitors receive restricted, expiring session JWTs held in sessionStorage; restart/logout invalidates their server-side session. Browser JavaScript can read bearer tokens, so CSP and React's escaped text rendering remain important. Normal-mode behavior is retained. |
| Password/security secrets | Existing Argon2 hashing, 12–128 character passwords and CLI-only administrator provisioning remain. Public login/registration/password changes are disabled. Private seed credentials are never shown/distributed; four independent generated production secrets are required. |
| CORS, XSS and headers | Same-origin `/api/v1`, explicit HTTPS origin, CSP with scripts only from self, frame denial, nosniff, referrer/permissions policy, host-only HSTS. Inline styles remain permitted for React animation/layout. Chat/user content renders as text. |
| Rate limits / resource abuse | Bounded session store, per-IP/global public-demo request limits, session creation and chat limits, 16 KB backend demo POST bound, 64 KB proxy body cap, proxy timeouts, API concurrency cap, memory/CPU/PID limits. One process makes in-memory enforcement consistent. This is a small portfolio stack; host-level network/DDoS protection is still the VPS operator's responsibility. |
| Upload validation/storage | Existing MIME/content/pixel/size/animation checks and metadata stripping retained. Public upload endpoints are denied before parsing; sample images are bundled and authorized by backend publication/ownership checks. Upload volume persists for operator recovery. |
| SQL injection / integrity | SQLAlchemy parameterization and validated bounded schemas; state/identity/booking/scheduling invariants enforced in PostgreSQL. API DB role is not superuser. Existing transactional retry logic remains unchanged. |
| API errors/log privacy | Existing redacted validation/database errors retained; production API/Caddy request access logs disabled; useful runtime logs are rotated. No public debug/OpenAPI pages. Avoid copying expanded Compose env/inspect output into reports. |
| LLM requests | Demo router selects the deterministic simulator; demo availability does not depend on a key, and assistant action confirmation is denied. Production explicitly blanks any key and app containers have no direct outbound network route. Tests intercept the live runner to ensure it is unused. |
| Data retention / reset | Public sessions/chat live only in bounded memory and expire; restarting the worker resets them. Shared SQL data survives restarts/seeding and cannot be mutated by visitors. Full synthetic-date refresh uses a new dedicated DB/volume after backup, never a scheduled destructive reset. |

## Verification performed

Results are limited to what was actually run locally, not to an unprovisioned public server:

| Check | Result |
| --- | --- |
| Frontend unit tests | 94 passed after the Undici dependency update. |
| Optimized frontend build / lint | Passed locally; production frontend Docker build also succeeded. |
| Backend full suite | 319 passed on disposable PostgreSQL after final security/cleanup additions. |
| Existing normal Playwright workflows | 7 passed in Chrome. |
| Public-demo Playwright workflows | All 5 passed in Chrome against the final rebuilt production Caddy image, including mobile/accessibility checks, in 10.9 seconds. |
| Environment preflight tests | 5 passed; valid temp configuration accepted without printing secrets. |
| Production Compose configuration | Docker Compose validation passed with an isolated loopback-only test override. |
| Docker build context secret exclusions | Actual Docker sentinel build passed: nested `.env`, `.env.production` and `.DS_Store` files excluded; safe examples retained. |
| Production first start | Docker images built; fresh PostgreSQL 18 initialization, non-superuser app role, Alembic, synthetic seed and DB/API/Caddy health passed. |
| Caddy configuration | Built-image `caddy validate` passed. Local HTTP override intentionally skipped ACME/public DNS. |
| Production HTTP smoke | Passed static assets/CSP, API proxy, deep links, sample image bytes, three roles, role isolation, blocked registration/writes/uploads, simulated chat, visitor isolation and per-visitor logout. |
| Container restart / seed rerun | Passed local API/Caddy restart and readiness, followed by the complete HTTP smoke; seed rerun preserved the existing dataset. |
| Logical DB/image/Caddy-data backup and isolated restore | Passed documented backup script, non-superuser restore to fresh PostgreSQL 18 volumes, migration/seed rerun, synthetic PNG and Caddy-data archive probes, and full HTTP smoke against the restored stack. The local plain-HTTP test did not create a real public certificate. |
| Public DNS, real HTTPS, external firewall and VPS reboot | Not performed; requires the live server and domain configuration. |
| GitHub workflow execution | Runs automatically on pushes and pull requests. See [PR #17 checks](https://github.com/salehmmrezaei/ai-rental-agent/pull/17/checks) for the current hosted results. The browser tests use portable artifact paths and wait for listing details before refresh assertions. |

Production npm dependency audit reports zero vulnerabilities. The complete development audit still reports six high-severity affected packages from the unpatched [Picomatch glob ReDoS advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf), with no critical advisories. These are build/test chains through Vite/Vitest and are absent from the final Caddy static runtime. Build only trusted source/configuration, keep development/preview servers private and revisit the upstream patch before the next rebuild. Undici's fix is included in the lockfile.

## Remaining live acceptance and operating limits

The owner prepares and retains VPS SSH access, the intended public IP, DNS account access, ACME email and independently generated secrets privately. There is no need to share credentials in chat. No registrar/hosting access was assumed and no DNS records were changed. Follow `docs/deployment.md` for exact first deployment, backup/restore, firewall and URL tests.

Verify the actual hostname from outside the VPS, including HTTP→HTTPS, certificate trust/renewal persistence, protected ports, role UI/mobile/Blu, image routing, repeated/concurrent read-only behavior, backend restart and host reboot recovery. Measure CPU/RAM/disk under expected portfolio traffic and keep encrypted off-server backups. A bounded single worker is a deliberate simplicity choice; multi-replica hosting requires a shared session/limiter design first.

The demo's seed is idempotent and date anchored. Current visits/leases naturally become historical; available-until dates expire two years after initial seeding. A reset creates new dedicated volumes after backup and verification. Do not remove guardrails to expose an older mixed development database.

The code and deployment files are on `feat/safe-public-demo` in [draft PR #17](https://github.com/salehmmrezaei/ai-rental-agent/pull/17), targeting the existing `demo` branch. Record the reviewed commit and completed live acceptance evidence in the release; no claim of public deployment should be made before that URL is verified.
