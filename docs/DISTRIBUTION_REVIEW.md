# trueRiver distribution review

Date: 2026-05-23

This is an engineering release review, not legal advice. It records the current dependency/licensing shape and the concrete work still needed before publishing trueRiver as a public tech demo.

## Executive status

Status: installable source tech demo is plausible under `AGPL-3.0-or-later`; public Docker images still need extra license packaging.

The source tree is close to releasable, but these items must be resolved first:

1. Keep the root `LICENSE` at `AGPL-3.0-or-later`, unless GPL/LGPL dependencies are removed and the licensing strategy is deliberately revisited.
2. Keep `NOTICE.md` aligned with the exact artifacts we actually distribute. The initial notice file now exists.
3. Either accept copyleft components under a compatible open-source license, or replace them:
   - `mutagen==1.47.0` is GPL-2.0-or-later.
   - `soundtouchjs@0.3.0` is LGPL-2.1 and is bundled into the web build.
   - the current Debian FFmpeg installed in the backend image is built with `--enable-gpl`.
   - `psycopg[binary]==3.2.6` is LGPLv3.
4. Redis 7.4+ has already been removed from the compose path. The public stack now uses `valkey/valkey:7.2-alpine`.
5. Treat `wg-easy` as an optional third-party AGPL-3.0-only service. The issue is not that it "infects" trueRiver through Docker networking; the issue is that if we redistribute or modify wg-easy, or present it as bundled product functionality, we need to satisfy its AGPL obligations and expose that clearly to users.
6. Remote metadata providers are optional runtime services, not bundled code, but releases must carry the provider attribution/privacy notices and must not ship private API keys.
7. Do not distribute user media, scan dumps, avatars, local `.env`, Android `local.properties`, runtime database volumes, or unsigned/debug-only build artifacts. A release-signed Android TV APK can be distributed, provided it has no local defaults/secrets and includes the required notices.

## Recommended project license

Recommended default for the current project: `AGPL-3.0-or-later`.

Why:
- trueRiver is network/server software, and AGPL keeps hosted modifications open to the users of that network service.
- The current backend already uses `mutagen`, which is GPL-2.0-or-later. That makes a permissive MIT/Apache project license awkward unless we remove or isolate mutagen.
- Apache-2.0 dependencies such as hls.js and AndroidX Media3 are compatible with GPLv3-family licensing.
- The optional `wg-easy` service is already AGPL-3.0-only, so using AGPL for trueRiver reduces conceptual mismatch.

Alternative:
- If we want maximum adoption and a permissive license, use `Apache-2.0`, but first replace `mutagen`, avoid GPL FFmpeg binary distribution, and handle LGPL JavaScript/audio dependencies carefully.
- If we want copyleft but less network-specific reciprocity, use `GPL-3.0-or-later`, but AGPL fits this product better.

Resolved for the current public tech demo: the root `LICENSE` is `AGPL-3.0-or-later`.

## Distribution modes

This distinction matters a lot.

### Source-only GitHub release

If we publish trueRiver source, Dockerfiles, Compose files, and configuration, but do not publish prebuilt Docker images, we are primarily distributing our code and configuration. The user pulls PostgreSQL, Valkey, NGINX, wg-easy, Debian packages, Python wheels, and npm packages from upstream sources.

In that mode:
- Docker Compose references to upstream services are not the same thing as redistributing those binaries.
- We should still document the upstream services and their licenses.
- We still need notices for vendored files in the repo, such as the local Tabler icon pack.
- If we publish a built web bundle in the repo, notices for bundled JavaScript dependencies apply.

### Binary / artifact release

The planned binary artifacts are:
- built frontend assets
- Android TV APK

If we publish these, we are redistributing bundled third-party code for those artifacts.

In that mode:
- `NOTICE.md` and full license texts must travel with the artifact.
- The frontend must include/link the exact source tag or commit used to build it.
- The APK must include/link the exact source tag or commit used to build it.
- LGPL obligations apply for bundled frontend libraries such as `soundtouchjs`.
- Android dependency notices apply to the APK.

If we later publish any of these, then additional obligations apply:
- prebuilt backend Docker image
- all-in-one image or tarball containing images
- modified or mirrored third-party service images

For those later artifacts:
- FFmpeg source/build configuration obligations apply if the backend image contains FFmpeg.
- LGPL obligations apply for bundled backend libraries such as `psycopg`.
- GPL/AGPL obligations apply for `mutagen`, GPL FFmpeg builds, and any redistributed/modified wg-easy image.

## Source repository strategy

Separate repos are optional, not required for license compliance. What matters is that every distributed artifact points to the exact corresponding source.

Recommended path for now:
- keep one canonical source repo while frontend, backend, and Android TV APIs are still moving together
- tag releases, for example `v0.5.0`
- set build metadata in the frontend and APK to link to that exact tag or commit
- publish frontend build and APK as release assets from the same tag

Split repos later if release cadence diverges:
- `trueriver-server` for backend, compose, proxy and deployment docs
- `trueriver-web` for the browser frontend
- `trueriver-tv-android` for the Android TV APK

If split repos happen, the frontend and APK should still show their own source links in-app, pointing to the exact repo/tag used for that artifact.

## Direct dependency snapshot

Backend Python, from `/home/dockers/triver/srcs/backend/requirements.txt` and package metadata in the running backend container:

| Component | Version | License signal | Release note |
| --- | ---: | --- | --- |
| Django | 5.1.8 | BSD-3-Clause | Include license/notice. |
| Django REST Framework | 3.15.2 | BSD | Include license/notice. |
| django-filter | 25.1 | BSD | Include license/notice. |
| Celery | 5.4.0 | BSD-3-Clause | Include license/notice. |
| gunicorn | 23.0.0 | MIT | Include license/notice. |
| psycopg / psycopg-binary | 3.2.6 | LGPLv3 | Keep license text and source/relink compliance path. Consider non-binary install against system `libpq`. |
| mutagen | 1.47.0 | GPL-2.0-or-later | Main copyleft concern in backend code. If trueRiver is not GPL-compatible, replace it or isolate it as a separate process/tool. |
| python-magic | 0.4.27 | MIT | Include license/notice. |

Frontend web, from `/home/dockers/dev/srcs/data/0_dev/triver/package.json` and installed package metadata:

| Component | Version | License signal | Release note |
| --- | ---: | --- | --- |
| React / React DOM | 18.3.1 | MIT | Include license/notice. |
| Vite / @vitejs/plugin-react | 8.0.13 / 6.0.2 | MIT | Dev/build dependency notice. |
| hls.js | 1.6.16 | Apache-2.0 | Include Apache license and notices. |
| wavesurfer.js | 7.12.5 | BSD-3-Clause | Include license/notice. |
| butterchurn | 2.6.7 | MIT | Include license/notice. |
| butterchurn-presets | 2.4.7 | MIT | Include license/notice. |
| soundtouchjs | 0.3.0 | LGPL-2.1 | Bundling into a minified Vite artifact needs LGPL compliance: license text, source link, modification notice, and a practical way to replace/relink the library. |
| Tabler Icons | internal icon components, notice retained | MIT | Full local SVG pack removed from the source candidate; keep `THIRD_PARTY_NOTICES/Tabler-Icons-MIT.txt`. |

Android TV:

| Component | Version | License signal | Release note |
| --- | ---: | --- | --- |
| Android Gradle Plugin | 8.5.2 | Android/Apache ecosystem | Include Android OSS notices in APK release notes. |
| AndroidX Media3 / ExoPlayer | 1.4.1 | Apache-2.0 | Include Apache license and notices. |

Runtime / containers:

| Component | Current use | License signal | Release note |
| --- | --- | --- | --- |
| PostgreSQL | `postgres:16-alpine` | PostgreSQL License | Permissive; include notice if distributing images. |
| Valkey | `valkey/valkey:7.2-alpine` | BSD-style Valkey license | Preferred over Redis 7.4+ for release packaging. |
| NGINX | `nginx:1.27-alpine` | BSD-like NGINX license | Include notice if distributing images. |
| FFmpeg / ffprobe | apt package in backend image | LGPL/GPL depending build; current build has `--enable-gpl` | Binary image distribution requires FFmpeg source offer/build notes and GPL compliance. |
| wg-easy | optional VPN profile | AGPL-3.0-only | Keep optional and prominently noticed, or replace with plain WireGuard. |
| ClamAV | upload scan service, `clamav/clamav:1.5_base` | GPL-2.0 | Source installs pull the upstream image; include GPL notices/source offer if trueRiver redistributes a ClamAV image or image bundle. |
| Docker Compose | packaging/runtime | Apache-2.0 ecosystem | Compose files are fine; notices needed for distributed images. |

Optional remote metadata providers:

| Provider | Current use | Release note |
| --- | --- | --- |
| TMDb | Manual movie/TV metadata lookup when configured and enabled. | Add TMDb attribution in Credits/About and do not ship private keys. |
| MusicBrainz | Manual music metadata lookup when configured and enabled. | Use an identifiable User-Agent and conservative request rate. |
| Cover Art Archive | Optional artwork retrieval through MusicBrainz metadata flows. | Attribute provider and keep artwork/provider terms visible. |
| OMDb / TheTVDB | Credentials are reserved in local env files; provider implementation is not active yet. | Do not claim support or ship keys until implementation and terms are reviewed. |

## What changed for release hygiene

- Removed maintainer-specific Android TV first-boot network defaults.
- Removed maintainer-specific public URL from the web Server Settings placeholder.
- Made Android TV FTP upload helper require `MIBOX_FTP_HOST` and `MIBOX_FTP_USER` instead of shipping personal defaults.
- Added `.gitignore` coverage for local `.env`, node modules, Gradle/build output, APKs, Android local SDK config, and runtime data.
- Moved the cache service in `docker-compose.yml` from Redis 7.x to Valkey 7.2 for a cleaner public stack.
- Replaced the maintainer-specific Docker backend network with a generic `triver_backend` network.
- Added ClamAV as an upstream runtime service for browser uploads into `trive-In`; uploaded files are scanned before final placement.
- Added `PRIVACY.md` and `DISCLAIMER.md` for local-first behavior, provider data sharing and no-warranty/operator responsibility.
- Added optional remote metadata notices for TMDb, MusicBrainz and Cover Art Archive.
- Added Classic Import for read-only external host folders mounted into the Docker stack by local ignored compose configuration.

## High-risk items

### Mutagen

`mutagen` is imported directly by backend scan/catalog tasks. PyPI lists it as GPL-2.0-or-later. If trueRiver is AGPL/GPL-compatible and we publish full source, this is acceptable. If we want MIT/Apache/proprietary licensing, it is a blocker because the backend is not just "talking to an executable"; it imports and uses the Python library.

Options:
- Keep `mutagen`, choose a GPL-compatible trueRiver license, and publish full corresponding source.
- Replace metadata extraction with `ffprobe` plus a permissive parser.
- Move `mutagen` into an optional external worker process with clear distribution boundaries, then review with counsel.

### FFmpeg

The backend image currently installs Debian FFmpeg. The running binary reports `--enable-gpl` and GPL codec libraries such as x264/x265.

If we only publish source and Dockerfiles, users pull/build FFmpeg from Debian themselves. We still document the dependency, but the binary redistribution burden is much lighter.

If we publish a ready-made backend Docker image, then we redistribute that FFmpeg binary. At that point we need exact FFmpeg source availability, build configuration, license text, and GPL-compatible distribution handling. FFmpeg's own compliance checklist says LGPL-only builds should be compiled without `--enable-gpl` and `--enable-nonfree`; our current image is not in that category.

Options:
- Publish an installable source tech demo with the web build committed and no prebuilt backend image.
- Ship an LGPL-only FFmpeg build without GPL/nonfree flags.
- Keep GPL FFmpeg and make trueRiver's distribution GPL-compatible with full source/offers.

### soundtouchjs

`soundtouchjs` is LGPL-2.1 and is used for pitch/speed work in the browser. Because Vite bundles JavaScript, compliance is not just a tiny footer credit. For a binary web bundle, we need license text, source link, build instructions, and a practical way for users to rebuild/replace the LGPL library.

Options:
- Remove `soundtouchjs` before release if pitch shifting is not essential.
- Keep it and publish unminified source, build instructions, exact lockfile, and LGPL text/source links.
- Replace pitch shifting with browser/native APIs or a permissively licensed worklet.

### Redis 7.4+

Resolved. The old `redis:7-alpine` tag resolved locally to Redis 7.4.9, whose licensing is RSALv2/SSPLv1 rather than the old BSD line. `docker-compose.yml` now uses `valkey/valkey:7.2-alpine`.

### wg-easy

The optional VPN container uses `ghcr.io/wg-easy/wg-easy:15`, whose project is AGPL-3.0-only. If users pull it directly via Compose, trueRiver is distributing configuration, not the wg-easy binary. Still:
- mark it as optional third-party software
- do not obscure its identity/license
- do not publish a modified wg-easy image without AGPL compliance
- keep the firewall/wiring config in our own tree under the trueRiver license

### Remote metadata providers

Remote metadata lookup is optional and manual by default. Opening Settings or
switching the lookup mode does not contact providers; configured providers can
receive media search terms such as titles, artist names, album names, years,
external IDs or filenames only after a manual content action, or after an
explicitly configured automation. That is a privacy and provider-terms issue,
not a bundled-code license issue.

Release requirements:
- do not ship provider API keys or maintainer accounts
- keep provider configuration in ignored local env files
- keep provider attribution in `NOTICE.md` and in-app Credits
- keep `PRIVACY.md` visible from release/install documentation
- for MusicBrainz, send an identifiable User-Agent and stay at conservative
  request rates
- for TMDb, include the required non-endorsement attribution in Credits/About

## Assets and content

- trueRiver logo/icon assets appear project-owned and can be distributed once the project license is chosen.
- Tabler SVG icons are MIT and already include a local license file.
- Do not ship personal music/video/media files, generated covers, scan dumps, `trive-*` volume data, user avatars, or database snapshots.
- Do not ship Classic Import local compose files or host paths; they are operator-specific local configuration.
- Generated/default cover art created by trueRiver can ship if it contains no third-party marks or copied artwork.

## Release checklist

Before GitHub/public tech demo:

1. Verify root `LICENSE` is present and matches the intended project license.
2. Keep `NOTICE.md` current and include full license texts in binary releases.
3. Add `.env.example` with safe generic defaults.
4. Pin Docker image versions by digest or exact version and document licenses.
5. Decide what to do with `mutagen`.
6. Decide what to do with `soundtouchjs`.
7. Decide whether FFmpeg distribution is source-only, LGPL-only binary, or GPL-compatible binary.
8. Keep `wg-easy` behind an optional profile and mention AGPL on the VPN settings page.
9. Keep `PRIVACY.md`, `DISCLAIMER.md`, provider attributions and in-app Credits aligned with enabled runtime integrations.
10. Run dependency license generation:
   - `npm ls --json` plus package license extraction from `package-lock.json`.
   - `pip` metadata extraction or `pip-licenses` inside the backend image.
   - Gradle dependency/license report for Android.
11. Verify `.gitignore` excludes media, volumes, APKs, secrets, and generated builds.

## Source references checked

- FFmpeg legal page: https://www.ffmpeg.org/legal.html
- Redis licensing page: https://redis.io/legal/licenses/
- GNU AGPLv3 overview: https://www.gnu.org/licenses/agpl-3.0.html
- Apache 2.0 / GPL compatibility: https://www.apache.org/licenses/GPL-compatibility
- PostgreSQL license: https://www.postgresql.org/about/licence/
- wg-easy repository/license: https://github.com/wg-easy/wg-easy
- mutagen PyPI metadata: https://pypi.org/project/mutagen/
- psycopg license: https://www.psycopg.org/license/
- wavesurfer.js npm metadata: https://www.npmjs.com/package/wavesurfer.js
- hls.js npm metadata: https://www.npmjs.com/package/hls.js
- soundtouchjs npm metadata: https://www.npmjs.com/package/soundtouchjs
- butterchurn npm metadata: https://www.npmjs.com/package/butterchurn
- AndroidX Media3 Maven metadata: https://mvnrepository.com/artifact/androidx.media3/media3-exoplayer/1.4.1
- ClamAV licensing and Docker documentation: https://docs.clamav.net/
- TMDb API attribution FAQ: https://developer.themoviedb.org/docs/faq
- MusicBrainz API rate limiting: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
- Cover Art Archive API documentation: https://musicbrainz.org/doc/Cover_Art_Archive/API
- GNU AGPLv3 text: https://www.gnu.org/licenses/agpl-3.0.html
