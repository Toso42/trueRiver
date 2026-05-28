# Changelog

## v0.1.0-techdemo.4

Catalog refresh fix release.

- The web app now resolves the active library again when switching sections or
  using refresh, so Tracks, Albums, Artists and Home pick up a library created
  after the app was already open.
- Library resolution now falls back to the latest Trive-Up job as well as the
  latest scan job.
- Global refresh now clears filters and also reloads the catalog binding.

## v0.1.0-techdemo.3

Server update and first-run fix release.

- The default `localhost:3080` browser origin is now trusted by Django CSRF
  checks, so authenticated actions such as starting a scan work after a fresh
  local install.
- The nginx proxy now forwards the original host including port to the backend.
- `scripts/pre-compose-up.sh` updates existing `.env` files with the local CSRF
  origins needed by the configured proxy port.
- `scripts/update-server.sh` adds a one-command server updater for Git installs
  and can convert source-archive installs when `TRIVER_GIT_REMOTE` is supplied.

## v0.1.0-techdemo.1

First public trueRiver tech demo.

This release packages the project as a self-hosted media library that can run
from source with Docker Compose and connect to an Android TV device through a
signed APK.

Highlights:

- Docker Compose stack with backend, frontend build step, nginx proxy,
  PostgreSQL, Valkey and optional VPN profile.
- React web app served by the local nginx proxy.
- Signed Android TV APK with first-run server configuration.
- Media library backend with scanning, playback endpoints, artwork and metadata
  groundwork.
- Release artifacts for source, web build, Android TV APK, checksums and
  third-party notices.
- AGPL-3.0-or-later licensing baseline, DCO contribution policy and release
  audit notes.

Known scope:

- This is a tech demo, not a polished consumer release.
- Your media library, local runtime data and signing keys stay on your machine.
- The Android TV app and media metadata flows are still under active iteration.
