# Android TV Build

The Android TV app source is in `apk/source`.

Generated APK files are release artifacts. They should not be committed to the
source repository.

## Release Requirements

Each APK release must:

- link to the exact source tag or commit used to build it;
- include or link to third-party notices for AndroidX Media3 / ExoPlayer and
  other Android dependencies;
- avoid hardcoded local server addresses, credentials, signing keys, or personal
  deployment defaults;
- include checksums in the release notes or attached `checksums.txt`.

## Release Build

Use the root build helper:

```bash
./scripts/build-android-tv-apk.sh release
```

Only when you intentionally want to bump the Android TV app too, prepare the
Android release version from the repository root:

```bash
./scripts/prepare-release-version.sh --android <version>
```

The version helper updates Android `versionName`, increments `versionCode` when
the visible version changes, and keeps the TV shell user-agent/version marker in
sync. Use `--android-version-code N` if a specific Play/installer monotonic code
is required. Normal server/frontend release preparation leaves Android unchanged.

The helper builds inside a pinned Android SDK container so the release path does
not depend on Android Studio or the old local `dev` container. Override the
builder with `TRIVER_ANDROID_BUILDER_IMAGE` only when intentionally updating the
release build environment.

Signed public release builds require a keystore stored outside Git. Keep it
under `apk/source/.signing/`, which is ignored by the repository, and export:

```bash
export TRIVER_ANDROID_KEYSTORE=.signing/trueriver-release.jks
export TRIVER_ANDROID_KEYSTORE_PASSWORD='<store-password>'
export TRIVER_ANDROID_KEY_ALIAS='<key-alias>'
export TRIVER_ANDROID_KEY_PASSWORD='<key-password>'
./scripts/build-android-tv-apk.sh release
```

The release signing key must be the Android TV continuity key whose public
certificate SHA-256 is:

```text
488e9cc9dc3c0d0964c908fbdeb3e56846aa7cb24526abec679c2d3d66216acc
```

The build helper checks this fingerprint for signed release builds and fails if
a different release key is used. Do not replace it with a freshly generated
keystore, because Android will reject updates over installs signed with the
continuity key.

For this machine, the local release signing env is stored at
`apk/source/.signing/release.env`. It is intentionally ignored by Git. Back up
`apk/source/.signing/trueriver-release.jks` and that env file somewhere private;
losing them means future APKs cannot update installs signed with this key.

The signed APK is written to `apk/package/trueriver-tv-<version>.apk` with a
sidecar SHA-256 file. Pass that APK to the release artifact script with:

```bash
TRIVER_APK_PATH=apk/package/trueriver-tv-<version>.apk ./scripts/build-release-artifacts.sh
```

For local verification only, an unsigned release build can be produced with:

```bash
TRIVER_ANDROID_UNSIGNED_RELEASE=1 ./scripts/build-android-tv-apk.sh release
```

Debug APKs are useful for device iteration but are not public release artifacts.
