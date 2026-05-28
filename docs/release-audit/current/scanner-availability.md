# Scanner Availability

Generated: 2026-05-20T08:00:33Z

| Tool | Status |
| --- | --- |
| `reuse` | missing |
| `scancode` | missing |
| `jscpd` | missing |
| `gitleaks` | missing |
| `trufflehog` | missing |
| `npm` | missing |
| `python3` | available: `/usr/bin/python3` |
| `gradle` | missing |

Containerized scanner pass:

- `ghcr.io/gitleaks/gitleaks:latest`: available, ran as `v8.30.1`.
- `ghcr.io/trufflesecurity/trufflehog:latest`: available, ran as `3.95.3`.
- `jscpd@4.2.3`: available through `node:20-alpine` and `npx`.
- `scancode-toolkit==32.5.0`: available through `python:3.12-slim`
  after installing `libgomp1`.

See `docs/release-audit/current/scanner-runs.md`.
