# Skill: Estrategia de Contenido

## Descripción
Capacidad de definir la estrategia de contenido para cada canal, adaptando mensajes, formatos y tonos según la plataforma y la etapa de la campaña.

## Herramientas Disponibles
- **adapt_for_channel**: Adapta un mensaje base a las convenciones de un canal específico.
- **suggest_format**: Recomienda el formato óptimo (carrusel, video, story, post) según objetivo.
- **generate_hashtags**: Genera hashtags relevantes para el sector y la audiencia.
- **craft_cta**: Crea llamadas a la acción efectivas según la etapa del funnel.

## Flujo de Razonamiento

```
PASO 1: Contextualizar la publicación
- Identificar etapa, canal, objetivo y posición en el arco narrativo
- Log: "[RAZONAMIENTO] Contexto: etapa={etapa}, canal={canal}, objetivo={obj}"

PASO 2: Definir ángulo de contenido
- Elegir el enfoque específico para esta publicación
- Log: "[RAZONAMIENTO] Ángulo: {enfoque}, Diferenciador: {elemento_único}"

PASO 3: Adaptar al canal
- Aplicar convenciones del canal (longitud, tono, formato)
- Log: "[RAZONAMIENTO] Adaptación: longitud={chars}, tono={tono_canal}, formato={formato}"

PASO 4: Generar elementos complementarios
- Crear hashtags, CTA e image_prompt coherentes
- Log: "[RAZONAMIENTO] Hashtags: {n}, CTA: {tipo}, Imagen: {estilo}"

PASO 5: Verificar alineación con ADN
- Confirmar que el contenido respeta la identidad de marca
- Log: "[RAZONAMIENTO] Alineación ADN: tono={ok|ajustado}, personalidad={ok|ajustado}"
```

## Reglas por Canal
- Instagram: visual, emocional, hashtags abundantes (8-15), CTA en bio
- LinkedIn: profesional, datos concretos, casos de éxito, CTA directo
- Facebook: comunidad, conversacional, preguntas abiertas, variedad de formatos
- X (Twitter): conciso (<280 chars), opinático, trending topics, hilos
- WhatsApp: personal, directo, sin hashtags, CTA inmediato, brevedad

## Criterios de Calidad
- Texto listo para publicar (no requiere edición adicional)
- Coherencia con publicaciones anteriores de la campaña
- Progresión clara hacia el objetivo de la etapa
- Image_prompt suficientemente detallado para generación visual
