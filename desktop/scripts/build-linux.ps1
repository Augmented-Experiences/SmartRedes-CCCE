# Build SmartCaja Linux installers (AppImage / .deb / .rpm) via Docker.
# Same approach as SmartRedes: Tauri cannot emit those bundles from Windows.
param()
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Desktop = Split-Path -Parent $Here
$Root = Split-Path -Parent $Desktop
$Out = Join-Path $Root "dist\linux"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no está en PATH. Instala Docker Desktop y vuelve a intentar."
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null
Write-Host "==> Building Linux installers in Ubuntu 24.04 (Docker)"
docker pull ubuntu:24.04
docker run --rm --platform linux/amd64 `
  -e DEBIAN_FRONTEND=noninteractive `
  -v "${Root}:/src:ro" `
  -v "${Out}:/out" `
  ubuntu:24.04 `
  bash -lc 'tr -d ''\015'' < /src/desktop/scripts/linux-docker-build.sh > /tmp/linux-docker-build.sh && bash /tmp/linux-docker-build.sh'

Write-Host ""
Write-Host "Linux installers:" -ForegroundColor Green
Get-ChildItem $Out | ForEach-Object { Write-Host "  $($_.FullName)" }
Copy-Item (Join-Path $Out "*") (Join-Path $Root "dist") -Force
Write-Host "Copied to $Root\dist"
