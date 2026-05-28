# Scanner runs

Date: 2026-05-23

## gitleaks

Command:

```bash
docker run --rm \
  -v /home/dockers/triver-publish-candidate:/repo \
  ghcr.io/gitleaks/gitleaks:latest \
  detect --source=/repo --redact \
  --report-format json \
  --report-path=/repo/docs/release-audit/current/gitleaks.json \
  --exit-code 1
```

Version: `gitleaks v8.30.1`.

Result:

```text
10 commits scanned.
scanned ~12624804 bytes (12.62 MB) in 42.4s
no leaks found
```

Raw report: `docs/release-audit/current/gitleaks.json`, ignored by Git and
regenerated locally or in CI.

## trufflehog

Command:

```bash
docker run --rm \
  -v /home/dockers/triver-publish-candidate:/repo \
  ghcr.io/trufflesecurity/trufflehog:latest \
  filesystem /repo --json --only-verified \
  > docs/release-audit/current/trufflehog.jsonl
```

Version: `trufflehog 3.95.3`.

Result:

```text
verified_secrets=0
unverified_secrets=0
```

Raw report: `docs/release-audit/current/trufflehog.jsonl`, ignored by Git and
regenerated locally or in CI.

## jscpd

Command:

```bash
docker run --rm \
  -v /tmp/triver-public-provenance-audit:/scan:ro \
  -v /home/dockers/triver-publish-candidate/docs/release-audit/current:/out \
  node:20-alpine \
  sh -lc "cd /scan && npx --yes jscpd@4.2.3 backend frontend/source/srcnew apk/source/app/src/main deploy scripts --reporters json,markdown --output /out/jscpd --ignore '**/node_modules/**,**/frontend/package/build/**,**/package-lock.json' --min-lines 80 --min-tokens 120"
```

Version: `jscpd 4.2.3`.

Result:

```text
Found 0 exact clones with 0(0%) duplicated lines in 132 files.
```

Reports:

- `docs/release-audit/current/jscpd/jscpd-report.md`
- raw JSON is ignored by Git and regenerated locally or in CI

## ScanCode Toolkit

Command:

```bash
docker run --rm \
  -e PIP_DEFAULT_TIMEOUT=180 \
  -e DEBIAN_FRONTEND=noninteractive \
  -v /tmp/triver-public-provenance-audit:/scan:ro \
  -v /home/dockers/triver-publish-candidate/docs/release-audit/current:/out \
  python:3.12-slim \
  sh -lc "apt-get update -qq && apt-get install -y -qq --no-install-recommends libgomp1 >/dev/null && pip install --no-cache-dir -q --root-user-action=ignore scancode-toolkit && scancode --license --copyright --info --classify --summary --processes 2 --json-pp /out/scancode-public-head.json /scan"
```

Version: `ScanCode 32.5.0`.

Result:

```text
375 files scanned
0 scan errors
```

Reports:

- `docs/release-audit/current/code-provenance-audit.md`
- raw JSON is ignored by Git and regenerated locally or in CI
