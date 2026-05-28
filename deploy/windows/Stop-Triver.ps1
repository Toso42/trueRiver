param(
  [string]$InstallRoot = (Join-Path $env:USERPROFILE "trueRiver"),
  [switch]$RemoveContainers
)

. "$PSScriptRoot\Common.ps1"

$paths = Get-TriverInstallPaths $InstallRoot
$repoRoot = Get-TriverRepoRoot
$composeArgs = Get-TriverComposeArgs $paths.Root

Assert-TriverDocker

Push-Location $repoRoot
try {
  if ($RemoveContainers) {
    & docker compose @composeArgs down
  } else {
    & docker compose @composeArgs stop
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to stop trueRiver."
  }
} finally {
  Pop-Location
}
