# trueRiver

Your media library, under your roof.

trueRiver is a self-hosted media library for music, videos, albums, artists,
movies and series. Drop your files into a local folder, let trueRiver scan them,
then browse and play your collection from the web or from Android TV.

The goal is simple: keep the comfort of a modern streaming interface without
handing your library, habits or metadata to a cloud platform.

The first public builds are tech demos. They already include the Docker server,
browser app and Android TV APK, while deeper polish around metadata, playback
and TV browsing is still moving fast.

## Public Tech Demo Safety Note

trueRiver can scan, index, upload, move and delete files in folders you connect
to the stack. Try it first with copies of your media or with a backed-up test
library. Keep backups of your media, database and local configuration before
using TriveImport, Classic Import, dedup/version handling or file deletion.

Known rough edges in the current tech demo:

- Docker is required for normal server installs.
- Android TV support is usable but still experimental.
- Video cache preparation, remote metadata and dedup/version workflows are
  still evolving.
- Public hosting requires careful reverse-proxy, HTTPS and authentication
  configuration.

## Download Or Build

For the easiest test, download the files attached to a tagged release:

- `trueriver-install-<version>.tar.gz` if you want to run the server with the
  web app already built;
- `trueriver-windows-<version>.zip` if you want the same server stack packaged
  for Docker Desktop on Windows;
- `trueriver-source-<version>.tar.gz` if you want the complete source tree with
  the web app already built;
- `trueriver-tv-<version>.apk` if you want to sideload the Android TV app;
- `checksums.txt` to verify downloaded files.

Git checkouts and source archives include the built web frontend under
`frontend/package/build/`, so a normal server install does not need Node or npm.
The install archive adds a shorter root README for the quickest server setup.

## Release Versioning

Version tags and release artifacts are maintained by the project maintainer.
Contributors do not need to bump `VERSION` in pull requests.

## Repository Layout

- `backend/`: Django API, catalog, scanner and playback services.
- `frontend/source/`: React source used to build the webapp.
- `apk/source/`: Android TV shell source.
- `deploy/`: Docker Compose, nginx config, container Dockerfiles and local runtime folders.
- `docs/`: roadmap, distribution review and publish-readiness notes.

## Local Run

From a release install archive, prepare local configuration and media folders:

```bash
./scripts/pre-compose-up.sh
```

Then start the stack:

```bash
./scripts/deploy-local.sh
```

Docker Compose serves the included web client through nginx.

Open the webapp at:

```text
http://localhost:3080
```

Add media files to:

```text
deploy/volumes/trive-In
```

As scans run, trueRiver uses these folders:

- `trive-In`: put new media here for scanning/import.
- `trive-Up`: upload/import staging area.
- `trive-Out`: generated or exported media output.
- `trive-dump`: scan dumps, cache-like data and generated metadata.

To index an existing external folder without copying files into the TriveImport
pipeline, configure Classic Import sources:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/configure-classic-import-sources.sh /path/to/media
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

Then open `Trive-IO`, switch to `Classic Import`, select the mounted folder and
start indexing. See `docs/deploy/classic-import.md`.

`Trive-IO` also includes an `AutoImport` section. It is off by default and can
watch `trive-In`, Classic Import sources, or both, then start scan/catalog jobs
when new files become stable.

For a long-running install, keep secrets, host-specific paths and reverse-proxy
overrides outside the Git checkout:

```bash
./scripts/init-local-config.sh
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

Before deploying a public host, edit `../triver-local/.env` and set
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
`VITE_TRIVER_PUBLIC_URL` and any host-side storage paths. See:

```text
docs/deploy/local-config.md
```

## Updating

If you installed trueRiver from a Git checkout, update the server with:

```bash
./scripts/deploy-local.sh
```

To move to a specific release tag:

```bash
./scripts/deploy-local.sh v0.1.0-techdemo.3
```

If you started from an install archive, or any archive without `.git`, set the
repository URL once:

```bash
TRIVER_GIT_REMOTE=<repo-url> ./scripts/update-server.sh v0.1.0-techdemo.3
```

The deploy/update wrappers keep ignored local configuration and media folders in
place, fetch the selected source version when Git is available, use the bundled
web client unless `TRIVER_REBUILD_FRONTEND=1` is set, and restart the Docker
stack.

## Git Checkout

A Git checkout is installable because it already contains the built web
frontend. Use this path when you want to follow source updates instead of
downloading release archives:

```bash
git clone https://github.com/Toso42/trueRiver.git trueriver
cd trueriver
./scripts/init-local-config.sh
$EDITOR ../triver-local/.env
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

This keeps local configuration, secrets and media paths outside the checkout.
Node and npm are not needed for normal runtime installs.

## Windows

Windows installs use Docker Desktop with the WSL 2 backend. The release zip
includes PowerShell helpers that create persistent config and data folders under
`%USERPROFILE%\trueRiver`, then start the same Docker stack used on Linux:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\deploy\windows\Install-Triver.ps1
```

The web app opens at `http://localhost:3080`. Put new media files in
`%USERPROFILE%\trueRiver\data\trive-In`.

## Privacy And Notices

Remote metadata lookup is optional and manual by default. Opening Settings or
changing the lookup mode does not contact providers; configured providers can
receive metadata search terms only after a manual content action, or after an
explicitly configured automation. See `PRIVACY.md`.

For the project license, no-warranty notice and third-party attribution, see
`LICENSE`, `DISCLAIMER.md`, `NOTICE.md` and `THIRD_PARTY_NOTICES/`.

## Support

trueRiver is donation-supported open source. Donations are optional and do not
unlock features, support priority or private builds. If the project is useful to
you, you can support development here:

```text
https://buymeacoffee.com/tosomalemodo
```

## Android TV

Download the Android TV APK from the release attachments for the version you
want to install.

On first launch, configure the TV app with the host and port of the machine
running the Docker stack. For a default local LAN setup, use the server machine
IP and port `3080`, unless you expose nginx on port `80`.

## License

trueRiver is licensed under `AGPL-3.0-or-later`.

The project license is in `LICENSE`. Third-party notices and license texts are
in `NOTICE.md` and `THIRD_PARTY_NOTICES/`.
