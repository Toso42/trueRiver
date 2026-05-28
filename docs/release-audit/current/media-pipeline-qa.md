# Media pipeline QA checklist

Date: 2026-05-20

Scope: documented QA plan for endpoints that need real media fixtures:

- subtitle extraction and conversion;
- video poster frame generation and selection;
- waveform generation.

The backend unit tests currently cover helper-level behavior for subtitle filename parsing, poster timecode parsing and HTTP Range responses. Full media-pipeline tests were not executed in this pass because the release candidate must not include user media fixtures and this environment does not yet contain a sanitized public fixture set.

## Required fixtures before public release

Use only redistributable synthetic or public-domain media:

- one short MP4/H.264 video with AAC audio and no subtitles;
- one short MKV or MP4 with embedded subtitle stream;
- one matching external `.srt` subtitle file;
- one matching external `.vtt` subtitle file;
- one short MP3 or WAV audio file for waveform generation.

## Subtitle extraction QA

1. Scan/import the embedded-subtitle video and external subtitle files.
2. Confirm API payload exposes `subtitle_streams` with stable selectors.
3. Request `/api/tracks/<id>/subtitles/<selector>/`.
4. Confirm response is `text/vtt`.
5. Confirm cached subtitle is stored under `/tmp/triver-subtitles`.
6. Confirm invalid selector returns a controlled 400/404 response.
7. Confirm subtitle options are visible in the web video player and Android TV player.

## Video poster QA

1. Request `/api/tracks/<id>/poster/`.
2. Confirm a JPEG response is generated from the default timestamp.
3. Request `/api/tracks/<id>/poster/frame/?seconds=1`.
4. Confirm timecode validation rejects negative, non-numeric or out-of-range values.
5. Request `/api/tracks/<id>/poster/candidates/?count=6`.
6. Confirm candidate URLs return JPEG frames.
7. POST `/api/tracks/<id>/poster/select` with an approved timestamp.
8. Confirm selected poster is reused by webapp and Android TV catalog views.
9. For a TV series, POST `/api/videos/series-poster` and confirm the series-level poster is returned by `/api/videos/series-poster/?series_key=<key>`.

## Waveform QA

1. Request `/api/tracks/<id>/waveform/` for a short audio file.
2. Confirm response includes levels for the supported resolutions.
3. Request a specific level with `?level=<resolution>`.
4. Confirm unsupported level returns a controlled 400 response.
5. Confirm cache reuse on a second request.
6. Confirm the web audio timeline renders the returned waveform.

## Release status

Status: documented, not fully executed.

Public release blocker: create a sanitized fixture pack and run the checklist on a clean checkout.
