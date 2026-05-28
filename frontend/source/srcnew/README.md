# srcnew

`srcnew/` is the active web frontend for `trueRiver`.

The browser app has a single top-level product surface: the audio library shell.
There is no standalone web Video mode and no standalone web TV mode. Unknown
paths are redirected back to `/audio`.

## Current Top-Level Routes

Implemented routes:

- `/`
  - enters the audio library after auth, replacing the URL with `/audio`;
- `/audio/*`
  - main browser library shell;
- `/_triver/*`
  - internal visual/debug routes.

Route entry points live in:

- `app/AppRoot.jsx`
- `pages/AudioPage.jsx`

## Main Frontend Surface

The audio shell includes:

- persistent sidebar;
- audio player dock;
- app content region;
- optional video player dock when the active library item is a video;
- global content navigation and search-driven filtering in the content area.

Important files:

- `layouts/AudioLayout.jsx`
- `features/audio/sidebar/*`
- `features/audio/player/*`
- `features/audio/content/*`
- `features/video/VideoSurface.jsx`

## Build

Canonical build workflow:

```bash
cd frontend/source
npm ci
npm run build:new
```

The Docker helper from the repository root is:

```bash
VITE_TRIVER_VERSION="$(cat VERSION)" ./scripts/build-frontend.sh
```

The generated web app is copied to `frontend/package/build/` and committed so
normal installs do not need Node or npm.

`index.html` is the canonical entry point for `srcnew/main.jsx`. The previous
legacy frontend under `src/` was removed from the publish candidate so release
builds cannot accidentally target the obsolete monolith.
