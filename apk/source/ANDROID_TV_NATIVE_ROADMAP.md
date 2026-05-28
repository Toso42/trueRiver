# Android TV Native Roadmap

## Goal

Move `trueRiver TV` toward a real Android TV application with:
- native DPAD focus
- native video playback
- stable Android TV lifecycle behavior
- direct use of Triver API endpoints
- zero dependency on `WebView` as the main runtime

## Current decisions

### Decision 1: Native is the real path

This is no longer tentative.

The Mi Box tests already established that:
- native shell works
- native API access works
- native video playback works
- `WebView` became a low-value debugging rabbit hole

So the roadmap now assumes:
- native app = mainline
- no `WebView` shell in the main product path

### Decision 2: Device-local connection setup

The TV app should not ship with a maintainer-specific LAN IP, public URL, or credential.
The current strategy is a device-local connection setup screen that stores server address, port, user, and password in app preferences.

## Current state

### Already completed

Completed:
- native launcher and entry flow
- native home shell
- native mode switch:
  - `Video`
  - `Audio`
  - `Search`
- direct API reads for:
  - `/api/scan-jobs/latest/`
  - `/api/videos/`
  - `/api/artists/`
  - `/api/albums/`
  - `/api/tracks/`
- native detail placeholder for non-video items
- native video playback using `Media3 / ExoPlayer`
- successful playback validation on Mi Box

### Current known issues

Known issues after first working native playback:
- player overlay band is still visible on top of the video
- player controls are not yet a polished TV OSD
- subtitle handling is not yet where it needs to be
- search is still placeholder-only
- audio mode still browses data but does not yet offer its own native playback path

## Phase breakdown

## Phase 0
Foundation

Status:
- completed

Delivered:
- app bootstrap
- Android TV launcher
- native layout skeleton
- build pipeline inside `dev` container
- working sideload loop through Mi Box FTP

## Phase 1
Native library browsing

Status:
- completed at first useful level

Delivered:
- native home shell
- native mode switching
- native rows for:
  - videos
  - artists
  - albums
  - tracks
- working focus and activation model good enough for device testing

Still worth improving inside this phase:
- richer card layouts
- poster / thumbnail loading
- focus restore by rail and item
- better visual hierarchy in rows

## Phase 2
Native playback

Status:
- started and already partially completed

Delivered already:
- `Media3 / ExoPlayer`
- native video player activity
- backend playback URL integration
- working playback on Mi Box

Still needed in this phase:
1. hide / show player overlay correctly
2. proper TV OSD controls
3. native subtitle selection
4. resume position tracking
5. HLS vs fallback strategy handling where needed
6. error / buffering UI polish

## Phase 3
Audio mode as a real native playback surface

Status:
- not started as a true playback phase

Current reality:
- audio data loads
- audio browsing exists
- audio still lacks a native playback surface equivalent to the video path

Goals:
1. native audio player activity or persistent audio player region
2. play from track rows
3. queue behavior
4. DPAD-friendly controls
5. continue listening state

## Phase 4
Native search

Status:
- placeholder only

Goals:
1. native TV keyboard
2. quick search over:
   - videos
   - artists
   - albums
   - tracks
3. activation from results into player or detail screen
4. focus restore when closing search

## Phase 5
TV intelligence and home curation

Status:
- planned

Goals:
1. `Continue Watching`
2. `Continue Listening`
3. `Recently Added`
4. technical rails:
   - `4K`
   - `Full HD`
   - `HD Ready`
5. later curated rails once metadata and backend support are stronger

## Phase 6
Packaging and release discipline

Status:
- planned

Goals:
1. replace placeholder banner / icon assets
2. signing
3. reproducible release build
4. device QA on:
   - Mi Box
   - Chromecast with Google TV
   - other Android TV / Google TV devices if needed

## Explicit non-goals right now

Do not spend mainline time on:
- turning `WebView` into the final runtime
- making the old wrapper path the main delivery mechanism
- over-polishing diagnostic `Web Diag` before native player/search/audio are stable

## Immediate next steps

Most useful next engineering steps:

1. native player overlay auto-hide and OSD cleanup
2. native subtitle handling
3. resume position support
4. native search implementation
5. native audio playback path

## Medium term

Medium-term goals:
- resume-aware home rails
- richer artwork and metadata hierarchy
- continue watching / continue listening
- stronger Android TV visual language aligned with the product

## Long term

Long-term goals:
- cleaner backend contracts for TV home surfaces
- dedicated support for thumbnails / frame strips / progress metadata
- fully native Android TV product surface with no dependency on the diagnostic `WebView` path
