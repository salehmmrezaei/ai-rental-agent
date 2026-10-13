# Casa — rental frontend

React, Vite, TypeScript and Tailwind CSS. Public listing search and tenant,
landlord and agency workspaces use the existing FastAPI backend. No rental
fixtures or mock responses are bundled into the application.

From this directory:

```sh
npm ci
npm run dev
npm run build
npm test
```

Start the backend on port 8000 using the repository README. Vite proxies
`/api` to `http://127.0.0.1:8000`, so browser requests stay on the frontend origin.
Docker supplies `API_PROXY_TARGET=http://backend:8000`. To change the local
backend address, copy `.env.example` to `.env` and edit API_PROXY_TARGET.
VITE_API_BASE_URL is an optional public build-time API base; it defaults to
`/api/v1`. An absolute URL requires the matching backend CORS origin. Keep
backend secrets out of VITE variables.

Phase 7 adds `/tenant/assistant`, recent chats, verified home references and
explicit confirmation cards. It uses the backend's `/assistant` routes and requires
a root backend `OPENAI_API_KEY` for live replies. The frontend never holds the key.
See [Phase 7 setup and verification](../docs/phase-7.md).

`npm run preview` serves a built bundle with the same proxy for local checks.
Static deployments must forward `/api` to FastAPI and rewrite other frontend
routes to index.html. Vite's development server is not a production host.

## Structure

- `src/api`: DTOs, HTTP client, multipart support and persisted bearer sessions.
- `src/auth`: server-verified profiles, expiration/revocation and role gates.
- `src/components`: forms, dialogs, pagination, listing cards and protected images.
- `src/hooks`: abortable account-scoped reads and guarded mutations.
- `src/layouts`: responsive public navigation and role-specific workspaces.
- `src/pages`: actual rental and property workflows.
- `src/tests`: Vitest/React Testing Library behavior tests with isolated fetch mocks.
- `e2e`: Chrome tests against the real local FastAPI/PostgreSQL stack.

## Browser tests

Install Chrome, backend dependencies and frontend dependencies. Use a disposable,
migrated PostgreSQL database ending in `_test`. These tests create synthetic
accounts and records. Never run backend truncating tests while browser tests share
that database. The administrator is provisioned through the backend models with
random credentials held in process memory; no demo password is saved.

From the repository root, start a temporary backend using your disposable URL:

```sh
export DATABASE_URL='postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@127.0.0.1:5432/rental_test'
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
ASSISTANT_ENABLED=false backend/.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

Set JWT_SECRET using the normal ignored backend configuration. In another terminal:

```sh
cd frontend
E2E_DATABASE_URL='postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@127.0.0.1:5432/rental_test' npm run test:e2e
```

Playwright owns the Vite server on port 5174. E2E_API_TARGET overrides its backend
proxy when necessary. Set E2E_BASE_URL to test an already-running frontend;
Playwright then uses that URL without starting Vite. E2E_SEED_DEMO=1 and a local
E2E_DEMO_PASSWORD enable the complete Faker dataset and fourth browser test.
Screenshots and test reports are ignored. Browser checks
cover persisted rental journeys, desktop/mobile layouts and automated WCAG checks;
manual assistive-technology review remains deployment work.

See [Phase 5 implementation](../docs/phase-5.md) for routes, decisions and verification.

Phase 6 provides populated demo accounts and verifies all three roles against
Docker. From the repository root, `backend/.venv/bin/python -m app.verify` runs
the current Phase 7 suite with separate disposable databases and automatically manages
the verification frontend on port 5174. See [Phase 6](../docs/phase-6.md) and the
root README for demo credentials and setup. The normal development site remains
http://localhost:5173. Verification disables live AI requests and checks the assistant's
setup state, desktop/mobile layout and accessibility. Backend tests exercise the
actual Agents SDK loop with an offline scripted model.
