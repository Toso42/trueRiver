# GPL Readiness Review

## Executive summary

- Stato complessivo: procedi, ma non pubblicare ancora.
- Motivo principale: la repo candidate e' ora strutturata e privata su Gitea e ha una baseline AGPL completa, DCO e artifact policy, ma prima della pubblicazione pubblica mancano ancora notice/licenze terze parti complete, scanner automatici e verifica build end-to-end.

Questa revisione e' tecnica, non sostituisce una revisione legale professionale.

## Blocking issues

| File/area | Descrizione | Rischio | Correzione consigliata |
|---|---|---|---|
| Third-party notices incompleti | La repo contiene testi licenza comuni e note specifiche iniziali, ma non ancora tutti i copyright notice per frontend/APK release artifacts. | Una release binaria deve includere notice e testi completi delle licenze applicabili. | Completare `THIRD_PARTY_NOTICES/` con notice package-specific e allegarlo agli artefatti di release. |
| Web frontend build | Il bundle web minificato e' tracciato in Git e allegato anche alle release. Include dipendenze MIT, BSD, Apache-2.0 e LGPL-2.1. | Distribuire il bundle richiede testi licenza completi e istruzioni per ricostruire/sostituire LGPL `soundtouchjs`. | Tenere source tag, lockfile, build instructions, notices e checksums allineati alla build distribuita. |
| Android TV APK release artifact | L'APK non e' piu' tracciato in Git, ma sara' allegato alle release. | Binario distribuibile: richiede notice/licenze complete per dipendenze Android/Media3, Gradle wrapper e sorgente corrispondente. | Tenere APK solo come release artifact con notice completa, source tag e processo riproducibile. |
| `backend/requirements.txt` + Dockerfile | Backend usa `mutagen` GPL-2.0-or-later e installa Debian `ffmpeg`. | GPL-compatible ok solo se progetto pubblicato con licenza compatibile e distribuzione binaria rispetta obblighi FFmpeg. | GPL/AGPL compatibile, testi licenza completi, fonte/build notes FFmpeg; oppure sostituire/isolare componenti. |
| `docker-compose.yml` optional VPN | `ghcr.io/wg-easy/wg-easy:15` e' servizio AGPL-3.0-only. | Non blocca se solo pull via compose, ma richiede notice chiara e attenzione se si ridistribuisce/modifica immagine. | Tenere profilo `vpn` opzionale, documentare AGPL e link sorgente wg-easy. |

## Non-blocking issues

| File/area | Descrizione | Azione consigliata |
|---|---|---|
| Web sourcemap release policy | I sourcemap non sono tracciati in Git, ma la release dovra' decidere se allegarli. | Decidere se distribuirli pubblicamente; possono aiutare la source compliance ma aumentano superficie. |
| `frontend/source/package.json` | `"private": true` con `license: AGPL-3.0-or-later`. | Stato accettabile per repo monorepo; mantenere coerente con root `LICENSE`. |

## Files requiring manual review

| File | Motivo | Severita' | Cosa verificare |
|---|---|---:|---|
| `backend/apps/library/tasks.py` | Parsing metadata, hashing file, chiamate `ffprobe`, regex TV-series e catalog sync complesso. | Media-Alta | Verificare provenienza interna delle regex/heuristic parser, aggiungere test su filename reali e documentare che non derivano da snippet esterni. |
| `backend/apps/api/views.py` | Streaming/range requests, HLS, ffmpeg, poster extraction, waveform generation, auth endpoints. | Alta | Verificare sicurezza, licenze FFmpeg, assenza snippet copiati e copertura test per range/subtitle/poster/HLS. |
| `backend/apps/api/serializers.py` | Subtitle probing/parsing, regex file subtitles, ffprobe fallback. | Media | Verificare provenienza parsing, correttezza naming subtitle e robustezza su file esterni non fidati. |
| `frontend/source/srcnew/features/audio/player/hooks/useAudioPlayer.js` | Hook player da 1213 righe, Web Audio, `soundtouchjs`, queue, waveform, pitch/speed. | Alta | Verificare provenance delle parti Web Audio/pitch, obblighi LGPL di `soundtouchjs`, test su speed+pitch. |
| `frontend/source/srcnew/features/audio/player/WaveSurferTimeline.jsx` | Wrapper WaveSurfer/Regions con accesso a shadow DOM, ruler, scrollbar custom e selezione regioni. | Media-Alta | Verificare che sia implementazione interna sopra API WaveSurfer e non copia da esempi; aggiungere note/test UI. |
| `frontend/source/srcnew/features/audio/player/AudioVisualizerOverlay.jsx` | Uso butterchurn/Milkdrop-style visualizer e fallback canvas procedurale. | Media-Alta | Verificare licenze preset, notice complete e provenance del fallback visual. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/NativeHomeActivity.java` | UI Android TV programmatica da 1609 righe con header Netflix-style, carousel, image loading. | Media-Alta | Verificare provenance di layout/loader/carousel e valutare split in classi piu' piccole prima della release. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/NativePlayerActivity.java` | Player Android TV da 906 righe con Media3/ExoPlayer, playlist, subtitle options e overlay. | Media-Alta | Verificare codice derivato da esempi ExoPlayer/Media3, notice Apache-2.0 e gestione subtitle. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/AudioVisualizerView.java` e `TvScreensaverView.java` | Disegno Canvas procedurale/frattale-like. | Media | Confermare origine interna, perche' i visualizer sono blocchi algoritmici facili da copiare da demo pubbliche. |
| `apk/source/gradle/wrapper/gradle-wrapper.jar` | Binario Gradle wrapper. | Media | Verificare checksum/provenienza e policy di pubblicazione. |
| Android TV APK release artifact | Artefatto binario firmato, non tracciato in Git. | Alta | Verificare notice, sorgente corrispondente e processo riproducibile prima di allegarlo alla release. |
| Web frontend release artifact | Artefatto web compilato, non tracciato in Git. | Alta | Verificare notice e source compliance per tutte le librerie bundle prima di allegarlo alla release. |

## Dependency license table

| Dipendenza | Versione | Licenza rilevata | Sorgente | Compatibilita' GPL presunta | Note |
|---|---:|---|---|---|---|
| Django | 5.1.8 | BSD-3-Clause | metadata installato | Compatibile | Backend. |
| psycopg[binary] | 3.2.6 | LGPLv3 | metadata installato | Compatibile con obblighi | Valutare non-binary e note LGPL. |
| djangorestframework | 3.15.2 | BSD | metadata installato | Compatibile | Backend API. |
| django-filter | 25.1 | BSD | metadata installato | Compatibile | Backend filtering. |
| celery[redis] | 5.4.0 | BSD-3-Clause | metadata installato | Compatibile | Worker/beat. |
| gunicorn | 23.0.0 | MIT | metadata installato | Compatibile | Web server Python. |
| mutagen | 1.47.0 | GPL-2.0-or-later | metadata installato | Compatibile solo con GPL-family | Copyleft principale nel backend. |
| python-magic | 0.4.27 | MIT | metadata installato | Compatibile | MIME detection. |
| react | 18.3.1 | MIT | package-lock | Compatibile | Frontend. |
| react-dom | 18.3.1 | MIT | package-lock | Compatibile | Frontend. |
| hls.js | 1.6.16 | Apache-2.0 | package-lock | Compatibile con GPLv3 | Frontend video playback. |
| wavesurfer.js | 7.12.5 | BSD-3-Clause | package-lock | Compatibile | Frontend waveform. |
| butterchurn | 2.6.7 | MIT | package-lock | Compatibile | Visualizer. |
| butterchurn-presets | 2.4.7 | MIT | package-lock | Compatibile | Preset visualizer, notice da verificare. |
| soundtouchjs | 0.3.0 | LGPL-2.1 | package-lock | Compatibile con obblighi LGPL | Bundled nel frontend; serve source/relink path. |
| @vitejs/plugin-react | 6.0.2 | MIT | package-lock | Compatibile | Dev dependency. |
| vite | 8.0.13 | MIT | package-lock | Compatibile | Build tool. |
| AndroidX Media3 | 1.4.1 | Apache-2.0 presunta | Gradle manifest | Compatibile con GPLv3 | Verificare con Gradle dependency report/licence file. |
| PostgreSQL image | 16-alpine | PostgreSQL License presunta | compose image | Compatibile | Pull esterno via Docker. |
| Valkey image | 7.2-alpine | BSD-style presunta | compose image | Compatibile | Preferibile a Redis 7.4+. |
| nginx image | 1.27-alpine | BSD-like nginx | compose image | Compatibile | Pull esterno via Docker. |
| wg-easy image | 15 | AGPL-3.0-only | compose image/docs | Compatibile solo se obblighi rispettati | Profilo opzionale VPN. |

## Point 4 deep pass methodology

Il punto 4 del `docs/prePublishPlan.md` richiede un controllo sui blocchi lunghi, specifici, non idiomatici o algoritmici che potrebbero avere provenienza esterna. Ho eseguito un pass manuale mirato su:

- file sorgente Python, JavaScript/JSX e Java piu' lunghi;
- blocchi con `ffmpeg`, `ffprobe`, HTTP Range, subtitle parsing, hash, Web Audio, WaveSurfer, butterchurn, Media3/ExoPlayer, Canvas drawing;
- stringhe di provenienza esplicita come `copied from`, `adapted from`, `StackOverflow`, `gist.github`, copyright/header di terzi.

Risultato verificato: non ho trovato commenti o header nel sorgente applicativo che dichiarino copia/adattamento da StackOverflow, Gist, tutorial o repository terzi. Questo non prova originalita': senza scanner di similarita' o confronto internet resta una review euristica. Gli scanner specializzati non sono installati nell'ambiente corrente (`jscpd`, `scancode`, `reuse`, `gitleaks`, `trufflehog`).

## Suspicious code blocks

| File | Righe/area | Motivo | Severita' | Azione |
|---|---|---|---:|---|
| `backend/apps/api/views.py` | 1267-1394 | Due implementazioni HTTP byte-range per audio/binario con parsing `Range`, `Content-Range`, 416 e chunk streaming. Blocchi di questo tipo sono spesso presi da recipe/framework examples. | Alta | Verificare provenance, aggiungere test RFC-ish per range validi/suffix/invalidi, oppure sostituire con helper/framework noto e attribuito. |
| `backend/apps/api/views.py` | 1398-1545 | Poster video: token/path cache, timecode parser, selezione frame random/anchor, comando `ffmpeg`. Logica molto specifica e security-sensitive. | Media-Alta | Documentare origine interna, testare sanitizzazione input timecode e path, tenere tutto come liste argomento subprocess. |
| `backend/apps/api/views.py` | 1555-1809 | Estrazione subtitle VTT, strategia codec browser-friendly, cache playback e live ffmpeg streaming. E' una combinazione lunga di esempi FFmpeg/streaming plausibilmente copiabili. | Alta | Review manuale, test su file con subtitle embedded/external, documentazione FFmpeg e hardening timeout/process cleanup. |
| `backend/apps/api/views.py` | 1882-1955 | Generazione HLS VOD con segmenti e playlist. Comandi HLS spesso derivano da esempi online. | Media-Alta | Verificare origine e aggiungere commento/docs con scelta parametri; coprire cache failure. |
| `backend/apps/api/views.py` | 1988-2112 | Generazione waveform: `ffprobe` sample-rate, decode PCM f32le via `ffmpeg`, bucket min/max. Blocco algoritmico/DSP-like. | Media-Alta | Confermare origine interna, testare file grandi e memoria; valutare streaming/chunking. |
| `backend/apps/library/tasks.py` | 548-735 | Split artisti con escape, cleanup release tokens, regex season/episode (`SxxEyy`, `1x02`, italiano/inglese) e inferenza serie. Parser specifico richiesto dal prodotto ma ad alta probabilita' di pattern simili online. | Media-Alta | Documentare come heuristica interna, aggiungere fixture/test con nomi file reali, includere limiti noti. |
| `backend/apps/library/tasks.py` | 884-958 | Wrapper `ffprobe` e normalizzazione metadata video in payload catalogo. | Media | Verificare origine comando e fields; test su stream senza duration/subtitle. |
| `backend/apps/library/tasks.py` | 991-1164 | Hash SHA-256 file/path, risoluzione path legacy, upsert media file e accessory matching. Non sembra copiato, ma e' blocco lungo e critico. | Media | Documentare motivazione migrazione legacy e aggiungere test sui path `triv*`/`trive-*`. |
| `backend/apps/api/serializers.py` | 167-346 | Token subtitle SHA-1, parsing nome subtitle esterno, enumerazione subtitle embedded/external, fallback `ffprobe`. | Media-Alta | Confermare origine interna, testare nomi `movie.it.forced.srt`, `default`, VTT/SRT/ASS, collisioni token improbabili. |
| `frontend/source/src/App.jsx` | removed | Legacy monolith React da 7677 righe, duplicato rispetto al frontend attivo `srcnew`. | Risolto | Rimosso dalla candidate; `index.html` ora punta a `srcnew/main.jsx` e i build script usano `vite.srcnew.*`. |
| `frontend/source/srcnew/features/audio/player/hooks/useAudioPlayer.js` | 29-1213 | Hook audio complesso con `soundtouchjs` `PitchShifter`, Web Audio graph, cache buffer, queue persistence, waveform loading. | Alta | Verificare parti tratte da esempi SoundTouch/Web Audio, rispettare LGPL `soundtouchjs`, testare speed+pitch e fallback. |
| `frontend/source/srcnew/features/audio/player/audioAnalysis.js` | 1-45 | Bande EQ e lettura spectrum da `AnalyserNode`. Blocco piccolo ma DSP-like. | Bassa-Media | Confermare origine interna; se derivato da formule/esempi terzi, aggiungere riferimento o riscrivere. |
| `frontend/source/srcnew/features/audio/player/WaveSurferTimeline.jsx` | 1-480 | Wrapper WaveSurfer/Regions con ruler custom, shadow DOM probing, zoom ancorato e scrollbar pointer custom. | Media-Alta | Verificare se codice e' interno o adattato da esempi WaveSurfer; documentare dipendenza API shadow DOM. |
| `frontend/source/srcnew/features/audio/player/PlayerTimelineVisual.jsx` | 1-190 | Costruzione SVG waveform path min/max e selezione con pointer events. Algoritmico ma relativamente semplice. | Media | Confermare origine interna e aggiungere test/manual QA per selezioni. |
| `frontend/source/srcnew/features/audio/player/AudioVisualizerOverlay.jsx` | 1-260 | Visualizer butterchurn + fallback canvas con ring/bar procedural. Include preset minificati esterni via pacchetto. | Media-Alta | Notice per butterchurn/presets, provenance fallback visual, evitare asset/preset non licenziati. |
| `frontend/source/srcnew/api/client.js` | 1-124 | Wrapper fetch/CSRF/cookie e riscrittura URL. Non e' sospetto per copia, ma e' security-sensitive. | Media | Verificare cookie/CSRF e policy host prima di public demo. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/TvConnectionConfig.java` | 80-144 | Riscrittura URL server, virtual host header e Basic auth Base64. Blocco corto ma security/config-sensitive. | Media | Verificare niente credenziali hardcoded, documentare uso Basic auth e storage locale. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/NativeHomeActivity.java` | 431-626 | Card builder + Netflix-style preview header in Java programmatic UI, focus animation, image loader hook. | Media | Verificare origine interna; se ispirato a UI Netflix va bene come stile, ma non copiare asset/layout proprietari. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/NativePlayerActivity.java` | 230-319 | Setup ExoPlayer/Media3 con custom headers, playlist e subtitle refresh. | Media-Alta | Verificare eventuale derivazione da examples Media3; attribuire dove necessario e includere Apache-2.0 notices. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/AudioVisualizerView.java` | 14-129 | Canvas visualizer procedurale con ring deformati e barre progress. | Media | Confermare origine interna, dato che somiglia a demo visualizer generiche. |
| `apk/source/app/src/main/java/com/trueriver/tvshell/TvScreensaverView.java` | 14-131 | Screensaver/plasma cells/rings procedural. | Media | Confermare origine interna o sostituire con implementazione dichiaratamente nostra. |

## Third-party assets

| File/area | Tipo | Licenza/provenienza rilevata | Rischio | Azione |
|---|---|---|---|---|
| Tabler Icons | Icone UI usate come componenti interni | MIT, notice copiato in `THIRD_PARTY_NOTICES/Tabler-Icons-MIT.txt` | Basso | Il full pack vendored e' stato rimosso; mantenere solo le icone effettivamente implementate/usate e il notice. |
| `frontend/source/public/trueriver-*`, `apk/source/.../trueriver_only_logo.png` | Logo trueRiver | Provenienza interna dichiarata dall'utente | Basso-Medio | Documentare autore/proprietario nel README o AUTHORS. |
| Web frontend release artifact | Build artifact | Derivato da frontend source e dipendenze | Alto | Pubblicare come release artifact con notice completa, source tag e checksums. |
| Android TV APK release artifact | Binary artifact | Derivato da Android source e Gradle deps | Alto | Pubblicare come release artifact con notice completa, source tag e checksums. |
| `apk/source/gradle/wrapper/gradle-wrapper.jar` | Build tool binary | Gradle wrapper | Medio | Verificare checksum/provenienza. |

## Secrets check

Controlli eseguiti:

- grep locale per parole chiave: password, token, secret, API key, private key, cookie, OAuth, IP locali e riferimenti personali.
- verifica file tracciati contro `.env`, `.jks`, `.keystore`, `local.properties`, `.signing`, volumi runtime.

Risultato:

- Nessun segreto reale confermato nei file tracciati.
- `.env.example` contiene placeholder `change-me-before-use`, non segreti reali.
- `backend/triver/settings.py` fallisce quando `DJANGO_SECRET_KEY` manca con `DJANGO_DEBUG=0`; il fallback `triver-dev-secret-change-me` resta solo per sviluppo esplicito.
- `apk/source/upload-to-mibox-ftp.sh` e README usano placeholder per FTP password.
- I token Gitea temporanei generati per creare/pushare la repo sono stati rimossi dal database Gitea dopo il push.

Scanner specializzati non disponibili nell'ambiente corrente: `gitleaks`, `trufflehog`, `scancode`, `reuse`, `licensee`, `jscpd`.

## Recommended repository changes

1. Mantenere `LICENSE`, README e package metadata allineati su `AGPL-3.0-or-later`.
2. Aggiornare `README.md` da "planned license" a licenza effettiva.
3. Aggiungere testi completi licenze terze parti, non solo tabella notice.
4. Mantenere `frontend/package/build/` tracciato per installazioni senza Node/npm; tenere `apk/package/*.apk` fuori dal repository sorgente e pubblicarlo solo come release artifact.
5. Tenere `deploy/volumes/*` vuote con solo `.gitkeep`.
6. Aggiungere `SECURITY.md`, `CONTRIBUTING.md`, `AUTHORS` o `COPYRIGHT`.
7. Documentare build frontend e APK riproducibile.
8. Documentare FFmpeg: immagine sorgente-only, LGPL-only o GPL-compatible con source offer.
9. Eseguire scanner automatici in CI: `gitleaks`, `reuse lint`, `scancode`, npm license checker, pip licenses, jscpd.
10. Mantenere rimosso il full set vendored Tabler Icons e conservare il notice MIT.

## License Status

Decisione corrente:

```text
trueRiver
Copyright (C) 2026 Tommaso Di Leo and trueRiver contributors

License: AGPL-3.0-or-later
```

Il file root `LICENSE` contiene ora il testo verbatim della GNU Affero General Public License v3.0. `COPYRIGHT`, `README.md` e `frontend/source/package.json` sono allineati su questa scelta.

## Final recommendation

Procedi, ma non pubblicare ancora su GitHub finche' non sono chiusi: notice complete, compliance FFmpeg/LGPL per gli artefatti, scanner automatici e build/release artifact riproducibili.
