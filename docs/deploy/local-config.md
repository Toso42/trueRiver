# Local Configuration

The source checkout should stay replaceable. Keep machine-specific settings in
ignored files or in a sibling directory, then combine them with the public
Compose file at deploy time.

## Default Single-Checkout Setup

For a simple local test:

```bash
./scripts/pre-compose-up.sh
./scripts/deploy-local.sh
```

This creates an ignored `.env`, creates empty `deploy/volumes/trive-*`
directories and starts the stack with the committed web frontend. The explicit
frontend build step is only needed when `frontend/package/build/` is missing or
when you changed frontend source or `VITE_TRIVER_*` build settings.

The browser-facing settings shown by the frontend are built from `VITE_TRIVER_*`
values in `.env`. If those values are empty, the app falls back to the current
browser origin where possible.

## External Local Config

For a long-running install, keep private files outside the repository:

```bash
./scripts/init-local-config.sh
```

Edit `../triver-local/.env` for secrets, host names, trusted CSRF origins and
host-side storage paths. The init script creates the default host-side
directories listed in the env file, but you can change those paths before the
first deploy.

At minimum, check these values for a real install:

- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `VITE_TRIVER_PUBLIC_URL`
- `VITE_TRIVER_HTTP_ENDPOINT`
- `VITE_TRIVER_VPN_ENDPOINT`, if the VPN profile is enabled
- `TRIVER_POSTGRES_HOST_PATH`
- `TRIVER_VALKEY_HOST_PATH`
- `TRIVER_INGEST_HOST_PATH`, `TRIVER_DIGEST_HOST_PATH`,
  `TRIVER_NORMALIZE_HOST_PATH` and `TRIVER_DUMP_HOST_PATH`

The Valkey/Celery URLs use the `redis://` scheme because Valkey speaks the
Redis protocol and the Python clients expect that URL scheme.

For long-running installs, keep `COMPOSE_PROJECT_NAME` stable. That prevents
Compose from creating a second stack if the checkout directory is renamed.

If you do not need to attach trueRiver to an existing reverse-proxy Docker
network, `docker-compose.local.yml` is enough.

If another nginx/Traefik/Caddy container should proxy to trueRiver's internal
nginx proxy, also copy the edge-network example:

```bash
cp deploy/examples/docker-compose.edge.yml ../triver-local/
```

Then deploy with both overrides:

```bash
TRIVER_LOCAL_DIR=../triver-local \
TRIVER_COMPOSE_OVERRIDE="../triver-local/docker-compose.local.yml:../triver-local/docker-compose.edge.yml" \
./scripts/deploy-local.sh
```

Deploy with:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

Run Compose commands through the wrapper so the same env and override files are
used consistently:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/compose-local.sh ps
TRIVER_LOCAL_DIR=../triver-local ./scripts/compose-local.sh logs -f triver-backend
```

## Updating

After a pull or when moving to a tag:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh v0.1.0-techdemo.5
```

The deploy wrapper recreates the nginx proxy before starting the stack. If you
update from a Git checkout and need a fresh web bundle, run:

```bash
TRIVER_LOCAL_DIR=../triver-local TRIVER_REBUILD_FRONTEND=1 ./scripts/deploy-local.sh
```

That optional path uses the Node builder image. Normal runtime deploys from Git
checkouts or release archives only start the server services and nginx proxy.
