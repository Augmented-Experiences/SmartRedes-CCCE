# ============================================================
# pull_model.ps1 — Descarga modelos de IA necesarios
# Siempre descarga llama3.1:8b (requerido por agentes clave)
# y adicionalmente un modelo ligero según RAM disponible.
# Compatible con entornos Pinokio (conda base).
# ============================================================

$ErrorActionPreference = "Continue"

Write-Host "=== Descargando modelos de IA ===" -ForegroundColor Cyan

# Función para encontrar el ejecutable de Ollama
function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

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
    Write-Host "AVISO: Ollama no disponible. Saltando descarga de modelos." -ForegroundColor Yellow
    Write-Host "Instala Ollama desde https://ollama.com/download y luego ejecuta 'ollama pull llama3.1:8b'" -ForegroundColor Yellow
    exit 0
}

# Verificar que Ollama está corriendo
$ollamaRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($r.StatusCode -eq 200) { $ollamaRunning = $true }
} catch { }

if (-not $ollamaRunning) {
    Write-Host "AVISO: Ollama no esta corriendo. Saltando descarga de modelos." -ForegroundColor Yellow
    exit 0
}

# Detectar RAM total del sistema
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "RAM detectada: ${ramGB}GB" -ForegroundColor Cyan

# --- Paso 1: Siempre descargar llama3.1:8b (requerido por brand_interviewer y campaign_strategist) ---
$requiredModel = "llama3.1:8b"
Write-Host ""
Write-Host "Paso 1: Verificando modelo principal $requiredModel..." -ForegroundColor Cyan

function Test-ModelExists($modelName) {
    try {
        $tagsJson = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -UseBasicParsing
        $tags = ($tagsJson.Content | ConvertFrom-Json).models
        $found = $tags | Where-Object { $_.name -like "$modelName*" }
        return [bool]$found
    } catch {
        return $false
    }
}

if (Test-ModelExists $requiredModel) {
    Write-Host "OK: Modelo $requiredModel ya esta disponible localmente." -ForegroundColor Green
} else {
    Write-Host "Descargando $requiredModel (~4.7 GB, puede tardar varios minutos)..." -ForegroundColor Yellow
    try {
        & $ollamaExe pull $requiredModel
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: Modelo $requiredModel descargado correctamente." -ForegroundColor Green
        } else {
            Write-Host "AVISO: La descarga de $requiredModel puede haber fallado (codigo $LASTEXITCODE)." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "ERROR al descargar $requiredModel : $_" -ForegroundColor Red
    }
}

# --- Paso 2: Descargar modelo adicional según RAM ---
if ($ramGB -lt 6) {
    $extraModel = "llama3.2:1b"
    Write-Host ""
    Write-Host "Paso 2: RAM < 6GB, descargando modelo ligero adicional $extraModel..." -ForegroundColor Yellow
} elseif ($ramGB -lt 12) {
    $extraModel = "llama3.2:3b"
    Write-Host ""
    Write-Host "Paso 2: RAM 6-12GB, descargando modelo adicional $extraModel..." -ForegroundColor Green
} else {
    $extraModel = $null
    Write-Host ""
    Write-Host "Paso 2: RAM >= 12GB, $requiredModel es suficiente. No se necesita modelo adicional." -ForegroundColor Green
}

if ($extraModel) {
    if (Test-ModelExists $extraModel) {
        Write-Host "OK: Modelo $extraModel ya esta disponible localmente." -ForegroundColor Green
    } else {
        Write-Host "Descargando $extraModel..." -ForegroundColor Yellow
        try {
            & $ollamaExe pull $extraModel
            if ($LASTEXITCODE -eq 0) {
                Write-Host "OK: Modelo $extraModel descargado correctamente." -ForegroundColor Green
            } else {
                Write-Host "AVISO: La descarga de $extraModel puede haber fallado (codigo $LASTEXITCODE)." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "ERROR al descargar $extraModel : $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "=== Descarga de modelos completada ===" -ForegroundColor Green
exit 0
