# trueRiver Privacy Notes

trueRiver is designed as a self-hosted, local-first media server. Your media
files, database, generated metadata and runtime configuration stay on the host
where you install trueRiver unless you deliberately expose that host or enable
an external integration.

## Local Media And Uploads

- Media imported into `trive-In`, `trive-Up`, `trive-Out` and `trive-dump`
  stays on the storage paths configured by the installer or `.env` file.
- Browser uploads are scanned by the local ClamAV service before they are moved
  into `trive-In`.
- trueRiver does not include a cloud account, hosted analytics service or remote
  telemetry endpoint.

## Remote Metadata

Remote metadata lookup is manual by default. Opening Settings or changing the
lookup mode does not contact providers. If you configure provider credentials
and start a manual lookup from a content action, or explicitly configure
automation, trueRiver may send search terms such as titles, artist names, album
names, years, external IDs or filenames to the selected provider.

Current optional providers:

- TMDb for movie and TV metadata when a TMDb token or API key is configured.
- MusicBrainz for music metadata. A contact value in
  `TRIVER_MUSICBRAINZ_CONTACT` is recommended for a compliant User-Agent.
- OMDb and TheTVDB keys are reserved for optional provider support and are not
  used unless the corresponding provider code is enabled.

Media files themselves are not uploaded to these metadata providers by the
current implementation.

## Operator Responsibility

The person running a trueRiver server controls network exposure, user accounts,
reverse proxies, VPN settings, storage mounts and provider API keys. Review your
local `.env` file before exposing a server outside a trusted network.
