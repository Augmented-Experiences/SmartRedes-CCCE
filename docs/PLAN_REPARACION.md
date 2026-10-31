# Plan de Reparación y Mejoras: SmartRedes

## 1. Corrección de Error Crítico de Arranque
**Problema:** Error `Windows cannot find '{{input.event[0]}}/ui/index.html'` al iniciar el plugin.
**Causa:** En `start.json`, el paso que abre el navegador usa `{{input.event[0]}}` para obtener la URL, pero el evento regex `/(http:\/\/[0-9.:]+)/` no está capturando correctamente o la variable local no se está asignando bien antes de llamar a `browser.open`.
**Solución:** 
- Modificar `start.json` para usar `http://127.0.0.1:{{port}}/ui/index.html` directamente en `browser.open`, eliminando la dependencia de `{{input.event[0]}}` que es frágil.
- Actualizar `pinokio.js` para asegurar que el botón "Abrir UI" también use la URL estática con el puerto.

## 2. Mejoras en la Interfaz de Usuario (UI/UX)
**Objetivo:** Mantener al usuario informado en todo momento, evitando la sensación de que la aplicación está "congelada".

### 2.1. Indicadores de Estado y Carga (Overlay)
- Implementar un `loading-overlay` global (tono gris semitransparente) que se active durante peticiones síncronas (ej. guardar configuraciones, crear marcas).
- Mostrar mensajes amables como "Configurando entorno, por favor espera..." cuando hay procesos en background (ej. descarga de modelos).
- Añadir un banner o notificación persistente en el dashboard cuando la aplicación está "Lista para usar" tras finalizar descargas iniciales.

### 2.2. Progreso Detallado del Escaneo Web
- Modificar `server/web_scraper.py` y `server/app.py` para emitir eventos de progreso durante el análisis web.
- Crear un nuevo endpoint `GET /api/brands/{id}/analyze-status` que devuelva el paso actual (ej. "Extrayendo HTML", "Renderizando JavaScript", "Analizando colores", "Generando ADN").
- En `app/index.html`, actualizar la UI de la tarjeta de marca para mostrar una barra de progreso y el texto del paso actual durante el estado `analyzing`.

## 3. Mejoras en el Backend y Modelos
### 3.1. Descarga Automática de llama3.1:8b
- Modificar `install.json` y `server/app.py` para asegurar que `llama3.1:8b` se descargue por defecto, independientemente de la RAM, ya que es requerido por los agentes `brand_interviewer` y `campaign_strategist`.
- Mantener la lógica de fallback para modelos más ligeros si el usuario lo cambia manualmente, pero el default inicial debe incluir el 8b.

### 3.2. Semáforo de Rendimiento (Inspirado en canirun.ai)
- Crear un endpoint `GET /api/hardware/performance` que evalúe la RAM del sistema (y VRAM si es posible) contra los modelos instalados.
- Implementar una heurística de estimación de tokens por segundo (tok/s) basada en el tamaño del modelo y la RAM disponible.
- En el dashboard (`app/index.html`), añadir un indicador visual (semáforo) junto a cada modelo:
  - 🟢 **RUNS GREAT** (>30 tok/s)
  - 🟡 **DECENT** (10-30 tok/s)
  - 🟠 **TIGHT FIT** (5-10 tok/s)
  - 🔴 **TOO HEAVY** (<5 tok/s)

## 4. Suite de Tests Robustos (Cross-Platform)
- Crear un directorio `tests/` con scripts de prueba automatizados.
- Implementar pruebas unitarias para `server/app.py` y `server/web_scraper.py` usando `pytest`.
- Crear scripts de validación `scripts/test_windows.ps1` y `scripts/test_mac.sh` que verifiquen:
  - Instalación correcta de dependencias.
  - Arranque del servidor FastAPI.
  - Disponibilidad de Ollama.
  - Endpoints críticos (crear marca, iniciar análisis).

## Cronograma de Ejecución
1. **Fase 1:** Corrección de `start.json` y `pinokio.js` (Inmediato).
2. **Fase 2:** Implementación de endpoints de progreso y semáforo en backend.
3. **Fase 3:** Actualización de `app/index.html` con overlays, progreso y semáforo.
4. **Fase 4:** Creación de tests y validación final.
