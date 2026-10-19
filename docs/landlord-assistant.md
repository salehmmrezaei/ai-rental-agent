# Landlord AI assistant

Sign in as a landlord and open **AI assistant** at `/landlord/assistant`, or open
Blu from any page. **Ask AI assistant** on a managed property pre-fills its
reference. Blu includes the managed property's reference when you send a message
from that page. The server checks ownership independently of page context.

| Use case | Example request |
| --- | --- |
| Portfolio and listing status | “Show my Bologna properties and draft listings.” |
| Property creation | “Help me add a property and its rooms.” |
| Property details and amenities | “Update this property's description and add WiFi.” |
| Rooms and apartments | “Add a study room at €700 per month with a €500 deposit.” |
| Rent and deposit changes | “Set Room A's rent to €725 and deposit to zero.” |
| Listing preparation | “Create a draft listing available from January 1, 2027.” |
| Availability changes | “Remove the end date from this draft listing.” |
| Listing submission | “Submit this listing for agency review.” |
| Listing withdrawal | “Withdraw my submitted listing so I can edit it.” |
| Exact rental dates | “Is Room A available from January 1 to March 1, 2027?” |
| Contracts | “Show the rental dates and agreed rent for this property's contracts.” |
| Occupancy and contracted rent | “Give me an occupancy report as of January 1, 2027.” |

The assistant reads live records, searches by property/unit name or city, filters
by property or status and paginates in groups of six. It asks for missing details
or a choice between matching records. New properties belong to the signed-in
landlord automatically. Property inputs remain synthetic development data as
required by the existing app. Contracted monthly rent describes agreements;
payment collection and payment tracking are not implemented.

Every write produces a review card with exact proposed fields and amounts.
Click **Confirm action** or **Dismiss**. Typing “yes” does not execute a change.
Proposals expire after ten minutes. Property, unit and listing creation each
require confirmation; the agent uses the confirmed record IDs for the next step.

Listing approval, rejection, publishing and unpublishing remain agency actions.
Reviewed property and unit content stays locked: the agency must unpublish public
listings, then the owner can withdraw reviewed listings before editing. Existing
forms handle photo uploads and deletions; those operations are outside the agent.
Tenant application decisions, visit scheduling, messaging, contract changes,
maintenance tickets, accounting and legal decisions are also outside its tools.

Reads and proposals check the live authenticated role and ownership. Confirmation
checks them again, along with record versions, review locks and availability.
Contracts omit tenant identifiers and personal details. Landlords cannot access
tenant applications, messages, other landlords' inventory or another user's
assistant chats. Retried or concurrent confirmations use the persisted result,
and business changes commit atomically with action completion.

Use the existing backend `OPENAI_API_KEY`, `OPENAI_MODEL` and `ASSISTANT_ENABLED`
settings. Apply `alembic upgrade head` and restart the backend. Migration
`0007_landlord_assistant` permits landlord-owned assistant threads while preserving
tenant and agency history. Its downgrade refuses incompatible landlord history
instead of deleting it. Without an API key the UI explains the setup state and
ordinary landlord forms remain available.

`backend/tests/test_landlord_assistant.py` exercises the actual Agents SDK loop
with an offline scripted model and real PostgreSQL. It covers portfolio reads,
contract privacy, creation through listing submission, owner and role boundaries,
availability conflicts, stale/locked records, transaction rollback and concurrent
confirmation. Frontend tests cover landlord chat, review cards, destinations and
Blu. Browser tests check desktop/mobile access and setup behavior. Automated tests
do not make billable model calls.
