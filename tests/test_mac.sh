#!/bin/bash
# ============================================================
# SmartRedes — Test Suite para macOS / Linux
# ============================================================
# Ejecutar:
#   cd smartredes
#   chmod +x tests/test_mac.sh
#   ./tests/test_mac.sh
# ============================================================

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
SKIP=0
FAILED_TESTS=""

# Determinar directorio raíz
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  SmartRedes — Test Suite (macOS/Linux)${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Función de assert
assert() {
    local name="$1"
    local result="$2"
    
    if [ "$result" = "true" ] || [ "$result" = "0" ]; then
        echo -e "  ${GREEN}[PASS]${NC} $name"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}[FAIL]${NC} $name"
        FAIL=$((FAIL + 1))
        FAILED_TESTS="$FAILED_TESTS\n  - $name"
    fi
}

skip() {
    local name="$1"
    local reason="$2"
    echo -e "  ${YELLOW}[SKIP]${NC} $name ($reason)"
    SKIP=$((SKIP + 1))
}

# ============================================================
# TESTS DE ESTRUCTURA DE ARCHIVOS
# ============================================================

echo -e "${YELLOW}--- Estructura de archivos ---${NC}"

assert "start.json existe" "$([ -f "$ROOT/start.json" ] && echo true || echo false)"
assert "pinokio.js existe" "$([ -f "$ROOT/pinokio.js" ] && echo true || echo false)"
assert "install.json existe" "$([ -f "$ROOT/install.json" ] && echo true || echo false)"
assert "stop.json existe" "$([ -f "$ROOT/stop.json" ] && echo true || echo false)"
assert "server/app.py existe" "$([ -f "$ROOT/server/app.py" ] && echo true || echo false)"
assert "app/index.html existe" "$([ -f "$ROOT/app/index.html" ] && echo true || echo false)"
assert "requirements.txt existe" "$([ -f "$ROOT/requirements.txt" ] && echo true || echo false)"

# ============================================================
# TESTS DE CONFIGURACIÓN PINOKIO
# ============================================================

echo ""
echo -e "${YELLOW}--- Configuración Pinokio ---${NC}"

# start.json válido
if python3 -c "import json; json.loads(open('$ROOT/start.json').read())" 2>/dev/null; then
    assert "start.json es JSON válido" "true"
else
    assert "start.json es JSON válido" "false"
fi

# start.json NO usa input.event en browser.open
if ! grep -q 'browser.open.*input.event' "$ROOT/start.json" 2>/dev/null; then
    assert "start.json NO usa input.event en browser.open" "true"
else
    assert "start.json NO usa input.event en browser.open" "false"
fi

# start.json pasa PORT como env var
if grep -q '"PORT"' "$ROOT/start.json" 2>/dev/null; then
    assert "start.json pasa PORT como env var" "true"
else
    assert "start.json pasa PORT como env var" "false"
fi

# start.json usa local.set + local.url (patrón compatible con Pinokio)
if grep -q '"method": "local.set"' "$ROOT/start.json" 2>/dev/null \
    && grep -q '{{local.url}}' "$ROOT/start.json" 2>/dev/null \
    && ! grep -q 'self.session.url' "$ROOT/start.json" 2>/dev/null; then
    assert "start.json usa local.set y local.url para browser.open" "true"
else
    assert "start.json usa local.set y local.url para browser.open" "false"
fi
# install.json válido
if python3 -c "import json; json.loads(open('$ROOT/install.json').read())" 2>/dev/null; then
    assert "install.json es JSON válido" "true"
else
    assert "install.json es JSON válido" "false"
fi

# install.json incluye llama3.1:8b
if grep -q "llama3.1:8b" "$ROOT/install.json" 2>/dev/null; then
    assert "install.json incluye llama3.1:8b" "true"
else
    assert "install.json incluye llama3.1:8b" "false"
fi

# pinokio.js título
if grep -q "SmartRedes" "$ROOT/pinokio.js" 2>/dev/null; then
    assert "pinokio.js tiene título correcto" "true"
else
    assert "pinokio.js tiene título correcto" "false"
fi

# pinokio.js no usa input.event
if ! grep -q "input.event\[0\]" "$ROOT/pinokio.js" 2>/dev/null; then
    assert "pinokio.js NO contiene input.event en href" "true"
else
    assert "pinokio.js NO contiene input.event en href" "false"
fi

# pinokio.js recupera la URL desde la memoria local de Pinokio
if grep -q 'kernel.memory.local' "$ROOT/pinokio.js" 2>/dev/null \
    && ! grep -q 'session.json' "$ROOT/pinokio.js" 2>/dev/null; then
    assert "pinokio.js usa memoria local para URL" "true"
else
    assert "pinokio.js usa memoria local para URL" "false"
fi

# ============================================================
# TESTS DE PYTHON
# ============================================================

echo ""
echo -e "${YELLOW}--- Python y Dependencias ---${NC}"

# Python disponible
if command -v python3 &>/dev/null; then
    assert "Python3 disponible" "true"
else
    assert "Python3 disponible" "false"
fi

# Sintaxis de app.py
if python3 -c "import ast; ast.parse(open('$ROOT/server/app.py', encoding='utf-8').read())" 2>/dev/null; then
    assert "app.py tiene sintaxis válida" "true"
else
    assert "app.py tiene sintaxis válida" "false"
fi

# Dependencias core
CORE_DEPS=("fastapi" "uvicorn" "requests" "httpx" "beautifulsoup4" "pydantic" "Pillow")
for dep in "${CORE_DEPS[@]}"; do
    if pip3 show "$dep" &>/dev/null; then
        assert "Dependencia: $dep instalada" "true"
    else
        assert "Dependencia: $dep instalada" "false"
    fi
done

# ============================================================
# TESTS DE OLLAMA
# ============================================================

echo ""
echo -e "${YELLOW}--- Ollama ---${NC}"

# El plugin instala o inicia Ollama automáticamente; en CI puede no estar presente.
assert "start.json incluye arranque automático de Ollama" "$(grep -q 'ollama serve' "$ROOT/start.json" && echo true || echo false)"

if ! command -v ollama &>/dev/null \
    && [ ! -f "/usr/local/bin/ollama" ] \
    && [ ! -f "$HOME/.ollama/ollama" ]; then
    skip "Comprobación dinámica de Ollama" "Ollama no está instalado en este entorno"
elif curl -s --max-time 5 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    assert "Ollama respondiendo en localhost:11434" "true"
    
    # Verificar modelos
    MODELS=$(curl -s "http://localhost:11434/api/tags" | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data.get('models',[])))" 2>/dev/null || echo "0")
    if [ "$MODELS" -gt 0 ]; then
        assert "Ollama tiene modelos descargados ($MODELS)" "true"
    else
        assert "Ollama tiene modelos descargados" "false"
    fi
    
    # Verificar llama3.1:8b
    HAS_LLAMA31=$(curl -s "http://localhost:11434/api/tags" | python3 -c "import json,sys; data=json.load(sys.stdin); models=[m['name'] for m in data.get('models',[])]; print('true' if any('llama3.1' in m for m in models) else 'false')" 2>/dev/null || echo "false")
    assert "Modelo llama3.1:8b disponible" "$HAS_LLAMA31"
else
    skip "Comprobación dinámica de Ollama" "el servicio no está activo; Pinokio lo inicia al ejecutar start.json"
fi

# ============================================================
# TESTS DE UI
# ============================================================

echo ""
echo -e "${YELLOW}--- Interfaz de Usuario ---${NC}"

HTML="$ROOT/app/index.html"

assert "index.html contiene readinessBanner" "$(grep -q 'readinessBanner' "$HTML" && echo true || echo false)"
assert "index.html contiene globalLoadingOverlay" "$(grep -q 'globalLoadingOverlay' "$HTML" && echo true || echo false)"
assert "index.html contiene checkReadiness" "$(grep -q 'checkReadiness' "$HTML" && echo true || echo false)"
assert "index.html contiene model-perf-badge" "$(grep -q 'model-perf-badge' "$HTML" && echo true || echo false)"
assert "index.html contiene safeDisplayValue" "$(grep -q 'safeDisplayValue' "$HTML" && echo true || echo false)"
assert "index.html contiene analyze-progress-panel" "$(grep -q 'analyze-progress-panel' "$HTML" && echo true || echo false)"
assert "index.html NO muestra [object Object]" "$(! grep -q '\[object Object\]' "$HTML" && echo true || echo false)"
assert "DOMPurify library existe" "$([ -f "$ROOT/app/lib/purify.min.js" ] && echo true || echo false)"

# ============================================================
# TESTS DE SEGURIDAD
# ============================================================

echo ""
echo -e "${YELLOW}--- Seguridad ---${NC}"

assert "No hay API keys hardcodeadas" "$(! grep -qE 'sk-[a-zA-Z0-9]{20,}' "$ROOT/server/app.py" && echo true || echo false)"
assert "No hay passwords hardcodeadas" "$(! grep -qE 'password\s*=\s*[\"'"'"'][^\"'"'"']+[\"'"'"']' "$ROOT/server/app.py" && echo true || echo false)"
assert "DOMPurify se usa para sanitizar HTML" "$(grep -q 'DOMPurify' "$HTML" && echo true || echo false)"

# ============================================================
# TESTS DE SERVIDOR (si está corriendo)
# ============================================================

echo ""
echo -e "${YELLOW}--- Servidor API (si está corriendo) ---${NC}"

SERVER_URL="http://127.0.0.1:42003"

if curl -s --max-time 3 "$SERVER_URL/api/health" >/dev/null 2>&1; then
    # Health
    HEALTH=$(curl -s "$SERVER_URL/api/health")
    HEALTH_OK=$(echo "$HEALTH" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if d.get('status')=='ok' else 'false')" 2>/dev/null || echo "false")
    assert "API /health retorna status ok" "$HEALTH_OK"
    
    # Readiness
    READY=$(curl -s "$SERVER_URL/api/readiness")
    READY_OK=$(echo "$READY" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if 'ready' in d else 'false')" 2>/dev/null || echo "false")
    assert "API /readiness retorna campo ready" "$READY_OK"
    
    # Hardware Performance
    PERF=$(curl -s "$SERVER_URL/api/hardware/performance")
    PERF_OK=$(echo "$PERF" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if 'hardware' in d and 'models' in d else 'false')" 2>/dev/null || echo "false")
    assert "API /hardware/performance retorna hardware y models" "$PERF_OK"
    
    # Brands list
    BRANDS=$(curl -s "$SERVER_URL/api/brands")
    BRANDS_OK=$(echo "$BRANDS" | python3 -c "import json,sys; d=json.load(sys.stdin); print('true' if 'brands' in d else 'false')" 2>/dev/null || echo "false")
    assert "API /brands retorna lista" "$BRANDS_OK"
    
    # UI accesible
    UI_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/ui/index.html")
    assert "UI accesible en /ui/index.html (HTTP $UI_STATUS)" "$([ "$UI_STATUS" = "200" ] && echo true || echo false)"
else
    echo -e "    ${CYAN}(Servidor no está corriendo en $SERVER_URL — inicia con 'python server/app.py')${NC}"
fi

# ============================================================
# RESUMEN
# ============================================================

echo ""
echo -e "${CYAN}============================================================${NC}"
TOTAL=$((PASS + FAIL))
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}  RESUMEN: $PASS/$TOTAL tests pasaron; $SKIP omitidos ✓${NC}"
else
    echo -e "${YELLOW}  RESUMEN: $PASS pasaron, $FAIL fallaron, $SKIP omitidos${NC}"
fi
echo -e "${CYAN}============================================================${NC}"
echo ""

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}Tests fallidos:${NC}"
    echo -e "$FAILED_TESTS"
    echo ""
    exit 1
fi
