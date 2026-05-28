# Provenance notes

Date: 2026-05-20

Scope: local source review of visualizer, screensaver and audio-player code called out by `docs/GPL_READINESS_REVIEW.md`.

This is a project-maintainer provenance note, not a legal opinion and not a similarity scan. The environment did not have `jscpd`, `scancode`, `reuse`, `gitleaks` or `trufflehog` installed at the time of this pass.

## Web audio visualizer

Files:

- `frontend/source/srcnew/features/audio/player/AudioVisualizerOverlay.jsx`

Findings:

- The primary visualizer path uses the npm packages `butterchurn` and `butterchurn-presets`.
- The package licenses must remain covered in `NOTICE.md` and release notices.
- The fallback renderer is local trueRiver Canvas code: radial gradient background, sinusoidal ring paths and level bars drawn from `spectrumLevels`.
- The fallback renderer does not include copied Milkdrop preset text or external image assets.
- The fallback renderer should stay small and readable so future changes remain reviewable.

## Android TV visualizer and screensaver

Files:

- `apk/source/app/src/main/java/com/trueriver/tvshell/AudioVisualizerView.java`
- `apk/source/app/src/main/java/com/trueriver/tvshell/TvScreensaverView.java`

Findings:

- Both classes are local trueRiver Canvas implementations using Android `Paint`, gradients, trigonometric motion and procedural bars/rings/cells.
- No third-party assets, preset files or copied source headers are present in these classes.
- A local grep pass found no explicit provenance markers such as `StackOverflow`, `gist`, `copied`, `adapted`, `based on` or third-party copyright headers in these files.
- Because visualizer code is a common tutorial/demo category, run a similarity scanner before public release.

## WaveSurfer timeline

Files:

- `frontend/source/srcnew/features/audio/player/WaveSurferTimeline.jsx`

Findings:

- This file is a trueRiver wrapper around `wavesurfer.js`, the Regions plugin and app-specific region/ruler/scrollbar controls.
- It probes WaveSurfer-rendered DOM/shadow DOM for styling and scrollbar behavior; that is an API-fragility risk, not a license risk by itself.
- A local grep pass found no copied-example markers or third-party headers.
- Before public release, keep `wavesurfer.js` license notices and run UI QA for zoom, region creation, region editing and horizontal scrolling.

## Audio player hook

Files:

- `frontend/source/srcnew/features/audio/player/hooks/useAudioPlayer.js`

Findings:

- This hook is local trueRiver player orchestration around browser audio, queue state, waveform loading and optional `soundtouchjs` pitch/time-stretch.
- `soundtouchjs@0.3.0` is LGPL-2.1 according to `package-lock.json`; the project currently treats it as an unmodified dependency.
- LGPL handling is tracked separately in `THIRD_PARTY_NOTICES/soundtouchjs.md` and `docs/build/frontend.md`.
- A local grep pass found no copied-example markers or third-party headers.
- Before public release, run manual QA for speed+pitch combinations and confirm the distributed frontend build can be rebuilt with a replacement `soundtouchjs` package.

## Local grep check

Command shape used:

```sh
grep -RInE "StackOverflow|stackoverflow|gist|copied|adapted|based on|source:|copyright|Copyright" \
  frontend/source/srcnew/features/audio/player \
  apk/source/app/src/main/java/com/trueriver/tvshell/AudioVisualizerView.java \
  apk/source/app/src/main/java/com/trueriver/tvshell/TvScreensaverView.java
```

Only one app comment was found, describing a WaveSurfer timing behavior. No third-party provenance markers were found.
