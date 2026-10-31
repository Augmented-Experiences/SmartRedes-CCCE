# Informe de verificación — SmartRedes

> Nota CCCE: este informe documenta la verificación original del rename a SmartRedes sobre la identidad CCS. La edición SmartRedes-CCCE sustituye esa identidad por el kit visual y la atribución de la Cámara Colombiana de Comercio Electrónico.

**Fecha de validación:** 12 de agosto de 2026

**Repositorio evaluado:** `vtomasv/ccs-brand-assistant`

**Estado final:** **APROBADO**

## Objetivo y alcance

Se verificó y aplicó el cambio integral de nombre del plugin de marketing para PYMEs a **SmartRedes**. La intervención cubre las superficies visibles de Pinokio, la interfaz web, la API, los mensajes del ciclo de vida, los registros internos, las exportaciones, la documentación y las pruebas. La funcionalidad del plugin y la identidad visual corporativa de la Cámara de Comercio de Santiago se preservaron.

| Área revisada | Resultado | Evidencia principal |
|---|---:|---|
| Menú de Pinokio | Aprobado | `pinokio.js` declara `title: "SmartRedes"`. |
| Interfaz web | Aprobado | Título HTML, nombre del sidebar y exportación actualizados a SmartRedes. |
| Ciclo de vida | Aprobado | Mensajes de instalar, iniciar, detener y desinstalar muestran SmartRedes. |
| API y metadatos | Aprobado | FastAPI y OpenAPI anuncian SmartRedes; `plugin_name` usa `smartredes`. |
| Documentación y diagnósticos | Aprobado | README, planes, changelog, dependencias y scripts nombran SmartRedes. |
| Identidad corporativa CCS | Aprobado | Logo, icono, paleta y atribución institucional sin modificaciones. |

> **Criterio de aceptación:** no permanece ninguna referencia visible al nombre anterior del producto en los archivos versionados. La única excepción técnica es la URL del repositorio remoto, que conserva su slug actual hasta que se renombre el repositorio en GitHub.

## Cambios implementados

El nombre se actualizó de forma consistente en `pinokio.js`, `app/index.html`, los scripts `install.json`, `start.json`, `stop.json` y `reset.json`, los módulos Python del servidor, las pruebas, los scripts de diagnóstico y la documentación. Los identificadores de registros, nombres de exportación y caché de imágenes también se trasladaron a `smartredes`.

Se añadió la variable de entorno vigente `SMARTREDES_DATA_DIR`. Para no interrumpir instalaciones existentes, el backend conserva una ruta de compatibilidad que atiende `CCS_DATA_DIR` únicamente cuando la nueva variable no está definida. La precedencia es, por tanto, **SmartRedes primero; configuración heredada después**.

Durante la ejecución de la suite completa se detectó una condición de carrera existente en las escrituras JSON simultáneas. Se corrigió mediante un `threading.Lock` por archivo, complementario al bloqueo asíncrono ya disponible. Esta corrección evita que múltiples escritores compartan el mismo archivo temporal `.tmp` y fue verificada con las pruebas de concurrencia.

| Elemento | Cambio aplicado |
|---|---|
| Nombre presentado | SmartRedes en UI, Pinokio, API, mensajes y documentos. |
| Identificadores técnicos | `smartredes` en logs, exportaciones, caché y metadatos. |
| Persistencia | `SMARTREDES_DATA_DIR` con fallback compatible a la variable anterior. |
| Inicio en Pinokio | Conserva el patrón `local.set` + `{{local.url}}`. |
| Concurrencia | Escrituras JSON síncronas protegidas por bloqueo por archivo. |
| Pruebas nuevas | `tests/test_smartredes_branding.py` con 14 pruebas de regresión. |

## Preservación de la imagen corporativa

Los activos visuales y la paleta corporativa fueron verificados por hash y por tokens CSS. El cambio en las tarjetas de instalación e inicio se limitó a sustituir la inicial mostrada de `B` a `S`, sin alterar colores, gradientes, tamaños ni composición.

| Recurso o regla visual | Verificación | Resultado |
|---|---|---:|
| `icon.png` | SHA-256 `d36c5ae2750ad9e7961692b2e1850a1f2326bc2dcd5f1af1b4fbc9845871d4de` | Sin cambios |
| `app/logo-ccs.svg` | SHA-256 `a5f41aebfe00751cd38351ba69f943a90960255effb9944885cd7d207e38898f` | Sin cambios |
| Paleta CCS | `#0D3DA6`, `#3DAE2B`, `#0D56CA`, `#3A6DDE`, `#0DD700` | Sin cambios |
| Atribución institucional | Logotipo y texto alternativo de la Cámara de Comercio de Santiago | Conservados |

## Pruebas ejecutadas

| Prueba | Resultado | Alcance |
|---|---:|---|
| `pytest -q tests/test_smartredes_branding.py --tb=short` | **14 aprobadas** | Nombre de producto, scripts de Pinokio, API, activos, paleta, almacenamiento y validadores por plataforma. |
| `pytest -q --tb=short` | **268 aprobadas** | Suite funcional completa: API, seguridad, entrevistas, campañas, persistencia, concurrencia y resiliencia LLM. |
| `bash tests/test_mac.sh` | **37/37 aprobadas**; 1 omitida | Validación macOS/Linux, estructura, Pinokio, UI y seguridad. La comprobación dinámica de Ollama se omitió porque no está instalado en el entorno aislado. |
| Compilación estática | **Aprobada** | `python3 -m compileall -q server tests`. |
| Validación de scripts | **Aprobada** | JSON de Pinokio válido y sintaxis de `pinokio.js` comprobada. |
| Calidad de cambios | **Aprobada** | `git diff --check` sin errores de formato. |
| Validación HTTP temporal | **Aprobada** | `/api/health`, `/openapi.json`, `/ui/index.html` y `/api/readiness` respondieron localmente. |

La validación HTTP arrancó SmartRedes con un directorio de datos temporal y confirmó que la API declara **SmartRedes** en OpenAPI, que la interfaz muestra el nuevo nombre y que continúa enlazando el logotipo corporativo. La ausencia de Ollama se comunicó correctamente como falta de disponibilidad de modelos, sin impedir el inicio, la salud de la API ni la interfaz.

## Advertencias y limitaciones conocidas

La suite completa finalizó sin fallos. Se emitieron **464 advertencias de deprecación** relacionadas principalmente con `FastAPI.on_event` y `datetime.utcnow()`. No son regresiones del cambio de nombre ni afectan al funcionamiento validado, pero constituyen una mejora técnica recomendable para una futura versión.

La suite de Windows fue actualizada para validar el patrón vigente de Pinokio (`local.set` y `kernel.memory.local`). No fue posible ejecutarla directamente porque el entorno de validación no dispone de PowerShell. Su contenido fue validado estáticamente desde la suite de regresión de SmartRedes. La validación ejecutable de macOS/Linux sí se completó correctamente.

La URL `https://github.com/vtomasv/ccs-brand-assistant` permanece en el README como referencia técnica al remoto existente. No aparece como nombre visible del producto. Si se desea que la URL coincida también con SmartRedes, será necesario renombrar explícitamente el repositorio remoto y actualizar esos dos enlaces.

## Conclusión

El plugin está preparado para identificarse como **SmartRedes** en todas sus superficies de producto y conserva íntegramente la imagen corporativa preexistente. Las verificaciones automáticas, funcionales y de ejecución local concluyeron satisfactoriamente, incluida la corrección de la concurrencia de persistencia revelada durante las pruebas.

**Dictamen final: SmartRedes funciona correctamente después del cambio de nombre.**
