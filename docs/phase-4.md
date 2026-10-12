# Phase 4 — Rental operations

Implemented the backend rental workflows on the existing PostgreSQL/FastAPI stack.
Phase 5 frontend work has not started.

## Routes

All paths below are relative to `/api/v1`; all require bearer authentication.
Collections return `items`, `total`, `page` and `page_size` (1–100). Private
responses use `Cache-Control: no-store`.

| Methods and paths | Access and behavior |
| --- | --- |
| GET/POST `/applications` | Tenant's own applications; agency can list all. Creation takes listing_id, start_date, end_date and optional note. |
| GET `/applications/{id}` | Own tenant or agency; hidden records return 404. |
| POST `/applications/{id}/withdraw` | Own tenant; submitted/reviewing requests only. |
| GET `/admin/applications` | Agency directory, optional status and rental_unit_id filters. |
| POST `/admin/applications/{id}/review` | Agency starts review. |
| POST `/admin/applications/{id}/approve` | Agency approves and creates a confirmed contract atomically; optional monthly_rent override. Returns the contract. |
| POST `/admin/applications/{id}/reject` | Agency rejects, with required review_note. |
| GET `/contracts`, `/contracts/{id}` | Own tenant; landlord's owned properties with tenant/application IDs omitted; agency unrestricted. |
| GET/POST `/admin/contracts` | Agency directory or create from application_id, using the same atomic approval operation. |
| PATCH `/admin/contracts/{id}` | Agency status, confirmed-rent amendment or effective termination. |
| GET/POST `/visits`, GET `/visits/{id}` | Own tenant or agency reads; tenant requests using listing_id and future requested_at with timezone. |
| POST `/visits/{id}/cancel` | Own tenant cancels requested/scheduled visits. |
| GET `/admin/visits` | Agency visit directory. Visit lists filter by status and period=all/upcoming/past. |
| PATCH `/admin/visits/{id}` | Agency schedules/reschedules, completes, cancels or rejects visits. |
| GET/POST `/conversations`, GET `/conversations/{id}` | Own tenant or agency reads; tenant creation requires subject and initial_message. |
| GET `/admin/conversations` | Agency inbox. |
| GET/POST `/conversations/{id}/messages` | Own tenant or agency; new message takes body. Sender comes from authentication. |
| POST `/conversations/{id}/read` | Mark incoming unread messages; returns updated count. |
| GET/PATCH `/admin/users/{id}` | Agency profile management: full_name, email and/or is_active. |
| GET/POST `/saved-listings` | Tenant's own saves; POST takes listing_id. Repeated save returns the existing record. |
| DELETE `/saved-listings/{id}` | Remove own save by saved-record ID. |
| GET `/dashboard/statistics` | Tenant, landlord or agency statistics scoped to their role. |
| GET `/occupancy`, `/admin/occupancy` | Owner's portfolio or agency report; optional as_of business date and pagination. Admin alias is agency-only. |

Applications and contract directories accept status and rental_unit_id filters.
Messages sort chronologically; applications/contracts sort newest first. Landlords
cannot read applications, visit requests or tenant conversations. Staff IDs appear
only in agency visit responses. Contract ownership checks apply to each read.

## Workflow rules

Application creation requires a published listing, nonpast start, end after start,
the full listing availability window and no conflicting contract. Pending requests
reserve no dates. Duplicate pending requests from the same tenant for the same
unit/dates return 409. Other applicants may request the same interval until approval.

Applications transition submitted → reviewing/rejected/withdrawn, then reviewing →
approved/rejected/withdrawn. Approval can start directly from submitted, performing
both transitions inside one transaction. The property is locked before the request;
publication, active tenant and availability are rechecked. A losing approval leaves
the request pending and creates no contract. Repeating approval returns the existing
contract; a conflicting rent override returns 409. Contract dates/parties cannot
be supplied independently of the application.

Contracts transition confirmed → active/cancelled and active → completed/terminated.
Activation requires the start date to have arrived. Completion requires the original
end date to have arrived; an elapsed confirmed contract can pass through active to
completed atomically. Rent can change only while confirmed. Termination requires
an explicit terminated_on date after start and no later than original end. The
original interval remains available for history; the effective end is immutable.
All dated availability and occupancy queries use the effective end. Intervals are
half-open `[start, end)`, permitting adjacent contracts. A cancelled contract
reserves no interval; completion retains historical dates. Legacy terminated rows
without terminated_on retain their original end.

Visits transition requested → scheduled/rejected/cancelled, then scheduled →
completed/cancelled; scheduled visits can also be rescheduled. Scheduling requires
future scheduled_at, duration_minutes (1–180, default 30), and an active assigned
administrator (defaults to the acting admin). PostgreSQL rejects overlapping staff
or tenant appointments, even at different properties; adjacent appointments pass.
Completion requires the visit end to have elapsed. Rejection requires agency_note.
Timezone offsets are required; timestamps are normalized to UTC.

Conversations are private between one tenant and the agency. Neither caller-supplied
sender IDs nor tenant IDs are accepted. Bodies are trimmed, nonempty and limited to
10,000 characters. Only incoming messages are marked read; the agency shares one
read state across staff. Sending touches conversation.updated_at for inbox sorting.
Sent bodies, sender IDs and conversation identities are immutable in PostgreSQL.
No external messages are sent.

Admin account edits preserve role and password controls. Email/activation changes
increment token_version; deactivation blocks existing tokens immediately. Reactivation
does not restore old tokens. Admins cannot deactivate themselves; stable active-admin
locks and reauthorization prevent concurrent mutual deactivation. Saved listings are
private and only published listings can be added. An unpublished saved listing remains
in the list with listing=null, allowing removal without exposing reviewed content.

## Reporting

Counts derive from database records. Tenant statistics include pending applications,
current/future rentals, upcoming visits, saved listings and unread agency messages.
Landlord statistics include owned properties, contracts, published listings and
occupancy. Agency statistics add user, pending review/application and inbox counts.

Occupancy uses Europe/Rome dates and effective contract intervals. Properties with
rooms count rooms as physical units, excluding their alternative whole-apartment
unit from the denominator. Whole-apartment contracts occupy all those rooms; rent
is counted once. Properties without rooms count their apartment units. Future
bookings count as reserved only when the unit is not currently occupied. Totals
cover the entire scoped portfolio while items are paginated. Contracted monthly
rent sums current noncancelled contracts; it is not collected revenue.

## Migration and transaction safety

`0004_operations` adds review notes, effective contract termination and visit
scheduling fields, PostgreSQL `btree_gist` exclusions, and identity guards. Existing
scheduled visits get a 30-minute end; existing staff assignments remain null until
rescheduled. Migration requires permission to install btree_gist. Legacy overlapping
scheduled visits must be resolved before exclusions can be installed; no data is
silently discarded.

All new mutations use fresh sessions and authorization for each complete transaction.
Serialization failures (40001) and deadlocks (40P01) roll back before bounded retries
(maximum three attempts with short jitter). Exhaustion and integrity conflicts return
sanitized 409 errors. Property booking_revision updates ensure stale transactions
abort under stronger isolation. Existing inventory mutations use the same property
lock, coordinating publication changes with approval. The database contract guard
still enforces apartment/room conflicts for direct writes.

Downgrade refuses leases whose original intervals would overlap after effective
termination is removed. Resolve those records before downgrade; restoring earlier
rules must not introduce invalid bookings. The shared btree_gist extension is retained.

## Verification

The final complete backend run passed **218 tests** (162 existing + 56 new),
with one existing TestClient deprecation warning.

- Existing 162 backend tests passed after the new migration and endpoint wiring.
- 56 new Phase 4 tests passed: complete application/contract lifecycles, rejection,
  withdrawal, inactive applicants, duplicate/past/unpublished requests, ownership,
  role privacy, idempotent approval, early termination and reporting, visit lifecycle
  and staff/tenant overlap, internal messages/read receipts, token revocation and saves, concurrent administrator deactivation safety, and
  refusal to downgrade contracts that depend on effective termination.
- Competing apartment/room approvals yielded exactly one contract under READ
  COMMITTED, REPEATABLE READ and SERIALIZABLE. Concurrent visits at different
  properties with the same staff member yielded exactly one scheduled visit.
- Real PostgreSQL failure injection verified rollback and complete reexecution for
  serialization/deadlock errors, bounded retry exhaustion and reauthorization after
  token revocation between retries. Identity changes were rejected by database triggers.
- A fresh disposable PostgreSQL database passed upgrade → head, downgrade → base,
  re-upgrade → head, with no metadata differences. The temporary database was removed.
- A localhost Uvicorn/PostgreSQL smoke run exercised registration/login, publication,
  application approval, tenant/owner contract views, visit scheduling, agency replies,
  read receipts, saves, dashboard statistics and occupancy. The server was stopped.

Run the full suite against a migrated, disposable database ending in `_test`:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/rental_test'
DATABASE_URL="$TEST_DATABASE_URL" backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/pytest backend/tests -q
```

The existing Starlette/httpx TestClient deprecation warning remains. Docker configuration
can be validated, but complete Docker startup is still pending the Phase 6 integration
work. The frontend remains the Vite/React starter; Phase 5 will connect the real routes.
No payments, external messaging or AI integration were added.
