# Agency AI assistant

Sign in as an agency admin and open **AI assistant** at `/admin/assistant`, or
open the Blu companion. Give requests in natural language, for example:

- “Show me listings waiting for approval.”
- “Create a synthetic property in Bologna for this landlord.”
- “Set Room A's monthly rent to €725.”
- “Approve this application at the current rent.”
- “Schedule this requested visit for Friday at 14:00 in Rome.”
- “Reply to this tenant with the visit details.”
- “Give me the occupancy report for next month.”

The agent reads live agency records, including unpublished inventory, and asks
for missing details or a choice when multiple records match. Active landlord
and agent lookup exposes only identifiers, names and roles. Tenant name searches
identify applications, visits and conversations without needing a record ID. Dashboard and occupancy
reports use the existing reporting services. Collection tools return six
records per page; the agent can paginate or fetch a specific record.

Listing results also appear as clickable cards showing the property, room or
apartment, city, monthly rent, review status and availability dates. Open a card
to review that exact listing in the private agency workspace, including listings
that have not been published. These references come from authorized backend
records and persist with the user's chat; the model does not generate their links.
The assistant keeps its reply brief instead of repeating the listing catalogue.

Visit queues also return persisted clickable cards with the property, room, tenant
name, preferred time, status and request note. Their count and Next/Previous pages
come from the same authorized backend query, including an explicit empty state.
Opening a card selects that exact visit in the agency scheduling workspace.
Page buttons reload current records without an AI request; a request scheduled in
the meantime leaves the pending queue. Each user's assistant history and pagination
remain private, including between agency administrators.

## Supported requests

| Workflow | Requests |
| --- | --- |
| Properties | Create for an active landlord; edit title, description, city, address, postal code and amenities |
| Rooms/apartments | Create; edit name, EUR rent/deposit, bedrooms and area |
| Listings | Create a draft; edit availability; submit, withdraw, approve, reject, publish and unpublish |
| Applications | Start review; approve and create a contract with reviewed rent; reject with a reason |
| Visits | Schedule/reschedule with exact time, duration and agent; complete, cancel or reject |
| Messages | Read agency conversations; send a reply in an existing conversation |
| Reports | Dashboard counts; occupancy and contracted monthly rent for an optional date |

Account management, deleting records, uploading images, changing landlord
ownership and editing contract terms are outside this assistant's tools.
Property inputs remain synthetic development data, as required by the existing API.

## Review and execution

Every write produces a card showing the proposed fields, dates, amounts and
message/rejection text. Click **Confirm action** to execute it or **Dismiss** to
cancel it. Saying “yes” in chat does not confirm an action. Proposals expire after
ten minutes, with at most three per reply. Confirmation rechecks authentication,
the user's role, the reviewed record version, ownership, valid transitions,
availability and scheduling conflicts through the existing services.

Property and unit edits follow the existing review locks. Unpublish and withdraw
reviewed listings first, using separately confirmed requests. Creating a property,
then a unit, then a draft listing is a sequence of confirmed actions; the agent
reads the newly created IDs before preparing the next step. Listing submission,
approval and publication also require individual valid transitions.

Inventory writes and assistant action completion commit in one transaction.
Repeated or concurrent confirmations return the saved result without duplicating
records or messages. A failed operation rolls back both the business change and
action resolution. A changed record requires a fresh proposal.

## Access, setup and migration

The existing `/api/v1/assistant` endpoints accept tenants, landlords and admins.
Each role receives separate SDK instructions and tool sets; service checks enforce
action roles independently of the model. The [landlord assistant](landlord-assistant.md)
uses owner-scoped inventory tools. Chats and action confirmations are private to their
owner; another admin cannot read or confirm a colleague's assistant requests.

Use the existing `OPENAI_API_KEY`, `OPENAI_MODEL` and `ASSISTANT_ENABLED` settings.
Apply `alembic upgrade head` and restart the backend after updating. Migration
`0006_agency_assistant` renames assistant ownership columns to `user_id` and
`user_role`, preserves existing tenant history, and permits agency actions.
Downgrading refuses incompatible agency records instead of silently deleting them.

Necessary agency rental data and chat are sent to OpenAI for answers. Provider
response storage and SDK tracing remain disabled. Password hashes, access tokens
and other account credentials are never available to agent tools. Descriptions
and messages are treated as untrusted data.

## Verification

`backend/tests/test_agency_assistant.py` uses a scripted model in the actual Agents
SDK loop and real PostgreSQL. It checks agency reads, private history, role
boundaries, property/unit/listing workflows, application decisions, visit scheduling,
agency replies, atomic rollback, stale records and concurrent confirmation.
Existing tenant assistant, inventory and database checks also cover regressions.
Frontend assistant and companion tests check agency access, chat navigation,
display of zero amounts and cleared fields, and explicit confirmation.
These automated checks do not make live, billable model requests.
