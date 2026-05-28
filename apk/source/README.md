# trueRiver Android TV

Native Android TV application for `trueRiver`.

This project started as a thin `WebView` wrapper and is now moving in the correct direction:
- native Android TV shell
- native API reads
- native playback
- no dependency on `WebView` as a mainline runtime path

## Current status

Current application version in code:
- `0.4.3`

Current state:
- native home shell works on Mi Box
- native `Video` and `Audio` modes load real API data
- native video playback via `Media3 / ExoPlayer` is already working on Mi Box
- first launch, or any connection failure, opens a native connection setup page for address, port, user, and password

Known current player issue:
- the native player still leaves a visible overlay band on top of the video and needs OSD polish

## Why this app exists

The web TV route was useful for prototyping, but the actual Mi Box work exposed two concrete realities:

1. the box had broken / unreliable DNS behavior for the public hostname
2. the `WebView` path became too fragile to justify making it the main runtime

Because of that, the Android TV app now follows this direction:
- use native Android TV activities
- use direct API access
- use native video playback
- treat `WebView` only as a secondary diagnostic instrument

## Current capabilities

### Native home shell

Implemented:
- native launcher / entry screen
- native home shell
- native sidebar / mode switch:
  - `Video`
  - `Audio`
  - `Search`

### Native data loading

Implemented:
- direct API reads for:
  - `/api/scan-jobs/latest/`
  - `/api/videos/`
  - `/api/artists/`
  - `/api/albums/`
  - `/api/tracks/`

### Native video playback

Implemented:
- `Media3 / ExoPlayer`
- native player activity
- playback from backend `playback_url`
- working playback test on Mi Box

### Native detail fallback

Implemented:
- non-video items still open a native detail placeholder activity

## Connection model

The native TV shell no longer ships with a personal LAN address, public URL, or baked-in API credentials.

On first launch, or whenever the connection fails, the app shows a local setup page where the user enters:
- server address
- port
- trueRiver username
- trueRiver password

Important consequence:
- `android:usesCleartextTraffic="true"` is enabled for LAN/self-hosted testing. Revisit this before a public release profile.

## Project structure

Important files:
- `app/build.gradle`
  - app version, default API host/port, virtual host header, dependencies
- `app/src/main/java/com/trueriver/tvshell/NativeHomeActivity.java`
  - native Android TV launcher shell, connection setup, and library browsing
- `app/src/main/java/com/trueriver/tvshell/NativePlayerActivity.java`
  - native `Media3 / ExoPlayer` video playback
  - subtitle track mounting and selection cycling
- `app/src/main/java/com/trueriver/tvshell/TvConnectionConfig.java`
  - local device configuration for API address, port, user, and password
- `app/src/main/java/com/trueriver/tvshell/NativeDetailActivity.java`
  - placeholder detail activity for non-video items
- `ANDROID_TV_NATIVE_ROADMAP.md`
  - next phases for the native TV app
- `upload-to-mibox-ftp.sh`
  - upload helper for sideload iteration through CX File Explorer FTP

## Build

Release builds are built from the repository root with `scripts/build-android-tv-apk.sh`.
The script uses an Android SDK container and writes generated APKs under `apk/package/`.

Debug iteration can still use any local Android SDK environment that can run Gradle.

Release build command:

```bash
./scripts/build-android-tv-apk.sh release
```

Debug build command:

```bash
./scripts/build-android-tv-apk.sh debug
```

Generated APK copies:
- `apk/package/trueriver-tv-<version>.apk` for signed release builds
- `apk/package/trueriver-tv-<version>-debug.apk` for debug builds

Notes:
- release signing inputs come from environment variables documented in `docs/build/android-tv.md`
- the native app no longer stores API credentials in `BuildConfig`; credentials are entered on the Mi Box and saved in app-local preferences
- default connection values are blank server address and port `80`; user/password must be configured on the box

Current APK state:
- native video playback works on Mi Box
- subtitle tracks are now fed from the same backend subtitle URLs used by the browser
- subtitle cycling is wired in the native player overlay
- the app icon and banner use the `tR` trueRiver mark

Related frontend rule:
- the web frontend must also be built from inside `dev`
- canonical frontend workflow:

```bash
docker exec -it dev bash
cd triver
npm run build:new
```

- never modify generated `build/` artifacts directly

## Upload to Mi Box

### Recommended path

The current working workflow is:
1. open CX File Explorer FTP server on the Mi Box
2. build the APK
3. upload into `device/Download`
4. install from the file manager on the box

Helper script:

```bash
./upload-to-mibox-ftp.sh
```

What it does:
- prompts for the FTP password every run, unless `MIBOX_FTP_PASSWORD` is already set
- uploads the debug APK to the Mi Box
- uses active FTP mode, which is the mode that worked with CX File Explorer

Required environment:
- `MIBOX_FTP_HOST`
- `MIBOX_FTP_USER`

Optional environment:
- `MIBOX_FTP_PORT`, default `8290`
- `MIBOX_FTP_REMOTE_DIR`, default `device/Download`
- `MIBOX_FTP_REMOTE_NAME`, default derived from `versionName`

Non-interactive upload example:

```bash
cd /home/dockers/dev/srcs/data/0_dev/triver/android-tv-shell
MIBOX_FTP_HOST='<device-address>' MIBOX_FTP_USER='<ftp-user>' MIBOX_FTP_PASSWORD='<password>' ./upload-to-mibox-ftp.sh
```

Full debug build plus sideload flow:

```bash
./scripts/build-android-tv-apk.sh debug
cd apk/source
MIBOX_FTP_HOST='<device-address>' MIBOX_FTP_USER='<ftp-user>' MIBOX_FTP_PASSWORD='<password>' MIBOX_FTP_REMOTE_NAME='trueriver-<version>-debug.apk' ./upload-to-mibox-ftp.sh ../package/trueriver-tv-<version>-debug.apk
```

If Android TV says `App not installed` while updating a debug APK:
- the APK may be valid but signed with a different debug key than the app already installed on the box
- uninstall `trueRiver TV` from the Mi Box once, then install the new APK again
- if a file manager appears to cache `app-debug.apk`, upload with a versioned name:

```bash
MIBOX_FTP_HOST='<device-address>' MIBOX_FTP_USER='<ftp-user>' MIBOX_FTP_PASSWORD='<password>' MIBOX_FTP_REMOTE_NAME='trueriver-0.4.0.apk' ./upload-to-mibox-ftp.sh
```

On first launch:
- address: enter the reachable trueRiver server address
- port: `80` for plain LAN HTTP, or the exposed proxy port for a custom install
- user/password: enter a registered trueRiver account
- if the connection later fails, the same setup page is shown again so the values can be changed

## Current practical test flow

Recommended test flow:
1. build APK inside `dev`
2. upload APK with `upload-to-mibox-ftp.sh`
3. install on Mi Box
4. verify:
   - native home shell opens
   - `Video` mode loads rows
   - `Audio` mode loads rows
   - opening a video starts native playback
   - `Back` exits playback correctly

## What is done vs in progress

### Done

Done already:
- native launcher
- native home shell
- native mode switching
- real API reads
- Mi Box networking workaround through LAN IP + Host header
- native player activity with `Media3 / ExoPlayer`
- validated native playback on Mi Box

### In progress

Still in progress:
- player overlay / OSD polish
- native subtitle handling
- resume position tracking
- native search surface
- richer card / poster presentation
- native audio playback path

### Deprioritized

Deprioritized by explicit decision:
- making `WebView` the main runtime path on Mi Box

## Recommendation

If you need to push the TV experience forward, spend the next engineering cycles here:
- native player polish
- native search
- native audio playback
- resume-aware home rails

Do not spend mainline effort trying to resurrect the `WebView` path as the production runtime.
