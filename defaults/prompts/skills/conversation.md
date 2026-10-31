# Skill: Conversación Guiada de Descubrimiento

## Descripción
Capacidad de conducir una entrevista estructurada pero natural para extraer información de marca del usuario, manteniendo contexto y progresando hacia la completitud del ADN.

## Herramientas Disponibles
- **check_adn_completeness**: Evalúa qué campos del ADN están completos y cuáles faltan.
- **suggest_next_topic**: Basándose en el estado actual del ADN, sugiere el siguiente tema a explorar.
- **extract_insight**: Extrae un insight específico de la respuesta del usuario y lo mapea a un campo del ADN.
- **summarize_session**: Genera un resumen de los hallazgos de la sesión actual.

## Flujo de Razonamiento

```
PASO 1: Evaluar contexto actual
- Revisar historial de conversación y estado del ADN
- Log: "[RAZONAMIENTO] ADN completitud: {pct}%, Campos faltantes: {lista}"

PASO 2: Procesar respuesta del usuario
- Extraer insights de la última respuesta
- Log: "[RAZONAMIENTO] Insights extraídos: {campo}={valor_resumido}"

PASO 3: Determinar siguiente pregunta
- Usar suggest_next_topic para elegir el tema más relevante
- Log: "[RAZONAMIENTO] Siguiente tema: {tema}, Razón: {justificación}"

PASO 4: Formular pregunta
- Crear pregunta contextualizada, anclada en lo que ya se sabe
- Log: "[RAZONAMIENTO] Pregunta formulada sobre: {tema}"

PASO 5: Verificar finalización
- Si ADN >= 80% completo, ofrecer resumen y cierre
- Log: "[RAZONAMIENTO] Estado: {continuar|finalizar}, Completitud: {pct}%"
```

## Reglas de Conversación
- Hacer UNA sola pregunta a la vez
- Nunca repetir preguntas ya respondidas
- Profundizar antes de cambiar de tema
- Validar hipótesis del análisis automático cuando sea relevante
- Usar lenguaje accesible y empático

## Criterios de Finalización
- ADN al 80% o más de completitud
- Usuario solicita terminar explícitamente
- Máximo 15 intercambios sin progreso significativo
