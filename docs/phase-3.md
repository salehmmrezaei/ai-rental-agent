# Phase 3 — Properties and listings

Phase 3 is implemented and verified. Phase 4 rental operations, Phase 5 product
frontend, Phase 6 Faker/demo data and Phase 7 AI remain outside this delivery.

## Delivered

- Property CRUD for authenticated owners and agency admins; scoped pagination,
  validated synthetic addresses, immutable ownership, normalized amenities.
- Apartment/room CRUD with independent rents/deposits, validated sizes, one entire
  apartment per property, unique unit names and derived occupancy status.
- Listing drafts, availability editing, submission/withdrawal, agency approval,
  rejection with reason, publication/unpublication and a paginated review queue.
- Property content freezing under the same row lock used for review transitions,
  preventing edits from bypassing approval. Published listings must first be
  unpublished by the agency before reviews can be withdrawn for editing.
- Public published listing detail/search with city, price, apartment/room type,
  room/bedroom count, complete date-range availability, sorting and pagination.
  Future inventory exposes available_now explicitly. Private metadata is omitted.
- Shared contract-based availability and occupancy logic with apartment/room
  conflict handling, independent room bookings and adjacent interval boundaries.
- Property/room image upload, metadata editing, ordering, deletion and permission-aware
  serving. JPEG, PNG and WebP content is decoded/re-encoded; dimensions, animation,
  size and MIME mismatch are checked; private metadata is stripped.
- Upload request bounds before multipart parsing, generated storage names, file
  cleanup on failed inserts/deletes, and persistent nonroot Docker image storage.
- Existing rental/visit history preserved by constrained deletion and transaction
  rollback. Previous ownership, authentication and rental-conflict tests remain passing.

Endpoint tables, input fields, workflows and configuration are documented in the
[README](../README.md#inventory-and-listings-api); key decisions are in the
[architecture document](architecture.md#phase-3-inventory-decisions).

## Files added or changed

| Files | Purpose |
| --- | --- |
| `backend/app/schemas/inventory.py` | Strict property/unit/listing/image inputs; private/public response models and query validation |
| `backend/app/repositories/inventory.py` | Shared availability predicate, occupancy, search, images and amenities queries |
| `backend/app/services/inventory.py` | Scoped CRUD, parent locks, amenities, review transitions, deletion rollback and safe views |
| `backend/app/services/images.py` | Validation, metadata removal, storage, compensated writes, permissions and cleanup |
| `backend/app/routers/inventory.py` | Inventory, moderation, public search/availability and image endpoints |
| `backend/app/upload_limits.py` | Bounded multipart request middleware |
| `backend/alembic/versions/0003_inventory.py` | Reversible unpublished-review withdrawal transitions |
| `backend/app/main.py`, `backend/app/config.py`, `backend/app/errors.py` | Router/config/middleware wiring and safe constraint-conflict responses |
| `backend/app/routers/health.py` | Readiness requires current migration 0003_inventory |
| `backend/tests/test_inventory.py` | 70 new PostgreSQL-backed workflow and security cases |
| `backend/pyproject.toml`, `backend/requirements.lock` | Pillow/multipart dependencies and tested versions |
| `backend/Dockerfile`, `backend/.dockerignore`, `docker-compose.yml` | Writable persistent upload volume and excluded local uploads |
| `.env.example`, `README.md`, `docs/architecture.md`, `docs/phase-3.md` | Configuration, setup, API behavior, decisions and verification |

No existing frontend source, prior migration, user data or project source was
removed. No new database tables were needed; the normalized Phase 1 entities cover
inventory. The new migration updates the database listing transition function.

## Verification

All database checks used the isolated temporary PostgreSQL server on localhost
port 55432 and disposable database rental_phase1_test. Fixtures and the real HTTP
smoke workflow used clearly synthetic users, properties, dates and generated solid-color
images. No payments, external messages, real personal data or OpenAI calls were used.

| Executed check | Result |
| --- | --- |
| `pip install -e 'backend[test]'` | Pillow/multipart dependencies installed |
| `alembic -c backend/alembic.ini upgrade head` | Migration applied |
| `pytest backend/tests -q --tb=short` | **162 passed, 1 warning, 22.93 seconds**, final run |
| `alembic check` | No new upgrade operations detected |
| `alembic downgrade 0002_auth` then `alembic upgrade head` | Phase 3 migration round trip passed |
| `alembic check` after round trip | No new upgrade operations detected |
| `alembic upgrade head --sql` | Offline SQL generated successfully |
| Real Uvicorn/HTTP workflow without dependency overrides | Property/unit CRUD, image upload, approval/publication, public search, live availability, unpublish/withdraw, editing and cleanup passed |
| `pip check` | No broken requirements |
| `python -m compileall` | Application, migrations and tests compile |
| `docker compose config --quiet` | Compose configuration valid |
| `git diff --check` | No whitespace errors |

The 162 tests comprise 92 existing cases and 70 new cases. New coverage includes
actual-route role/ownership enforcement, safe admin ownership assignment, synthetic
and immutable input restrictions, unique apartment/name constraints, amenity persistence,
complete review lifecycle and content freezes, invalid/expired listing handling,
public privacy, search filters/sorting/pages, dates/window boundaries, apartment/room
availability matrix, current/future occupancy and cancellation, historical deletion
rollback, valid JPEG/PNG/WebP upload, generated filename safety, private/public image
visibility, room isolation, MIME/invalid-content rejection, byte/pixel/image limits,
chunked request bounds, PNG text and JPEG EXIF removal, and physical file cleanup.

The first full Phase 3 run passed 158 tests. Final review tightened inaccessible
resource query privacy and partial-write cleanup, then added four edge cases; the
final complete run passed 162 tests. Existing concurrent contract-write tests under
READ COMMITTED and REPEATABLE READ also remain passing.

## Limits and next phase

- Docker daemon is stopped. Compose configuration passed, but image builds and
  complete container startup were not executed. The real backend HTTP workflow
  was verified through local Uvicorn and PostgreSQL.
- One existing Starlette/httpx TestClient deprecation warning remains; tests pass.
- Availability results are live observations, not booking guarantees. Phase 4
  approval must recheck and create the contract in one transaction; the database
  already rejects overlapping apartment/room contracts.
- Noncancelled completed/terminated records retain their recorded intervals.
  Effective early termination and future-date release remain Phase 4 design work.
- Upload bytes use local storage with a persistent Docker volume. A crash between
  file/metadata operations can leave an unreferenced file; it cannot be served.
  Storage reconciliation and coordinated file/database backups are deployment work.
- Search min_rooms represents bedrooms. Without dates, unexpired future inventory
  remains visible with available_now; callers must supply dates for full-stay filtering.
- Product UI, authentication screens and dashboards remain Phase 5; no frontend
  buttons or mock rental interactions were introduced. Faker/demo credentials remain
  Phase 6. AI has not started.

## Run

Existing setup instructions remain valid. Install the updated dependency lock and
apply migrations for local development, or start Docker and run:

```sh
docker compose up --build
```

Open http://localhost:8000/docs to register/login and exercise the real routes.
Administrator provisioning is documented in the README. UPLOAD_DIR defaults to
backend/uploads locally; Docker uses its persistent /app/uploads volume.

Phase 4 will add rental applications and transactional approvals/rejections,
contract management, visits/scheduling, internal tenant-to-agency messages,
occupancy reporting and transaction retries. Phase 4 has not started.
