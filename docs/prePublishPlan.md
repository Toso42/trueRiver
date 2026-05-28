Agisci come revisore di compliance open source, copyright e rischio di contaminazione del codice prima della pubblicazione della repository su GitHub sotto licenza GPL.

Obiettivo:
Valutare questa repository e produrre un report pratico sui rischi che potrebbero impedire o rendere rischiosa la pubblicazione open source GPL.

Contesto:
- Il progetto è stato sviluppato con assistenza di strumenti AI.
- Voglio pubblicarlo su GitHub con licenza GPL, preferibilmente GPL-3.0-or-later.
- Non devi modificare il codice, salvo propormi patch separate e motivate.
- Non devi fare assunzioni ottimistiche: segnala incertezze, file sospetti e punti che richiedono verifica manuale.

Analizza l’intera repository, inclusi:
- codice sorgente;
- file di configurazione;
- lockfile e manifest delle dipendenze;
- script;
- test;
- documentazione;
- asset;
- file generati;
- vendor directory;
- submodule;
- snippet copiati;
- esempi presi da template;
- file minificati o compressi;
- binari o artefatti inclusi.

Verifica in particolare:

1. Licenza del progetto
- Controlla se esiste un file LICENSE.
- Controlla se la licenza dichiarata è coerente tra README, package manifest, pyproject, Cargo.toml, go.mod, composer.json, gemspec, setup.py, ecc.
- Se manca una licenza, suggerisci GPL-3.0-or-later e i file minimi da aggiungere.
- Se ci sono indicazioni discordanti, elencale.

2. Compatibilità GPL
- Identifica tutte le dipendenze dichiarate.
- Per ciascuna dipendenza, segnala la licenza se presente nei manifest o nei lockfile.
- Classifica le dipendenze in:
  - presumibilmente compatibili con GPL;
  - da verificare;
  - potenzialmente incompatibili;
  - chiaramente problematiche.
- Presta particolare attenzione a licenze come:
  - AGPL;
  - SSPL;
  - BUSL;
  - Commons Clause;
  - PolyForm;
  - Elastic License;
  - licenze non-commercial;
  - licenze source-available;
  - licenze proprietarie;
  - licenze sconosciute;
  - codice senza licenza.

3. Copyright e intestazioni
- Cerca copyright header appartenenti a terzi.
- Cerca riferimenti a repository, autori, aziende, tutorial, blog post, StackOverflow, GitHub Gist o altri sorgenti esterni.
- Cerca stringhe come:
  - “Copyright”
  - “All rights reserved”
  - “Licensed under”
  - “MIT License”
  - “Apache License”
  - “BSD”
  - “GPL”
  - “AGPL”
  - “source available”
  - “do not distribute”
  - “generated from”
  - “based on”
  - “adapted from”
  - “copied from”
  - “StackOverflow”
  - “gist.github”
  - “github.com”
  - “npmjs.com”
  - “pypi.org”
  - “TODO license”
- Per ogni occorrenza sospetta, indica file, riga e motivo del sospetto.

4. Rischio di codice copiato o troppo specifico
- Individua blocchi lunghi, molto specifici o non idiomatici che potrebbero essere stati copiati da codice pubblico.
- Segnala algoritmi, utility, parser, regex complesse, polyfill, implementazioni crittografiche, funzioni di hashing, wrapper API, client SDK, componenti UI complessi o file che sembrano derivati da template.
- Non dire che sono copiati se non puoi provarlo: classificali come “richiede verifica manuale”.
- Per ogni blocco sospetto, spiega perché è sospetto.

5. Codice vendored, generato o di terze parti
- Cerca directory come:
  - vendor/
  - third_party/
  - external/
  - deps/
  - dist/
  - build/
  - generated/
  - public/vendor/
  - static/vendor/
  - node_modules/
- Distingui tra:
  - codice sorgente originale del progetto;
  - codice generato;
  - codice vendored;
  - artefatti di build;
  - asset di terze parti.
- Segnala file che sarebbe meglio rimuovere dal repository prima del push.

6. Asset e contenuti non-code
- Controlla immagini, font, icone, audio, video, dataset, modelli ML, fixture e documentazione.
- Segnala asset senza provenienza o licenza chiara.
- Presta particolare attenzione ai font, alle icone e ai dataset.

7. Sicurezza e segreti
- Cerca possibili segreti prima del push:
  - API key;
  - token;
  - password;
  - private key;
  - .env;
  - credential file;
  - cookie;
  - session token;
  - OAuth secret;
  - certificati;
  - database dump.
- Non stampare il valore completo dei segreti trovati. Mostra solo file, riga, tipo di segreto e una versione mascherata.

8. File da aggiungere prima della pubblicazione
Suggerisci, se mancanti:
- LICENSE;
- README con licenza chiara;
- NOTICE, se necessario;
- COPYRIGHT o AUTHORS, se utile;
- THIRD_PARTY_NOTICES, se utile;
- SBOM, se appropriato;
- .gitignore;
- SECURITY.md;
- CONTRIBUTING.md;
- SPDX headers nei file principali.

9. Comandi consigliati
Se l’ambiente lo permette, suggerisci o esegui comandi come:
- scancode;
- reuse lint;
- licensee;
- license-checker;
- pip-licenses;
- cargo-deny;
- go-licenses;
- npm license checker;
- jscpd;
- gitleaks;
- trufflehog.

Non installare strumenti globali senza chiedere. Se non sono disponibili, indica i comandi da eseguire localmente.

10. Output richiesto
Produci un report finale in Markdown con questa struttura:

# GPL Readiness Review

## Executive summary
- Stato complessivo:
  - OK per pubblicazione
  - OK con correzioni minori
  - Pubblicazione sconsigliata finché non si risolvono i problemi
  - Impossibile determinare
- Motivo principale della valutazione.

## Blocking issues
Elenca problemi che bloccano o sconsigliano fortemente il push pubblico.

Per ogni problema:
- file;
- riga o area;
- descrizione;
- rischio;
- correzione consigliata.

## Non-blocking issues
Elenca problemi minori o miglioramenti consigliati.

## Files requiring manual review
Tabella con:
- file;
- motivo;
- severità;
- cosa verificare.

## Dependency license table
Tabella con:
- dipendenza;
- versione;
- licenza rilevata;
- sorgente dell’informazione;
- compatibilità GPL presunta;
- note.

## Suspicious code blocks
Tabella con:
- file;
- righe;
- motivo del sospetto;
- severità;
- azione consigliata.

## Third-party assets
Tabella con:
- file;
- tipo di asset;
- licenza/provenienza rilevata;
- rischio;
- azione consigliata.

## Secrets check
- Risultato della scansione.
- Eventuali segreti mascherati.
- Azioni consigliate.

## Recommended repository changes
Elenco concreto delle modifiche da fare prima del push.

## Suggested LICENSE/NOTICE content
Se mancano LICENSE o NOTICE, proponi bozze adatte a GPL-3.0-or-later.

## Final recommendation
Dai una raccomandazione chiara:
- “puoi procedere”;
- “procedi dopo queste correzioni”;
- “non procedere ancora”.

Regole importanti:
- Non inventare licenze o compatibilità se non sono verificabili dai file presenti.
- Non rimuovere codice automaticamente.
- Non sostituire una revisione legale professionale.
- Se trovi incertezza, dillo chiaramente.
- Distingui sempre tra fatto verificato, inferenza e sospetto.




### dopo tutto questo, ultimo step


Ora prepara una patch minimale per rendere la repository pronta alla pubblicazione GPL-3.0-or-later, senza modificare la logica applicativa.

Puoi solo:
- aggiungere LICENSE;
- aggiornare README;
- aggiungere THIRD_PARTY_NOTICES se necessario;
- aggiungere .gitignore;
- aggiungere SECURITY.md;
- aggiungere SPDX headers dove opportuno;
- rimuovere dal tracking solo artefatti chiaramente generati, cache, build output, lock temporanei o segreti fittizi.

Prima di modificare qualunque file, mostrami il piano della patch.