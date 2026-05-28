# trueRiver public techdemo roadmap

Status: paused as a public release target, active as an infrastructure track.

## Product shape

trueRiver should ship as a self-hosted media server with three first-class surfaces:

- webapp for cataloging, playback, metadata and administration
- Android TV app for living-room playback
- private sharing path for trusted friends and family

The techdemo should not expose a raw development stack. The intended public shape is a single Docker Compose project with a dedicated reverse proxy, persistent volumes, documented environment variables, and optional VPN.

## Packaging target

Core services:

- `triver-proxy`: dedicated nginx reverse proxy and static webapp host
- `triver-backend`: Django API, media streaming and admin API
- `triver-worker`: background ingest, metadata and media tasks
- `triver-beat`: scheduled jobs
- `triver-db`: Postgres
- `triver-valkey`: Valkey, using the Redis protocol for Celery transport

Optional services:

- `triver-vpn`: WireGuard gateway for private access
- `triver-vpn-firewall`: namespace firewall that only allows VPN clients to reach the trueRiver proxy
- future `triver-control`: tiny internal control plane for safe deployment operations

## Public access model

Default public techdemo stance:

- LAN/local access first
- VPN-first sharing for friends and family
- direct public HTTP(S) only after auth, TLS, rate limits and streaming behavior have been reviewed

VPN clients should reach trueRiver, not the full host LAN. The VPN container is therefore wired to a small edge network where the only application target is `triver-proxy`.

## Settings roadmap

The webapp Settings section should grow into an admin-only deployment area:

- read current proxy public URL and exposed port
- show VPN status and WireGuard endpoint
- create, disable and revoke VPN peers
- display peer QR/config download
- show firewall mode and allowed target
- eventually apply safe config changes through `triver-control`

The frontend must not receive raw Docker socket access. Backend/admin APIs should call a narrow internal service with a fixed allowlist of operations.

## Visualizer roadmap

Webapp:

- fullscreen MilkDrop-style visualizer while audio is playing
- Butterchurn/WebGL engine with preset rotation
- now-playing overlay with track, progress, next track and transport controls
- fallback canvas visualizer when WebGL/Butterchurn is unavailable

Android TV:

- default audio surface opens to a moving visualizer to reduce burn-in risk
- overlay behaves like video playback overlay
- first native version uses a lightweight animated renderer
- later version can use PCM/FFT data from ExoPlayer and eventually projectM/libprojectM if worth the native complexity

## Release checklist

- one documented `docker compose up -d` path
- `.env.example` with safe defaults
- admin bootstrap flow
- persistent media, db, Valkey and WireGuard volumes
- nginx healthcheck
- backup/export note for database and metadata
- Android TV APK build/upload documentation
- basic streaming tests over LAN and VPN
- security pass on auth, upload, media stream endpoints and admin settings
