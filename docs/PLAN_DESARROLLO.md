# Plan de Desarrollo Detallado — SmartRedes

**Versión:** 0.1.0  
**Fecha:** Marzo 2025  
**Proyecto:** CCCE — Plugins de IA local para PYMEs

---

## 1. Visión del producto

SmartRedes es un plugin de Pinokio que permite a las PYMEs construir y operar una máquina de marketing asistida por inteligencia artificial completamente local. El diferenciador central no es la generación de contenido en volumen, sino la **coherencia estratégica**: todo el contenido nace de un perfil estructurado de identidad de marca —el ADN empresarial— que el sistema construye, versiona y utiliza como fuente de verdad para todas las piezas posteriores.

El sistema opera sobre cuatro pilares funcionales que se ejecutan en secuencia: descubrimiento de marca, construcción del ADN, planificación de campañas y producción de contenido. Cada pilar tiene su propio agente especializado con prompts configurables y trazabilidad completa.

---

## 2. Arquitectura técnica

### 2.1 Stack tecnológico

| Capa | Tecnología | Justificación |
|------|-----------|---------------|
| Frontend | HTML + CSS + JavaScript vanilla | Máxima compatibilidad con el webview de Electron de Pinokio; sin dependencias de build |
| Backend | FastAPI (Python) | Async nativo, tipado con Pydantic, ideal para APIs con procesamiento en background |
| IA local | Ollama + LLaMA 3.x | Modelos de código abierto con excelente relación calidad/recursos para PYMEs |
| Persistencia | JSON en disco | Sin base de datos externa; compatible con el modelo de datos local de Pinokio |
| Web scraping | BeautifulSoup4 + requests | Extracción de texto de sitios web sin dependencias pesadas |

### 2.2 Flujo de datos

El flujo de procesamiento de una nueva marca sigue este pipeline:

```
Usuario ingresa URL
       ↓
Agente analizador (brand_analyzer)
  → Scraping del sitio web
  → Extracción de señales de identidad
  → Generación de borrador de ADN (JSON)
       ↓
Agente entrevistador (brand_interviewer)
  → Preguntas contextuales basadas en el borrador
  → Respuestas del usuario refinan el ADN
  → Sesión persistida en disco
       ↓
ADN aprobado y versionado
       ↓
Agente estratega (campaign_strategist)
  → Recibe ADN + objetivos de campaña
  → Genera planificación temporal con etapas
  → Produce publicaciones por canal
       ↓
Agente redactor (content_writer)
  → Mejora o regenera publicaciones individuales
  → Respeta ADN y etapa narrativa
       ↓
Calendario poblado → Revisión y publicación manual
```

### 2.3 Estructura de datos

**Marca (`data/brands/{id}/brand.json`)**

```json
{
  "id": "uuid",
  "name": "Nombre de la marca",
  "website": "https://...",
  "sector": "retail",
  "language": "es",
  "onboarding_status": "complete",
  "adn_version": "1.0",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

**ADN empresarial (`data/brands/{id}/adn.json`)**

```json
{
  "id": "uuid",
  "brand_id": "uuid",
  "version": "1.0",
  "status": "approved",
  "fields": {
    "value_proposition": "...",
    "tone": "...",
    "personality_traits": ["..."],
    "target_audience": "...",
    "differentiators": ["..."],
    "color_palette": ["..."],
    "content_themes": ["..."]
  }
}
```

**Campaña (`data/campaigns/{brand_id}_{id}/campaign.json`)**

```json
{
  "id": "uuid",
  "brand_id": "uuid",
  "adn_version": "1.0",
  "name": "...",
  "objective": "awareness",
  "channels": ["Instagram", "LinkedIn"],
  "start_date": "2025-03-01",
  "end_date": "2025-03-15",
  "status": "active",
  "publications_count": 18
}
```

---

## 3. Módulos funcionales y estado de implementación

### 3.1 Módulo de Marcas

**Estado: Implementado (v0.1)**

Permite crear, listar, actualizar y eliminar marcas. Cada marca tiene un estado de onboarding que evoluciona a lo largo del flujo: `pending → analyzing → interviewing → complete`. La UI muestra tarjetas visuales con el estado actual y acciones disponibles según el estado.

**Pendiente para v0.2:**
- Importación de marcas desde archivo CSV
- Duplicación de marca con nuevo ADN
- Archivado de marcas inactivas

### 3.2 Módulo de Análisis de Sitio Web

**Estado: Implementado (v0.1)**

El análisis se ejecuta en background usando FastAPI `BackgroundTasks`. El agente `brand_analyzer` recibe el texto extraído del sitio y produce un JSON con los campos del ADN. La UI hace polling cada 5 segundos para detectar cuando el análisis termina.

**Limitaciones actuales:**
- El scraping es básico (solo texto visible de las primeras páginas)
- No extrae imágenes ni paleta de colores real
- No maneja sitios con JavaScript pesado (SPAs)

**Pendiente para v0.2:**
- Scraping con Playwright para sitios JavaScript
- Extracción real de paleta de colores de imágenes
- Análisis de múltiples páginas del sitio (hasta 10)

### 3.3 Módulo de ADN Empresarial

**Estado: Implementado (v0.1)**

El ADN se construye en dos etapas: inferencia automática del sitio web y refinamiento por entrevista. Soporta versionado: cada aprobación crea una versión oficial y archiva la anterior. Los campos son editables individualmente desde la UI.

**Pendiente para v0.2:**
- Editor visual de campos del ADN con validación
- Comparación entre versiones del ADN
- Exportación del ADN en PDF para presentaciones

### 3.4 Módulo de Entrevista Guiada

**Estado: Implementado (v0.1)**

La entrevista es una conversación con el agente `brand_interviewer`. El historial se persiste en disco por sesión. El agente recibe el ADN borrador como contexto y formula preguntas progresivas.

**Pendiente para v0.2:**
- Extracción automática de insights de las respuestas para actualizar el ADN
- Indicador de progreso de completitud del ADN
- Modo de revisión rápida para ADN ya construidos

### 3.5 Módulo de Campañas

**Estado: Implementado (v0.1)**

La creación de campañas dispara la generación en background. El agente `campaign_strategist` recibe el ADN y los parámetros de la campaña y produce un plan con etapas narrativas y publicaciones por canal. La UI hace polling para mostrar el progreso.

**Pendiente para v0.2:**
- Generación de imágenes para cada publicación
- Exportación de campaña completa en PDF
- Duplicación de campañas exitosas
- Plantillas de campaña por objetivo y sector

### 3.6 Módulo de Calendario y Publicaciones

**Estado: Implementado (v0.1)**

Vista de lista de publicaciones filtrable por canal y estado. Editor modal con simulación visual del post, edición de texto/hashtags/CTA y regeneración asistida con instrucción libre.

**Pendiente para v0.2:**
- Vista de calendario mensual real (grid 7x5)
- Drag & drop para reprogramar publicaciones
- Copia masiva de publicaciones al portapapeles
- Descarga de imagen generada

### 3.7 Módulo de Agentes

**Estado: Implementado (v0.1)**

Panel para ver y editar los system prompts de cada agente. Los cambios se persisten en disco y se aplican en la próxima llamada al agente sin reiniciar el servidor.

**Pendiente para v0.2:**
- Asignación y revocación de skills por agente
- Selección de modelo por agente (no solo global)
- Historial de versiones de prompts
- Test de prompt desde la UI

### 3.8 Módulo de Auditoría

**Estado: Implementado (v0.1)**

Registro en formato JSONL de todas las operaciones de agentes: agente, tarea, modelo, entradas, salida, latencia y estado. La UI muestra una tabla de los últimos 100 registros.

**Pendiente para v0.2:**
- Filtros por agente, fecha y estado
- Exportación de logs en CSV
- Alertas de latencia alta o errores frecuentes

---

## 4. Tareas pendientes por prioridad

### Prioridad Alta (v0.2 — próxima iteración)

| Tarea | Módulo | Esfuerzo estimado |
|-------|--------|------------------|
| Generación de imágenes con Stable Diffusion local | Publicaciones | Alto |
| Extracción de paleta de colores real del sitio web | Análisis web | Medio |
| Exportación de campaña en PDF | Campañas | Medio |
| Vista de calendario mensual (grid) | Calendario | Medio |
| Actualización automática del ADN desde entrevista | ADN | Medio |
| Selección de modelo por agente | Agentes | Bajo |

### Prioridad Media (v0.3)

| Tarea | Módulo | Esfuerzo estimado |
|-------|--------|------------------|
| Soporte multi-usuario con roles | Sistema | Alto |
| Dashboard de métricas de ejecución | Dashboard | Medio |
| Biblioteca de activos visuales | Marcas | Medio |
| Plantillas de campaña por sector | Campañas | Bajo |
| Historial de versiones de prompts | Agentes | Bajo |

### Prioridad Baja (v1.0)

| Tarea | Módulo | Esfuerzo estimado |
|-------|--------|------------------|
| Integración con APIs de redes sociales | Sistema | Muy alto |
| Analítica de performance real | Dashboard | Alto |
| Aprendizaje basado en resultados | IA | Muy alto |
| Soporte multiidioma completo | UI | Medio |

---

## 5. Reglas de negocio críticas

Las siguientes reglas están implementadas en el backend y deben mantenerse en todas las versiones:

Una campaña no puede existir sin una marca asociada. El endpoint de creación de campaña verifica la existencia de la marca antes de proceder.

Una campaña debe referenciar una versión del ADN. Si la marca no tiene ADN (ni borrador ni aprobado), la creación de campaña retorna error 400.

Las publicaciones derivan de una campaña y un canal específico. No pueden existir publicaciones huérfanas.

Toda regeneración de una pieza preserva el historial de versiones anteriores en el campo `previous_versions`.

Los prompts editables se versionan en disco. Cada cambio sobreescribe el archivo `.md` del agente, pero el historial puede implementarse en v0.3.

El estado de publicación real es siempre manual. No existe publicación automática en redes en v0.1.

---

## 6. Checklist de calidad pre-release

Antes de cada release, verificar los siguientes puntos según el checklist del skill de Pinokio:

| Verificación | Estado v0.1 |
|-------------|-------------|
| Scripts de ciclo de vida son `.json` (no `.js`) | ✓ |
| `pinokio.js` apunta a archivos `.json` | ✓ |
| No hay `background: true` en ningún script | ✓ |
| Nombre del venv es consistente (`venv`) | ✓ |
| Rutas del servidor Python son absolutas | ✓ |
| Servidor crea directorios de datos al arrancar | ✓ |
| Todas las funciones JS están definidas en scope global | ✓ |
| No hay `let`/`const`/`import`/`export` en la UI | ✓ |
| `init()` se llama al final del script | ✓ |
| El servidor sirve la UI en `/ui/index.html` | ✓ |

---

## 7. Notas de arquitectura para futuras iteraciones

**Generación de imágenes.** La especificación menciona VLLM para generación visual local. La integración recomendada es con Stable Diffusion via AUTOMATIC1111 o ComfyUI, que Pinokio ya soporta como plugins separados. El agente `content_writer` ya genera `image_prompt` para cada publicación; la integración visual solo requiere conectar ese prompt al motor de imágenes.

**Scraping avanzado.** Para sitios con JavaScript pesado, la solución recomendada es Playwright (disponible en Python). Requiere instalación adicional en `install.json` pero mejora significativamente la calidad del análisis para sitios modernos.

**Procesamiento asíncrono.** El modelo actual usa `BackgroundTasks` de FastAPI, que es suficiente para v0.1. En versiones futuras con múltiples usuarios o campañas largas, se recomienda migrar a una cola de tareas como Celery con Redis, o usar el sistema de jobs de Pinokio.

**Persistencia.** El modelo JSON en disco es simple y efectivo para un único usuario. Si se agrega soporte multi-usuario, se recomienda migrar a SQLite con SQLAlchemy, que mantiene la filosofía local sin requerir un servidor de base de datos.
