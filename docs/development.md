# Development

Run commands from the repository root. The [README](../README.md) introduces the project; [architecture](architecture.md) explains the design.

## Docker quick start

Requires Docker with Compose and available ports 5432, 8000 and 5173.

```sh
cp -n .env.example .env
```

Edit the private `.env`: choose a database password, match it in `DATABASE_URL`, generate a random `JWT_SECRET` of at least 32 bytes, and set `DEMO_PASSWORD` to 12–128 characters. Keep `OPENAI_API_KEY` empty.

```sh
docker compose up --build -d --wait
docker compose --profile demo run --build --rm seed
```

Open [localhost:5173](http://localhost:5173). Sign in using `DEMO_PASSWORD` and one of these fictional accounts:

| Role | Email |
| --- | --- |
| Tenant | `demo.tenant@example.com` |
| Landlord | `demo.landlord@example.com` |
| Agency | `demo.agency@example.com` |

The seed adds 300 properties, 900 listings and bundled photos. Reruns preserve records, dates and passwords; incomplete seeds fail without replacing data. Use a fresh database for a new dataset.

```sh
docker compose logs --tail 100 backend migrate db
docker compose stop
```

Database and upload volumes survive ordinary restarts. `down -v` deletes volumes.

## Native development

Requires Python 3.12+, Node 24 and PostgreSQL. Configure the root `.env` for your local database.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.lock
backend/.venv/bin/python -m pip install --no-deps -e backend
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m app.seed --demo --non-interactive
backend/.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
```

In a second terminal:

```sh
npm ci
npm --prefix frontend ci
npm run dev
```

Vite proxies `/api` to FastAPI on port 8000. `API_PROXY_TARGET` changes that address; backend secrets belong outside `frontend/` and `VITE_` variables.

## Local Neon demo

Follow [Neon setup](vercel-neon.md) for migrations and the restricted runtime role. Create private `.env.neon-demo` from `.env.vercel.example`, using the pooled `casa_runtime` URL and an independent JWT secret; set permissions to `600`.

```sh
npm run dev:neon:api
```

Run `npm run dev` in another terminal. This uses the Vercel entrypoint: password-free role entry, simulated chat, PostgreSQL visitor state and read-only rental data. Your normal Docker `.env` remains separate.

## Tests

Frontend build and tests:

```sh
npm run build
npm test
npm --prefix frontend run lint
backend/.venv/bin/python -m unittest discover -s deploy -p 'test_*.py'
```

Backend tests need a migrated, disposable PostgreSQL database ending in `_test`. They truncate fixture tables; never use the public Neon database.

```sh
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/rental_test'
DATABASE_URL="$TEST_DATABASE_URL" DATABASE_DIRECT_URL="$TEST_DATABASE_URL" backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m pytest backend/tests -q
```

For the managed local backend/frontend/browser checks, install the dependencies above and Google Chrome, configure Docker `.env`, then run:

```sh
backend/.venv/bin/python -m app.verify
```

It uses separate disposable databases and disables live model calls. `--skip-build` reuses current Docker images. Stop its extra services with:

```sh
docker compose -f docker-compose.yml -f docker-compose.verify.yml stop verify-frontend verify-backend
```

For public-demo browser checks against a running frontend:

```sh
E2E_PUBLIC_DEMO=1 E2E_BASE_URL=http://localhost:5173 npm --prefix frontend run test:e2e
```

This suite uses disposable visitor/chat state and does not create rental fixtures. See the [frontend guide](../frontend/README.md) for individual browser-test settings.

## API and administration

In normal local mode, [localhost:8000/docs](http://localhost:8000/docs) is the API reference. Routes use `/api/v1`; login accepts JSON and authenticated requests use bearer tokens. Public-demo mode hides API docs and blocks registration and rental writes.

- Liveness: `/api/v1/health/live`
- Database readiness: `/api/v1/health/ready`
- Create a local administrator: `backend/.venv/bin/python -m app.admin --email synthetic.admin@example.com --full-name "Synthetic Admin"` (prompts privately for a password).

The [assistant guide](assistant.md) covers simulated and optional local live chat. [Vercel/Neon](vercel-neon.md) and [Docker deployment](deployment.md) cover hosting and recovery.
