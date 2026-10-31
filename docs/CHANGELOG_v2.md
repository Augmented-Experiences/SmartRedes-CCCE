# Changelog — SmartRedes v2.0

## Resumen de Reparaciones y Mejoras

**Fecha:** 12 de mayo de 2026  
**Commit:** `7cc0509`  
**Branch:** `main`

---

## 1. Error Crítico Reparado

### Problema
Al hacer clic en "Abrir UI" en Pinokio, Windows mostraba el error:

> Windows cannot find '{{input.event[0]}}/ui/index.html'

**Causa raíz:** El archivo `start.json` usaba una variable local `"url": "{{input.event[0]}}"` que no se resolvía correctamente en Windows porque `input.event` es un array que contiene las URLs emitidas por el proceso, pero la interpolación fallaba antes de que el evento se emitiera.

### Solución
- Se eliminó completamente la dependencia de `input.event[0]` en `start.json`
- Se usa ahora la variable de plantilla `{{port}}` de Pinokio que se resuelve correctamente
- Se actualizó `pinokio.js` para usar `start.json` (no `.js`) y el href correcto `http://127.0.0.1:{{port}}/ui/index.html`

---

## 2. Mejoras de Interfaz de Usuario

### 2.1 Banner de Readiness (Estado del Sistema)
- Al cargar el dashboard, se muestra un banner que indica si el sistema está listo o en preparación
- **Verde:** "Sistema listo para usar" — Ollama activo con modelos disponibles
- **Amarillo:** "Preparando el sistema..." — Modelos descargándose u Ollama iniciando
- **Rojo:** "Sistema no disponible" — Problemas críticos que impiden el funcionamiento
- Se actualiza automáticamente cada 5 segundos cuando no está listo

### 2.2 Global Loading Overlay
- Overlay semitransparente con spinner que cubre toda la pantalla durante requests síncronos
- Evita que el usuario piense que no se está ejecutando nada
- Se activa al iniciar análisis de sitio web y se desactiva al recibir respuesta

### 2.3 Progreso de Escaneo Web
- Panel detallado con 8 pasos del proceso de análisis
- Barra de progreso con porcentaje
- Lista de pasos con iconos: completado (✓), activo (▶), pendiente (○)
- Se actualiza cada 2 segundos vía polling al endpoint `/api/brands/{id}/analyze-progress`
- Pasos: Preparando → HTML → Meta tags → Colores → Contenido → IA → Procesando → Guardando

### 2.4 Semáforo de Rendimiento de Modelos (estilo canirun.ai)
- Cada modelo descargado muestra un badge de rendimiento con:
  - **Grado:** S (excelente) / A (muy bueno) / B (bueno) / C (aceptable) / D (lento) / F (no viable)
  - **Tokens/segundo estimados** según el hardware detectado
  - **Barra de uso de RAM** (verde/amarillo/rojo)
- Información de hardware: RAM total, GPU, cores de CPU
- Se actualiza cada 60 segundos

### 2.5 Prevención de [object Object]
- Nueva función `safeDisplayValue()` que convierte cualquier tipo de dato a string legible
- Renderizado especial para paleta de colores con swatches visuales (círculos de color)
- Backend sanitiza todos los campos ADN con `_sanitize_adn_fields()` antes de guardar

---

## 3. Mejoras de Backend

### 3.1 Nuevos Endpoints
| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/readiness` | GET | Estado completo del sistema (Ollama, modelos, pulls activos) |
| `/api/brands/{id}/analyze-progress` | GET | Progreso detallado del análisis web |
| `/api/hardware/performance` | GET | Info de hardware y estimación de rendimiento por modelo |

### 3.2 Descarga Automática de llama3.1:8b
- Al iniciar el servidor, se verifica si `llama3.1:8b` está disponible
- Si no existe, se inicia la descarga automáticamente en background
- También se descarga durante la instalación del plugin (actualizado `install.json`)

### 3.3 Mejora del Prompt de Brand Analyzer
- Prompt más detallado para extraer mejor el ADN de marca
- Instrucciones explícitas para devolver colores en formato hex
- Mejor extracción de propuesta de valor, tono y audiencia

### 3.4 Sanitización de ADN
- Función `_sanitize_adn_fields()` que garantiza tipos correctos en todos los campos
- Convierte dicts a listas, objetos anidados a strings
- Previene que el frontend reciba datos que no puede renderizar

---

## 4. Suite de Tests

### 4.1 Tests Python (pytest) — 36 tests
- **Health & System:** health, readiness, config
- **Ollama:** status, hardware/performance, model grades
- **Brands CRUD:** create, get, list, delete, not-found
- **Analyze Progress:** campos, estado sin análisis activo
- **ADN Sanitization:** strings, listas, dicts, None, objetos anidados, prevención [object Object]
- **Model Performance:** estimación de parámetros, tokens/s, Apple Silicon, grados
- **Pinokio Config:** start.json, pinokio.js, install.json validación
- **Cross-Platform:** rutas, encoding UTF-8

### 4.2 Script Windows (`tests/test_windows.ps1`)
- Estructura de archivos
- Configuración Pinokio (JSON válido, sin input.event, puerto)
- Python y dependencias
- Ollama (instalado, respondiendo)
- UI (readiness, overlay, progreso, semáforo)
- Seguridad (no API keys, no passwords, DOMPurify)

### 4.3 Script macOS/Linux (`tests/test_mac.sh`)
- Misma cobertura que Windows adaptada a bash
- Tests adicionales de servidor API si está corriendo

---

## 5. Archivos Modificados

| Archivo | Tipo de cambio |
|---------|---------------|
| `start.json` | Reescrito — eliminado input.event[0] |
| `pinokio.js` | Corregido — href y referencia a start.json |
| `install.json` | Actualizado — descarga llama3.1:8b |
| `server/app.py` | Extendido — 3 nuevos endpoints, sanitización, hardware |
| `app/index.html` | Extendido — readiness, overlay, progreso, semáforo |
| `defaults/prompts/brand_analyzer.md` | Mejorado — prompt más detallado |
| `scripts/pull_model.ps1` | Actualizado — descarga llama3.1:8b primero |
| `tests/test_api.py` | Nuevo — 36 tests pytest |
| `tests/test_windows.ps1` | Nuevo — suite PowerShell |
| `tests/test_mac.sh` | Nuevo — suite bash |
| `tests/conftest.py` | Nuevo — configuración pytest |
| `docs/PLAN_REPARACION.md` | Nuevo — plan de desarrollo |
| `docs/canirun-research.md` | Nuevo — investigación semáforo |
