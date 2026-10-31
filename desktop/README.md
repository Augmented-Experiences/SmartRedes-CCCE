# SmartSuite Desktop Kit (CCCE) — App/Instalador de escritorio (Tauri)

Esta copia del kit está configurada para **SmartRedes** (`desktop/smartsuite.config.json`).

Kit **reutilizable** para empaquetar las herramientas del SmartSuite de la CCCE (**SmartCaja**, **SmartRedes**, **SmartGastos**, …) como instaladores nativos para **Windows**, **macOS** y **Linux**, sin necesidad de Pinokio. Empaqueta la interfaz web + el backend FastAPI en una app de escritorio con identidad CCCE.

Este mismo `desktop/` sirve para las 3 herramientas: solo cambia `smartsuite.config.json` (nombre, id, acento, modelos) — el resto es común. `scripts/configure.mjs` genera los archivos variables antes de compilar.

## Arquitectura

```
Ventana Tauri (webview nativo)
        │  al iniciar muestra ui/index.html (pantalla de carga)
        ▼
Rust (src-tauri/src/main.rs) — genérico para todas las herramientas
  1. Elige un puerto libre.
  2. Lanza el backend empaquetado como "sidecar" (backend), pasándole
     PORT y DATA_DIR por variables de entorno.
  3. Prepara Ollama **sin instalador de sistema** (sin MSI / OllamaSetup.exe):
     si ya hay un Ollama sano en `127.0.0.1:11434` lo reutiliza; si no, arranca
     un binario portable previo en `%APPDATA%/SmartRedes/ollama/` (o el data dir
     de la herramienta); si no existe, descarga el zip/tgz oficial, extrae,
     arranca `ollama serve` y hace pull del modelo **sin reiniciar la app**.
     Solo se detiene el PID de Ollama que esta app haya arrancado.
  4. Muestra el progreso en la pantalla de carga y, al estar listo,
     navega a http://127.0.0.1:<puerto>/ui/index.html (la UI real).
  5. Al cerrar la app, detiene el backend.
        │
        ▼
Backend FastAPI (server/app.py) empaquetado con PyInstaller
  - Sirve la UI (/ui) y la API (/api), igual que en Pinokio.
  - Recursos (app/, defaults/) desde el bundle; datos del usuario en una
    carpeta escribible por-usuario (DATA_DIR por entorno).
```

Ventajas: el usuario descarga **un instalador** y ejecuta la app; no necesita conocer Pinokio ni la terminal.

## Configuración por herramienta (`smartsuite.config.json`)

Todo lo específico de cada app vive en `desktop/smartsuite.config.json`:

| Campo | Uso |
|---|---|
| `productName`, `identifier`, `version` | Nombre, id de bundle y versión. |
| `dataDirName` | Nombre de la carpeta de datos por-usuario. |
| `accent` | Color de acento CCCE para diferenciar la herramienta (SmartCaja: dorado `#F4C10E`). |
| `window` | Título y tamaño de ventana. |
| `splashLogo` | Wordmark color CCCE en la pantalla de carga (`../app/logo-ccce.png`). |
| `splashMark` | Isotipo blanco sobre negro para la marca en splash oscuro (`../icon.png`). |
| `ollama.tiers` | Modelo (chat/LLM) a descargar según la RAM (`maxRamGb: 0` = sin límite / último). |
| `ollama.extraModels` | Modelos adicionales a descargar con progreso (p. ej. un modelo de **visión para OCR neuronal** como `moondream`). Se descargan igual que el LLM, con barra de progreso en la pantalla de carga — así capacidades pesadas (OCR) no requieren empaquetar torch/easyocr. |

`scripts/configure.mjs` (se ejecuta solo con `npm run build`/`npm run dev`) genera desde ese config: `src-tauri/tauri.conf.json` (`.msi`/`-setup.exe` en Windows), `src-tauri/appconfig.json` (que Rust lee), `src-tauri/Cargo.toml`, `ui/index.html` (splash), `package.json` y los CSS de marca (`ui/ccce-theme.css`, `ui/accent.css`). Plantilla: `brand/splash.template.html`.

## Brand kit CCCE (estilo compartido)

`desktop/brand/` contiene la identidad reutilizable: `ccce-theme.css` (paleta CCCE + acentos, con `--ccce-accent` sobreescribible por herramienta) y los logos (`logo-ccce.png` wordmark, `ccce-mark.png` isotipo, `logo-ccce-white.png` splash). El isotipo también vive en `icon.png` (Pinokio / `npm run icon`) y `app/favicon.ico`. Cualquier UI puede enlazar `ccce-theme.css` y usar las variables `--ccce-*`. Cada herramienta se diferencia con su `accent` (SmartCaja: dorado `#F4C10E`).

## Requisitos de build

- **Python 3.10–3.12 (recomendado 3.12)** + este repo (`requirements.txt`) — para empaquetar el backend. **No uses 3.13/3.14**: `numpy 1.26.4` (pinneado) no publica wheels para esas versiones y pip intentaría compilarlo desde fuente (falla en Windows). Los scripts de build validan la versión y avisan.
- Rust (stable) + Cargo.
- Node 18+ (para la CLI de Tauri).
- Linux: `libwebkit2gtk-4.1-dev`, `librsvg2-dev`, `libgtk-3-dev`, `libayatana-appindicator3-dev`, `patchelf`, `build-essential` (ver CI).
- **Ollama** NO se empaqueta en el instalador ni se ejecuta el MSI/sistema: al primer arranque la app descarga un **Ollama portable** al data dir (`%APPDATA%\SmartRedes\ollama\` en Windows; `~/.local/share/SmartRedes/ollama/` en Linux) si no hay un Ollama sano ya escuchando en el puerto 11434.

## Build local

```bash
# 1) Empaquetar el backend (genera el sidecar 'backend' en src-tauri/binaries/)
bash desktop/scripts/build-backend.sh      # Windows: desktop/scripts/build-backend.ps1

# 2) Generar iconos (una sola vez; requiere red la primera vez)
cd desktop && npm install && npm run icon   # crea src-tauri/icons/

# 3) Construir el instalador (configure.mjs corre antes de tauri build)
npm run build
```

Los instaladores quedan en `desktop/src-tauri/target/release/bundle/` (`.AppImage`/`.deb`/`.rpm` en Linux, `.dmg` en macOS, `.msi`/`.exe` en Windows).

## Aplicar el kit a otra herramienta (SmartRedes, SmartGastos)

Como los repos son separados, se copia el kit a cada uno:

1. Copia a la raíz del repo destino las carpetas `desktop/` y usa su propio `icon.png` (mismo isotipo CCCE) en la raíz.
2. Sustituye `desktop/smartsuite.config.json` por el de la herramienta (hay ejemplos listos en `desktop/examples/smartredes.config.json` y `desktop/examples/smartgastos.config.json`).
3. **Parche de `server/app.py` (2–3 líneas, retrocompatible con Pinokio):**
   - `BASE_DIR` debe apuntar al bundle cuando la app está empaquetada (para servir `app/` y `defaults/`):
     ```python
     # antes:
     BASE_DIR = Path(__file__).parent.parent.resolve()
     # después:
     BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent.resolve()
     ```
   - `DATA_DIR` debe respetar la variable de entorno (el kit la fija a una carpeta escribible por-usuario):
     ```python
     DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
     ```
   - Asegúrate de que `import sys` esté presente.

   Ya hay parches listos en los artefactos del agente: `smartredes_app_py.patch` y `smartgastos_app_py.patch` (aplícalos con `git apply`). Es retrocompatible: Pinokio no define `DATA_DIR` ni `frozen`, así que su comportamiento no cambia.
4. Genera iconos (`npm run icon`) y construye (`bash scripts/build-backend.sh` + `npm run build`).

El backend se lanza con `PORT` y `DATA_DIR` por entorno, así que sirve para las 3 apps (SmartCaja/SmartRedes usan `--port`/`PORT`; SmartGastos usa `PORT`, default 8000 — irrelevante porque el kit fija el puerto).

Para aplicar además el **estilo CCCE a la UI** de cada herramienta (colores/logos como en SmartCaja), enlaza `brand/ccce-theme.css` en su `app/index.html` y reemplaza su paleta por las variables `--ccce-*` (con su `accent`).

## Build multiplataforma (recomendado)

Los instaladores de cada SO deben construirse en su propio SO. Usa el workflow de GitHub Actions incluido: `.github/workflows/desktop-build.yml` (ejecútalo con *workflow_dispatch* o al publicar un tag `v*`). Genera los artefactos para Windows/macOS/Linux y los sube como *artifacts*.

## Troubleshooting

- **`Preparing metadata (pyproject.toml) ... error` al instalar numpy (Windows):** tu Python es demasiado nuevo (3.13/3.14) y `numpy 1.26.4` no tiene wheel; pip intenta compilar desde fuente. Solución: usa Python 3.12.
  ```powershell
  winget install -e --id Python.Python.3.12
  Remove-Item -Recurse -Force venv
  py -3.12 -m venv venv
  venv\Scripts\python -m pip install -r requirements.txt pyinstaller
  powershell -ExecutionPolicy Bypass -File desktop\scripts\build-backend.ps1
  ```

- **`rustc : The term 'rustc' is not recognized...` (Windows) o `rustc: command not found`:** Rust no está instalado o no está en el PATH. Instálalo y reabre la terminal:
  ```powershell
  winget install -e --id Rustlang.Rustup
  # reabre PowerShell y luego:
  rustup default stable-msvc
  ```
  Rust es necesario tanto para nombrar el sidecar como para `npm run build`.

## Cómo funciona con Ollama y los modelos

Igual que la versión Pinokio a nivel de API HTTP: la app habla con Ollama en `127.0.0.1:11434`. Al iniciar: (1) reutiliza un Ollama de sistema **ya en ejecución** si `/api/tags` responde; (2) si no, arranca un Ollama portable ya descargado en el data dir; (3) si no hay binario, descarga el zip (Windows amd64) o tgz/tar.zst (Linux) oficial, extrae y arranca `serve` **sin reiniciar**; (4) hace pull del modelo según RAM (`<6 GB` → `llama3.2:1b`, `6–12 GB` → `llama3.2:3b`, `>12 GB` → `llama3.1:8b`) con progreso en el splash. Al cerrar la ventana se detiene el sidecar y **solo** el Ollama que esta app haya arrancado — nunca un Ollama de sistema que el usuario ya tenía. Requiere internet solo la primera vez; luego funciona 100% local.
