# Code Provenance Audit

Date: 2026-05-23

Scope: clean `git archive HEAD` export of the public source tree at
`7370523 Record clean export secret scanner results`.

This report is an engineering provenance pass. It is not a legal opinion and it
does not prove originality against the entire public internet. It records the
checks run, their results, and the remaining limits before public release.

## Tools Run

### jscpd

Purpose: detect exact copy/paste clones within the source tree.

Command shape:

```bash
docker run --rm \
  -v /tmp/triver-public-provenance-audit:/scan:ro \
  -v docs/release-audit/current:/out \
  node:20-alpine \
  sh -lc "cd /scan && npx --yes jscpd@4.2.3 backend frontend/source/srcnew apk/source/app/src/main deploy scripts --reporters json,markdown --output /out/jscpd --ignore '**/node_modules/**,**/frontend/package/build/**,**/package-lock.json' --min-lines 80 --min-tokens 120"
```

Result:

- `jscpd 4.2.3`
- 132 files analyzed
- 29,193 lines analyzed
- 295,269 tokens analyzed
- 0 exact clones
- 0 duplicated lines
- 0 duplicated tokens

Reports:

- `docs/release-audit/current/jscpd/jscpd-report.md`
- raw JSON is intentionally ignored by Git and regenerated locally or in CI

### ScanCode Toolkit

Purpose: detect license texts, copyright statements, package metadata and
license-like notices in the clean export.

Command shape:

```bash
docker run --rm \
  -v /tmp/triver-public-provenance-audit:/scan:ro \
  -v docs/release-audit/current:/out \
  python:3.12-slim \
  sh -lc "apt-get update -qq && apt-get install -y -qq --no-install-recommends libgomp1 >/dev/null && pip install --no-cache-dir -q scancode-toolkit && scancode --license --copyright --info --classify --summary --processes 2 --json-pp /out/scancode-public-head.json /scan"
```

Result:

- `ScanCode 32.5.0`
- 375 files scanned
- 124 directories scanned
- 9.79 MB scanned
- 0 scan errors
- raw JSON output is intentionally ignored by Git and regenerated locally or in
  CI

Main detections were expected:

- project AGPL license and trueRiver copyright files
- third-party notice and license texts under `THIRD_PARTY_NOTICES/`
- bundled frontend notices for React, hls.js, wavesurfer.js, butterchurn,
  butterchurn-presets, soundtouchjs and Tabler Icons
- LGPL/GPL detections related to documented dependencies and notices

Important notes:

- `proprietary-license` detections occur in documentation discussing
  proprietary license risks and in the bundled hls.js / dash.js CEA-608 notice.
  They are review items, not confirmed proprietary app code.
- The frontend bundle intentionally contains third-party copyright notices from
  dependencies; these must stay aligned with `NOTICE.md` and full license texts.
- ScanCode is a license/copyright scanner, not a plagiarism detector.

### Marker Grep

Purpose: find obvious copied-code provenance markers in application source.

Command shape:

```bash
grep -RInE "StackOverflow|stackoverflow|gist\\.github|copied from|adapted from|based on|from https?://|Copyright \\(c\\)|Copyright \\(C\\)|MIT License|Apache License" \
  backend frontend/source/srcnew apk/source/app/src/main deploy scripts
```

Result:

- no application-source markers indicating copied/adapted snippets were found
- expected third-party attribution records were found in
  `frontend/source/srcnew/features/audio/content/noticeData.js`

### External Exact-String Search

Purpose: spot-check unusual project-specific identifiers against public web
indexes.

Sampled exact searches included:

- `create_video_playback_cache_job`
- `_video_curation_settings_payload`
- `classic_import_sources_payload`
- `TRIVER_FRONTEND_PRIVATE_PATTERN`
- `player-eq-tray-overlay`
- `readSpectrumLevels EQ_BANDS`
- `PlayerTimelineVisual WaveSurferTimeline SpectrumBars`

Result:

- no meaningful external source matches were found for project-specific
  identifiers
- broad audio-player and WaveSurfer styling terms produced unrelated generic
  player examples, not code matches

## Interpretation

The current source tree has no exact internal copy/paste clones at the chosen
threshold and no obvious copied-code markers in application source. ScanCode
found expected license/copyright material from project licensing, notices and
bundled dependencies.

This is enough for a reasonable public tech-demo hygiene pass, provided GitHub
is populated from a clean current-tree export rather than the internal Git
history.

## Remaining Limits

- `jscpd` only compares files given to it. It does not search GitHub or the
  public internet.
- Search-engine exact-string checks are partial and index-dependent.
- ScanCode detects licenses/copyrights/package metadata; it does not prove code
  originality.
- A stronger external-code provenance audit would require a dedicated snippet
  similarity service or a known corpus, for example FossID, Black Duck, FOSSA,
  FOSSology/ORT pipelines, or an internally curated GitHub/code corpus with a
  similarity engine.

## Repeatable Routine

Run the local clone detector:

```bash
./scripts/run-code-provenance-audit.sh
```

Run clone detection plus ScanCode:

```bash
TRIVER_RUN_SCANCODE=1 ./scripts/run-code-provenance-audit.sh
```
