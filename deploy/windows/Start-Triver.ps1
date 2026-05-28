param(
  [string]$InstallRoot = (Join-Path $env:USERPROFILE "trueRiver"),
  [string]$Ref = "",
  [switch]$Open
)

. "$PSScriptRoot\Common.ps1"

$repoRoot = Get-TriverRepoRoot
$paths = Get-TriverInstallPaths $InstallRoot
$envFile = Join-Path $paths.Local ".env"
$frontendBuild = Join-Path $repoRoot "frontend\package\build\index.html"

Assert-TriverDocker

if (-not (Test-Path $envFile)) {
  & "$PSScriptRoot\Install-Triver.ps1" -InstallRoot $paths.Root -SkipStart
}

if (Test-Path (Join-Path $repoRoot ".git")) {
  $git = Get-Command "git" -ErrorAction SilentlyContinue
  if ($git) {
    Push-Location $repoRoot
    try {
      & git fetch --tags origin
      if ($Ref) {
        & git checkout --force $Ref
      } else {
        & git pull --ff-only
      }
      if ($LASTEXITCODE -ne 0) {
        throw "Git update failed."
      }
    } finally {
      Pop-Location
    }
  }
}

if (-not (Test-Path $frontendBuild)) {
  throw "frontend/package/build/index.html is missing. trueRiver Windows installs expect the prebuilt web frontend to be included."
}

$composeArgs = Get-TriverComposeArgs $paths.Root

Push-Location $repoRoot
try {
  & docker compose @composeArgs rm -sf triver-proxy | Out-Host
  & docker compose @composeArgs up -d --build --remove-orphans
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to start trueRiver."
  }
} finally {
  Pop-Location
}

$port = Get-TriverEnvValue $envFile "TRIVER_PROXY_HTTP_PORT" "3080"
$url = "http://localhost:$port"
Write-Host "trueRiver is starting at $url"
Write-Host "First start can take a few minutes while ClamAV initializes."

if ($Open) {
  Start-Process $url
}
