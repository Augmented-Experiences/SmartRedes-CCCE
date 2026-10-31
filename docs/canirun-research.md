# Investigación canirun.ai — Semáforo de Rendimiento de Modelos

## Concepto Principal
canirun.ai muestra para cada modelo de IA:
- **Nombre del modelo** (ej: Llama 3.1 8B)
- **VRAM requerida** (ej: 4.6 GB)
- **% de VRAM usado** (ej: 4%)
- **Contexto** (ej: 128K ctx)
- **Tokens por segundo estimados** (ej: ~57 tok/s)
- **Calificación/Grado** con color semáforo

## Sistema de Calificación (Semáforo)
| Grado | Color | Score | Significado |
|-------|-------|-------|-------------|
| RUNS GREAT | Verde brillante | 80-100 | Excelente rendimiento |
| RUNS WELL | Verde | 65-79 | Buen rendimiento |
| DECENT | Amarillo | 50-64 | Rendimiento aceptable |
| TIGHT FIT | Naranja | 30-49 | Ajustado, puede ser lento |
| BARELY RUNS | Rojo | 15-29 | Apenas funciona |
| TOO HEAVY | Rojo oscuro | 0-14 | No puede ejecutarse |

## Factores de Hardware Detectados
- GPU (seleccionable)
- VRAM disponible
- Bandwidth de memoria (~GB/s)
- RAM del sistema
- Número de cores

## Fórmula de Estimación de tok/s
La velocidad de tokens se basa en:
- Tamaño del modelo (parámetros en billones)
- VRAM disponible
- Bandwidth de memoria
- Si el modelo cabe completamente en VRAM o necesita offloading a RAM

## Adaptación para SmartRedes
Para nuestro caso, necesitamos:
1. Detectar RAM total del sistema (ya disponible via Pinokio {{ram}})
2. Detectar GPU/VRAM si es posible (via Ollama API o sistema)
3. Estimar tok/s basado en el hardware
4. Mostrar semáforo al lado de cada modelo descargado

### Heurística simplificada para modelos Ollama:
| Modelo | RAM Mín | tok/s (CPU 8GB) | tok/s (CPU 16GB) | tok/s (GPU) |
|--------|---------|-----------------|-------------------|-------------|
| llama3.2:1b | 2GB | ~30 | ~40 | ~80 |
| llama3.2:3b | 4GB | ~15 | ~25 | ~50 |
| llama3.1:8b | 8GB | ~5 | ~15 | ~35 |

### Endpoint necesario: GET /api/hardware/info
Retorna: { ram_gb, gpu_name, vram_gb, cpu_cores, platform }

### Endpoint necesario: GET /api/models/performance
Retorna para cada modelo: { model, estimated_tps, grade, grade_label, grade_color }
