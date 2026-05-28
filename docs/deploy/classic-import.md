# Classic Import

Classic Import is the read-only indexing flow for media that already lives in
external folders. It does not move files through `trive-In`, `trive-Up` or
`trive-Out`.

Use it when you want to test trueRiver against an existing NAS share, mounted
disk or media folder without copying that library into the TriveImport staging
pipeline.

## Linux / macOS Shell

From the trueRiver checkout:

```bash
TRIVER_LOCAL_DIR=../triver-local ./scripts/configure-classic-import-sources.sh /path/to/media /another/path
TRIVER_LOCAL_DIR=../triver-local ./scripts/deploy-local.sh
```

The script writes:

- `../triver-local/.env`
- `../triver-local/classic-import.local.yml`

Each selected host folder is mounted read-only under `/srv/triver-classic/<key>`
inside the backend, worker and beat containers.

## Windows

After running the normal Windows installer:

```powershell
.\deploy\windows\Configure-ClassicImportSources.ps1 -SourcePath "D:\Media","E:\Archive"
.\deploy\windows\Start-Triver.ps1
```

The script writes the same local `.env` and compose-extra configuration under
`%USERPROFILE%\trueRiver\triver-local`.

## Web App Flow

Open `Trive-IO`, switch from `TriveImport` to `Classic Import`, select one or
more configured folders, then start Classic Indexing.

The `AutoImport` section in the same page can run this flow automatically. The
daemon is disabled by default. Enable it only after choosing whether it should
watch `trive-In`, Classic Import sources, or both; `Check now` runs one manual
low-priority check without waiting for the next poll.

Classic Import creates catalog records that point back to the mounted external
files. If a folder is later removed from the local compose configuration or the
host path disappears, the next Classic Import scan marks those files as missing
rather than deleting the source media.

Configured Classic Import folders also appear in File Explorer as `Classic:`
locations. They can be browsed and used for indexed metadata actions without
copying files into `trive-In`.
