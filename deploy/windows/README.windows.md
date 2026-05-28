# trueRiver Windows Install

This package runs trueRiver on Windows through Docker Desktop. It uses the
prebuilt web app already included in the checkout or release archive; Node and
npm are not needed for a normal install.

## Requirements

- Windows 10 or Windows 11 with virtualization enabled.
- Docker Desktop for Windows with the WSL 2 backend.
- PowerShell.
- Git only if you want `Start-Triver.ps1` to update a Git checkout before
  starting.

## Install

Open PowerShell in the trueRiver folder and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\deploy\windows\Install-Triver.ps1
```

The script creates persistent config and data under:

```text
%USERPROFILE%\trueRiver
```

It starts the Docker stack and serves the web app at:

```text
http://localhost:3080
```

Put new media files in:

```text
%USERPROFILE%\trueRiver\data\trive-In
```

Browser uploads into `trive-In` are scanned by the bundled ClamAV container
before the files are moved into place. The first start can take a few minutes
while ClamAV downloads and loads its signature database.

To index an existing external folder without copying it into `trive-In`, mount
it as a Classic Import source:

```powershell
.\deploy\windows\Configure-ClassicImportSources.ps1 -SourcePath "D:\Media"
.\deploy\windows\Start-Triver.ps1
```

Then open `Trive-IO`, switch to `Classic Import`, select the folder and start
Classic Indexing.

Remote metadata lookup is manual by default. To use TMDb, OMDb or TheTVDB, add
the provider keys to:

```text
%USERPROFILE%\trueRiver\triver-local\.env
```

Then restart trueRiver and keep Remote Metadata in `Manual` mode unless you
intentionally configure automation. Opening Settings or switching modes does not
contact providers. MusicBrainz works without an API key; setting
`TRIVER_MUSICBRAINZ_CONTACT` is recommended so requests use an identifiable
User-Agent.

## Start And Stop

```powershell
.\deploy\windows\Start-Triver.ps1
.\deploy\windows\Stop-Triver.ps1
```

To stop and remove the containers while keeping data volumes and media folders:

```powershell
.\deploy\windows\Stop-Triver.ps1 -RemoveContainers
```

## Custom Install Folder

```powershell
.\deploy\windows\Install-Triver.ps1 -InstallRoot "D:\trueRiver" -Port 3080
```

## Updating

For a Git checkout:

```powershell
.\deploy\windows\Start-Triver.ps1
```

For a specific tag:

```powershell
.\deploy\windows\Start-Triver.ps1 -Ref v0.1.0-techdemo.5
```

For a downloaded release zip, unpack the new zip over a fresh source folder and
run `Start-Triver.ps1` again while keeping the same `%USERPROFILE%\trueRiver`
install folder.

## Notes

The Windows package is an installer/orchestrator for the Docker stack, not a
native Windows backend. This keeps the same Linux runtime used by public
self-host installs and avoids a separate Postgres, Valkey, ClamAV and nginx
service stack on Windows.

Read `PRIVACY.md`, `DISCLAIMER.md` and `NOTICE.md` before exposing the server or
enabling third-party metadata providers.
