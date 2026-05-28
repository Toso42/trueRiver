# trueRiver Project Status

## Purpose

This document is the current operational snapshot of `trueRiver` / `Triver`.
It exists to answer four questions quickly:

1. what the system is trying to do
2. what is already working
3. what is still being built
4. which directions are now considered dead ends or lower priority

This file should be the first document to read before touching either:
- the web frontend in `srcnew/`
- the Android TV app in `android-tv-shell/`

## Product Context

`trueRiver` is evolving into a library and playback system that treats audio and video as part of the same catalog pipeline, while exposing different user experiences for:
- desktop / browser-oriented library work
- device-specific Android TV runtime

The codebase now has two parallel UI tracks:

1. `srcnew/`
   - the new web frontend
   - useful for desktop/browser library use
   - includes the audio-first shell and browser video playback inside that shell
   - no longer ships standalone web Video mode or web TV mode

2. `android-tv-shell/`
   - the native Android TV app
   - now the preferred direction for real TV devices such as Mi Box

## High-Level Architecture

### Backend / Media Pipeline

Current backend/media assumptions:
- audio and video share the same library pipeline
- `media_kind` distinguishes `audio` vs `video`
- `/api/videos/` exists alongside the existing audio-oriented endpoints
- video metadata extraction is already part of the pipeline
- playback metadata now includes concepts such as:
  - `playback_strategy`
    - `direct`
    - `remux`
    - `audio_transcode`
    - `transcode`
  - `subtitle_strategy`
    - `none`
    - `soft`
    - `burn_required`

The browser/player layer has already pushed the backend toward:
- HLS support for video playback experimentation
- subtitle extraction endpoints for browser-compatible text subtitle flows
- playback status endpoints for cache/fallback tracking

### Web Frontend

The web frontend has one product surface:
- `/`
  - enters the audio library after auth and replaces the URL with `/audio`
- `/audio/*`

The most mature browser surface is still the `audio` shell, which now also hosts video playback in a browser-friendly way.

### Android TV App

The Android TV app started as a WebView wrapper and then moved to a native direction.
This change is now considered the correct architectural decision.

The native app talks to the backend directly and no longer depends on the old WebView runtime for its main flow.

## Current Surface Status

| Surface | Status | Notes |
| --- | --- | --- |
| Web audio library (`/audio`) | Working | Main browser library shell. Stable enough for daily library work. |
| Web video inside audio shell | Working | HLS/fallback browser playback is functional. |
| Android TV native shell | Working | Native home shell loads real library data on Mi Box. |
| Android TV native video playback | Working, needs polish | Native `Media3 / ExoPlayer` playback is already working on Mi Box. |
| Android TV native subtitle controls | In progress, working first pass | Native player now mounts subtitle tracks from backend subtitle URLs and can cycle subtitle selection. |
| Browser trive-In explorer | Working first pass | `FolderNavigation` was replaced with a real `trive-In` explorer and scoped Trive-In / Trive-Up actions. |

## What Is Already Implemented

### Library and Media Model

Implemented:
- unified library flow for audio and video
- backend `/api/videos/`
- frontend video-aware data layer
- video metadata surfaced to clients:
  - resolution
  - fps
  - video codec
  - audio codec
  - subtitle stream information
  - browser/playback strategy metadata
  - episodic video metadata:
    - `series_title`
    - `season_number`
    - `episode_number`
    - `episode_title`

### Web Frontend: Audio / Desktop Shell

Implemented:
- audio layout with persistent sidebar, player region, and content region
- views for tracks, albums, artists, metadata-oriented browsing, and library operations
- `Trive-IO` operational surface
- settings sidebar entries split into App Settings, Metadata Settings, Dedup Manager and Video Curation
- browser video playback integrated into the audio shell
- separate audio and video docks
- `Videos` view under the library model
- `Video Curation` workspace for server-authoritative web and Android TV video row order
- right-click `Assegna Tag` flow on track/video rows
- `trueRiver` shared brand component

### Web Frontend: Video Playback

Implemented:
- browser video playback using:
  - direct source when possible
  - HLS where available
  - fallback playback strategy metadata
- subtitle extraction and track mounting where supported
- HLS support in the frontend through `hls.js`
- richer browser video metadata display

Current limitation:
- browser playback is useful, but it is not the right foundation for constrained Android TV devices.

### Removed Web Modes

Removed from the active browser app:
- standalone web Video mode (`/video`)
- standalone web TV mode (`/tv/*`)
- landing mode selector for Audio / Video / TV

The browser app now goes directly through auth into the audio shell.

### Android TV Native App

Implemented:
- native launcher and home shell
- native mode switch:
  - `Video`
  - `Audio`
  - `Search` placeholder
- direct API reads for:
  - videos
  - artists
  - albums
  - tracks
- native card browsing
- native detail placeholder for non-video items
- native video player based on `Media3 / ExoPlayer`
- successful native playback test on Mi Box

Current issue already observed:
- the native player still leaves a visible overlay band on top of the video and needs UI polish

## Work In Progress

### Browser / Web Work

Still in progress:
- polishing web video playback UX
- refining desktop/browser library workflows

### Android TV Native App

Active work:
- native player overlay / OSD polish
- subtitle handling in the native player
- resume position tracking
- richer card presentation and artwork
- native on-screen search
- native audio playback path instead of placeholder-only audio browsing

## Explicit Decisions

### Decision: Stop Treating WebView as the Main Android TV Runtime

This is now explicit.

Reason:
- Mi Box device behavior exposed too many problems in the `WebView` route:
  - DNS resolution problems
  - unstable WebView runtime behavior
  - threading / lifecycle issues
  - too much effort for too little value

Conclusion:
- Android TV work should continue natively

## Tag model

Current shared curation model:
- `Audio Tag`
- `Video Tag`

Both are implemented as backend `TagDefinition` entries with `scope=track`, so they are assignable to any track-backed media item, including both audio and video content.

Native TV/video landing order is now:
1. `Recently Added`
2. `All Videos`
3. ordered `Video Tag` values through `TagValue.display_order`

### Decision: Device-local connection setup on Android TV

The native app no longer ships with a maintainer-specific LAN IP, public URL, or virtual-host header.
The Android TV setup screen collects server address, port, user, and password locally on the device.

## Current Priorities

Priority order right now:

1. Android TV native player polish
2. Android TV native search
3. Android TV native audio playback path
4. richer native TV home surfaces and resume-based rails
5. continue refining the web frontend for desktop/browser use

## What Is Stable Enough To Use

Good enough to use now:
- browser audio library shell
- browser video playback inside the audio shell
- native Android TV home shell on Mi Box
- native Android TV video playback on Mi Box

## What Should Be Treated As Experimental

Experimental:
- reviving browser TV mode as a final TV deployment target
- `Web Diag` / WebView wrapper on Android TV
- any future work that tries to make WebView the main TV runtime again

## Build and Delivery Notes

### Web Frontend

Project path:
- `srcnew/`

Canonical build workflow:

```bash
VITE_TRIVER_VERSION="$(cat VERSION)" ./scripts/build-frontend.sh
```

Rules:
- modify source files only
- do not edit generated frontend artifacts directly
- rebuild from source and commit the refreshed `frontend/package/build/`
- installs use the committed prebuilt frontend and do not require Node/npm

### Android TV App

Project path:
- `android-tv-shell/`

Current build is done inside the `dev` container.

Working command:

```bash
docker exec dev bash -lc 'cd /app/triver/android-tv-shell && su -s /bin/bash node -c "./gradlew --no-daemon assembleDebug"'
```

Current APK output:
- `android-tv-shell/app/build/outputs/apk/debug/app-debug.apk`

Current practical sideload path:
- upload to Mi Box FTP via `upload-to-mibox-ftp.sh`
- install from `device/Download`

## Document Map

- [srcnew/README.md](../frontend/source/srcnew/README.md)
  - current web frontend structure and status
- [android-tv-shell/README.md](./android-tv-shell/README.md)
  - native Android TV app overview and build/test notes
- [android-tv-shell/ANDROID_TV_NATIVE_ROADMAP.md](./android-tv-shell/ANDROID_TV_NATIVE_ROADMAP.md)
  - native Android TV execution plan

## Short Version

If someone asks which direction is correct today:
- browser library work: `srcnew/`
- TV device work: `android-tv-shell/`
- WebView on Mi Box: no longer the main path
