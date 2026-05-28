# Android Gradle Dependency Snapshot

Generated from `apk/source/app/build.gradle` and root Gradle files.

## Plugins

| Component | Version | Notes |
| --- | ---: | --- |
| Android Gradle Plugin | 8.5.2 | Declared in `apk/source/build.gradle`. |

## App Dependencies

| Component | Version | License signal | Notes |
| --- | ---: | --- | --- |
| `androidx.media3:media3-exoplayer` | 1.4.1 | Apache-2.0 | Verified from Google Maven POM. |
| `androidx.media3:media3-exoplayer-hls` | 1.4.1 | Apache-2.0 | Verified from Google Maven POM. |
| `androidx.media3:media3-ui` | 1.4.1 | Apache-2.0 | Verified from Google Maven POM. |

## Build Metadata

- `compileSdk`: 34
- `minSdk`: 24
- `targetSdk`: 34
- `versionCode`: 43
- `versionName`: 0.4.3

## Notice Verification

- Google Maven POMs for all three Media3 artifacts declare `The Apache Software License, Version 2.0`.
- See `THIRD_PARTY_NOTICES/AndroidX-Media3-Apache-2.0.md`.
- A local Gradle dependency command was attempted, but the host environment has no Java runtime configured:
  `ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.`
- The containerized Android release build path was verified with
  `TRIVER_ANDROID_UNSIGNED_RELEASE=1 ./scripts/build-android-tv-apk.sh release`.
