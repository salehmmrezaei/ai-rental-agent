# Casa public portfolio deployment

This guide covers the optional VPS/Docker architecture. For the zero-additional-cost
Vercel Hobby + Neon Free path, use [the serverless guide](vercel-neon.md).

The repository is prepared for `https://casa.salehmmrezaei.com`. These instructions do not imply that the site is deployed. Review the exact configuration and provide hosting/DNS access through your own accounts before running the live steps.

## Architecture and operating policy

One VPS runs Docker Compose: Caddy serves the optimized React bundle and proxies `/api/v1` to one FastAPI worker; PostgreSQL 18 stores the synthetic portfolio. Only TCP 80/443 are published. PostgreSQL and the API have no host port and use an internal Docker network without an internet route. Caddy also joins an outbound network for certificate issuance. The backend runs as the existing nonroot `rental` user, with a read-only container filesystem and a separate upload volume.

`docker-compose.prod.yml` is independent of the local `docker-compose.yml`. It always sets `PUBLIC_DEMO_MODE=true`, empties `OPENAI_API_KEY`, disables the live assistant and hides API docs. The real OpenAI integration remains available in normal local environments. No external model requests are made by the simulated assistant; no API key is required by visitors.

Visitors choose tenant, landlord or agency from the demo role guide. Each gets a restricted, expiring visitor token; seed account passwords are never sent to visitors. Shared rental records are read-only, including direct API calls. Registration, password/profile/account administration, messages, uploads, saves, applications, contracts, visits and action confirmations are blocked from mutation. The useful interactive exception is simulated chat: bounded, role-scoped database reads with temporary conversation state held only in process memory.

The dataset must be a complete, dedicated synthetic seed with its bundled images. Demo access and reads fail closed if unrelated users, business records or image metadata are present. Never point this stack at a real business database or reuse an existing development database. The application cannot determine whether an operator manually replaced fictional text with real personal information: keep this dedicated database synthetic throughout its lifecycle.

Sessions last 30 minutes by default, chat is bounded, and one visitor's logout revokes only that visitor. Chat has independent limits: 512 visitor histories, three threads per history, 768 total threads, 12 turns per thread and a 30-minute absolute lifetime; oldest histories/threads may be evicted sooner at capacity. Restarting the backend clears sessions/chat and signs visitors out. It preserves PostgreSQL and image volumes. Run exactly **one backend process and one replica**; multiple workers require a shared session store and a separate review.

## Requirements and credentials to prepare

- A Linux VPS with Docker Engine and the Compose plugin; SSH access and permission to run Docker. Keep SSH restricted to your administration addresses where practical.
- DNS edit access for `salehmmrezaei.com`, the VPS public IPv4 address and, only if configured correctly, its IPv6 address.
- A real email address for certificate expiry/account notices.
- Four independently generated secrets: PostgreSQL bootstrap password, application DB password, JWT signing secret and private seed password. No OpenAI credential is needed.
- A private backup location outside the VPS and a maintenance schedule.

Start with 2 vCPU, 2–4 GiB RAM and 20–40 GiB SSD, adjusting after measuring load. Building the frontend may temporarily need more RAM than serving it. The configured runtime caps total about 1.6 GiB plus the OS/Docker; first seed runs instead of the API and hashes 301 account passwords, so allow several minutes on a small CPU. Disk must cover images, DB growth, Docker layers and backups. Ongoing costs are the VPS, its storage/snapshots, outbound bandwidth, off-server backups and your existing domain renewal. TLS and the simulated assistant require no paid API. Provider prices and traffic charges must be checked with the provider you choose.

## Prepare configuration

On the server, clone the reviewed branch/commit into a private working directory. From its repository root:

```sh
cp -n .env.production.example .env.production
chmod 600 .env.production
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Run the secret-generation command four times and edit `.env.production` privately. Use one output per secret; do not reuse them. Use plain unquoted `KEY=value` lines. Hex DB passwords avoid URL escaping in `DATABASE_URL`. Set `ACME_EMAIL`, keep `CASA_DOMAIN=casa.salehmmrezaei.com`, and optionally set `CASA_VERSION` to the reviewed short commit SHA for local image tags.

`POSTGRES_USER` is a bootstrap superuser used only inside the database/backup operation. The first-start script creates a separate `APP_DB_USER` with no superuser, role creation, database creation or replication powers; the API/migrations use only this role. The dedicated DB and public schema belong to it. `btree_gist` is installed during bootstrap for migration constraints.

The `POSTGRES_*` and `APP_DB_*` bootstrap environment applies **only to an empty PostgreSQL volume**. Changing a password in the file does not rotate an existing database role; rotate through an explicit PostgreSQL administration procedure and update matching service configuration together. Reusing older development volumes skips the production init script and is unsupported.

```sh
python3 deploy/check_env.py
deploy/compose.sh config --quiet
deploy/compose.sh build
deploy/compose.sh run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Preflight validates identifiers, private permissions, independent nonplaceholder secrets, domain/email and demo settings without printing values. Avoid running `docker compose config` without `--quiet`, publishing `docker inspect` output or pasting env files: expanded configuration contains credentials. Keep `.env.production` backed up separately in a password manager/encrypted store; it is excluded from Git and Docker build contexts.

Frontend build configuration is `VITE_API_BASE_URL=/api/v1`; no runtime host URL or frontend secret is needed. Backend CORS is restricted to `https://casa.salehmmrezaei.com`. Requests remain same-origin, so no permissive wildcard or credentialed cross-origin access is required. No development `.env` is imported into production.

## DNS and HTTPS

Review and apply this record through your DNS provider when ready:

| Type | Name | Value |
| --- | --- | --- |
| A | `casa` | The VPS public IPv4 address |
| AAAA (optional) | `casa` | Its working, publicly routed IPv6 address |

Remove a stale AAAA record if the server has no working IPv6. Start with ordinary DNS resolution, without a provider HTTP proxy, unless that proxy's TLS/client-IP behavior has been reviewed. Allow inbound TCP 80 and 443 in the provider firewall and the host's Docker-aware firewall. Do not publish 5432, 8000, Caddy's admin port or the internal health listener. Docker-published ports can bypass uncomplicated host firewall rules; verify from a different machine.

Caddy obtains and renews certificates automatically when DNS resolves to the server and ports 80/443 are reachable. HTTP redirects to HTTPS automatically. Persistent `caddy_data` stores certificates/private keys; preserve it across upgrades. HSTS applies only to this hostname. The setup needs no DNS-provider API token or wildcard certificate. Caddy preserves the `/api/v1` prefix, serves built assets directly and falls back to `index.html` for React deep links. `/api/*` errors remain API errors, never the SPA shell.

The proxy limits bodies to 64 KB, configures timeouts and security headers/CSP, and replaces forwarded client-IP headers. `--forwarded-allow-ips=*` is acceptable here because the API is reachable only on its private network and Caddy is the sole HTTP ingress; do not publish its port or attach untrusted containers. Caddy is not configured to trust an upstream CDN. CSP permits inline styles for React/animation, same-origin scripts, and same-origin/data/blob images needed by photos and Blu. User messages render as text. Request access logs are disabled; runtime/error logs remain available with rotation.

## First deployment and upgrades

The following is the live deployment action. Run it only after the configuration/hosting/DNS review:

```sh
deploy/compose.sh up --build -d --wait --wait-timeout 600
deploy/compose.sh ps -a
```

Startup waits for PostgreSQL health, runs Alembic, seeds the synthetic dataset and bundled image metadata, starts the API after seed success, then starts Caddy after API readiness. A migration/seed failure stops this chain. On a small VPS, inspect the seed logs before deciding that the timeout needs increasing.

`seed` preserves all existing sample records, original password hashes and the initial date anchor when rerun. Partial seeds fail with no destructive repair. Bundled image pixels are installed inside the backend image and authorized through `/api/v1/images/...`; visitor uploads are blocked. The persistent upload volume preserves any operator-maintained files, although only the bundled image metadata is accepted for the public demo.

For an upgrade, back up first, review migrations and dependency/image changes, check out the reviewed commit, run preflight/build, then:

```sh
deploy/compose.sh stop web backend
deploy/compose.sh run --rm migrate
deploy/compose.sh run --rm --no-deps seed
deploy/compose.sh up -d --wait --wait-timeout 600
python3 deploy/smoke.py https://casa.salehmmrezaei.com
```

This intentionally uses a short maintenance window, so an older API cannot write/read against a changing schema. Migration/seed failures leave the application stopped for investigation. Do not automatically downgrade data. Roll back to a compatible application image or restore the backup into a fresh stack. Major PostgreSQL upgrades need a documented dump/restore or `pg_upgrade` plan; do not change its major tag over the existing volume. Image major tags receive patches when deliberately pulled/rebuilt; record tested image digests for a release and review updates regularly.

Ordinary restart and shutdown preserve data:

```sh
deploy/compose.sh restart backend web
deploy/compose.sh up -d --wait --wait-timeout 120
deploy/compose.sh down
```

Run `up -d --wait` again after shutdown. Never use `down -v` on a retained deployment; it deletes database, uploads and certificates. Docker restart policies recover persistent services after host reboot when the Docker service is enabled; migration/seed jobs run for releases through Compose. Health checks detect failure but do not themselves restart an unhealthy still-running process; alert and investigate, then restart deliberately if needed.

## Backups and restore

While no operator is editing the synthetic dataset, run:

```sh
deploy/backup.sh
```

This writes a private timestamped directory under ignored `backups/` containing a custom-format PostgreSQL dump, upload archive and Caddy certificate-data archive. `.partial` files indicate incomplete backups and must not be restored. Encrypt backups before copying them off-server: dumps include password hashes and Caddy data includes private keys. Keep the corresponding reviewed commit/image digests and encrypted `.env.production` separately. A daily backup with seven daily and four weekly copies is a reasonable starting policy; test a restore regularly and monitor available disk. Synthetic data is reproducible, but that does not replace backup verification.

Restore **into new volumes**, retaining the previous stack for rollback. The example uses the separate project `casa-restore`, which does not publish ports until `web` starts. Set the actual private backup directory:

```sh
casa_backup=backups/REPLACE_WITH_TIMESTAMP
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml up -d --wait db
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml exec -T db sh -c 'PGPASSWORD="$APP_DB_PASSWORD" pg_restore -h 127.0.0.1 -U "$APP_DB_USER" -d "$POSTGRES_DB" --no-owner --no-acl --no-comments --exit-on-error' < "$casa_backup/database.dump"
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps -T --entrypoint tar backend -C /app/uploads -xzf - < "$casa_backup/uploads.tar.gz"
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps -T --entrypoint tar web -C /data -xzf - --no-same-owner < "$casa_backup/caddy-data.tar.gz"
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps migrate
docker compose -p casa-restore --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps seed
```

Use the same configured DB role names; `--no-owner --no-acl` creates application objects as the non-superuser app role. Bootstrap already installs `btree_gist`; `--no-comments` avoids changing extension comments owned by bootstrap. Restore into a newly initialized database, with no app migrations run before `pg_restore`. Run migrations afterward using the compatible reviewed code. Once verified, stop the old `web`/`backend`, start the restore project with `up -d --wait`, and rerun acceptance tests. Ports must be free before starting its `web`. Use `-p casa-restore` for subsequent commands, or explicitly use `CASA_PROJECT_NAME=casa-restore deploy/compose.sh ...`; the default helper continues to address `casa`. `CASA_ENV_FILE` optionally selects a different private env path for an isolated stack.

## Demo reset and retention

For disposable visitor state, `deploy/compose.sh restart backend` clears sessions/chat immediately without touching rental records. Default sessions expire after 30 minutes. Capacity is bounded (`DEMO_MAX_SESSIONS=1000`); logged-out sessions are discarded, and expired visitor state is pruned. Do not enter personal information into chat. No user chat is persisted to PostgreSQL. Runtime errors and host logs still follow your administration retention policy.

Rental data is preserved across reruns/restarts and cannot be changed by public visitors. The seed's available-until date is two years after first creation; sample visits/current leases become historical sooner. Rerunning seed intentionally does **not** refresh dates. For a fresh date anchor or recovery from partial/mixed data, back up and create a **new dedicated database/Compose project with new volumes**, run migrations/seed there, verify it, then switch the service during maintenance. Preserve the old stack until accepted. No scheduled destructive reset or deletion of unrelated data is provided. Rotating the JWT secret revokes all visitor tokens after restart; seed reruns do not rotate account passwords.

## Monitoring and troubleshooting

```sh
deploy/compose.sh ps -a
deploy/compose.sh logs --tail 100 backend web
deploy/compose.sh logs --tail 100 migrate seed db
deploy/compose.sh exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker stats --no-stream
df -h
curl --fail --silent --show-error https://casa.salehmmrezaei.com/api/v1/health/ready
```

Monitor the public readiness URL, HTTPS expiry, disk/memory and backup freshness from an external system you control. Container logs are rotated at 10 MB × 3 per service. Avoid logging request bodies, JWTs, passwords or chat; do not enable production debug/access logs without a privacy review. Readiness verifies migration revision; update that check when adding migrations.

| Symptom | Check/action |
| --- | --- |
| No certificate / timeout | DNS A/AAAA, external 80/443, server clock, Caddy logs and persistent data permissions. |
| API 502/503 | API health, migration/seed exit status, app DB role/password and container resource pressure. |
| `demo_dataset_required` | Dedicated synthetic footprint and bundled image metadata; do not bypass the guard or attach real data. |
| First start role/auth failure | Init scripts only run on empty DB volumes; use new production volumes and matching secrets. |
| 401 after restart / expiry | Re-enter a demo role; temporary sessions are deliberately cleared. |
| 429 / demo capacity | Per-IP/global/request/session limits; wait for expiry, investigate load, adjust only within available resources. |
| Missing photos | Complete backend assets/package and successful image seed; confirm `/api/v1/images/...` is proxied. |
| Refresh 404 | Confirm production Caddy image/config and SPA fallback, not the Vite server. |
| Missing normal write behavior | Production is deliberately a read-only demo; use the separate local development configuration. |

## Live acceptance checklist

Only mark deployment complete after the real public URL passes these checks from outside the VPS:

```sh
dig +short casa.salehmmrezaei.com A
dig +short casa.salehmmrezaei.com AAAA
curl --head http://casa.salehmmrezaei.com
curl --head https://casa.salehmmrezaei.com
python3 deploy/smoke.py https://casa.salehmmrezaei.com
```

Confirm DNS targets the intended server, HTTP redirects to HTTPS, and the certificate validates without insecure flags. The smoke script checks optimized assets, CSP, same-origin API, page/detail refresh, real image bytes, all three roles, cross-role denial, direct write/registration/upload denial, simulated chat, visitor isolation and logout. It only attempts blocked business writes and temporary chat/session operations; it does not mutate shared sample records.

In a desktop and mobile browser, explore tenant applications/visits/contracts/messages/saved homes; landlord properties/listings/occupancy; agency moderation/users/applications/visits/messages. Confirm write controls explain read-only behavior; no passwords or API-key errors are displayed. Ask the simulated assistant to find Bologna rooms, explain an application and inspect each role's scoped data. Check listing cards and Blu's existing animations, and confirm no external model requests appear. Try an unsupported/privileged action and confirm the simulator explains its limits without changing data.

Refresh a public listing URL and each role's deep link. Use two separate browser contexts to confirm chat isolation. Restart backend/web, re-enter roles, verify sample listings/images remain unchanged and no old chat returns. Reboot the VPS and confirm service recovery. From another machine confirm 5432/8000/2019/8080 are unreachable. Exercise a backup and restore into isolated fresh volumes before relying on recovery. The GitHub workflow also runs normal/demo browser tests and a local plain-HTTP production-container smoke test; CI success does not verify public DNS, TLS, firewall or actual VPS recovery.

## Reference configuration sources

The deployment follows [Docker Compose dependency/health conditions](https://docs.docker.com/compose/how-tos/startup-order/), [the PostgreSQL 18 image storage layout](https://hub.docker.com/_/postgres), [Caddy SPA and proxy patterns](https://caddyserver.com/docs/caddyfile/patterns), [Caddy HTTPS requirements](https://caddyserver.com/docs/automatic-https), [Caddy request body limits](https://caddyserver.com/docs/caddyfile/directives/request_body) and [PostgreSQL logical backup guidance](https://www.postgresql.org/docs/18/backup-dump.html).
