# SmartRedes

**Asistente de ADN de marca y campañas digitales con IA local para PYMEs**

> Un producto de la **Cámara Colombiana de Comercio Electrónico (CCCE)**, adaptado a la realidad comercial y de redes de Colombia.

SmartRedes permite a las pequeñas y medianas empresas construir una identidad de marca estructurada —el **ADN empresarial**— y usarla para planificar campañas de marketing digital multicanal. La inteligencia artificial corre en el computador del usuario, sin dependencia de servicios en la nube.

## Adaptación Colombia (CCCE)

SmartRedes-CCCE parte de SmartRedes-CCS y se ajusta a la operación de una PYME colombiana:

- Mercados por defecto: **Colombia**, Perú, México y LatAm
- Idioma: **español** para audiencia colombiana
- Zona horaria de publicación: **COT (UTC-5)**
- Calendario comercial: Semana Santa, Día de la Madre, Amor y Amistad, Cyberlunes/HotSale, Independencia (20 de julio), Boyacá (7 de agosto) y Navidad
- Montos y ofertas en **COP** cuando la campaña habla de precios
- Identidad visual: kit CCCE (azul `#173A7A`, rojo `#CE1126`, dorado `#F4C10E`)

## Características principales

**Módulo de Marcas.** Permite registrar y gestionar múltiples marcas con sus datos básicos: nombre, sitio web, sector, mercados objetivo e idioma. Cada marca tiene su propio espacio de trabajo semiaislado con historial, ADN y campañas independientes.

**Análisis automático de sitio web.** A partir de la URL de la marca, el agente analizador extrae señales de identidad: propuesta de valor, tono comunicacional, paleta de colores, estilo visual, productos y servicios, y público objetivo.

**Entrevista guiada por agente.** Un agente especializado en marketing conduce una conversación de descubrimiento para refinar el ADN. Las preguntas son contextuales, progresivas y ancladas en lo que el sistema ya sabe de la marca.

**ADN empresarial versionado.** El ADN es un objeto semiestructurado con campos claros: propuesta de valor, tono, personalidad, paleta, tipografía, público objetivo, diferenciadores, restricciones y más.

**Generación de campañas con IA.** El agente estratega toma el ADN y los objetivos de negocio para construir una planificación temporal con etapas narrativas y publicaciones concretas por canal.

**Generación de imágenes con IA local.** Motor embebido (HuggingFace Diffusers) compatible con Windows, macOS y Linux. Soporta LCM Dreamshaper v7, SD Turbo y SDXL Turbo. En el instalador de escritorio este motor se omite para mantener el paquete liviano.

## Arquitectura

```
smartredes/
├── pinokio.js          # Configuración y menú dinámico del plugin
├── install.json        # Instalación con 1 click (Ollama + venv + deps)
├── start.json          # Inicio del servidor como daemon
├── stop.json           # Parada del servidor
├── reset.json          # Desinstalación (conserva datos)
├── requirements.txt    # Dependencias Python
├── scripts/            # Scripts PowerShell para Windows
├── app/
│   ├── index.html      # Frontend SPA (HTML + CSS + JS vanilla)
│   ├── logo-ccce.png   # Wordmark de la Cámara Colombiana de Comercio Electrónico
│   └── fonts/          # Fuentes DM Sans, Feeling Passionate, Brushwell
├── server/
│   ├── app.py          # Backend FastAPI con todos los módulos
│   └── image_engine.py # Motor de generación de imágenes (Diffusers)
├── defaults/
│   ├── agents.json
│   └── prompts/
├── desktop/            # Instalador Tauri (SmartSuite CCCE)
└── data/               # Datos del usuario (persistentes)
```

## Requisitos del sistema

| Componente | Mínimo | Recomendado |
|-----------|--------|-------------|
| RAM | 4 GB | 8 GB o más |
| Almacenamiento | 5 GB libres | 10 GB libres |
| Python | 3.9+ | 3.11+ |
| Pinokio | Última versión | Última versión |
| Ollama | Opcional | Recomendado |

El modelo de texto se selecciona automáticamente según la RAM disponible:

| RAM disponible | Modelo instalado |
|---------------|-----------------|
| Menos de 6 GB | `llama3.2:1b` |
| 6 a 12 GB | `llama3.2:3b` |
| Más de 12 GB | `llama3.1:8b` |

## Instalación

### Instalador de escritorio (recomendado)

El release es el instalador nativo (Windows `.exe` / macOS `.dmg`), armado desde `desktop/`. Al abrirlo, la app descarga Ollama portable y el modelo de texto según la RAM. Los datos quedan en la carpeta local de SmartRedes.

Para compilarlo en esta máquina: `desktop/WINDOWS-BUILD.md` y `desktop/README.md`.

### Vía Pinokio

1. Abre **Pinokio** en tu computador.
2. Ve a la sección de descarga de plugins.
3. Ingresa la URL de este repositorio.
4. Haz click en **Instalar**. El proceso es completamente automático.
5. Una vez instalado, haz click en **Iniciar**.

### Manual

```bash
git clone https://github.com/Augmented-Experiences/SmartRedes-CCCE.git
cd SmartRedes-CCCE
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python server/app.py --port 7860
```

## Uso básico

**Paso 1 — Crear la marca.** Ve a la sección Marcas y haz clic en "Nueva Marca".

**Paso 2 — Analizar el sitio web.** Desde la tarjeta de la marca, haz clic en "Analizar web".

**Paso 3 — Entrevista de descubrimiento.** Ve a "Entrevista IA" y responde las preguntas del agente.

**Paso 4 — Aprobar el ADN.** Ve a "ADN de Marca" y haz clic en "Aprobar ADN".

**Paso 5 — Crear una campaña.** Ve a "Campañas" y haz clic en "Nueva Campaña".

**Paso 6 — Revisar y publicar.** Abre el calendario para ver y editar las publicaciones.

## Instalador de escritorio (SmartSuite / Tauri)

El kit **SmartSuite** está en `desktop/` (Tauri + splash + sidecar PyInstaller), configurado vía `desktop/smartsuite.config.json`.

- Dependencias del sidecar: `requirements-desktop.txt` (sin `diffusers`, `torch` ni `playwright`).
- Build local: ver `desktop/README.md` y `desktop/WINDOWS-BUILD.md`.
- CI opcional: workflow `.github/workflows/desktop-build.yml` (tags `v*` o manual).

## Privacidad y seguridad

- **100% offline** después de la primera descarga de modelos
- **Sin telemetría**: no se envían datos a servidores externos
- **Datos locales**: marcas, ADN y campañas quedan en la carpeta de datos de la app
- **Código abierto**: todo el código es auditable

## Licencia

MIT License

## Créditos

Desarrollado para la **Cámara Colombiana de Comercio Electrónico (CCCE)** como parte del programa de digitalización de PYMEs con inteligencia artificial local.
