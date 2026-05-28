# trueRiver NOTICE

This notice covers third-party components whose copyright and license notices must be retained when distributing built trueRiver artifacts.

It is intentionally not a general stack list. Docker Compose services that are pulled by an end user from their upstream registries are documented in `DISTRIBUTION_REVIEW.md`; they become trueRiver notice obligations only if trueRiver publishes or redistributes those images itself.

Planned binary artifacts:
- built web frontend
- Android TV APK

Each binary artifact should link to the exact source tag or commit used to build it, plus the lockfiles and build instructions needed to reproduce it.

## Web Client Bundle

These notices apply to the built browser bundle distributed with trueRiver.

| Component | License | Notice | Source |
| --- | --- | --- | --- |
| React, React DOM, Scheduler | MIT | Copyright (c) Facebook, Inc. and its affiliates. | https://github.com/facebook/react |
| hls.js | Apache-2.0 | Copyright (c) 2017 Dailymotion. | https://github.com/video-dev/hls.js |
| wavesurfer.js | BSD-3-Clause | Copyright (c) 2012-2023, katspaugh and contributors. | https://github.com/katspaugh/wavesurfer.js |
| butterchurn | MIT | Copyright (c) 2013-2018 Jordan Berg. | https://github.com/jberg/butterchurn |
| butterchurn-presets | MIT | Copyright (c) 2013-2018 Jordan Berg. | https://www.npmjs.com/package/butterchurn-presets |
| soundtouchjs | LGPL-2.1 | Copyright notices are retained from SoundTouchJS and the GNU Lesser General Public License text. | https://www.npmjs.com/package/soundtouchjs |
| Tabler Icons | MIT | Copyright (c) 2020-2026 Pawel Kuna. | https://tabler.io/icons |

Copied package-level npm license and notice files are collected under `THIRD_PARTY_NOTICES/frontend-npm/`. That directory should be regenerated from the final lockfile/install state and shipped with the web frontend release attachment.

## Android TV APK

These notices apply when distributing the trueRiver Android TV APK.

| Component | License | Notice | Source |
| --- | --- | --- | --- |
| AndroidX Media3 / ExoPlayer | Apache-2.0 | The Android Open Source Project. | https://developer.android.com/guide/topics/media/media3 |

## Optional Remote Metadata Providers

These services are not bundled software dependencies. They are optional runtime
data providers used only when configured and enabled by the server operator.

| Provider | Terms / License Signal | Notice | Source |
| --- | --- | --- | --- |
| TMDb | TMDb API terms | This product uses the TMDb API but is not endorsed or certified by TMDb. | https://www.themoviedb.org/ |
| MusicBrainz | Open music metadata project; provider usage rules apply | Music metadata may be retrieved from MusicBrainz when Remote Metadata is enabled. | https://musicbrainz.org/ |
| Cover Art Archive | Cover art service connected to MusicBrainz | Cover images may be retrieved from the Cover Art Archive when MusicBrainz metadata is used. | https://coverartarchive.org/ |

## Conditional Backend Image Notices

If trueRiver later publishes a prebuilt backend/container image, that artifact must carry notices for backend Python dependencies and bundled system binaries such as FFmpeg. For now those are tracked in `DISTRIBUTION_REVIEW.md`, because the planned public artifacts are the frontend build and Android TV APK.

## Runtime Services Pulled By Compose

The source install starts some upstream containers directly from their public registries. They are not bundled into the web build or Android APK, but they are visible to users in the running app credits and distribution review.

| Component | License | Use | Source |
| --- | --- | --- | --- |
| ClamAV | GPL-2.0 | Upload antivirus scanning through `clamd`. | https://www.clamav.net/ |

## Release Packaging Note

Formal binary releases should include the full license texts for every component above, not only this summary table.
