# AI Rental Agent

Incremental rental management platform. **Phase 1: database and architecture** is
implemented. The backend currently exposes health checks and OpenAPI documentation;
authentication and rental APIs follow in later phases. The existing React/Vite
starter is preserved; it is not yet the rental interface.

See [architecture, schema, API plan and roadmap](docs/architecture.md) and
[Phase 1 implementation and verification](docs/phase-1.md).

## Local development with Docker

Prerequisites: Docker Engine/Desktop with Compose, running daemon, available ports
5432, 8000 and 5173. Container bindings are limited to localhost.

```sh
# A local ignored .env may already have been generated during setup.
# If absent, copy the template:
cp -n .env.example .env
# Edit .env: replace the example password and match it in DATABASE_URL.
docker compose up --build
```

Use a URL-safe password or percent-encode it in database URLs. CORS_ORIGINS is a
JSON array of exact frontend origins. No JWT or OpenAI secret is required yet.
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
message authorship, image/unit consistency, CORS and health checks. Competing-write
tests prove the second transaction blocks on the property row and cannot commit a
conflicting contract under READ COMMITTED or REPEATABLE READ.

## Current scope and next phase

No tenant/landlord/admin login exists yet and no demo credentials are provided.
Demo accounts and the required Faker dataset will be created in Phase 6 after
secure authentication and rental workflows are implemented. Tests use clearly
synthetic records and unusable password strings only.

Phase 2 will add secure password hashing, JWT authentication, tenant/landlord
registration, admin provisioning, profile endpoints, backend permissions, and
authentication/authorization tests. Subsequent phases add inventory, transactional
rental operations, the TypeScript/Tailwind interface, demo data and integration
verification. AI development starts only after the core platform is operational
and tested. No real payments or external messages are integrated.

Docker configuration was validated, but full Compose startup could not be tested
because the Docker daemon was stopped. PostgreSQL migration and database tests
were executed on an isolated local PostgreSQL server; see the verification report.
