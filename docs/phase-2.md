# Phase 2 — Authentication and authorization

Phase 2 implements the backend authentication flow. Phase 3 inventory features,
Phase 5 frontend authentication screens, Phase 6 demo data and Phase 7 AI remain
outside this delivery.

## Implemented endpoints

All paths below are prefixed by `/api/v1`.

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /auth/register | Tenant/landlord only; validated profile, HTTP 201 |
| POST | /auth/login | JSON credentials; bearer token, expiry and safe profile |
| POST | /auth/logout | Persistently revoke all user's tokens, HTTP 204 |
| GET | /users/me | Authenticated profile |
| PATCH | /users/me | Persist full_name/email; email requires current_password |
| PUT | /users/me/password | Verify current_password, hash new_password, revoke tokens |
| GET | /users/{user_id} | Self or administrator profile; hide other users with 404 |
| GET | /admin/users | Administrator-only, bounded paginated user directory |

The existing health endpoints remain public and readiness now requires migration
`0002_auth`. OpenAPI includes the HTTP Bearer security scheme.

## Security and database decisions

- Argon2id password hashing: 64 MiB memory, three iterations, four lanes, unique
  salts and opportunistic rehashing on successful login. Registration/change
  passwords are 12–128 characters. Test credentials are synthetic development-only
  values, never application defaults.
- HS256 JWTs require signature, issuer, audience, subject, expiration, issued-at,
  not-before, UUID token ID, access type and integer token version. Invalid tokens
  return a generic 401 with a Bearer challenge. Algorithm choices are pinned.
- Required backend signing secret is stored in ignored local .env, not source or
  frontend assets. The existing .env was extended with a cryptographically generated
  value only when JWT_SECRET was absent. The template documents configuration.
- Every authenticated request fetches the current account: inactive/deleted users
  and revoked tokens are denied, and the database role controls permissions.
- Migration `0002_auth` adds nonnegative `users.token_version`. Logout, password
  changes and email changes increment it, revoking all existing tokens across devices
  and server processes. Profile writes lock the user row and recheck token version
  before making changes, protecting against stale concurrent credential mutations.
- Normalized unique emails rely on PostgreSQL enforcement; duplicate races become
  HTTP 409 after rollback. Password hashes never enter response profiles or errors.
- Registration and profile input schemas forbid unknown or privileged fields. Admin
  provisioning is a local password-prompt command; duplicate existing accounts are
  rejected rather than promoted.
- Reusable property/unit owner dependencies scope SQL to the authenticated landlord
  or agency admin. Tenant, other-landlord and missing-resource access return 404.
  Phase 3 will attach these dependencies to actual inventory CRUD routes. Test-only
  guarded routes are defined solely in the test application, never production.
- Shared HTTP/validation/database error envelopes omit request values and SQL
  parameters. Authentication/profile/directory responses use Cache-Control: no-store.
- A bounded per-process IP auth limiter returns 429 and Retry-After. It combines
  login and registration attempts, ignores request X-Forwarded-For itself and does
  not affect health routes. Deployment across replicas requires a shared ingress
  limiter and correct trusted-proxy configuration.

See [architecture decisions](architecture.md#phase-2-authentication-decisions) for
library documentation references and [README](../README.md) for API bodies/setup.

## Files added or changed

| Files | Purpose |
| --- | --- |
| `backend/app/security.py` | Password hashes, dummy verification, JWT issue/validation |
| `backend/app/dependencies.py` | Live authentication, roles, property/unit ownership |
| `backend/app/errors.py` | Shared safe HTTP, validation and database errors |
| `backend/app/throttle.py` | Bounded authentication attempt limiter |
| `backend/app/schemas/auth.py` | Strict auth/profile inputs and safe response schemas |
| `backend/app/repositories/users.py` | User lookups, row locks and pagination |
| `backend/app/services/auth.py` | Persistent registration/login/profile/password/logout |
| `backend/app/routers/auth.py`, `backend/app/routers/users.py` | Public/authenticated/admin API routes |
| `backend/app/admin.py` | Local administrator provisioning with hidden password prompts |
| `backend/app/config.py`, `backend/app/main.py` | Auth configuration, startup checks, middleware and router wiring |
| `backend/app/models/entities.py`, `backend/alembic/versions/0002_auth.py` | Persistent token revocation version and migration |
| `backend/app/routers/health.py` | Readiness requires current migration |
| `backend/tests/test_auth.py`, `backend/tests/test_health.py` | Auth/permission integration tests and updated health setup |
| `backend/pyproject.toml`, `backend/requirements.lock` | Argon2, PyJWT, email-validator dependencies and tested lock |
| `.env.example`, ignored `.env` | JWT and limiter configuration |
| `README.md`, `docs/architecture.md`, `docs/phase-2.md` | Updated setup, decisions and delivery report |

No frontend sources or Phase 1 migration were changed. No new database tables were
needed; authentication extends users with its revocation version.

## Verification executed

All database checks used the isolated temporary PostgreSQL server on localhost
port 55432 with disposable database `rental_phase1_test`. No real personal data,
payments, outgoing messages or OpenAI calls were used.

| Check | Result |
| --- | --- |
| `pip install -e 'backend[test]'` | Dependencies installed; initial sandbox network failure retried with escalation |
| `alembic -c backend/alembic.ini upgrade head` | Phase 2 migration applied successfully |
| `pytest backend/tests -q --tb=short` | **92 passed, 1 warning, 6.48 seconds** |
| `alembic check` | No new upgrade operations detected |
| `alembic downgrade 0001_initial` then `alembic upgrade head` | Phase 2 migration round trip successful |
| `alembic check` after round trip | No new upgrade operations detected |
| `alembic upgrade head --sql` | Offline full migration SQL generation succeeded |
| Actual Uvicorn + localhost HTTP requests, without test dependency overrides | Readiness, registration, login, authenticated profile, admin denial, logout and token revocation passed |
| `pip check` | No broken requirements |
| `python -m compileall` | Application, migrations and tests compile |
| `docker compose config --quiet` | Compose configuration valid with updated auth environment |
| `git diff --check` | No whitespace errors |

The 92 tests comprise the 36 Phase 1 regression tests and 56 new Phase 2 cases.
Coverage includes tenant/landlord signup, admin/privileged-field rejection, email
normalization/duplicates, validation without password echo, independent Argon2
salts, generic bad-login responses, account deactivation, malformed/expired/future
or wrongly signed JWTs, issuer/audience/claim validation, logout revocation,
profile persistence, forbidden profile mutation, confirmed email/password changes,
duplicate-change rollback, live admin role checks, profile read privacy,
property/room ownership, CLI provisioning and duplicates, request throttling and
required signing key configuration.

## Limits and next phase

- Docker daemon remains stopped. Configuration validation passed; full container
  builds/startup were not executed.
- The locked Starlette/httpx TestClient combination emits one existing deprecation
  warning; all 92 tests pass.
- Tokens have no refresh endpoint; expiration requires login again. Logout is
  intentionally across all devices. Email/password changes also require login again.
- No external email verification/recovery workflow is implemented. The local auth
  limiter is per process, not an account-level or multi-replica limiter.
- The admin directory is read-only. Full admin user management follows in rental
  operations. Inventory endpoints follow in Phase 3; ownership helpers are ready.
- Frontend login/registration/dashboard screens and authentication persistence remain
  Phase 5. Fake demo accounts/seed data remain Phase 6. AI has not started.

Run and administrator commands are documented in the [README](../README.md).
Phase 3 will add ownership-safe property/unit CRUD, room management, secure uploads,
listing review/publishing/search and availability calculations.
