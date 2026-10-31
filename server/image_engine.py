"""
image_engine.py — Motor de generación de imágenes embebido para SmartRedes.

Usa HuggingFace Diffusers con modelos LCM (Latent Consistency Models) que permiten
generar imágenes de calidad en 2-4 pasos en CPU, sin necesidad de GPU.

Modelos soportados (en orden de velocidad/calidad):
  - LCM-Dreamshaper-v7 (SimianLuo/LCM_Dreamshaper_v7): ~512px, 2-4 pasos, ~2-8 min CPU
  - SDXL-Turbo (stabilityai/sdxl-turbo): ~512px, 1 paso, más lento en CPU
  - SD-Turbo (stabilityai/sd-turbo): ~512px, 1 paso, más ligero

El motor descarga el modelo la primera vez (~2-4 GB) y lo cachea en disco.
Las siguientes generaciones son más rápidas porque el modelo ya está en caché.

Compatibilidad: Windows, macOS, Linux (CPU). Con GPU NVIDIA/AMD/Apple Silicon es mucho más rápido.
"""

import io
import logging
import os
import threading
import time
import base64
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("smartredes")

# ─── Constantes ────────────────────────────────────────────────────────────────

# Directorio de caché para modelos descargados
MODELS_CACHE_DIR = Path(os.environ.get(
    "CSS_MODELS_CACHE",
    str(Path.home() / ".cache" / "smartredes" / "models")
))

# Modelo por defecto: LCM-Dreamshaper-v7 (mejor balance velocidad/calidad en CPU)
DEFAULT_DIFFUSION_MODEL = os.environ.get(
    "CSS_DIFFUSION_MODEL",
    "SimianLuo/LCM_Dreamshaper_v7"
)

# Número de pasos de inferencia (menos = más rápido, más = mejor calidad)
DEFAULT_STEPS = int(os.environ.get("CSS_DIFFUSION_STEPS", "4"))

# Resolución de salida (512 es el óptimo para CPU; 768 usa ~2x más RAM)
DEFAULT_WIDTH = int(os.environ.get("CSS_DIFFUSION_WIDTH", "512"))
DEFAULT_HEIGHT = int(os.environ.get("CSS_DIFFUSION_HEIGHT", "512"))

# ─── Estado global del motor ────────────────────────────────────────────────────

_engine_lock = threading.Lock()
_pipeline = None          # Pipeline de diffusers cargado en memoria
_pipeline_model = None    # Nombre del modelo actualmente cargado
_engine_status = {
    "state": "idle",       # idle | loading | ready | error
    "model": None,
    "progress": 0,
    "message": "Motor no iniciado",
    "error": None,
    "loaded_at": None,
}

# ─── Funciones públicas ─────────────────────────────────────────────────────────

def get_engine_status() -> dict:
    """Retorna el estado actual del motor de imagen."""
    return dict(_engine_status)


def is_engine_ready() -> bool:
    """Retorna True si el pipeline está cargado y listo para generar."""
    return _engine_status["state"] == "ready" and _pipeline is not None


def load_engine_async(
    model_id: str = DEFAULT_DIFFUSION_MODEL,
    on_progress: Optional[Callable[[dict], None]] = None
) -> None:
    """Carga el motor de imagen en un hilo background.

    Args:
        model_id: ID del modelo HuggingFace a cargar.
        on_progress: Callback opcional que recibe el estado actualizado.
    """
    def _load():
        _load_pipeline(model_id, on_progress)

    t = threading.Thread(target=_load, daemon=True, name="image-engine-loader")
    t.start()


def generate_image(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, ugly, watermark",
    model_id: str = DEFAULT_DIFFUSION_MODEL,
    steps: int = DEFAULT_STEPS,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    guidance_scale: float = 1.0,
    seed: Optional[int] = None,
) -> dict:
    """Genera una imagen a partir de un prompt de texto.

    Carga el modelo si no está en memoria (puede tardar varios minutos la primera vez).

    Args:
        prompt: Descripción de la imagen a generar.
        negative_prompt: Qué evitar en la imagen.
        model_id: Modelo HuggingFace a usar.
        steps: Pasos de inferencia (2-8 para LCM, 1 para turbo).
        width: Ancho en píxeles.
        height: Alto en píxeles.
        guidance_scale: Escala de guía (1.0 para LCM/turbo, 7.5 para SD clásico).
        seed: Semilla para reproducibilidad (None = aleatorio).

    Returns:
        dict con keys: success, image_b64, generation_time_s, model, steps, error
    """
    global _pipeline, _pipeline_model

    start = time.time()

    # Cargar pipeline si no está listo
    if not is_engine_ready() or _pipeline_model != model_id:
        logger.info(f"[ImageEngine] Cargando modelo {model_id}...")
        _load_pipeline(model_id)

    if not is_engine_ready():
        return {
            "success": False,
            "error": _engine_status.get("error", "Motor no disponible"),
            "image_b64": None,
        }

    try:
        import torch

        logger.info(f"[ImageEngine] Generando imagen: '{prompt[:80]}...' ({steps} pasos, {width}x{height})")

        # Configurar semilla para reproducibilidad
        generator = None
        if seed is not None:
            generator = torch.Generator().manual_seed(seed)

        with _engine_lock:
            # Generar imagen
            result = _pipeline(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=steps,
                width=width,
                height=height,
                guidance_scale=guidance_scale,
                generator=generator,
            )

        image = result.images[0]

        # Convertir PIL Image a base64
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        image_b64 = base64.b64encode(buffer.read()).decode("utf-8")

        elapsed = round(time.time() - start, 1)
        logger.info(f"[ImageEngine] Imagen generada en {elapsed}s")

        return {
            "success": True,
            "image_b64": image_b64,
            "generation_time_s": elapsed,
            "model": model_id,
            "steps": steps,
            "width": width,
            "height": height,
            "error": None,
        }

    except Exception as e:
        logger.error(f"[ImageEngine] Error generando imagen: {e}")
        return {
            "success": False,
            "error": str(e),
            "image_b64": None,
            "generation_time_s": round(time.time() - start, 1),
        }


def unload_engine() -> None:
    """Libera el pipeline de memoria RAM (útil si se necesita memoria para el LLM)."""
    global _pipeline, _pipeline_model
    import gc

    with _engine_lock:
        if _pipeline is not None:
            del _pipeline
            _pipeline = None
            _pipeline_model = None
            gc.collect()
            _update_status("idle", 0, "Motor descargado de memoria", None, None)
            logger.info("[ImageEngine] Pipeline descargado de memoria")


def list_available_models() -> list:
    """Retorna la lista de modelos de imagen disponibles con sus características."""
    return [
        {
            "id": "SimianLuo/LCM_Dreamshaper_v7",
            "name": "LCM Dreamshaper v7",
            "description": "Mejor balance velocidad/calidad en CPU. Genera imágenes artísticas en 2-4 pasos.",
            "steps_recommended": 4,
            "ram_gb": 4,
            "size_gb": 2.1,
            "speed": "rápido",
            "quality": "alta",
            "default": True,
        },
        {
            "id": "stabilityai/sd-turbo",
            "name": "SD Turbo",
            "description": "Modelo ultra-rápido de Stability AI. 1 paso, imágenes fotorrealistas.",
            "steps_recommended": 1,
            "ram_gb": 3,
            "size_gb": 1.9,
            "speed": "muy rápido",
            "quality": "media-alta",
            "default": False,
        },
        {
            "id": "stabilityai/sdxl-turbo",
            "name": "SDXL Turbo",
            "description": "Versión XL de SD Turbo. Mayor resolución y calidad, pero más lento en CPU.",
            "steps_recommended": 1,
            "ram_gb": 8,
            "size_gb": 6.9,
            "speed": "lento en CPU",
            "quality": "muy alta",
            "default": False,
        },
    ]


# ─── Funciones internas ─────────────────────────────────────────────────────────

def _update_status(state: str, progress: int, message: str, model: Optional[str], error: Optional[str]) -> None:
    """Actualiza el estado global del motor."""
    _engine_status.update({
        "state": state,
        "progress": progress,
        "message": message,
        "model": model,
        "error": error,
        "loaded_at": time.time() if state == "ready" else _engine_status.get("loaded_at"),
    })


def _load_pipeline(model_id: str, on_progress: Optional[Callable] = None) -> None:
    """Carga el pipeline de diffusers en memoria.

    Descarga el modelo de HuggingFace si no está en caché local.
    El modelo se guarda en MODELS_CACHE_DIR para evitar re-descargas.
    """
    global _pipeline, _pipeline_model

    if _pipeline is not None and _pipeline_model == model_id:
        logger.info(f"[ImageEngine] Modelo {model_id} ya está cargado")
        return

    _update_status("loading", 5, f"Iniciando carga de {model_id}...", model_id, None)
    if on_progress:
        on_progress(get_engine_status())

    try:
        # Importar dependencias (pueden no estar instaladas)
        try:
            import torch
            from diffusers import DiffusionPipeline, LCMScheduler
        except ImportError as e:
            msg = (
                f"Dependencias de imagen no instaladas: {e}. "
                "Ejecutá: pip install torch diffusers transformers accelerate safetensors"
            )
            _update_status("error", 0, msg, model_id, msg)
            logger.error(f"[ImageEngine] {msg}")
            return

        _update_status("loading", 15, "Dependencias OK. Descargando/cargando modelo...", model_id, None)
        if on_progress:
            on_progress(get_engine_status())

        # Crear directorio de caché
        MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(f"[ImageEngine] Cargando pipeline: {model_id} (caché: {MODELS_CACHE_DIR})")

        # Determinar configuración según el modelo
        is_lcm = "lcm" in model_id.lower() or "dreamshaper" in model_id.lower()
        is_sdxl = "sdxl" in model_id.lower()

        _update_status("loading", 30, "Descargando modelo (puede tardar varios minutos la primera vez)...", model_id, None)
        if on_progress:
            on_progress(get_engine_status())

        # Cargar pipeline
        pipeline_kwargs = {
            "cache_dir": str(MODELS_CACHE_DIR),
            "torch_dtype": torch.float32,  # float32 para CPU (float16 requiere GPU)
            "safety_checker": None,        # Deshabilitar safety checker para velocidad
            "requires_safety_checker": False,
        }

        if is_lcm:
            # LCM usa su propio scheduler optimizado
            pipeline = DiffusionPipeline.from_pretrained(model_id, **pipeline_kwargs)
            pipeline.scheduler = LCMScheduler.from_config(pipeline.scheduler.config)
        else:
            # SD-Turbo y SDXL-Turbo usan EulerAncestralDiscreteScheduler por defecto
            pipeline = DiffusionPipeline.from_pretrained(model_id, **pipeline_kwargs)

        _update_status("loading", 80, "Modelo descargado. Optimizando para CPU...", model_id, None)
        if on_progress:
            on_progress(get_engine_status())

        # Optimizaciones para CPU
        pipeline.enable_attention_slicing()  # Reduce uso de RAM
        try:
            pipeline.enable_vae_slicing()    # Reduce picos de RAM en VAE decode
        except AttributeError:
            pass  # No todos los pipelines lo soportan

        # No mover a GPU (usamos CPU)
        # pipeline.to("cpu")  # Ya está en CPU por defecto

        _update_status("loading", 95, "Calentando modelo (primer paso de inferencia)...", model_id, None)
        if on_progress:
            on_progress(get_engine_status())

        # Warmup: generar imagen pequeña para precompilar el grafo
        logger.info("[ImageEngine] Realizando warmup del modelo...")
        try:
            _ = pipeline(
                prompt="test",
                num_inference_steps=1,
                width=256,
                height=256,
                guidance_scale=1.0,
            )
            logger.info("[ImageEngine] Warmup completado")
        except Exception as warmup_err:
            logger.warning(f"[ImageEngine] Warmup falló (no crítico): {warmup_err}")

        with _engine_lock:
            _pipeline = pipeline
            _pipeline_model = model_id

        _update_status("ready", 100, f"Motor listo con {model_id}", model_id, None)
        if on_progress:
            on_progress(get_engine_status())

        logger.info(f"[ImageEngine] Pipeline {model_id} cargado y listo")

    except Exception as e:
        error_msg = f"Error cargando modelo {model_id}: {e}"
        _update_status("error", 0, error_msg, model_id, error_msg)
        if on_progress:
            on_progress(get_engine_status())
        logger.error(f"[ImageEngine] {error_msg}")
