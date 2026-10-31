# Skill: Análisis de Identidad de Marca

## Descripción
Capacidad de interpretar señales de identidad de marca a partir de contenido textual y visual, generando un ADN empresarial estructurado.

## Herramientas Disponibles
- **parse_brand_signals**: Identifica señales de marca en texto (tono, propuesta de valor, personalidad).
- **classify_sector**: Determina el sector/industria basándose en productos y servicios detectados.
- **analyze_tone**: Evalúa el tono comunicacional (formal, cercano, técnico, inspiracional).
- **detect_audience**: Infiere el público objetivo a partir del contenido y estilo.

## Flujo de Razonamiento

```
PASO 1: Identificar señales primarias
- Buscar propuesta de valor explícita, misión, visión
- Log: "[RAZONAMIENTO] Señales primarias: propuesta_valor={encontrada|no}, misión={encontrada|no}"

PASO 2: Clasificar sector y audiencia
- Usar classify_sector y detect_audience
- Log: "[RAZONAMIENTO] Sector inferido: {sector}, Audiencia: {audiencia}"

PASO 3: Analizar personalidad de marca
- Identificar adjetivos y atributos de personalidad
- Log: "[RAZONAMIENTO] Rasgos de personalidad detectados: {rasgos}"

PASO 4: Evaluar tono y formalidad
- Usar analyze_tone para determinar el registro comunicacional
- Log: "[RAZONAMIENTO] Tono: {tono}, Formalidad: {nivel}"

PASO 5: Detectar diferenciadores
- Identificar qué hace única a la marca vs competencia
- Log: "[RAZONAMIENTO] Diferenciadores clave: {lista}"

PASO 6: Compilar ADN completo
- Ensamblar todos los campos en el formato JSON estándar
- Log: "[RAZONAMIENTO] ADN compilado: {n_campos} campos con contenido, {n_vacios} vacíos"
```

## Criterios de Calidad
- Cada campo debe tener contenido significativo (no "No detectado" si hay evidencia)
- Los campos tipo lista deben tener al menos 2-3 elementos
- La propuesta de valor debe ser una oración completa y diferenciadora
- El tono debe ser consistente con los ejemplos de contenido analizados

## Formato de Salida
JSON estricto con los 13 campos del ADN empresarial.
