# trueRiver release plan

Date: 2026-05-20

This document turns the distribution and GPL readiness reviews into an execution plan. It should be updated after each release-prep pass.

## Decisions

| Area | Decision | Status | Notes |
| --- | --- | --- | --- |
| Project license | Use `AGPL-3.0-or-later`. | Decided | Fits trueRiver as network/server software. Commercial use, paid hosting, support, appliances and donations remain allowed, but distributed or network-served modified versions must keep corresponding source available. |
| Commercial posture | Public tech demo and donation-supported development, not a closed product. | Decided | Future proprietary relicensing would only be possible for code fully owned by the project owner. External AGPL contributions cannot be closed later without contributor permission. |
| Repository layout | Keep one canonical source repository for now. | Decided | Backend, web frontend, Android TV source, compose and docs move together until release cadence diverges. Split repos can happen later if needed. |
| Release artifacts | Keep the built frontend in Git and publish install/source archives plus APK as Gitea/GitHub release attachments. | Decided | Git checkouts, source archives and release install archives are runnable without Node/npm. |
| Release versioning | Keep the next release tag in `VERSION` and update it through `scripts/prepare-release-version.sh`; do not bump versions on every push. | Decided | Commit hashes identify every push. Semver identifies public release artifacts and prerelease tech demos. |
| Binary artifacts in Git | Keep generated `frontend/package/build/` in source for no-Node installs; keep `apk/package/*.apk` out of Git. | Decided | The web build is part of the installable source tree. APKs remain release attachments. |
| Docker/backend image | First public tech demo should be source/compose based, without publishing a prebuilt backend image. | Decided | This avoids taking on full binary redistribution duties for Debian FFmpeg in our own image release. |
| FFmpeg | Document as runtime/build dependency; do not publish our own FFmpeg-containing backend image until compliance is explicit. | Decided | If later publishing backend images, choose LGPL-only FFmpeg or publish GPL-compatible source/build notes/offers. |
| `mutagen` | Keep it under AGPL-compatible project licensing. | Decided | `mutagen` is GPL-2.0-or-later; AGPL/GPL-family project licensing is compatible enough for this release path. |
| `soundtouchjs` | Keep for now and prepare LGPL-2.1 compliance. | Decided for first pass | Package-lock reports `soundtouchjs@0.3.0` as `LGPL-2.1`. We will ship notices, license text, exact source/build instructions and rebuild path. Revisit replacement only when audio engine work resumes. |
| `wg-easy` | Keep optional under a Compose profile. | Decided | Treat as third-party AGPL software, not as a modified bundled image. Settings/docs must identify it clearly. |
| Valkey vs Redis | Use Valkey. | Done | Redis 7.4+ licensing concern is avoided in current compose path. |
| User media/runtime data | Never distribute user media, scan dumps, DB volumes, avatars, local env, signing keys, Android local SDK config or personal defaults. | Decided | Enforce through `.gitignore`, release scripts and final scans. |
| External contributions | Require DCO sign-off; do not require a CLA for now. | Decided | Keeps contribution provenance explicit without asking contributors to assign copyright. |
| Release scanners | Provide release-audit hooks and documented outputs first; do not add host installer scripts yet. | Decided | `scripts/release-audit.sh` records scanner availability and runs tools when installed. Docker/CI installer work can happen later. |
| First public tag | Use `v0.1.0-techdemo.1`. | Decided | Start from the current `main` release candidate after signed APK verification. Mark it as a prerelease/tech demo in Gitea/GitHub release metadata. |

## Release Model

Use one source repo:

```text
trueriver/
  backend/
  frontend/source/
  apk/source/
  deploy/
  docker-compose.yml
  README.md
  LICENSE
  NOTICE.md
  THIRD_PARTY_NOTICES/
  docs/
```

For each release tag, attach generated files to the release page:

```text
trueriver-tv-v0.1.0.apk
trueriver-web-v0.1.0.zip
trueriver-install-v0.1.0.tar.gz
trueriver-source-v0.1.0.tar.gz
trueriver-third-party-notices-v0.1.0.zip
checksums.txt
sbom-v0.1.0.json
```

Every binary artifact must point to the exact source tag or commit that produced it.

## Gate 1 - Legal And Notice Baseline

Goal: make the source repository legally coherent before public visibility.

- [x] Add root `LICENSE` declaring AGPL-3.0-or-later.
- [x] Replace root `LICENSE` with full verbatim AGPL text before public release.
- [x] Update `README.md` from planned license to actual `AGPL-3.0-or-later`.
- [x] Add `AUTHORS` or `COPYRIGHT`.
- [x] Add `SECURITY.md`.
- [x] Add `CONTRIBUTING.md` explaining AGPL contribution expectations.
- [x] Decide whether contributor licensing needs a lightweight Developer Certificate of Origin note.
- [x] Keep in-app Credits aligned with `NOTICE.md` for the current notice set.
- [x] Add baseline `THIRD_PARTY_NOTICES/` with common license texts.
- [x] Complete package-specific third-party copyright notices for first public release artifacts.
- [x] Update frontend package metadata with the project license or clear root-license reference.

Current note: `scripts/collect-frontend-notices.sh` generates `THIRD_PARTY_NOTICES/frontend-npm/` from the installed frontend npm tree. Regenerate it after dependency changes and before tagging a public release.

## Gate 2 - Artifact Policy Cleanup

Goal: keep Git source clean and move generated deliverables to release attachments.

- [x] Include `frontend/package/build/` in the tracked source candidate for no-Node installs.
- [x] Remove `apk/package/*.apk` from tracked source candidate.
- [x] Keep release archives and APK outputs ignored by `.gitignore`.
- [x] Add release script or docs that rebuild frontend from `frontend/source`.
- [x] Keep Node/npm out of the default runtime Compose path.
- [x] Add release script or docs that rebuild Android TV APK from `apk/source`.
- [x] Add release artifact script that writes release notes and SHA-256 checksums.
- [x] Add release version helper that updates `VERSION` and frontend package metadata, with opt-in Android updates.
- [x] Generate checksums for release attachments.
- [x] Ensure release notes link to exact source tag/commit.

## Gate 3 - LGPL Compliance For `soundtouchjs`

Goal: keep pitch/speed code for now without making the frontend bundle opaque.

- [x] Add full `LGPL-2.1` license text under `THIRD_PARTY_NOTICES/`.
- [x] Add `THIRD_PARTY_NOTICES/soundtouchjs.md` with:
  - package name and version: `soundtouchjs@0.3.0`;
  - license signal from `package-lock.json`: `LGPL-2.1`;
  - npm tarball URL and integrity hash;
  - statement whether trueRiver modifies it; current decision: no project modifications;
  - explanation that it is used by the web frontend for pitch/time-stretch playback.
- [x] Add frontend rebuild docs:
  - `cd frontend/source`;
  - install exact dependencies from lockfile;
  - run the production build;
  - replace `soundtouchjs` with a modified compatible version and rebuild.
- [x] Ensure the distributed frontend build is accompanied by source, lockfile and build instructions.
- [x] Add Credits/NOTICE entry visible from the app.
- [x] If `soundtouchjs` is ever patched locally, publish the modified library source and update notices.

## Gate 4 - Dependency And Binary Review

Goal: know exactly what is in source and artifacts.

- [x] Generate npm dependency license report from `frontend/source/package-lock.json`.
- [x] Generate backend Python license report inside the backend environment.
- [x] Generate Android Gradle dependency report for APK.
- [x] Verify AndroidX Media3/ExoPlayer notices.
- [x] Verify Tabler Icons notice and remove vendored full icon set from the candidate.
- [x] Document PostgreSQL, Valkey, NGINX and optional wg-easy as pulled third-party services.
- [x] Document FFmpeg as source/compose dependency for the first public release.

## Gate 5 - Suspicious Code Blocks

Goal: reduce provenance and maintenance risk before public release.

- [x] Decide whether `frontend/source/src/App.jsx` is obsolete. Preferred action: remove from candidate if `srcnew` is the actual app.
- [x] Add backend tests for HTTP Range responses.
- [x] Add backend tests for TV-series filename inference.
- [x] Add backend tests for subtitle parsing metadata.
- [x] Add backend tests or documented QA for full subtitle extraction, poster frame generation and waveform generation.
- [x] Add short provenance notes for custom visualizer/screensaver implementations.
- [x] Review `WaveSurferTimeline.jsx` and `useAudioPlayer.js` for copied-example risk and add notes/tests where practical.
- [x] Run similarity scanner before public release.

## Gate 6 - Security And Secrets

Goal: ensure the release candidate contains no local/private material.

- [x] Remove hardcoded personal IPs, personal URLs and maintainer-specific first-boot defaults.
- [x] Verify Android TV connection setup starts generic and configurable.
- [x] Ensure no signing keys, `.env`, `local.properties`, passwords, tokens, cookies or DB dumps are tracked.
- [x] Replace development fallback secrets in production paths with fail-fast behavior.
- [x] Add `gitleaks` and `trufflehog` hooks to `scripts/release-audit.sh`.
- [x] Run `gitleaks` and `trufflehog` with containerized tools before public push.

## Gate 7 - Runtime Packaging

Goal: make a clean first-run experience on a normal PC.

- [x] Keep compose volumes empty and host-mounted:
  - `trive-In`;
  - `trive-Up`;
  - `trive-Out`;
  - dump/cache/runtime data.
- [x] Provide `scripts/pre-compose-up.sh` for `.env`, secrets and folder checks.
- [x] Confirm `docker compose up` works locally from a clean checkout.
- [x] Confirm Git checkouts and release archives include prebuilt web assets before the release proxy serves them.
- [x] Keep optional VPN profile disabled by default.
- [x] Document LAN/localhost setup and Android TV connection setup.

## Gate 8 - Scanner And CI

Goal: make final release checks repeatable.

- [x] Add or document `reuse lint`.
- [x] Add or document `scancode`.
- [x] Add or document `jscpd`.
- [x] Add or document npm license extraction.
- [x] Add or document Python license extraction.
- [x] Add or document Gradle dependency/license report.
- [x] Add current frontend `npm audit` report.
- [x] Resolve or explicitly accept current moderate frontend `npm audit` findings.
- [x] Store generated audit output under `docs/release-audit/<version>/` or attach it to the release.

## Gate 9 - Final Release Candidate

Goal: tag only when public release risk is understood and bounded.

- [x] `git status` clean.
- [x] `LICENSE`, `NOTICE.md`, `THIRD_PARTY_NOTICES/`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md` present.
- [x] Generated web build committed for no-Node installs; APK outputs remain out of Git.
- [x] No user media, avatars, scan dumps or runtime volumes committed.
- [x] Frontend source builds reproducibly.
- [x] APK builds reproducibly.
- [x] Release artifacts generated and checksummed.
- [x] In-app Credits reflects `NOTICE.md`.
- [x] `docs/GPL_READINESS_REVIEW.md` updated from "proceed after corrections" to the current state.
- [x] Tag release and attach artifacts.

Current APK note: `scripts/build-android-tv-apk.sh` successfully builds an unsigned release APK inside the pinned Android SDK container. Public release APKs must use the same path with external signing variables set; debug or unsigned APKs are not public release artifacts.

First release note: `v0.1.0-techdemo.1` was the starting public tech demo tag. Current release attachments are generated after `scripts/prepare-release-version.sh` with `TRIVER_APK_PATH=apk/package/trueriver-tv-<version>.apk ./scripts/build-release-artifacts.sh` and uploaded to the Gitea release page.

## Current Open Questions

None at this stage.
