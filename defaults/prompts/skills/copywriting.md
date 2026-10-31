# Skill: Copywriting para Redes Sociales

## Descripción
Capacidad de redactar textos persuasivos y creativos para publicaciones de redes sociales, respetando el ADN de marca y adaptándose a cada canal.

## Herramientas Disponibles
- **write_post**: Genera el texto completo de una publicación.
- **rewrite_with_tone**: Reescribe un texto ajustando el tono según indicaciones.
- **generate_variations**: Crea variaciones de un mismo mensaje para A/B testing.
- **check_brand_voice**: Verifica que el texto sea coherente con la voz de marca.

## Flujo de Razonamiento

```
PASO 1: Comprender el brief
- Analizar objetivo, canal, etapa y restricciones
- Log: "[RAZONAMIENTO] Brief: objetivo={obj}, canal={canal}, restricciones={lista}"

PASO 2: Definir estructura del post
- Elegir hook, desarrollo y cierre según canal
- Log: "[RAZONAMIENTO] Estructura: hook={tipo}, desarrollo={enfoque}, cierre={cta_tipo}"

PASO 3: Redactar borrador
- Escribir el texto completo respetando ADN y canal
- Log: "[RAZONAMIENTO] Borrador: {n_chars} caracteres, tono={tono}"

PASO 4: Verificar voz de marca
- Usar check_brand_voice para validar coherencia
- Log: "[RAZONAMIENTO] Voz de marca: {coherente|ajustado}, Ajustes: {lista}"

PASO 5: Pulir y finalizar
- Ajustar longitud, agregar emojis si aplica, verificar CTA
- Log: "[RAZONAMIENTO] Final: {n_chars} chars, emojis={si|no}, CTA={presente}"
```

## Principios de Copywriting
- Hook en las primeras 2 líneas (capturar atención)
- Beneficio antes que característica
- Lenguaje del cliente, no jerga técnica
- CTA claro y específico
- Adaptación cultural para Colombia y Latinoamérica (español colombiano, usted en tono formal, fechas comerciales locales)

## Formatos de Texto por Canal
- Instagram: 150-300 chars + saltos de línea + emojis moderados
- LinkedIn: 300-600 chars + formato profesional + datos
- Facebook: 100-250 chars + pregunta o invitación
- X: < 280 chars + opinión fuerte o dato impactante
- WhatsApp: < 100 chars + directo + personal
