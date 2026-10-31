# ============================================================
# install_ollama.ps1 — Instala Ollama en Windows si no está
# presente. Compatible con entornos Pinokio (conda base).
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host "=== Verificando instalacion de Ollama ===" -ForegroundColor Cyan

# Verificar si Ollama ya está instalado
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue

if ($ollamaPath) {
    Write-Host "OK: Ollama ya esta instalado en: $($ollamaPath.Source)" -ForegroundColor Green
    ollama --version
    exit 0
}

# Buscar en rutas comunes de instalación
$commonPaths = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:ProgramFiles\Ollama\ollama.exe",
    "C:\Ollama\ollama.exe"
)

foreach ($p in $commonPaths) {
    if (Test-Path $p) {
        Write-Host "OK: Ollama encontrado en: $p" -ForegroundColor Green
        & $p --version
        # Agregar al PATH de la sesión actual
        $dir = Split-Path $p
        $env:PATH = "$dir;$env:PATH"
        exit 0
    }
}

# Ollama no está instalado — descargarlo e instalarlo silenciosamente
Write-Host "Ollama no encontrado. Descargando instalador..." -ForegroundColor Yellow

$installerUrl = "https://ollama.com/download/OllamaSetup.exe"
$installerPath = "$env:TEMP\OllamaSetup.exe"

try {
    Write-Host "Descargando desde: $installerUrl"
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    Write-Host "Descarga completada. Instalando silenciosamente..."
    Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait
    Write-Host "OK: Ollama instalado correctamente." -ForegroundColor Green
} catch {
    Write-Host "ERROR: No se pudo descargar o instalar Ollama: $_" -ForegroundColor Red
    Write-Host "Por favor, instala Ollama manualmente desde https://ollama.com/download" -ForegroundColor Yellow
    exit 1
} finally {
    if (Test-Path $installerPath) { Remove-Item $installerPath -Force }
}

# Verificar instalación
Start-Sleep -Seconds 3
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaPath) {
    Write-Host "OK: Ollama instalado y disponible." -ForegroundColor Green
} else {
    Write-Host "AVISO: Ollama instalado pero no disponible en PATH todavia." -ForegroundColor Yellow
    Write-Host "Es posible que necesites reiniciar Pinokio para que tome efecto." -ForegroundColor Yellow
}
