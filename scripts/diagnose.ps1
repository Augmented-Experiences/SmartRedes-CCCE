# ============================================================
# diagnose.ps1 — Script de diagnóstico del entorno Windows.
# Ejecutar manualmente si hay problemas de instalación.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\diagnose.ps1
# ============================================================

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  SmartRedes — Diagnostico Windows  " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Sistema operativo
Write-Host "[Sistema]" -ForegroundColor Yellow
$os = Get-CimInstance Win32_OperatingSystem
Write-Host "  OS: $($os.Caption) $($os.Version)"
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "  RAM: ${ram}GB"
Write-Host "  PowerShell: $($PSVersionTable.PSVersion)"
Write-Host ""

# Python
Write-Host "[Python]" -ForegroundColor Yellow
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    $ver = & python --version 2>&1
    Write-Host "  OK: $($py.Source) — $ver" -ForegroundColor Green
} else {
    Write-Host "  NO ENCONTRADO — Instala Python desde https://python.org" -ForegroundColor Red
}
Write-Host ""

# Entorno virtual
Write-Host "[Entorno Virtual]" -ForegroundColor Yellow
$venvPy = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $ver = & $venvPy --version 2>&1
    Write-Host "  OK: venv encontrado — $ver" -ForegroundColor Green
} else {
    Write-Host "  NO ENCONTRADO — Ejecuta install.json desde Pinokio" -ForegroundColor Red
}
Write-Host ""

# Ollama
Write-Host "[Ollama]" -ForegroundColor Yellow
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    $ver = & ollama --version 2>&1
    Write-Host "  OK: $($ollamaCmd.Source) — $ver" -ForegroundColor Green
} else {
    $paths = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe"
    )
    $found = $false
    foreach ($p in $paths) {
        if (Test-Path $p) {
            Write-Host "  OK (no en PATH): $p" -ForegroundColor Yellow
            $found = $true
            break
        }
    }
    if (-not $found) {
        Write-Host "  NO ENCONTRADO — Instala desde https://ollama.com/download" -ForegroundColor Red
    }
}

# Ollama corriendo
try {
    $r = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($r.StatusCode -eq 200) {
        $models = ($r.Content | ConvertFrom-Json).models
        Write-Host "  Servidor: CORRIENDO en puerto 11434" -ForegroundColor Green
        Write-Host "  Modelos disponibles: $($models.Count)"
        foreach ($m in $models) { Write-Host "    - $($m.name)" }
    }
} catch {
    Write-Host "  Servidor: NO CORRIENDO" -ForegroundColor Yellow
}
Write-Host ""

# Dependencias Python
Write-Host "[Dependencias Python]" -ForegroundColor Yellow
if (Test-Path $venvPy) {
    $pkgs = & $venvPy -m pip list --format=columns 2>&1
    $required = @("fastapi", "uvicorn", "requests", "pillow", "pydantic")
    foreach ($pkg in $required) {
        $found = $pkgs | Where-Object { $_ -match "^$pkg\s" }
        if ($found) {
            Write-Host "  OK: $($found.Trim())" -ForegroundColor Green
        } else {
            Write-Host "  FALTA: $pkg" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  No se puede verificar (venv no encontrado)" -ForegroundColor Yellow
}
Write-Host ""

# Puertos
Write-Host "[Puertos]" -ForegroundColor Yellow
$port8080 = netstat -ano | Select-String ":8080\s"
$port11434 = netstat -ano | Select-String ":11434\s"
if ($port8080) {
    Write-Host "  Puerto 8080: EN USO" -ForegroundColor Yellow
} else {
    Write-Host "  Puerto 8080: LIBRE" -ForegroundColor Green
}
if ($port11434) {
    Write-Host "  Puerto 11434 (Ollama): EN USO" -ForegroundColor Green
} else {
    Write-Host "  Puerto 11434 (Ollama): LIBRE" -ForegroundColor Yellow
}
Write-Host ""

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Diagnostico completado" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
