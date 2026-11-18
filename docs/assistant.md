# Assistant and Blu

Casa offers the same chat interface in each dashboard and through the floating [Blu companion](companion.md).

## Public demo: simulated, no API key

The public demo uses deterministic queries against fictional rental records. Every reply is labelled **Simulated AI Assistant**. It retrieves real database results, renders listing/visit cards and explains workflows without calling an external model or changing rental data.

| Role | Example question |
| --- | --- |
| Tenant | “Find rooms in Bologna under €700/month.” |
| Tenant | “Show my applications.” |
| Landlord | “Show my properties.” |
| Agency | “Show listings waiting for approval.” |

Supported requests use role-scoped queries; unsupported requests receive examples or explanations. A listing or property page can provide context, checked again by the backend.

Sessions and chat remain private to each visitor. PostgreSQL state supports separate serverless instances; the default Docker demo uses temporary memory. Expiry and capacity limits apply. See [architecture](architecture.md#temporary-state).

## Optional live assistant in local development

With public-demo mode disabled, the existing OpenAI integration can search records and propose actions. It is optional, requires a backend-only API key and can incur API charges. Casa's public Vercel entrypoint always disables it.

| Role | Available scope in normal mode |
| --- | --- |
| Tenant | Published homes, own applications/contracts/visits and agency conversations |
| Landlord | Own inventory, draft listings, availability, contracts and occupancy |
| Agency | Inventory moderation, application review, visit scheduling, conversations and reports |

Mutations require an explicit **Confirm action** click on a review card; typing “yes” is insufficient. Proposals expire after ten minutes. Confirmation rechecks authorization, record versions, valid transitions, dates and conflicts. The business change and action result commit together, and repeated confirmations do not duplicate writes.

The live assistant has no shell or SQL tool and cannot manage accounts or payments. Backend authorization applies independently of model output.

Live setup uses `PUBLIC_DEMO_MODE=false`, `OPENAI_API_KEY` and `ASSISTANT_ENABLED=true` in the private backend environment. The model is selected by `OPENAI_MODEL`. Keep credentials outside frontend code and `VITE_` variables. Live chat sends relevant conversation/tool data to the model provider; the public simulator does not.

## API and tests

All routes are under `/api/v1/assistant` and require an authorized role:

- `GET /status`, `GET /threads`, `GET /threads/{id}`
- `POST /chat` with a message and optional thread/context
- Listing/visit result pagination for the original authorized search
- `POST /actions/{id}/confirm` or `/cancel` in normal mode only

Another visitor/user's history is inaccessible, including between agency administrators. Responses use `Cache-Control: no-store`.

Tests cover isolation, role boundaries, confirmed actions, transaction conflicts, simulated responses and prevention of live model calls in demo mode. Live-agent tests use an offline scripted model. Run them through the [development guide](development.md#tests).
