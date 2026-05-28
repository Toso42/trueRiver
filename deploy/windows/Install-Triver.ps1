param(
  [string]$InstallRoot = (Join-Path $env:USERPROFILE "trueRiver"),
  [int]$Port = 3080,
  [switch]$SkipStart,
  [switch]$Open
)

. "$PSScriptRoot\Common.ps1"

$repoRoot = Get-TriverRepoRoot
$paths = Get-TriverInstallPaths $InstallRoot
$localDir = $paths.Local
$dataDir = $paths.Data
$envFile = Join-Path $localDir ".env"
$composeOverride = Join-Path $localDir "docker-compose.local.yml"
$frontendBuild = Join-Path $repoRoot "frontend\package\build\index.html"

if (-not (Test-Path $frontendBuild)) {
  throw "The prebuilt web frontend is missing at frontend/package/build/index.html. Use a release or Git checkout that includes the built web app."
}

Assert-TriverDocker

New-Item -ItemType Directory -Force -Path $paths.Root, $localDir, $dataDir | Out-Null

if (-not (Test-Path $envFile)) {
  Copy-Item (Join-Path $repoRoot "deploy\examples\local.env.example") $envFile
}
if (-not (Test-Path $composeOverride)) {
  Copy-Item (Join-Path $repoRoot "deploy\examples\docker-compose.local.yml") $composeOverride
}

$secret = Get-TriverEnvValue $envFile "DJANGO_SECRET_KEY" ""
if (-not $secret -or $secret -eq "change-me-before-use") {
  Set-TriverEnvValue $envFile "DJANGO_SECRET_KEY" (New-TriverSecret 64)
}

$dbPassword = Get-TriverEnvValue $envFile "POSTGRES_PASSWORD" ""
if (-not $dbPassword -or $dbPassword -eq "change-me-before-use") {
  Set-TriverEnvValue $envFile "POSTGRES_PASSWORD" (New-TriverSecret 32)
}

Set-TriverEnvValue $envFile "COMPOSE_PROJECT_NAME" "triver"
Set-TriverEnvValue $envFile "DJANGO_ALLOWED_HOSTS" "localhost,127.0.0.1,trueriver.local"
Set-TriverEnvValue $envFile "DJANGO_CSRF_TRUSTED_ORIGINS" "http://localhost:$Port,http://127.0.0.1:$Port,http://localhost,http://127.0.0.1"
Set-TriverEnvValue $envFile "VITE_TRIVER_PUBLIC_URL" "http://localhost:$Port"
Set-TriverEnvValue $envFile "VITE_TRIVER_HTTP_ENDPOINT" "localhost:$Port"
Set-TriverEnvValue $envFile "TRIVER_PROXY_BIND" "127.0.0.1"
Set-TriverEnvValue $envFile "TRIVER_PROXY_HTTP_PORT" "$Port"

$optionalProviderVars = @(
  "TRIVER_TMDB_ACCESS_TOKEN",
  "TRIVER_TMDB_API_KEY",
  "TRIVER_OMDB_API_KEY",
  "TRIVER_TVDB_API_KEY",
  "TRIVER_MUSICBRAINZ_CONTACT",
  "TRIVER_CLASSIC_IMPORT_SOURCES",
  "TRIVER_COMPOSE_EXTRA"
)

foreach ($key in $optionalProviderVars) {
  if (-not (Test-TriverEnvKey $envFile $key)) {
    Set-TriverEnvValue $envFile $key ""
  }
}

$hostPaths = @{
  TRIVER_POSTGRES_HOST_PATH = "postgres"
  TRIVER_VALKEY_HOST_PATH = "valkey"
  TRIVER_CLAMAV_HOST_PATH = "clamav"
  TRIVER_WIREGUARD_HOST_PATH = "wireguard"
  TRIVER_STORAGE_HOST_PATH = "storage"
}

foreach ($key in $hostPaths.Keys) {
  $folder = Join-Path $dataDir $hostPaths[$key]
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  Set-TriverEnvValue $envFile $key (ConvertTo-TriverComposePath $folder)
}

$storageDir = Join-Path $dataDir "storage"
foreach ($leaf in @("trive-In", "trive-Up", "trive-Out", "trive-dump")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $storageDir $leaf) | Out-Null
}
Set-TriverEnvValue $envFile "TRIVER_ALLOW_CROSS_DEVICE_MOVES" "false"

Write-Host "trueRiver Windows config is ready:"
Write-Host "  $localDir"
Write-Host "Media import folder:"
Write-Host "  $(Join-Path $storageDir 'trive-In')"

if (-not $SkipStart) {
  & "$PSScriptRoot\Start-Triver.ps1" -InstallRoot $paths.Root -Open:$Open
} else {
  Write-Host "Start later with:"
  Write-Host "  .\deploy\windows\Start-Triver.ps1 -InstallRoot `"$($paths.Root)`""
}
