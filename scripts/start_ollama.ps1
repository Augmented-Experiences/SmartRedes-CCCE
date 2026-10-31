# ============================================================
# start_ollama.ps1 — Inicia el servidor Ollama en Windows.
# Compatible con entornos Pinokio (conda base).
# Si Ollama ya está corriendo, no hace nada.
# ============================================================

$ErrorActionPreference = "Continue"

Write-Host "=== Iniciando Ollama ===" -ForegroundColor Cyan

# Función para encontrar el ejecutable de Ollama
function Find-Ollama {
    # 1. Intentar desde PATH
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    # 2. Rutas comunes de instalación en Windows
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe",
        "C:\Ollama\ollama.exe",
        "$env:USERPROFILE\AppData\Local\Programs\Ollama\ollama.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$ollamaExe = Find-Ollama

if (-not $ollamaExe) {
    Write-Host "AVISO: Ollama no encontrado. Continuando sin Ollama..." -ForegroundColor Yellow
    Write-Host "Para usar modelos de texto con Ollama, instala Ollama desde https://ollama.com/download" -ForegroundColor Yellow
    exit 0
}

Write-Host "Ollama encontrado en: $ollamaExe" -ForegroundColor Green

# Verificar si Ollama ya está corriendo
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "OK: Ollama ya esta corriendo en puerto 11434." -ForegroundColor Green
        exit 0
    }
} catch {
    # No está corriendo — continuar para iniciarlo
}

Write-Host "Iniciando servidor Ollama en segundo plano..."

# Iniciar Ollama como proceso en background
$processArgs = @{
    FilePath     = $ollamaExe
    ArgumentList = "serve"
    WindowStyle  = "Hidden"
    PassThru     = $true
}

try {
    $proc = Start-Process @processArgs
    Write-Host "Ollama iniciado con PID: $($proc.Id)" -ForegroundColor Green

    # Esperar hasta 15 segundos a que Ollama esté disponible
    $maxWait = 15
    $waited  = 0
    $ready   = $false

    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 1
        $waited++
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($r.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch { }
        Write-Host "  Esperando Ollama... ($waited/$maxWait s)"
    }

    if ($ready) {
        Write-Host "OK: Ollama listo y respondiendo." -ForegroundColor Green
    } else {
        Write-Host "AVISO: Ollama iniciado pero aun no responde. Continuando de todas formas..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "AVISO: No se pudo iniciar Ollama automaticamente: $_" -ForegroundColor Yellow
    Write-Host "Puedes iniciar Ollama manualmente ejecutando 'ollama serve' en otra terminal." -ForegroundColor Yellow
}

exit 0
