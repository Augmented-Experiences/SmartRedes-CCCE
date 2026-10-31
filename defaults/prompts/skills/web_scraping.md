# Skill: Web Scraping para Análisis de Marca

## Descripción
Capacidad de extraer y procesar contenido de sitios web para análisis de identidad de marca.

## Herramientas Disponibles
- **fetch_html**: Descarga el HTML de una URL y retorna el contenido textual limpio.
- **extract_meta**: Extrae meta tags (Open Graph, Twitter Cards, JSON-LD) del HTML.
- **extract_colors**: Analiza CSS inline y hojas de estilo para detectar paleta de colores.
- **extract_fonts**: Detecta tipografías declaradas en CSS y Google Fonts.

## Flujo de Razonamiento

```
PASO 1: Validar URL
- Verificar que la URL es accesible y segura (no localhost, no IPs privadas)
- Log: "[RAZONAMIENTO] Validando URL: {url} → {resultado}"

PASO 2: Extraer contenido
- Usar fetch_html para obtener el contenido textual
- Log: "[RAZONAMIENTO] Contenido extraído: {n_caracteres} caracteres"

PASO 3: Analizar meta tags
- Usar extract_meta para obtener OG, Twitter Cards, JSON-LD
- Log: "[RAZONAMIENTO] Meta tags encontrados: {lista_tags}"

PASO 4: Detectar identidad visual
- Usar extract_colors y extract_fonts
- Log: "[RAZONAMIENTO] Colores detectados: {colores}, Fuentes: {fuentes}"

PASO 5: Sintetizar ADN
- Combinar toda la información en el formato JSON de ADN
- Log: "[RAZONAMIENTO] Campos del ADN completados: {n_campos}/{total_campos}"
```

## Restricciones
- Timeout máximo por request: 30 segundos
- Tamaño máximo de contenido procesado: 50KB
- No seguir redirecciones a dominios diferentes al original
- Respetar robots.txt cuando sea posible

## Formato de Salida
JSON con los campos del ADN empresarial según el schema definido.
