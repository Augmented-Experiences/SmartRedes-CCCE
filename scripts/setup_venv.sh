#!/usr/bin/env bash
# ============================================================
# setup_venv.sh — Crea el entorno virtual Python e instala
# las dependencias del proyecto.
# Compatible con entornos Pinokio (conda base).
# ============================================================
set -e

echo "=== Configurando entorno Python ==="

# Directorio de trabajo (raíz del plugin)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
echo "Directorio del proyecto: $PROJECT_DIR"

# ── Crear entorno virtual ─────────────────────────────────────
VENV_DIR="$PROJECT_DIR/venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ -f "$VENV_PYTHON" ]; then
    echo "OK: Entorno virtual ya existe en: $VENV_DIR"
else
    echo "Creando entorno virtual en: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    echo "OK: Entorno virtual creado."
fi

# ── Actualizar pip ────────────────────────────────────────────
echo "Actualizando pip..."
"$VENV_PYTHON" -m pip install --upgrade pip --quiet || echo "AVISO: No se pudo actualizar pip."

# ── Instalar dependencias core ────────────────────────────────
if [ -f "$PROJECT_DIR/requirements-core.txt" ]; then
    echo "Instalando dependencias core..."
    "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements-core.txt"
    echo "CORE_DEPS_OK"
elif [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "Instalando dependencias desde requirements.txt..."
    "$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

# ── Instalar playwright ──────────────────────────────────────
echo "Instalando playwright..."
"$VENV_PYTHON" -m pip install playwright && "$VENV_PYTHON" -m playwright install chromium || echo "AVISO: playwright no instalado."

# ── Instalar torch (CPU) ─────────────────────────────────────
echo "Instalando torch (CPU)..."
"$VENV_PYTHON" -m pip install torch --index-url https://download.pytorch.org/whl/cpu || echo "AVISO: torch no instalado."

# ── Instalar diffusers ───────────────────────────────────────
echo "Instalando diffusers y transformers..."
"$VENV_PYTHON" -m pip install diffusers transformers accelerate safetensors || echo "AVISO: diffusers no instalado."

# ── Verificar módulos críticos ───────────────────────────────
echo "Verificando modulos criticos..."
"$VENV_PYTHON" -c "import requests, fastapi, uvicorn, pydantic, PIL; print('VERIFY_OK')"

echo "DEPS_OK"
echo "=== Entorno Python configurado correctamente ==="
exit 0
