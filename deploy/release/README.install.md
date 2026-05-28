# trueRiver Install

This archive contains the trueRiver server source and a prebuilt web app.
Normal installs do not need Node or npm.

## Quick Local Test

```bash
./scripts/pre-compose-up.sh
./scripts/deploy-local.sh
```

Open:

```text
http://localhost:3080
```

Put media files in:

```text
deploy/volumes/trive-In
```

## Persistent Install

Keep secrets, database paths and media paths outside this source folder:

```bash
./scripts/init-local-config.sh
$EDITOR ../triver-local/.env
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

Before exposing trueRiver on a real host, edit `../triver-local/.env` and check:

- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `VITE_TRIVER_PUBLIC_URL`
- `VITE_TRIVER_HTTP_ENDPOINT`
- `TRIVER_POSTGRES_HOST_PATH`
- `TRIVER_VALKEY_HOST_PATH`
- `TRIVER_CLAMAV_HOST_PATH`
- `TRIVER_STORAGE_HOST_PATH`

`TRIVER_STORAGE_HOST_PATH` must contain the four folders `trive-In`,
`trive-Up`, `trive-Out` and `trive-dump`. Keep them under one mounted storage
root so Trive-Up can promote files with fast renames instead of physical
cross-device copies.

Browser uploads into `trive-In` are scanned through the bundled ClamAV
service before files are moved into place. The first start can take a while
while ClamAV downloads and loads its signature database; keep at least a few
GB of RAM free for that service.

To index an existing external folder without copying it into `trive-In`, mount
it as a Classic Import source:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/configure-classic-import-sources.sh /path/to/media
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

Then open `Trive-IO`, switch to `Classic Import`, select the folder and start
Classic Indexing.

Remote metadata lookup is manual by default. To use TMDb, OMDb or TheTVDB,
set the provider keys in `../triver-local/.env`, redeploy, then keep
`Remote Metadata` in `Manual` mode unless you intentionally configure
automation. Opening Settings or switching modes does not contact providers.
MusicBrainz works without an API key; setting `TRIVER_MUSICBRAINZ_CONTACT` is
recommended.

Read `PRIVACY.md`, `DISCLAIMER.md` and `NOTICE.md` before exposing the server or
enabling third-party metadata providers.

## Update

Unpack the new release archive, keep the same external local config directory,
then run:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

## Rebuild The Web App

The web app is already built in this archive. Developers who change
`frontend/source/` can rebuild it with:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/build-frontend.sh
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

This optional build path downloads the Node builder image and npm dependencies.

## Windows

Windows users should prefer `trueriver-windows-<version>.zip`. It contains the
same prebuilt web app plus PowerShell helpers for Docker Desktop:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\deploy\windows\Install-Triver.ps1
```

The project README is included as `README.project.md`.
