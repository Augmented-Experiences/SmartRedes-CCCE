# Skill: Planificación de Campañas

## Descripción
Capacidad de diseñar la estructura temporal y narrativa de campañas de marketing digital, distribuyendo contenido de forma estratégica a lo largo del tiempo.

## Herramientas Disponibles
- **calculate_slots**: Genera la distribución de fechas y canales según frecuencia y duración.
- **design_narrative_arc**: Crea el arco narrativo de la campaña (etapas progresivas).
- **assign_objectives**: Asigna objetivos tácticos a cada etapa de la campaña.
- **validate_calendar**: Verifica que el calendario no tenga conflictos ni vacíos.

## Flujo de Razonamiento

```
PASO 1: Analizar parámetros de campaña
- Procesar fechas, canales, frecuencia, objetivo y audiencia
- Log: "[RAZONAMIENTO] Campaña: {días} días, {n_canales} canales, frecuencia={freq}"

PASO 2: Calcular slots de publicación
- Usar calculate_slots para generar el calendario base
- Log: "[RAZONAMIENTO] Slots calculados: {n_total} publicaciones en {n_días} días"

PASO 3: Diseñar arco narrativo
- Crear etapas progresivas adaptadas a la duración
- Log: "[RAZONAMIENTO] Etapas: {lista_etapas} con distribución {pcts}"

PASO 4: Asignar contenido por etapa
- Distribuir publicaciones entre etapas según peso narrativo
- Log: "[RAZONAMIENTO] Distribución: {etapa1}={n1}, {etapa2}={n2}, ..."

PASO 5: Generar publicaciones por lote
- Crear contenido respetando ADN, canal y etapa
- Log: "[RAZONAMIENTO] Lote {n}/{total}: {n_pubs} publicaciones para {etapa}"

PASO 6: Validar coherencia global
- Verificar progresión narrativa y variedad de contenido
- Log: "[RAZONAMIENTO] Validación: coherencia={ok|warning}, variedad={ok|warning}"
```

## Principios de Planificación
- Narrativa progresiva (no publicaciones aisladas)
- Adaptación por canal (Instagram visual, LinkedIn profesional, etc.)
- Evolución del CTA (de awareness a conversión)
- Variedad de formatos dentro de cada canal
- Respeto estricto del ADN de marca en todo el contenido

## Restricciones
- Máximo 30 días de campaña
- Máximo 5 publicaciones por lote de generación
- Cada publicación debe tener texto, hashtags, CTA e image_prompt
