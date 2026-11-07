# Development guide

Detailed setup, API behavior, and verification for Casa. Run commands from the
repository root unless a step explicitly changes directory. For the project overview,
see the [main README](../README.md).

Incremental rental management platform. **Phases 1–7: database, authentication, inventory, rental operations, frontend, demo integration and AI assistant** are
implemented. The backend exposes registration/login, revocable JWT authentication,
profile management, properties/units, secure images, listing moderation/search,
availability, transactional applications/contracts, visits, private agency messaging,
saved listings, occupancy reports, dashboard statistics, admin account management,
health checks and OpenAPI documentation. The React/TypeScript/Tailwind frontend
now provides public search and tenant, landlord and agency dashboards. Phase 7 adds a
tenant, landlord and agency AI assistants with live backend tools and explicit action confirmation.

See [architecture, schema, API plan and roadmap](architecture.md) and
[Phase 1 implementation and verification](phase-1.md), and
[Phase 2 implementation and verification](phase-2.md), and
[Phase 3 implementation and verification](phase-3.md), and
[Phase 4 implementation and verification](phase-4.md), and
[Phase 5 implementation and verification](phase-5.md), and
[Phase 6 demo data and integration verification](phase-6.md), and
[Phase 7 AI assistant and verification](phase-7.md).

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
secret during Phase 2. OpenAI configuration is optional; see the AI assistant setup below.
Do not commit .env. PostgreSQL data and uploaded images persist in named volumes. Uploaded image
metadata lives in PostgreSQL; files live in the backend image_data volume. Back up
both together. Removing containers without deleting volumes preserves pictures.

Compose waits for PostgreSQL readiness, applies `alembic upgrade head` in a
one-shot migration container, then starts the backend and frontend.

- Frontend: http://localhost:5173
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
conflicting contract under READ COMMITTED or REPEATABLE READ. Phase 4 also tests
complete approvals under SERIALIZABLE, transaction retries, concurrent visit
scheduling, effective termination, scoped messages/read receipts, saved listings
and role-specific reporting.

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
landlord. Optional demo accounts use a local operator-selected password; see below.
No real users or external messages are created.

## Demo data and accounts

Phase 6 provides 100 landlords, 200 tenants, one agency administrator and 300
synthetic properties, with 75 each in Bologna, Milan, Rome and Florence. Every
property has an apartment and two rooms. The dataset includes 900 listings (540
published), valid rental histories, future applications, visits, conversations,
messages, saved homes and amenities. Each demo property has four bundled sample
photos: an apartment interior, two private rooms and a shared kitchen. Normal
uploads remain available and are preserved. See [UI and sample photos](ui-improvements.md).

Choose a 12–128 character `DEMO_PASSWORD` in your ignored `.env`. It is used only
by the three accounts below; bulk accounts have independent random passwords.
The local environment prepared during Phase 6 already has a generated password.

```sh
docker compose up --build -d --wait
docker compose --profile demo run --build --rm seed
```

| Role | Email | Password |
| --- | --- | --- |
| Agency | `demo.agency@example.com` | `DEMO_PASSWORD` from your local `.env` |
| Landlord | `demo.landlord@example.com` | Same local value |
| Tenant | `demo.tenant@example.com` | Same local value |

Open http://localhost:5173/login. The landlord owns three properties; the tenant
has rental history, an active contract, a future application, a visit, a saved
home and an agency conversation. Public searches have homes in all four cities.

Without Docker, after applying migrations:

```sh
backend/.venv/bin/python -m app.seed --demo
```

This reads `DEMO_PASSWORD` from the environment or root `.env`, or prompts twice
if neither is set. `--non-interactive` requires a configured password. Optional
`--as-of YYYY-MM-DD` anchors the first import; otherwise dates use Europe/Rome today.

The import is transactional and serializes concurrent seed commands. Rerunning
preserves existing records, edits, dates and passwords. An incomplete dataset or
reserved email collision fails without replacing data. It runs only on explicit
invocation. To start over, use a fresh development database; the seed command has
no deletion/reset action. See the [Phase 6 report](phase-6.md) for details.

## Inventory and listings API

All routes use `/api/v1`. Landlords manage their own inventory; administrators can
manage every property while preserving its original landlord. Private collections
and individual records require authentication. Public listing and availability
responses omit owner identifiers, review notes and tenant/contract information.

| Methods | Path | Behavior |
| --- | --- | --- |
| GET, POST | /properties | Scoped paginated list; create property |
| GET, PATCH, DELETE | /properties/{id} | Owned/admin property detail, update, deletion |
| GET, POST | /properties/{id}/units | Scoped paginated units; create apartment or room |
| GET, PATCH, DELETE | /units/{id} | Owned/admin unit detail, price/detail update, deletion |
| GET, POST, PATCH | /units/{id}/listing | Owned/admin draft creation, detail and availability editing |
| POST | /listings/{id}/submit | Owner/admin submit for agency review |
| POST | /listings/{id}/withdraw | Owner/admin return unpublished review to draft |
| GET | /admin/listings | Admin queue with optional status and pagination |
| PATCH | /admin/listings/{id}/status | Admin approve/reject/publish/unpublish |
| GET | /listings | Public published search, filtering, sorting and pagination |
| GET | /listings/{id} | Public published detail, prices, amenities and images |
| GET | /listings/{id}/availability | Public live check for start_date and end_date |
| GET, POST | /properties/{id}/images | Owned/admin image metadata and multipart upload |
| PATCH, DELETE | /properties/{id}/images/{image_id} | Owned/admin alt text/order and deletion |
| GET | /images/{image_id} | Authorized image bytes; public only via published listings |

Create a property using fields title, description, city, address and a five-digit
postal_code; optional amenities is a list of names. Development addresses must be
synthetic; is_synthetic is fixed to true in API inputs. Landlords cannot supply
another owner; agency creation requires an active landlord_id. PATCH never allows
ownership changes. Amenities are trimmed, lowercased, deduplicated and normalized
in their own tables.

Create a unit with kind (`apartment` or `room`), name and monthly_rent. Optional
fields are deposit, bedrooms and area_sqm. EUR amounts use exact decimals with at
most two decimal places. One property may have at most one entire-apartment unit
and 50 total units. Unit names are unique within a property; property and kind are
immutable after creation. PATCH supports prices, deposit, size, bedrooms and name.
Delete operations reject records with rental applications/contracts or visit
history and roll back; existing business records are preserved.

Create its listing with available_from and optional available_until. Listing states:

```text
draft/rejected → submitted → approved/rejected
approved/unpublished → published → unpublished
submitted/approved/unpublished/rejected → draft (withdraw)
```

Rejecting requires review_note. Only the agency may approve, reject, publish or
unpublish. Availability dates may be edited only in draft/rejected states. While
any listing on a property is submitted/approved/published/unpublished, its property,
unit and image content is frozen to prevent changes bypassing approval. To edit:
unpublish public listings as admin, withdraw remaining reviewed listings as owner,
make changes, and resubmit. Drafting another existing unit's listing does not alter
approved property content and remains possible.

Public search supports city (case-insensitive), property_type (`apartment`/`room`),
min_price, max_price, min_rooms (minimum bedrooms), paired start_date/end_date,
sort (`newest`, `price_asc`, `price_desc`), page and page_size (maximum 100).
For example:

```text
/api/v1/listings?city=Bologna&property_type=room&max_price=700&start_date=2027-01-01&end_date=2027-03-01&sort=price_asc
```

Without dates, search shows unexpired published listings including future inventory,
with an explicit available_now value. With dates, it returns only listings whose
window covers the complete requested interval and whose unit is free throughout.
Intervals use `[start, end)`, allowing back-to-back rentals. Apartment rentals block
rooms and room rentals block the entire apartment, while distinct rooms may overlap.
All noncancelled contract intervals remain reserved, including historical completed
and terminated records. Availability checks are observations; contract approval
must recheck transactionally in Phase 4. Unit occupancy is derived from contracts
as occupied now, reserved for a future date, or available, using Europe/Rome dates.

## Image uploads

POST a multipart form with file, alt_text, optional position (0–1000) and optional
rental_unit_id belonging to the property. Default limits are 5 MiB per image,
20 million pixels and 30 images per property; the total multipart request is bounded
before parsing. Configure MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS and MAX_PROPERTY_IMAGES.
Only valid single-frame JPEG/PNG/WebP with matching MIME types are accepted.
Re-encoding applies orientation and removes EXIF/text metadata. Filenames are generated
by the server, and storage keys are not returned in APIs.

UPLOAD_DIR defaults to backend/uploads for local root-directory startup. Docker
pins /app/uploads and uses a persistent volume writable by its nonroot backend user.
Files are served through permission-aware routes rather than an unrestricted static
mount. Shared property pictures become public with any published unit; unit pictures
are visible with their unit or the whole apartment. Other unpublished room pictures
stay private. Unpublishing removes public file access. Managed/private previews need
a Bearer-authenticated request. Responses use no-store and nosniff headers.

File writes are compensated on database failure; deletes commit metadata before
removing files. A process crash or storage cleanup failure can leave an unreferenced
file; database authorization prevents serving it. Deployment should reconcile storage
and back up files with metadata. Missing files return 404 rather than exposing paths.

## AI assistant (Phase 7)

Sign in as a tenant and open **AI assistant** in the sidebar, or visit
http://localhost:5173/tenant/assistant. The assistant searches current published
homes, checks complete rental dates, reads your own rental status and agency
conversations, and prepares requested tasks. It can propose saving homes, applying,
requesting/cancelling visits, withdrawing applications and contacting the agency.
Review the exact dates, message and quoted rent in the card, then click **Confirm
action**. A chat reply such as “yes” does not execute an action. Proposals expire
after ten minutes; confirmation rechecks access, publication, availability and rent.

For live replies, add these backend settings to the ignored root `.env`:

```dotenv
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5.4-mini
ASSISTANT_ENABLED=true
```

Landlords can open **AI assistant** at `/landlord/assistant` or use the Blu
companion. The agent manages their own properties, rooms/apartments, rent,
deposits, amenities and draft listing availability; submits or withdraws eligible
listings; checks rental dates; and reads private contract and occupancy reports.
Every change requires a confirmation click. Ownership is assigned automatically,
and listing approval/publication stays with the agency. Open **Ask AI assistant**
on a property to start with its reference. See [landlord assistant](landlord-assistant.md).

Agency admins can open **AI assistant** in their sidebar at `/admin/assistant`,
or send requests through the floating Blu companion. The agency assistant can
create and edit properties, rooms/apartments and draft listings; submit, review,
publish and withdraw listings; review, approve or reject rental applications;
schedule and update visits; reply to tenant conversations; and read dashboard
and occupancy reports. Creation uses an existing active landlord. As with the
tenant assistant, writes require reviewing the exact action card and clicking
**Confirm action**. Chat history is private to each signed-in user, including
between agency admins. See [agency assistant](agency-assistant.md).

Then reload the backend environment:

```sh
docker compose up -d --force-recreate backend
```

Keep the key out of frontend/VITE settings and source control. For startup after a
code update use `docker compose up --build -d --wait`, which applies migrations.
Without a key, the app works normally and the assistant explains that it needs
configuration. `ASSISTANT_ENABLED=false` disables live chat. OpenAI requests use the
Agents SDK and Responses API; only the necessary rental data and chat are sent.
Local chat history is persisted in PostgreSQL. Provider response storage and SDK
tracing are disabled. Live requests use your OpenAI API account.

See [Phase 7](phase-7.md) for routes, tools, limits, privacy and verification.

## Current scope

Phases 1–7 are implemented: inventory, moderation, uploads, search, availability,
rental operations, private messaging, reporting, agency account management and
backend-connected public pages and role dashboards, plus synthetic demo data and
Docker integration verification and the tenant and agency AI assistants.

Password recovery and email verification are not implemented. No external email
is sent. Demo accounts and the Faker dataset are available through the opt-in seed. No real users,
real payments or outgoing email are created. Agency messages remain internal to
the platform. The optional tenant assistant calls OpenAI when configured.

The assistant's tools and confirmation workflows are verified with an offline model.
Live OpenAI search and action preparation also passed after local key configuration;
see the Phase 7 report.

## Rental operations API

Phase 4 routes are implemented under `/api/v1`. All require a bearer token;
collections support `page` and `page_size` (maximum 100). See the
[Phase 4 route table, lifecycle rules and verification](phase-4.md) for details.

- Tenants submit `/applications`, withdraw pending requests, request `/visits`,
  cancel visits, use `/conversations` and save `/saved-listings`.
- Agency administrators review, approve or reject applications and manage
  `/admin/contracts`, `/admin/visits` and `/admin/users/{id}`. Approval returns a
  confirmed contract after rechecking availability in the same transaction.
- `/contracts` shows a tenant's own contracts, an owner's redacted contracts,
  or the agency's full directory.
- `/dashboard/statistics` is role-scoped; `/occupancy` reports only the owner's
  properties or the agency's full portfolio.

Apply `backend/.venv/bin/alembic -c backend/alembic.ini upgrade head` from the
project root before starting this version. Migration
`0004_operations` installs PostgreSQL `btree_gist` for visit exclusions;
`0005_assistant` adds AI chat history and pending actions;
`0006_agency_assistant` preserves tenant chats and adds agency assistant access;
`0007_landlord_assistant` enables private landlord assistant history. Rental
dates are half-open: end dates can start another rental. Visits require timezone
offsets and use UTC; business occupancy dates use Europe/Rome.

The frontend is implemented in Phase 5; see its verification report.


## Frontend verification

The frontend uses React Router, TypeScript and Tailwind. Vite proxies `/api` to
FastAPI at `http://127.0.0.1:8000`; Compose uses `http://backend:8000`. Optional
settings are in `frontend/.env.example`. Static hosting needs both an API proxy
and an index.html fallback for frontend routes.

```sh
cd frontend
npm ci
npm run build
npm test
```

For Chrome tests against a disposable backend/database, follow the
[frontend README](../frontend/README.md). Tests create synthetic verification records
and random test administrator credentials. Phase 6 also verifies seeded demo
accounts against a separate Docker backend and frontend.

For the complete repeatable check, install the backend lock/editable package and
frontend dependencies, ensure Docker and Google Chrome are available, then run:

```sh
backend/.venv/bin/python -m app.verify
```

This starts the development stack, creates/reuses disposable `rental_phase7_test`
and `rental_browser_test` databases, applies migrations, runs backend tests,
frontend build/tests/lint, and all six Chrome tests. Backend tests truncate only
the disposable backend database. Browser data is retained for rerun checks; test
credentials are stored in ignored `frontend/.env.e2e.local`. The development
database is separate. Ports 8001 and 5174 belong to the verification services.
Use `--skip-build` when the backend image is already current. Stop only the extra
verification services afterward with:

```sh
docker compose -f docker-compose.yml -f docker-compose.verify.yml stop verify-frontend verify-backend
```
