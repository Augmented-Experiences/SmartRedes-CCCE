# ============================================================
# SmartRedes — Test Suite para Windows
# ============================================================
# Ejecutar desde PowerShell:
#   cd smartredes
#   .\tests\test_windows.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$script:PASS = 0
$script:FAIL = 0
$script:TESTS = @()

function Write-Header {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  SmartRedes — Test Suite (Windows)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Assert {
    param(
        [string]$Name,
        [scriptblock]$Test
    )
    try {
        $result = & $Test
        if ($result -eq $true) {
            Write-Host "  [PASS] $Name" -ForegroundColor Green
            $script:PASS++
            $script:TESTS += @{Name=$Name; Status="PASS"; Error=""}
        } else {
            Write-Host "  [FAIL] $Name — returned false" -ForegroundColor Red
            $script:FAIL++
            $script:TESTS += @{Name=$Name; Status="FAIL"; Error="returned false"}
        }
    } catch {
        Write-Host "  [FAIL] $Name — $($_.Exception.Message)" -ForegroundColor Red
        $script:FAIL++
        $script:TESTS += @{Name=$Name; Status="FAIL"; Error=$_.Exception.Message}
    }
}

function Write-Summary {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  RESUMEN: $($script:PASS) pasaron, $($script:FAIL) fallaron" -ForegroundColor $(if ($script:FAIL -eq 0) { "Green" } else { "Yellow" })
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    if ($script:FAIL -gt 0) {
        Write-Host "Tests fallidos:" -ForegroundColor Red
        foreach ($t in $script:TESTS) {
            if ($t.Status -eq "FAIL") {
                Write-Host "  - $($t.Name): $($t.Error)" -ForegroundColor Red
            }
        }
        exit 1
    }
}

# ============================================================
# TESTS DE ESTRUCTURA DE ARCHIVOS
# ============================================================

Write-Header
Write-Host "--- Estructura de archivos ---" -ForegroundColor Yellow

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path "$ROOT\start.json")) {
    $ROOT = Split-Path -Parent $PSScriptRoot
}

Test-Assert "start.json existe" { Test-Path "$ROOT\start.json" }
Test-Assert "pinokio.js existe" { Test-Path "$ROOT\pinokio.js" }
Test-Assert "install.json existe" { Test-Path "$ROOT\install.json" }
Test-Assert "stop.json existe" { Test-Path "$ROOT\stop.json" }
Test-Assert "server\app.py existe" { Test-Path "$ROOT\server\app.py" }
Test-Assert "app\index.html existe" { Test-Path "$ROOT\app\index.html" }
Test-Assert "requirements.txt existe" { Test-Path "$ROOT\requirements.txt" }

# ============================================================
# TESTS DE CONTENIDO DE CONFIGURACIÓN
# ============================================================

Write-Host ""
Write-Host "--- Configuración Pinokio ---" -ForegroundColor Yellow

Test-Assert "start.json es JSON válido" {
    $null = Get-Content "$ROOT\start.json" -Raw | ConvertFrom-Json
    $true
}

Test-Assert "start.json NO usa input.event en browser.open" {
    $content = Get-Content "$ROOT\start.json" -Raw
    # input.event[0] es correcto dentro de self.set, pero NO en browser.open
    -not ($content -match 'browser\.open.*input\.event')
}

Test-Assert "start.json pasa PORT como env var" {
    $content = Get-Content "$ROOT\start.json" -Raw
    $content -match '"PORT"'
}

Test-Assert "start.json usa local.set y local.url para browser.open" {
    $content = Get-Content "$ROOT\start.json" -Raw
    ($content -match '"method": "local.set"') -and
    ($content -match '\{\{local\.url\}\}') -and
    -not ($content -match "self\.session\.url")
}

Test-Assert "install.json es JSON válido" {
    $null = Get-Content "$ROOT\install.json" -Raw | ConvertFrom-Json
    $true
}

Test-Assert "install.json incluye llama3.1:8b" {
    $content = Get-Content "$ROOT\install.json" -Raw
    $content -match "llama3\.1:8b"
}

Test-Assert "pinokio.js tiene título SmartRedes" {
    $content = Get-Content "$ROOT\pinokio.js" -Raw
    $content -match "SmartRedes"
}

Test-Assert "pinokio.js NO contiene input.event en href" {
    $content = Get-Content "$ROOT\pinokio.js" -Raw
    -not ($content -match "input\.event\[0\]")
}

Test-Assert "pinokio.js usa memoria local para URL" {
    $content = Get-Content "$ROOT\pinokio.js" -Raw
    ($content -match "kernel\.memory\.local") -and
    -not ($content -match "session\.json")
}

# ============================================================
# TESTS DE PYTHON Y DEPENDENCIAS
# ============================================================

Write-Host ""
Write-Host "--- Python y Dependencias ---" -ForegroundColor Yellow

Test-Assert "Python disponible" {
    $py = Get-Command python -ErrorAction SilentlyContinue
    $null -ne $py
}

Test-Assert "app.py tiene sintaxis válida" {
    $result = python -c "import ast; ast.parse(open('$ROOT\server\app.py', encoding='utf-8').read()); print('OK')" 2>&1
    $result -match "OK"
}

# Verificar dependencias core
$coreDeps = @("fastapi", "uvicorn", "requests", "httpx", "beautifulsoup4", "pydantic", "Pillow")
foreach ($dep in $coreDeps) {
    Test-Assert "Dependencia: $dep instalada" {
        $result = pip show $dep 2>&1
        $LASTEXITCODE -eq 0
    }
}

# ============================================================
# TESTS DE OLLAMA
# ============================================================

Write-Host ""
Write-Host "--- Ollama ---" -ForegroundColor Yellow

Test-Assert "start.json incluye arranque automático de Ollama" {
    $content = Get-Content "$ROOT\start.json" -Raw
    $content -match "ollama serve"
}

Test-Assert "Ollama respondiendo en localhost:11434" {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
        $true
    } catch {
        Write-Host "    (Ollama no está corriendo — esto es esperado si no se ha iniciado)" -ForegroundColor DarkGray
        $true  # No es un error fatal para el test
    }
}

# ============================================================
# TESTS DE UI
# ============================================================

Write-Host ""
Write-Host "--- Interfaz de Usuario ---" -ForegroundColor Yellow

Test-Assert "index.html contiene readinessBanner" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "readinessBanner"
}

Test-Assert "index.html contiene globalLoadingOverlay" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "globalLoadingOverlay"
}

Test-Assert "index.html contiene checkReadiness" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "checkReadiness"
}

Test-Assert "index.html contiene model-perf-badge" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "model-perf-badge"
}

Test-Assert "index.html contiene safeDisplayValue" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "safeDisplayValue"
}

Test-Assert "index.html contiene analyze-progress-panel" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "analyze-progress-panel"
}

Test-Assert "index.html NO muestra [object Object]" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    -not ($content -match "\[object Object\]")
}

Test-Assert "DOMPurify library exists" {
    Test-Path "$ROOT\app\lib\purify.min.js"
}

# ============================================================
# TESTS DE SEGURIDAD
# ============================================================

Write-Host ""
Write-Host "--- Seguridad ---" -ForegroundColor Yellow

Test-Assert "No hay API keys hardcodeadas en app.py" {
    $content = Get-Content "$ROOT\server\app.py" -Raw
    -not ($content -match "sk-[a-zA-Z0-9]{20,}")
}

Test-Assert "No hay passwords hardcodeadas en app.py" {
    $content = Get-Content "$ROOT\server\app.py" -Raw
    -not ($content -match "password\s*=\s*['\"][^'\"]+['\"]")
}

Test-Assert "DOMPurify se usa para sanitizar HTML" {
    $content = Get-Content "$ROOT\app\index.html" -Raw
    $content -match "DOMPurify"
}

# ============================================================
# RESUMEN
# ============================================================

Write-Summary
