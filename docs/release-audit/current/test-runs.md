# Test Runs

## Backend Unit Tests

Date: 2026-05-21

Command:

```bash
docker run --rm -i \
  -v /home/dockers/triver-publish-candidate/backend:/backend \
  -w /backend \
  -e DJANGO_SETTINGS_MODULE=triver.settings \
  -e DJANGO_SECRET_KEY=test-release-audit-secret \
  triver-triver-backend \
  python - <<'PY'
import django
import unittest

django.setup()
suite = unittest.TestSuite()
for module_name in ['apps.library.tests', 'apps.api.tests']:
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(module_name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
PY
```

Result:

```text
Ran 11 tests in 0.009s

OK
```

Covered:

- TV-series filename metadata inference;
- logical artist splitting with escaped ampersand;
- binary HTTP Range responses;
- external subtitle filename token parsing;
- video poster timecode parsing and label formatting.

## Frontend Docker Build

Date: 2026-05-20

Command:

```bash
VITE_TRIVER_VERSION="$(cat VERSION)" ./scripts/build-frontend.sh
```

Result:

```text
108 modules transformed.
build/index.html
build/assets/index-Bxpijf4P.css
build/assets/index-B4LZdWlA.js
built in 571ms
```

Notes:

- The build output was generated under `frontend/package/build/`, which is tracked so installs do not need Node/npm.
- `npm audit --audit-level=moderate` now reports zero vulnerabilities after the Vite 8 upgrade; see `docs/release-audit/current/frontend-npm-audit.md`.

## Release Artifact Dry Run

Date: 2026-05-21

Command:

```bash
./scripts/build-release-artifacts.sh
```

Result:

```text
release artifacts written to /home/dockers/triver-publish-candidate/release/artifacts/v0.1.0-techdemo.5
```

Generated files:

- `trueriver-install-v0.1.0-techdemo.5.tar.gz`
- `trueriver-source-v0.1.0-techdemo.5.tar.gz`
- `trueriver-web-v0.1.0-techdemo.5.zip`
- `trueriver-third-party-notices-v0.1.0-techdemo.5.zip`
- `release-notes-v0.1.0-techdemo.5.md`
- `checksums.txt`
- `APK_NOT_INCLUDED.txt`

Notes:

- The install archive and source archive both contain the prebuilt web frontend
  for runtime installs.
- The script reads `VERSION` when no explicit version is passed.
- The committed web build includes `VITE_TRIVER_VERSION`.
- The script correctly generated SHA-256 checksums and source provenance in the release notes.
- Public release runs should use a clean worktree and pass `TRIVER_APK_PATH` for the signed Android TV APK.

## Android TV Container Release Build

Date: 2026-05-20

Command:

```bash
TRIVER_ANDROID_UNSIGNED_RELEASE=1 ./scripts/build-android-tv-apk.sh release
```

Result:

```text
BUILD SUCCESSFUL in 2m 21s
wrote /home/dockers/triver-publish-candidate/apk/package/trueriver-tv-0.4.3-unsigned.apk
```

Notes:

- This verifies the pinned Android SDK container build path and Gradle release task.
- The generated APK was unsigned and is not a public release artifact.
- Public APK releases must run the same helper with `TRIVER_ANDROID_KEYSTORE`, `TRIVER_ANDROID_KEYSTORE_PASSWORD`, `TRIVER_ANDROID_KEY_ALIAS` and `TRIVER_ANDROID_KEY_PASSWORD` set.

## Android TV Signed Release Build

Date: 2026-05-20

Commands:

```bash
set -a
. apk/source/.signing/release.env
set +a
./scripts/build-android-tv-apk.sh release
docker run --rm -v "$PWD:/repo" -w /repo \
  ghcr.io/cirruslabs/android-sdk@sha256:1c2e7e9c4490dbc1f85364556aa08e550945e6dffb29baab86d5fe2c7be0773a \
  /opt/android-sdk-linux/build-tools/34.0.0/apksigner verify --verbose apk/package/trueriver-tv-0.4.3.apk
```

Result:

```text
BUILD SUCCESSFUL in 2m 41s
wrote /home/dockers/triver-publish-candidate/apk/package/trueriver-tv-0.4.3.apk
Verifies
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): true
Number of signers: 1
```

Notes:

- The local release keystore and signing env live under ignored `apk/source/.signing/`.
- Back up `apk/source/.signing/trueriver-release.jks` and `apk/source/.signing/release.env` privately before publishing APKs signed with this key.

## Full Compose Smoke Test

Date: 2026-05-20

Command:

```bash
./scripts/pre-compose-up.sh
TRIVER_PROXY_HTTP_PORT=3099 docker compose up --build -d
curl -fsSI http://127.0.0.1:3099/
TRIVER_PROXY_HTTP_PORT=3099 docker compose down -v --remove-orphans
rm -f .env
```

Result:

```text
triver-backend   Up
triver-beat      Up
triver-db        Up
triver-proxy     Up 127.0.0.1:3099->80/tcp
triver-valkey    Up
triver-worker    Up

HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: text/html
```

Notes:

- The first attempt exposed a local Docker subnet conflict on `10.43.0.0/24`.
- The default VPN edge subnet was changed to `10.44.0.0/24` and the retry passed.
