# Phase 5 — Frontend

Replaced the React/Vite starter with Casa, a complete frontend for the existing
rental platform. React Router, strict TypeScript and Tailwind are integrated.
The interface uses warm ivory, dark green and a locally authored SVG illustration.
Listing pictures come from actual backend uploads; missing images have honest
placeholders. No fake listings, statistics or success interactions ship with the app.

## Pages and behavior

| Area | Routes and capabilities |
| --- | --- |
| Public | `/`, `/listings`, `/listings/:id`, `/login`, `/register` |
| Tenant | `/tenant` overview, saved homes, applications, rentals, visits, agency messages and profile |
| Landlord | `/landlord` overview, properties, new/edit property, units/photos/listings, occupancy and rental history |
| Agency | `/admin` overview, user/property management, listing reviews, applications/contracts, visit scheduling, inbox, occupancy and profile |

Search combines city, room/apartment type, price range, bedroom count and paired
rental dates. Filters and pagination stay in the URL. Details display photos,
amenities, prices, deposit and listing window. A tenant checks full-stay availability
before applying, requests visits, saves homes and starts private agency conversations.
Anonymous actions return to the listing after authentication. Applications and
confirmed contracts are always persisted through existing APIs.

Tenant applications can be withdrawn with confirmation. Visits show upcoming or
previous records and can be cancelled. Saved records remain removable when the
listing is unpublished. Conversations support new topics, replies, incoming read
receipts, pagination and inbox refresh. Replying moves to the page containing the
new message. Profiles support name/email/password changes; email and password
changes require current-password verification and sign the user out afterward.

Owners can create/edit/delete properties and room or apartment units, set prices,
deposits, bedrooms and area, upload scoped pictures, edit captions/order and delete
photos. Availability drafts can be created/edited/submitted/withdrawn. Reviewed
listings freeze property/unit/photo edits, matching the backend rules. A published
listing requires agency unpublishing before owner withdrawal. History constraints
may prevent deletion; the actual backend error remains visible.

The agency reviews property/unit details and pictures, approves/rejects listings,
publishes/unpublishes them, reviews rental requests and atomically creates contracts
through approval. Contracts support confirmed-rent amendments, activation,
cancellation, completion and effective termination. Future activation/completion
controls stay disabled until the recorded dates permit them. Termination clearly
explains that the effective end is permanent while original dates stay in history.

Visits can be scheduled/rescheduled with active staff selection and duration,
completed, rejected with reasons or cancelled. Rescheduling preserves the assigned
agent unless changed. Staff/owner selectors use paginated real user records.
Agency user management edits name/email/activation without granting role changes
or password access; current admins cannot deactivate themselves. Directory role
filters are explicitly per page because the existing backend directory has no
role-search endpoint.

Dashboards load role-scoped statistics. Reports query occupancy for the selected
Europe/Rome date, with physical room counts, reservations and contracted monthly
rent. Landlord contract views use backend redaction; private tenant information is
not synthesized or requested through an alternate route.

## Architecture and authorization

`src/api` centralizes DTOs, JSON/multipart requests, sanitized API errors and image
URLs. `src/auth` persists only the bearer token and expiration, then reloads the
profile from `/users/me`. Local storage never supplies a trusted role. Route gates
wait for server verification; failures show a retry/sign-in choice. Authenticated
401 responses and expiration clear the session. Storage events synchronize tabs;
logout calls server revocation and clears local persistence.

Resource hooks include the account/session in their identity, abort obsolete reads
and never render a prior account's cached response. Mutation hooks prevent repeated
submissions while pending. Errors remain visible; UI success follows a real API
response. Record confirmations explain the change before the request. The backend
continues to enforce all ownership, roles, lifecycle and conflict rules.

Private photos are fetched with Authorization and rendered through temporary blob
URLs, which are revoked on cleanup. Tokens never appear in image URLs. Public
images use validated backend image paths. No external image or font services are
required. Native dialogs, associated labels/help text, focus outlines, skip links,
responsive navigation and reduced-motion support are implemented.

The backend adds only property title, unit name and property ID to scoped application
and visit DTOs, allowing recognizable rental records without disclosing owner contact
information. No schema migration is needed. Privacy tests cover those projections.
Vite proxies `/api` locally; Docker's frontend proxy targets the backend service.
Static hosting requires an API reverse proxy and SPA route fallback.

Implementation follows [Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite),
[React Router's declarative routing](https://reactrouter.com/start/modes), and
[Testing Library setup](https://testing-library.com/docs/react-testing-library/setup/).

## Verification

- Strict TypeScript production build passes.
- Vitest/React Testing Library: 33 tests pass. Coverage includes API headers/errors,
  multipart behavior, malformed/expired/revoked sessions, all-role restoration,
  protected routes, registration/sign-in/logout, return URL safety, profile changes,
  search validation, availability/application submission, withdrawal, agency approval
  and conflict errors, saved homes, messaging/read receipts, property creation/locks,
  user activation, effective contract termination, photo upload and form pagination.
- Backend regression: 220 tests pass, including two new privacy tests for rental
  presentation fields. The existing TestClient deprecation warning remains.
- Playwright: all 3 real Chrome browser tests pass. Chrome/PostgreSQL journeys verify owner registration, property/room creation,
  price edits, actual multipart photos, submission, agency approval/publication,
  tenant authentication/return, saving, dated availability, applications/contracts,
  owner rental history/occupancy, visit scheduling, private replies/read receipts,
  reload persistence, role redirect and save removal.
- Desktop/mobile homepage and all agency dashboard routes are checked with axe
  against WCAG 2 A/AA and 2.1 AA tags and tested for page-level horizontal overflow.
  Wide tables scroll inside their panels. Representative screenshots are inspected
  at desktop and mobile widths. Automated checks do not replace manual accessibility
  review with assistive technologies.

The first browser checks caught low contrast on tinted backgrounds and a mobile
flex/table overflow; both were corrected. A test selector was scoped to status badges,
and the sign-in helper now waits for the authenticated URL before navigation.
The file-input unit test bridges jsdom's synthetic FileList behavior; real browser
uploads were also exercised against FastAPI and PostgreSQL.

## Run and remaining phases

From `frontend`, run `npm ci`, `npm run dev`, `npm run build` and `npm test`.
The backend must be migrated and available. Full setup and browser-test instructions
are in the root and frontend READMEs. Apply no additional migration for Phase 5.

Bulk Faker data, documented demo accounts and full Docker Compose startup validation
remain Phase 6. An empty development database shows empty states until owners create
properties and the agency publishes listings. No payments, outgoing messages or AI
integration were introduced. Phase 7 remains gated on the core integration work.
