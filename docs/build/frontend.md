# Frontend Build

The web frontend source is in `frontend/source`.

## Production Build

From the repository root, the Docker-based build helper is:

```bash
./scripts/build-frontend.sh
```

It uses `deploy/compose/frontend-build.yml`, downloads the `node:20-alpine`
builder image when needed and writes the generated web app to
`frontend/package/build/`.

The Docker build helper intentionally does not pass the local deployment
`.env` into Vite. The committed frontend bundle must stay relocatable: API and
media URLs are resolved from the browser origin at runtime, while the Settings
view falls back to the current origin when public endpoint build variables are
not present.

To build directly on a development machine with Node installed:

```bash
cd frontend/source
npm ci
npm run build:new
```

The generated output is committed under `frontend/package/build/` so Git
checkouts and source archives can be installed without Node or npm. Rebuild it
only when frontend source, `VITE_TRIVER_VERSION`, `VITE_TRIVER_SOURCE_URL` or
`VITE_TRIVER_SOURCE_REF` changes.

## Third-Party Notice Bundle

After installing dependencies for the release build, regenerate the npm notice
bundle:

```bash
./scripts/collect-frontend-notices.sh
```

The script writes copied package-level license and notice files to
`THIRD_PARTY_NOTICES/frontend-npm/`. Include that directory, the common license
texts in `THIRD_PARTY_NOTICES/`, `NOTICE.md`, the lockfile and this build note
with the web frontend release attachment.

## Rebuilding With A Modified `soundtouchjs`

The frontend currently uses `soundtouchjs@0.3.0`, whose license signal in
`package-lock.json` is `LGPL-2.1`.

To rebuild trueRiver with a modified compatible copy of `soundtouchjs`:

1. Replace the `soundtouchjs` dependency in `frontend/source/package.json` or
   install a compatible local/package-registry replacement.
2. Regenerate or update `frontend/source/package-lock.json`.
3. Run `npm ci` or the equivalent locked install for that dependency state.
4. Run `npm run build:new`.

If trueRiver distributes a built frontend bundle, the release must also provide
the corresponding source, lockfile, build instructions, and LGPL-2.1 license
text so recipients can rebuild the bundle with a modified compatible library.
