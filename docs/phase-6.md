# Phase 6 — Demo data and integration

Phase 6 implements the Faker dataset, documented local demo accounts, rental
histories and repeatable Docker/user-journey verification. Phase 7 AI work remains
outside this delivery. No schema migration is required beyond `0004_operations`.

## Dataset

| Records | Count and distribution |
| --- | --- |
| Landlords / tenants / agency | 100 / 200 / 1 |
| Properties | 300; 75 each in Bologna, Milan, Rome and Florence |
| Units | 900; one apartment and two rooms per property |
| Listings | 900; 540 published; 72 each draft, submitted, approved, rejected and unpublished |
| Applications | 750; 550 approved histories; 50 each submitted, reviewing, rejected and withdrawn |
| Contracts | 550; 150 active; 100 each confirmed, completed, terminated and cancelled |
| Visits | 100; 20 each requested, scheduled, completed, cancelled and rejected |
| Conversations / messages | 50 / 150, including unread agency replies |
| Saved homes | 200 |
| Amenities | Five reusable names and 900 property associations |

Names and synthetic streets use Faker's Italian locale. Names have a Demo prefix,
emails use reserved `example.com`, addresses have a Synthetic prefix, and every
property has `is_synthetic=true`. Prices use exact decimals. Each property has
three sampled amenities. Descriptions identify the data as demonstration records.
The later [UI improvement](ui-improvements.md) adds bundled AI-generated sample
photos to the demo properties. Existing upload workflows remain available.

The first import anchors dates to Europe/Rome today, or `--as-of YYYY-MM-DD`.
Listing windows span 400 days before to 730 days after the anchor. Histories cover
whole-apartment rentals, room rentals, effective early termination, back-to-back
leases, simultaneous distinct-room rentals by different tenants, cancellation,
current occupancy and future reservations. Completed histories end in the past;
active intervals contain the anchor; confirmed leases begin in the future.
Scheduled visits have nonoverlapping staff slots and exact duration end times.

## Seeding and credentials

From the repository root, configure the normal ignored `.env` and a local
`DEMO_PASSWORD` of 12–128 characters, then run:

```sh
docker compose up --build -d --wait
docker compose --profile demo run --build --rm seed
```

For a migrated local PostgreSQL database, run
`backend/.venv/bin/python -m app.seed --demo`. The CLI reads the environment/root
`.env` password, or prompts twice. `--non-interactive` fails if none is configured.
It reports counts and account emails without printing passwords or connection URLs.

| Account | Email | Password |
| --- | --- | --- |
| Agency | `demo.agency@example.com` | Local `.env` `DEMO_PASSWORD` |
| Landlord | `demo.landlord@example.com` | Same local value |
| Tenant | `demo.tenant@example.com` | Same local value |

The operator-selected password is individually Argon2id-hashed with independent
salts for those three accounts. The other 298 accounts use independently generated,
discarded random passwords; the shared demo password cannot log into them.
The development environment prepared for this phase contains a generated local
password in ignored `.env`. The landlord owns homes 001, 101 and 201. The tenant
has an active rental, histories, a future application, a requested visit, a saved
home and an agency conversation. The agency sees the complete portfolio.

The seed CLI is an explicit development import. It does not run during migrations,
normal Docker startup or application startup. Fixed versioned UUIDs identify its
records. All inserts run in one transaction with an advisory transaction lock.
Existing email collisions are rejected before account creation; triggers, foreign
keys and exclusions remain enabled throughout. Historical recognized states are
inserted directly, as allowed for controlled imports by the existing schema.

Rerunning a complete seed is a no-op: it does not duplicate records, change dates,
rotate passwords or erase edits. A changed password/date argument does not change
the original import. Missing reserved business records cause a clear failure;
the command never silently fills partial data, promotes existing accounts or
deletes data. Use a fresh development database for a clean dataset. Shared amenities
with matching names are reused. A failed transaction rolls back all inserted rows.

## Repeatable verification

Install the backend lock and editable package and run `npm ci` in `frontend`.
Docker Desktop/Engine, Compose and Google Chrome are required. Configure the root
`.env`, then execute from the repository root:

```sh
backend/.venv/bin/python -m app.verify
```

The host-side verifier creates/reuses `rental_phase6_test` for database regression
and `rental_browser_test` for Chrome. These are disposable; backend tests truncate
their database. The development database is separate. All database URLs remain
in process environments. The verifier starts the normal stack and the additional
services defined in `docker-compose.verify.yml`, applies migrations and runs:

- Full PostgreSQL backend regression suite, including the complete seed tests.
- Strict TypeScript/Vite production build, Vitest tests and frontend lint.
- Chrome workflow, seeded demo-account, public responsive/accessibility and agency
  responsive/accessibility tests against the Docker frontend/backend.

The verification frontend on port 5174 proxies to its isolated backend on port
8001. Each frontend has its own dependency volume to avoid competing `npm ci`
operations. Both frontends have HTTP health checks, so Compose `--wait` verifies
they are serving pages. Verification uploads have their own persistent volume.
The development site uses port 5173 and backend port 8000.

The browser setup requires a database ending in `_test`, imports the demo dataset,
and creates a random synthetic test administrator. Demo test credentials are
generated once and saved to ignored `frontend/.env.e2e.local` for reruns. It uses
`E2E_BASE_URL` to test the Docker site without starting a host Vite server. Existing
local browser instructions still work; the demo test skips unless its seed/password
is configured. The agency workflow traverses paginated approval queues after
property details finish loading and filters requested visits, so existing demo
records do not hide newly created records.

Use `--skip-build` only when Docker images are current. After verification, stop
the extra services without removing any volumes:

```sh
docker compose -f docker-compose.yml -f docker-compose.verify.yml stop verify-frontend verify-backend
```

## Verification results

Validated on 12 October 2026:

- Docker PostgreSQL 18 starts healthy; migrations complete; the nonroot backend
  passes readiness; frontend HTTP health checks pass.
- Opt-in Docker seed imports the full dataset successfully.
- Docker and local CLI reruns report `created: false` and preserve all records.
  Development login, role dashboards, readiness and the 540 published listings
  remain available through the frontend API proxy after backend/frontend restart.
- Backend: 231 tests pass, including 11 phase 6 tests covering real demo login,
  data counts/city distribution, contract matching and conflicts, password isolation,
  account preservation, idempotency, partial-data refusal, collision refusal,
  atomic rollback and concurrent advisory-lock contention.
- Frontend: production build and all 33 tests pass. Lint passes with existing
  React hook/Fast Refresh warnings. The existing TestClient deprecation warning
  remains in backend tests.
- Chrome: all four browser tests pass against the Docker verification stack,
  including desktop/mobile accessibility checks with the full seed dataset.
- The complete `python -m app.verify` command passes with freshly rebuilt images
  and an already-seeded browser database, verifying the rerun path end to end.

The seeded browser checks cover all three demo logins, reload persistence,
populated dashboards, rental history, agency messages, city/type filters and
pagination. Existing full journeys cover owner registration, inventory editing,
real photo upload, review/publication, tenant registration, dated availability,
applications/approval/contracts, owner occupancy, visit scheduling, private
messaging/read receipts and authorization redirects.

Faker is pinned to 40.43.0 for reproducible generated content; its
[seeding documentation](https://faker.readthedocs.io/en/stable/index.html#seeding-the-generator)
explains why matching package versions matter. Password hashes and random bulk
credentials intentionally differ between fresh imports.
