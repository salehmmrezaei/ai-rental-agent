# Phase 7 — Tenant AI rental assistant

Phase 7 implements the architecture roadmap's tenant assistant using the OpenAI
Agents SDK, Responses API, live backend tools, server-side chat history and
explicitly confirmed rental actions. The feature is available in the tenant
sidebar at `/tenant/assistant` and from a published home's detail page.
The tenant agent has no agency approval or account-management capabilities.
The subsequent [agency assistant](agency-assistant.md) extension adds a separate
admin tool set and `/admin/assistant` workspace.
The [landlord assistant](landlord-assistant.md) adds an owner-scoped tool set at
`/landlord/assistant` and in Blu.

## Local setup

Add `OPENAI_API_KEY` to the ignored root `.env`, keep `ASSISTANT_ENABLED=true`,
and optionally set `OPENAI_MODEL` (default `gpt-5.4-mini`). The key is read only by
the backend. Do not put it in frontend/VITE settings or commit it.

```sh
docker compose up --build -d --wait
```

Compose applies migrations through `0009_assistant_visit_search` before starting the API. On subsequent key/config
changes run `docker compose up -d --force-recreate backend`. For native startup,
install the updated `backend/requirements.lock`, run Alembic to head and restart
Uvicorn. No change to development accounts or seeded rental data is needed.

The rest of the app starts without OpenAI credentials. The assistant then displays
an unavailable setup state and leaves ordinary browsing and rental forms available.
`ASSISTANT_ENABLED=false` disables new AI replies even with a key. Existing chats
remain readable and pending actions can still be confirmed or dismissed.

Implementation follows the official [Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python)
and [agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents).
The default model is configurable; see the official [GPT-5.4 Mini model page](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

## API and tools

All assistant routes require a live authenticated **tenant, landlord or admin**.
Each role receives its own tools; another user's chat or action receives the same 404 as an absent record.
Responses are marked `Cache-Control: no-store`.

| Method / route under `/api/v1` | Behavior |
| --- | --- |
| GET `/assistant/status` | Configuration status; never returns keys |
| GET `/assistant/threads` | Up to 20 recent user-owned chats |
| GET `/assistant/threads/{id}` | Saved messages, references and action states |
| GET `/assistant/threads/{id}/messages/{message_id}/listings?page=2` | Tenant-owned search results for the original filters, six cards per page |
| POST `/assistant/chat` | `{message, thread_id?}`; starts/continues a server-owned chat |
| POST `/assistant/actions/{id}/confirm` | Requires exactly the explicit boolean `{confirmed: true}` |
| POST `/assistant/actions/{id}/cancel` | Dismisses a pending proposal |

The client cannot submit model history, system messages, tenant identifiers or
action parameters to confirmation. The backend maintains the model's tool-call
history and generates cards from actual database results rather than model URLs.

Read tools search published homes by city/type/budget/bedrooms/dates, retrieve
published home details, check current availability, read the tenant's applications,
contracts, visits and saved homes, and read their agency conversations. Collections
are bounded and use existing scoped repositories/serializers. Message excerpts
are limited to 2,000 characters and marked when truncated. Profile emails,
password hashes, other tenants' records and landlord/private moderation data are
excluded from tool output. Tools never mark messages as read.

Pure tenant search replies display clickable listing cards with Previous and
Next buttons rather than a repeated text catalogue. Each search stores its
validated filters and paging metadata on the assistant message. Page navigation
queries current published inventory using those same filters, full rental dates
and sorting; it does not call the model or create another chat message. Other
assistant replies, explanations and action review cards remain visible.
Empty searches show an empty result state. Older messages without stored search
metadata retain their existing presentation.

After navigating results, the client may include
`listing_search_context: {message_id, page}` with a follow-up chat request. The
server verifies the message belongs to the same authenticated tenant and thread,
resolves the page again and supplies the ordered card identifiers privately to
the model. Clients cannot supply search filters or listing identities through
this context. The displayed user message remains unchanged.

Preparation tools can draft seven actions: save a home, apply, request a visit,
start an agency conversation, send a message in an owned conversation, withdraw
an owned pending application, or cancel an owned upcoming visit. They validate
identifiers/dates through existing schemas and services, but do not mutate rental
records. At most three distinct proposals are returned in one reply.

## Confirmation and consistency

Pending actions are saved in PostgreSQL with their canonical payload, a backend
summary, owning tenant and ten-minute expiry. The UI shows dates, messages, notes,
visit times and quoted rent before confirmation. A textual “yes” is not a
confirmation mechanism and the model has no confirmation tool.

Confirmation starts a fresh retryable transaction, reauthenticates the tenant,
locks the chat/action and invokes the existing rental service. Publication,
ownership, lifecycle, dates, overlapping bookings and quoted application rent
are checked again. A changed price requires a new proposal. Application/visit
creation remains distinct from agency approval/scheduling.

The rental write and action result commit together. Retrying a confirmed action,
including simultaneous requests, returns the persisted result without duplicating
the rental write. Dismissal and expiry cannot be bypassed through a chat reply.
Business conflicts leave the action pending and produce a sanitized error.

Chat generation releases the read connection while waiting for OpenAI, then
reauthenticates before persistence. A version check prevents concurrent replies
from overwriting history or ignoring a concurrent action resolution. Provider
failure, timeout, exhausted tool turns and token revocation discard the reply
and any buffered proposals without changing rental data.

## Limits, privacy and operational behavior

Default limits are 10 chat requests per tenant/minute/process, 2,000 input
characters, 6 agent model turns, 16 tool calls, 1,800 output tokens per model turn,
60 seconds per request, 8 referenced homes and 3 proposed actions per reply.
`ASSISTANT_RATE_LIMIT`, `ASSISTANT_MAX_TURNS` and `ASSISTANT_TIMEOUT_SECONDS`
are configurable within bounded ranges. At 40 chat revisions the tenant starts a
new chat. Model context drops complete oldest turns above 80,000 serialized
characters and rejects a single context exceeding 100,000 characters.

Chat text and the tool results necessary to answer it are sent to OpenAI using
the configured API account. The UI explains this. Responses set `store=false`;
SDK tracing is disabled. This does not change the provider's applicable API data
policies. Local chat content and pending/confirmed actions persist in PostgreSQL
and should be included in ordinary database retention/backup planning.

Logs include tool names/outcomes, run duration/counts and action kind/status.
Prompts, free-text messages, payloads, tokens, keys and provider exception strings
are not added to application logs. Provider/SDK errors return a generic 503;
rate limiting returns 429 with `Retry-After`. The app never substitutes canned
AI answers for an unavailable model.

Agent instructions require current tool evidence for rental claims and treat
listing text/message content as untrusted data. The model has no SQL, shell,
external browsing, account-editing, contract-approval or payment tool. Model text
renders as plain text and verified links use local listing routes. Authorization
and confirmation are enforced by backend code rather than relying on prompts.
Production still needs shared gateway rate limits, retention policy and live
model quality evaluation for its chosen model.

## Verification

```sh
backend/.venv/bin/python -m app.verify
```

This builds/starts development plus separate verification services, applies
migrations, runs the full PostgreSQL backend suite, frontend build/tests/lint,
and Chrome journeys. Backend tests use disposable `rental_phase7_test`; browser
tests use `rental_browser_test`. Development users/properties are preserved.
The actual Agents SDK loop runs with an offline scripted model in tests, and
the browser backend explicitly disables live AI requests.

New coverage includes live published-search references, server-owned chat
history, tenant isolation, all seven proposed tasks, no mutation before
confirmation, expiry/dismissal, publication/booking/rent changes, concurrent
confirmation, concurrent chat turns, revoked credentials, provider errors,
timeouts, SDK turn limits, rate limits, sanitized logs and safe text rendering.
Chrome checks the assistant setup screen on desktop/mobile, layout overflow and
automated accessibility alongside the existing rental journeys.

Verified locally on 13 October 2026: **252 backend tests, 44 frontend tests and
6 Chrome journeys passed**. The frontend production build passed, the dependency
check reported no conflicts and lint passed with the existing frontend warnings.
The updated development stack is healthy with migration `0005_assistant` applied.
No OpenAI API key was configured during this verification, so no live model request
was made.

A live acceptance check also passed on 13 October 2026 after the operator added
an OpenAI API key and the backend was restarted. The demo tenant's real request
returned six verified Bologna room cards under €700/month (38 matching published
listings). A follow-up in the same server-owned chat prepared the selected home's
save action with pending status and requested a confirmation click. The test
proposal was dismissed through the API, preserving existing saved homes. Both
model turns returned HTTP 200 using the configured `gpt-5.4-mini` model.

For a manual check, sign in as a tenant, ask “Find a room in Bologna under €700
a month”, check the returned home cards, then ask to save one. Verify that it
appears in Saved homes only after clicking Confirm. API account/model access
must permit the configured model. Refresh an already-open assistant page after
changing backend configuration so it reloads the availability status.

To stop only verification services afterward:

```sh
docker compose -f docker-compose.yml -f docker-compose.verify.yml stop verify-frontend verify-backend
```
