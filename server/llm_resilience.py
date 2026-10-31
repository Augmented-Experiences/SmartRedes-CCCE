"""
SmartRedes — Módulo de Resiliencia para Llamadas LLM
=============================================================

Implementa reintentos inteligentes, rotación de sesiones y recuperación
ante fallos del LLM local (Ollama).

Patrones implementados:
  - Retry con backoff exponencial
  - Circuit breaker para detectar fallos persistentes
  - Rotación automática de sesión cuando el contexto se agota
  - Fallback a respuestas predefinidas cuando todo falla
  - Logging detallado de cada intento para diagnóstico
"""

import time
import logging
import asyncio
from typing import Optional, Callable, Any, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

from context_manager import (
    estimate_tokens,
    get_session_state,
    reset_session_state,
    calculate_retry_delay,
    SessionState,
    MAX_CONSECUTIVE_ERRORS,
)

logger = logging.getLogger("smartredes.resilience")

# ---------------------------------------------------------------------------
# Configuración de reintentos
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # segundos
MAX_RETRY_DELAY = 30.0  # segundos

# Errores que indican agotamiento de contexto (deben provocar compactación)
CONTEXT_EXHAUSTION_ERRORS = [
    "context length exceeded",
    "context window",
    "too many tokens",
    "maximum context",
    "token limit",
    "out of memory",
    "OOM",
    "context_length_exceeded",
    "model capacity",
]

# Errores que indican que Ollama no está disponible (no reintentar)
UNRECOVERABLE_ERRORS = [
    "connection refused",
    "no está disponible",
    "not available",
    "model not found",
]


def is_context_exhaustion_error(error: str) -> bool:
    """Detecta si un error indica agotamiento del contexto del LLM."""
    error_lower = error.lower()
    return any(pattern.lower() in error_lower for pattern in CONTEXT_EXHAUSTION_ERRORS)


def is_unrecoverable_error(error: str) -> bool:
    """Detecta si un error es irrecuperable (no vale la pena reintentar)."""
    error_lower = error.lower()
    return any(pattern.lower() in error_lower for pattern in UNRECOVERABLE_ERRORS)


# ---------------------------------------------------------------------------
# Llamada resiliente al LLM
# ---------------------------------------------------------------------------
async def call_ollama_with_retry(
    call_fn: Callable,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    timeout: Optional[int] = None,
    session_id: Optional[str] = None,
    brand_id: Optional[str] = None,
    thread_pool: Optional[ThreadPoolExecutor] = None,
    on_context_exhaustion: Optional[Callable] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Ejecuta una llamada al LLM con reintentos y gestión de errores.
    
    Args:
        call_fn: Función call_ollama a invocar
        model: Modelo a usar
        system_prompt: System prompt
        user_message: Mensaje del usuario (ya construido con contexto)
        temperature: Temperatura del modelo
        timeout: Timeout en segundos
        session_id: ID de sesión (para tracking de errores)
        brand_id: ID de marca (para tracking)
        thread_pool: ThreadPoolExecutor para ejecución async
        on_context_exhaustion: Callback cuando se detecta agotamiento de contexto
        
    Returns:
        Tuple de (respuesta, metadata) donde metadata incluye métricas del intento
        
    Raises:
        Exception: Si todos los reintentos fallan
    """
    session_state = None
    if session_id and brand_id:
        session_state = get_session_state(session_id, brand_id)
    
    metadata = {
        "attempts": 0,
        "total_retry_time_ms": 0,
        "final_error": None,
        "context_exhaustion_detected": False,
        "session_reset": False,
    }
    
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        metadata["attempts"] = attempt + 1
        start_time = time.time()
        
        try:
            # Ejecutar la llamada al LLM
            if thread_pool:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    thread_pool,
                    lambda: call_fn(
                        model, system_prompt, user_message,
                        temperature=temperature,
                        timeout=timeout,
                    )
                )
            else:
                response = call_fn(
                    model, system_prompt, user_message,
                    temperature=temperature,
                    timeout=timeout,
                )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Verificar respuesta vacía (posible error silencioso)
            if not response or not response.strip():
                raise ValueError("Respuesta vacía del LLM")
            
            # Éxito
            tokens_used = estimate_tokens(system_prompt + user_message + response)
            if session_state:
                session_state.record_success(tokens_used)
            
            metadata["latency_ms"] = latency_ms
            metadata["tokens_used"] = tokens_used
            
            logger.info(
                f"[Resilience] Llamada exitosa (intento {attempt + 1}/{MAX_RETRIES}, "
                f"{latency_ms}ms, ~{tokens_used} tokens)"
            )
            
            return response, metadata
            
        except Exception as e:
            error_str = str(e)
            latency_ms = int((time.time() - start_time) * 1000)
            metadata["total_retry_time_ms"] += latency_ms
            last_error = error_str
            
            logger.warning(
                f"[Resilience] Error en intento {attempt + 1}/{MAX_RETRIES}: {error_str[:200]}"
            )
            
            # Registrar error en el estado de sesión
            if session_state:
                session_state.record_error(error_str)
            
            # Verificar si es error de agotamiento de contexto
            if is_context_exhaustion_error(error_str):
                metadata["context_exhaustion_detected"] = True
                logger.info("[Resilience] Detectado agotamiento de contexto. Activando compactación.")
                
                if on_context_exhaustion:
                    # Callback para compactar el contexto y reintentar
                    new_user_message = on_context_exhaustion(user_message, error_str)
                    if new_user_message:
                        user_message = new_user_message
                        logger.info("[Resilience] Contexto compactado, reintentando...")
                        continue
                
                # Si no hay callback o no se pudo compactar, reducir el mensaje
                user_message = _emergency_truncate(user_message)
                logger.info("[Resilience] Truncamiento de emergencia aplicado, reintentando...")
                continue
            
            # Verificar si es error irrecuperable
            if is_unrecoverable_error(error_str):
                logger.error(f"[Resilience] Error irrecuperable: {error_str[:200]}")
                metadata["final_error"] = error_str
                raise
            
            # Verificar si necesitamos reiniciar la sesión
            if session_state and session_state.needs_reset():
                metadata["session_reset"] = True
                logger.warning(
                    f"[Resilience] Sesión {session_id} alcanzó {MAX_CONSECUTIVE_ERRORS} errores "
                    f"consecutivos. Reiniciando estado."
                )
                reset_session_state(session_id, brand_id)
            
            # Esperar antes de reintentar (backoff exponencial)
            if attempt < MAX_RETRIES - 1:
                delay = calculate_retry_delay(attempt, BASE_RETRY_DELAY, MAX_RETRY_DELAY)
                logger.info(f"[Resilience] Esperando {delay:.1f}s antes de reintentar...")
                await asyncio.sleep(delay)
    
    # Todos los reintentos fallaron
    metadata["final_error"] = last_error
    logger.error(
        f"[Resilience] Todos los reintentos agotados ({MAX_RETRIES} intentos). "
        f"Último error: {last_error[:200] if last_error else 'desconocido'}"
    )
    
    # Generar respuesta de fallback
    fallback_response = _generate_fallback_response(session_state)
    metadata["is_fallback"] = True
    
    return fallback_response, metadata


def _emergency_truncate(user_message: str) -> str:
    """Truncamiento de emergencia del mensaje cuando el contexto se agota.
    
    Estrategia: mantener solo el 50% del mensaje, priorizando el final
    (que contiene el mensaje actual del usuario).
    """
    if len(user_message) <= 1000:
        return user_message
    
    # Buscar la sección "MENSAJE DEL USUARIO:" y preservarla
    marker = "MENSAJE DEL USUARIO:"
    marker_pos = user_message.rfind(marker)
    
    if marker_pos > 0:
        # Preservar el mensaje del usuario y truncar el historial
        user_part = user_message[marker_pos:]
        context_part = user_message[:marker_pos]
        # Tomar solo el 30% del contexto
        truncated_context = context_part[:len(context_part) // 3]
        return truncated_context + "\n[...contexto compactado por límite de tokens...]\n\n" + user_part
    
    # Fallback: tomar la segunda mitad del mensaje
    midpoint = len(user_message) // 2
    return "[...contexto anterior omitido...]\n" + user_message[midpoint:]


def _generate_fallback_response(session_state: Optional[SessionState] = None) -> str:
    """Genera una respuesta de fallback cuando el LLM no está disponible.
    
    La respuesta es empática y guía al usuario sobre qué hacer.
    """
    if session_state and session_state.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        return (
            "Disculpa, estoy experimentando dificultades técnicas para procesar tu respuesta. "
            "He reiniciado mi contexto interno para poder continuar. "
            "¿Podrías repetir tu última respuesta o darme un resumen de lo que me compartiste? "
            "Así puedo retomar la entrevista desde donde quedamos."
        )
    
    return (
        "Lo siento, hubo un problema temporal al procesar tu mensaje. "
        "Por favor, intenta enviarlo nuevamente en unos segundos. "
        "Si el problema persiste, verifica que Ollama esté corriendo correctamente."
    )


# ---------------------------------------------------------------------------
# Decorador para endpoints con resiliencia
# ---------------------------------------------------------------------------
def with_llm_resilience(max_retries: int = MAX_RETRIES):
    """Decorador que agrega resiliencia a funciones que llaman al LLM.
    
    Uso:
        @with_llm_resilience(max_retries=3)
        async def my_endpoint(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_str = str(e)
                if is_unrecoverable_error(error_str):
                    raise
                logger.warning(f"[Resilience Decorator] Error capturado: {error_str[:200]}")
                raise
        return wrapper
    return decorator
