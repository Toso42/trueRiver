# Secrets And Hardcoded Values Scan

Date: 2026-05-23

Commands:

```bash
grep -RInE "(password|passwd|secret|token|api[_-]?key|private[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|csrftoken|sessionid|oauth|client_secret|KNOWN_PRIVATE_VALUE|192\\.168\\.|10\\.|172\\.1[6-9]\\.|172\\.2[0-9]\\.|172\\.3[0-1]\\.|127\\.0\\.0\\.1|localhost)" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=build --exclude='*.map' .

find . -path './.git' -prune -o -type f \
  \( -name '*.env' -o -name '.env.*' -o -name '*.jks' -o -name '*.keystore' -o -name 'local.properties' -o -name '*.pem' -o -name '*.p12' -o -name '*.sqlite' -o -name '*.db' -o -name '*.dump' -o -name '*.apk' \) -print
```

Result:

- No real private key, signing key, APK, database dump, local Android SDK config, or runtime database file was found in the tracked candidate tree.
- `.env.example` is present and intentionally contains placeholders.
- Localhost and RFC1918 values that remain are generic local defaults or optional VPN subnet defaults, not maintainer-specific deployment values.
- Android TV first-boot host default remains blank; port default is `80`; user/password are configured on device.
- Production `DJANGO_SECRET_KEY` now fails fast when missing and `DJANGO_DEBUG=0`.
- The distributable frontend build was scanned for maintainer-specific URLs,
  private LAN addresses and local deployment labels.
- The Git history contains removed frontend build artifacts from older candidate
  commits; publish GitHub from a clean current-tree export or rewritten history,
  not by mirroring this internal history directly.
- A clean `git archive HEAD` export was scanned with Dockerized `gitleaks`
  (`zricethezav/gitleaks:latest`) and reported no leaks.
- The same clean export was scanned with Dockerized `trufflehog`
  (`trufflesecurity/trufflehog:latest`) and reported zero verified and zero
  unverified secrets.

Specialized history scanners remain recommended before a public tag if the
internal Git history is ever rewritten and published:

- `gitleaks`
- `trufflehog`
