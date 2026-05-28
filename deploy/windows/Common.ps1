$ErrorActionPreference = "Stop"

function Get-TriverRepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Get-TriverInstallPaths {
  param(
    [string]$InstallRoot
  )

  $resolvedRoot = [System.IO.Path]::GetFullPath($InstallRoot)
  return @{
    Root = $resolvedRoot
    Local = (Join-Path $resolvedRoot "triver-local")
    Data = (Join-Path $resolvedRoot "data")
  }
}

function ConvertTo-TriverComposePath {
  param(
    [string]$Path
  )

  return ([System.IO.Path]::GetFullPath($Path)).Replace("\", "/")
}

function Assert-TriverCommand {
  param(
    [string]$Name,
    [string]$InstallHint
  )

  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "$Name is required. $InstallHint"
  }
}

function Assert-TriverDocker {
  Assert-TriverCommand "docker" "Install Docker Desktop for Windows with the WSL 2 backend enabled."
  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is required. Update Docker Desktop and make sure 'docker compose' works in PowerShell."
  }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running or the current user cannot access Docker."
  }
}

function Get-TriverEnvValue {
  param(
    [string]$EnvFile,
    [string]$Key,
    [string]$Default = ""
  )

  if (-not (Test-Path $EnvFile)) {
    return $Default
  }

  $escapedKey = [regex]::Escape($Key)
  $match = Get-Content $EnvFile | Where-Object { $_ -match "^$escapedKey=" } | Select-Object -Last 1
  if (-not $match) {
    return $Default
  }
  return ($match -split "=", 2)[1]
}

function Test-TriverEnvKey {
  param(
    [string]$EnvFile,
    [string]$Key
  )

  if (-not (Test-Path $EnvFile)) {
    return $false
  }

  $escapedKey = [regex]::Escape($Key)
  $match = Get-Content $EnvFile | Where-Object { $_ -match "^$escapedKey=" } | Select-Object -First 1
  return [bool]$match
}

function Set-TriverEnvValue {
  param(
    [string]$EnvFile,
    [string]$Key,
    [string]$Value
  )

  $line = "$Key=$Value"
  $lines = @()
  if (Test-Path $EnvFile) {
    $lines = @(Get-Content $EnvFile)
  }

  $escapedKey = [regex]::Escape($Key)
  $found = $false
  for ($index = 0; $index -lt $lines.Count; $index += 1) {
    if ($lines[$index] -match "^$escapedKey=") {
      $lines[$index] = $line
      $found = $true
    }
  }

  if (-not $found) {
    $lines += $line
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllLines($EnvFile, [string[]]$lines, $utf8NoBom)
}

function New-TriverSecret {
  param(
    [int]$Length
  )

  $alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_@%+=:,.^-"
  $bytes = New-Object byte[] $Length
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($bytes)
  } finally {
    $rng.Dispose()
  }

  $chars = New-Object char[] $Length
  for ($index = 0; $index -lt $Length; $index += 1) {
    $chars[$index] = $alphabet[$bytes[$index] % $alphabet.Length]
  }
  return -join $chars
}

function Get-TriverComposeProjectName {
  param(
    [string]$EnvFile
  )

  $project = Get-TriverEnvValue $EnvFile "TRIVER_COMPOSE_PROJECT_NAME" ""
  if (-not $project) {
    $project = Get-TriverEnvValue $EnvFile "COMPOSE_PROJECT_NAME" "triver"
  }
  return $project
}

function Get-TriverComposeArgs {
  param(
    [string]$InstallRoot
  )

  $repoRoot = Get-TriverRepoRoot
  $paths = Get-TriverInstallPaths $InstallRoot
  $envFile = Join-Path $paths.Local ".env"
  $overrideFile = Join-Path $paths.Local "docker-compose.local.yml"
  $project = Get-TriverComposeProjectName $envFile
  $extraCompose = $env:TRIVER_COMPOSE_EXTRA
  if (-not $extraCompose) {
    $extraCompose = Get-TriverEnvValue $envFile "TRIVER_COMPOSE_EXTRA" ""
  }

  $env:TRIVER_SERVICE_ENV_FILE = $envFile
  $env:TRIVER_LOCAL_DIR = $paths.Local

  $args = @("--env-file", $envFile, "-p", $project, "-f", (Join-Path $repoRoot "docker-compose.yml"))
  if (Test-Path $overrideFile) {
    $args += @("-f", $overrideFile)
  }
  if ($extraCompose) {
    foreach ($file in ($extraCompose -split ";")) {
      if ($file -and (Test-Path $file)) {
        $args += @("-f", $file)
      }
    }
  }
  return $args
}
