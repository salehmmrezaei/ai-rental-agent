# Casa frontend

React, TypeScript, Vite and Tailwind CSS. Uses the real FastAPI API for public search and tenant, landlord and agency dashboards.

From this directory:

```sh
npm ci
npm run dev
npm run build
npm test
```

Start FastAPI on port 8000. Vite proxies `/api` to `http://127.0.0.1:8000`; set `API_PROXY_TARGET` to change it. `npm run preview` serves the production build with the same proxy. Backend credentials stay outside `VITE_` variables.

Public-demo behavior comes from the backend: password-free role switching, read-only rental records and simulated chat in both the dashboard and Blu. Demo tokens are stored per tab.

## Browser checks

Playwright uses Google Chrome. With a running demo frontend:

```sh
E2E_PUBLIC_DEMO=1 E2E_BASE_URL=http://localhost:5173 npm run test:e2e
```

For normal rental workflows, use the managed `python -m app.verify` command in the [development guide](../docs/development.md#tests). Individual runs need a migrated disposable `E2E_DATABASE_URL` ending in `_test` and a backend on port 8001. Without `E2E_BASE_URL`, Playwright starts Vite on port 5174; `E2E_API_TARGET` selects its API target.

[Project overview](../README.md) · [Setup & tests](../docs/development.md) · [Assistant](../docs/assistant.md) · [Blu](../docs/companion.md)
