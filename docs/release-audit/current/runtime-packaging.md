# Runtime Packaging Check

Date: 2026-05-20

Checks performed:

- Ran `./scripts/pre-compose-up.sh`.
- Confirmed host-mounted media/runtime folders exist and contain only `.gitkeep`.
- Ran `docker compose config` successfully.
- Moved the Node frontend builder out of the runtime Compose file and into
  `deploy/compose/frontend-build.yml`.
- Ran `./scripts/build-frontend.sh` successfully.
- Confirmed Git checkouts and release archives should include
  `frontend/package/build/` so runtime installs do not need Node/npm.
- Confirmed optional VPN services are behind the `vpn` profile.
- Ran a full runtime `docker compose up --build -d` on `TRIVER_PROXY_HTTP_PORT=3099`.
- Confirmed nginx served the web frontend with `HTTP/1.1 200 OK`.
- Ran `docker compose down -v --remove-orphans` after the test to remove candidate containers, networks and volumes.

Notes:

- The first full compose attempt failed because the original VPN edge subnet
  `10.43.0.0/24` overlapped with an existing local Docker network. The default
  was changed to `10.44.0.0/24`, while remaining configurable through
  `TRIVER_VPN_EDGE_SUBNET`.
- `.env` generated during the check was removed after validation; it is ignored
  by Git and must not be committed.
