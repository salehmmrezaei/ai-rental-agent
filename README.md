# AI Rental Agent

Incremental rental management platform. **Phases 1 and 2: database, authentication and authorization** are
implemented. The backend exposes registration/login, revocable JWT authentication,
profile management, an admin user directory, health checks and OpenAPI documentation.
Rental APIs follow in later phases. The existing React/Vite
starter is preserved; it is not yet the rental interface.

See [architecture, schema, API plan and roadmap](docs/architecture.md) and
[Phase 1 implementation and verification](docs/phase-1.md), and
[Phase 2 implementation and verification](docs/phase-2.md).

## Local development with Docker

Prerequisites: Docker Engine/Desktop with Compose, running daemon, available ports
5432, 8000 and 5173. Container bindings are limited to localhost.

```sh
# A local ignored .env may already have been generated during setup.
# If absent, copy the template:
cp -n .env.example .env
# Edit .env: replace the example database password and match it in DATABASE_URL.
# Set JWT_SECRET to a random secret of at least 32 bytes; see below.
docker compose up --build
```

Use a URL-safe password or percent-encode it in database URLs. CORS_ORIGINS is a
JSON array of exact frontend origins. JWT_SECRET is required for backend startup.
Generate a local value with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
and save it only in ignored .env. The existing local .env was updated with a generated
secret during Phase 2. OpenAI is not integrated yet.
Do not commit .env. PostgreSQL data persists in a named volume.

Compose waits for PostgreSQL readiness, applies `alembic upgrade head` in a
one-shot migration container, then starts the backend and frontend.

- Frontend starter: http://localhost:5173
- Backend OpenAPI: http://localhost:8000/docs
- Liveness: http://localhost:8000/api/v1/health/live
- Database/migration readiness: http://localhost:8000/api/v1/health/ready

```sh
docker compose logs backend migrate db
docker compose stop
```

The backend runs as a nonroot container user. This is a development environment;
production deployment, TLS, backup policies and operational hardening are future work.

## Backend without Docker

Prerequisites: Python 3.12+ and PostgreSQL 18. Create a development database and role,
then set DATABASE_URL to a `postgresql+psycopg://` URL for that database.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
# Run from the repository root so the ignored .env is available.
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
```

The checked-in lock records the dependency versions used for verification.
`backend/pyproject.toml` specifies supported ranges and the test extra.

```sh
cd frontend
npm ci
npm run dev
```

## Tests

Database tests require real PostgreSQL; SQLite cannot verify the triggers or
concurrency guarantees. Create a **disposable** database whose name ends in `_test`.
Tests truncate its rental tables. Never point TEST_DATABASE_URL at useful data.
The test user must own the migrated schema and be able to inspect its own sessions.

```sh
export TEST_DATABASE_URL='postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/rental_test'
DATABASE_URL="$TEST_DATABASE_URL" backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/pytest backend/tests -q
```

The suite checks schema/model consistency, roles, ownership, valid dates, contract
approval, application matching, room/apartment conflicts, independent rooms,
back-to-back rentals, cancellation, immutable contract terms, lifecycle transitions,
message authorship, image/unit consistency, CORS and health checks. Authentication
tests verify hashed passwords, registration restrictions, JWT validation, live account
status and role checks, token revocation, profile privacy and ownership dependencies. Competing-write
tests prove the second transaction blocks on the property row and cannot commit a
conflicting contract under READ COMMITTED or REPEATABLE READ.

## Authentication API

All routes use `/api/v1`. Login accepts **JSON**, not OAuth form data. In Swagger,
use Authorize to paste the access token returned by login. Other clients send
`Authorization: Bearer <access_token>`. Tokens expire after 30 minutes by default
(configurable with ACCESS_TOKEN_MINUTES, 1–120). There are no refresh tokens yet;
log in again when an access token expires.

| Method and path | Behavior |
| --- | --- |
| POST /auth/register | Register tenant or landlord; return safe profile, HTTP 201 |
| POST /auth/login | Return bearer access token, expires_in and safe profile |
| POST /auth/logout | Revoke all of the user's tokens across devices, HTTP 204 |
| GET /users/me | Current authenticated profile |
| PATCH /users/me | Update full_name and/or email; email requires current_password |
| PUT /users/me/password | Change password using current_password and new_password |
| GET /users/{id} | Self or agency administrator only; other profiles return 404 |
| GET /admin/users?page=1&page_size=20 | Admin-only paginated directory; page_size ≤ 100 |

Example registration body (synthetic development data):

```json
{
  "email": "synthetic.tenant@example.com",
  "password": "Choose-your-own-local-password",
  "full_name": "Synthetic Tenant",
  "role": "tenant"
}
```

Login accepts only email and password. Passwords must be 12–128 characters for
registration and changes. Email is trimmed and lowercased; names are trimmed.
Registration rejects admin roles, privileged fields and duplicate email addresses.
Full profile responses never expose password hashes or token versions.

Email and password changes require the current password and revoke existing tokens;
log in again with the new credentials afterward. Logout revokes tokens across all
devices, while leaving the account active. Deactivated accounts cannot log in or
use existing tokens. Roles are read from PostgreSQL on every authenticated request.

HTTP errors use `{"error":{"code":"...","message":"..."}}`; validation errors
also include locations/types without echoing request values. Missing/invalid tokens
return 401 with a Bearer challenge; insufficient roles return 403; inaccessible
resources return 404; duplicate emails return 409; invalid inputs return 422.
Authentication responses are marked no-store.

The login and registration routes have a bounded per-process limiter (AUTH_RATE_LIMIT,
default 20 combined attempts per client IP per 60 seconds). Exceeded requests return
429 with Retry-After. For deployment across replicas, configure a shared gateway
rate limit and trust proxy headers only from your gateway. This limiter does not
provide account-wide protection across different client addresses.

## Administrator provisioning

Admin registration is unavailable through the public API. After migrations, an
operator can create a synthetic local administrator using a command that prompts
for a password twice, without putting it in shell arguments or environment values:

```sh
backend/.venv/bin/python -m app.admin --email synthetic.admin@example.com --full-name "Synthetic Agency Admin"
# Or with Docker running:
docker compose exec backend python -m app.admin --email synthetic.admin@example.com --full-name "Synthetic Agency Admin"
```

Duplicate emails are rejected; this command never promotes an existing tenant or
landlord. There are no shared demo passwords. Faker data and documented development
demo accounts remain Phase 6 work. No real users or external messages are created.

## Current scope and next phase

Phase 2 authentication and permission dependencies are complete. Ownership helpers
scope property and unit access to their landlord or an agency administrator; actual
inventory CRUD routes will connect them in Phase 3. The admin directory is read-only;
full agency user management remains a later rental-operations feature.

The frontend is still the preserved React starter. Login/registration pages,
TypeScript/Tailwind, routing and authentication persistence belong to Phase 5.
Password recovery and email verification would require additional confirmed workflows
and are not implemented. No external email is sent. Rotating JWT_SECRET invalidates
all current tokens; token_version changes invalidate an individual user's tokens.

Phase 3 will implement ownership-safe properties and rental units, room management,
validated image uploads, listing submission/moderation, search and availability.
Later phases add transactional rental operations, the frontend, demo data and
integration verification. AI development starts only after the core platform is
operational and tested. No real payments or external messages are integrated.

Docker configuration was validated, but full Compose startup could not be tested
because the Docker daemon was stopped. PostgreSQL migration and database tests
were executed on an isolated local PostgreSQL server; see the verification report.
