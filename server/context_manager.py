"""
SmartRedes — Módulo de Gestión de Contexto LLM
=======================================================

Este módulo implementa gestión robusta del contexto para llamadas al LLM local (Ollama),
resolviendo los problemas de agotamiento de contexto y errores repetidos.

Funcionalidades:
  - Estimación de tokens antes de cada llamada (heurística ~4 chars/token)
  - Compactación automática del historial cuando se acerca al límite de contexto
  - Reinicio de sesiones cuando se acumulan errores consecutivos
  - Reintentos con backoff exponencial para llamadas fallidas
  - Rotación de sesiones para mantener el contexto fresco
  - Resumen automático de conversaciones largas para preservar información clave

Diseño:
  - Cada sesión de entrevista tiene un ContextSession asociado
  - El ContextSession rastrea tokens usados, errores y estado
  - Cuando se detecta agotamiento de contexto, se compacta automáticamente
  - Si los errores persisten, se crea una nueva sesión con resumen del contexto anterior
"""

import json
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger("smartredes.context")

# ---------------------------------------------------------------------------
# Configuración de límites de contexto por modelo
# ---------------------------------------------------------------------------
# Tokens máximos de contexto por modelo (conservador para dejar espacio a la respuesta)
MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    "llama3.1:8b": 6000,       # 8K contexto, reservamos 2K para respuesta
    "llama3.2:3b": 4000,       # Modelo más pequeño, contexto más limitado
    "llama3.1:70b": 12000,     # Modelo grande
    "mistral:7b": 6000,
    "mixtral:8x7b": 10000,
    "gemma2:9b": 6000,
    "qwen2.5:7b": 10000,
    "phi3:mini": 4000,
    "deepseek-r1:8b": 6000,
}

# Límite por defecto si el modelo no está en la tabla
DEFAULT_CONTEXT_LIMIT = 5000

# Umbral para activar compactación (% del límite de contexto)
COMPACTION_THRESHOLD = 0.75

# Máximo de errores consecutivos antes de forzar reinicio de sesión
MAX_CONSECUTIVE_ERRORS = 3

# Máximo de mensajes antes de forzar compactación
MAX_MESSAGES_BEFORE_COMPACTION = 12

# Tokens reservados para el system prompt
SYSTEM_PROMPT_RESERVE = 800

# Tokens reservados para la respuesta del LLM
RESPONSE_RESERVE = 1500


# ---------------------------------------------------------------------------
# Estimación de tokens
# ---------------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Estima la cantidad de tokens en un texto.
    
    Heurística: ~4 caracteres por token para español/inglés.
    Para textos con mucho JSON o código, la ratio es ~3.5 chars/token.
    Usamos 3.8 como compromiso conservador.
    
    Args:
        text: Texto a estimar
        
    Returns:
        Número estimado de tokens
    """
    if not text:
        return 0
    # Heurística conservadora: 3.8 chars por token para español
    # (español usa más caracteres por palabra que inglés)
    char_count = len(text)
    return max(1, int(char_count / 3.8))


def estimate_messages_tokens(messages: List[Dict[str, str]]) -> int:
    """Estima tokens totales de una lista de mensajes.
    
    Args:
        messages: Lista de dicts con 'role' y 'content'
        
    Returns:
        Tokens estimados totales
    """
    total = 0
    for msg in messages:
        # Cada mensaje tiene overhead de ~4 tokens (role markers, separadores)
        total += 4
        total += estimate_tokens(msg.get("content", ""))
    return total


def get_context_limit(model: str) -> int:
    """Obtiene el límite de contexto para un modelo específico.
    
    Args:
        model: Nombre del modelo (e.g., "llama3.1:8b")
        
    Returns:
        Límite de tokens de contexto utilizable
    """
    # Buscar coincidencia exacta
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]
    
    # Buscar por base del modelo (sin tag)
    model_base = model.split(":")[0]
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if key.startswith(model_base):
            return limit
    
    return DEFAULT_CONTEXT_LIMIT


# ---------------------------------------------------------------------------
# Compactación de historial
# ---------------------------------------------------------------------------
def compact_history(messages: List[Dict[str, Any]], 
                    max_tokens: int,
                    preserve_last_n: int = 4) -> Tuple[List[Dict[str, Any]], str]:
    """Compacta el historial de conversación para caber en el límite de tokens.
    
    Estrategia de compactación:
    1. Siempre preservar los últimos N mensajes (contexto reciente)
    2. Los mensajes antiguos se resumen en un bloque compacto
    3. Se genera un "resumen de contexto" que captura los insights clave
    
    Args:
        messages: Historial completo de mensajes
        max_tokens: Tokens máximos disponibles para el historial
        preserve_last_n: Número de mensajes recientes a preservar intactos
        
    Returns:
        Tuple de (mensajes compactados, resumen generado)
    """
    if not messages:
        return [], ""
    
    # Si el historial ya cabe, no compactar
    current_tokens = estimate_messages_tokens(messages)
    if current_tokens <= max_tokens:
        return messages, ""
    
    logger.info(
        f"[Compactación] Historial excede límite: {current_tokens} tokens > {max_tokens}. "
        f"Compactando {len(messages)} mensajes..."
    )
    
    # Separar mensajes recientes (preservar) y antiguos (compactar)
    if len(messages) <= preserve_last_n:
        # Muy pocos mensajes, truncar contenido de cada uno
        truncated = []
        for msg in messages:
            content = msg.get("content", "")
            # Truncar a ~500 chars por mensaje
            if len(content) > 500:
                content = content[:500] + "..."
            truncated.append({**msg, "content": content})
        return truncated, ""
    
    recent_messages = messages[-preserve_last_n:]
    old_messages = messages[:-preserve_last_n]
    
    # Generar resumen compacto de los mensajes antiguos
    summary_parts = []
    for msg in old_messages:
        role = "Usuario" if msg.get("role") == "user" else "Agente"
        content = msg.get("content", "")
        # Extraer solo la esencia (primeras 150 chars)
        essence = content[:150].strip()
        if len(content) > 150:
            essence += "..."
        summary_parts.append(f"- {role}: {essence}")
    
    summary = "RESUMEN DE CONVERSACIÓN ANTERIOR:\n" + "\n".join(summary_parts)
    
    # Verificar que el resumen + mensajes recientes caben
    summary_tokens = estimate_tokens(summary)
    recent_tokens = estimate_messages_tokens(recent_messages)
    
    if summary_tokens + recent_tokens > max_tokens:
        # El resumen es demasiado largo, reducirlo más
        max_summary_tokens = max_tokens - recent_tokens - 100
        max_summary_chars = int(max_summary_tokens * 3.8)
        summary = summary[:max_summary_chars] + "\n[...conversación anterior truncada]"
    
    # Construir historial compactado
    compacted = [
        {"role": "system", "content": summary, "timestamp": datetime.utcnow().isoformat(), 
         "_compacted": True}
    ] + recent_messages
    
    final_tokens = estimate_messages_tokens(compacted)
    logger.info(
        f"[Compactación] Resultado: {len(compacted)} mensajes, "
        f"{final_tokens} tokens (de {current_tokens} original)"
    )
    
    return compacted, summary


def build_context_for_interview(
    system_prompt: str,
    adn_context: str,
    history: List[Dict[str, Any]],
    user_message: str,
    model: str,
) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Construye el contexto optimizado para una llamada de entrevista.
    
    Calcula el presupuesto de tokens disponible y compacta si es necesario.
    
    Args:
        system_prompt: Prompt del sistema para el agente
        adn_context: Contexto del ADN de marca (JSON)
        history: Historial de mensajes de la sesión
        user_message: Mensaje actual del usuario
        model: Modelo LLM a usar
        
    Returns:
        Tuple de (user_message_final, history_used, was_compacted)
    """
    context_limit = get_context_limit(model)
    
    # Calcular tokens fijos (system prompt + ADN + mensaje actual)
    system_tokens = estimate_tokens(system_prompt)
    adn_tokens = estimate_tokens(adn_context)
    user_tokens = estimate_tokens(user_message)
    fixed_tokens = system_tokens + adn_tokens + user_tokens + RESPONSE_RESERVE
    
    # Tokens disponibles para el historial
    available_for_history = context_limit - fixed_tokens
    
    if available_for_history < 200:
        # Muy poco espacio: truncar ADN context
        logger.warning(
            f"[Contexto] Espacio muy limitado ({available_for_history} tokens para historial). "
            f"Truncando ADN context."
        )
        # Reducir ADN a la mitad
        adn_context = adn_context[:len(adn_context) // 2] + "..."
        adn_tokens = estimate_tokens(adn_context)
        fixed_tokens = system_tokens + adn_tokens + user_tokens + RESPONSE_RESERVE
        available_for_history = context_limit - fixed_tokens
    
    # Compactar historial si es necesario
    was_compacted = False
    history_tokens = estimate_messages_tokens(history)
    
    if history_tokens > available_for_history or len(history) > MAX_MESSAGES_BEFORE_COMPACTION:
        history, _ = compact_history(history, available_for_history)
        was_compacted = True
    
    # Construir el historial como texto
    history_text = "\n".join([
        f"{'Usuario' if m['role'] == 'user' else 'Agente'}: {m['content']}"
        for m in history
        if not m.get("_compacted")  # No incluir el marcador de compactación como diálogo
    ])
    
    # Si hay un resumen de compactación, incluirlo al inicio
    compaction_summary = ""
    for m in history:
        if m.get("_compacted"):
            compaction_summary = m["content"] + "\n\n"
            break
    
    # Construir mensaje final
    final_user_message = f"""CONTEXTO DEL ADN ACTUAL:
{adn_context}

{compaction_summary}HISTORIAL DE CONVERSACIÓN:
{history_text}

MENSAJE DEL USUARIO: {user_message}"""
    
    # Verificación final de tokens
    total_estimated = estimate_tokens(system_prompt) + estimate_tokens(final_user_message) + RESPONSE_RESERVE
    if total_estimated > context_limit:
        logger.warning(
            f"[Contexto] Total estimado ({total_estimated}) excede límite ({context_limit}). "
            f"Truncando historial adicional."
        )
        # Truncar historial_text a la mitad
        history_text = history_text[:len(history_text) // 2] + "\n[...conversación truncada]"
        final_user_message = f"""CONTEXTO DEL ADN ACTUAL:
{adn_context}

{compaction_summary}HISTORIAL DE CONVERSACIÓN:
{history_text}

MENSAJE DEL USUARIO: {user_message}"""
    
    return final_user_message, history, was_compacted


# ---------------------------------------------------------------------------
# Gestión de sesiones con control de errores
# ---------------------------------------------------------------------------
@dataclass
class SessionState:
    """Estado de una sesión de entrevista para control de contexto."""
    session_id: str
    brand_id: str
    consecutive_errors: int = 0
    total_errors: int = 0
    total_calls: int = 0
    successful_calls: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[str] = None
    tokens_used_total: int = 0
    compactions_count: int = 0
    session_resets: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def record_success(self, tokens_used: int = 0):
        """Registra una llamada exitosa."""
        self.consecutive_errors = 0
        self.total_calls += 1
        self.successful_calls += 1
        self.tokens_used_total += tokens_used
    
    def record_error(self, error: str):
        """Registra un error en la llamada."""
        self.consecutive_errors += 1
        self.total_errors += 1
        self.total_calls += 1
        self.last_error = error
        self.last_error_time = datetime.utcnow().isoformat()
    
    def needs_reset(self) -> bool:
        """Determina si la sesión necesita reiniciarse."""
        return self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS
    
    def record_compaction(self):
        """Registra que se realizó una compactación."""
        self.compactions_count += 1
    
    def record_reset(self):
        """Registra que se reinició la sesión."""
        self.session_resets += 1
        self.consecutive_errors = 0
    
    def to_dict(self) -> dict:
        """Serializa el estado a diccionario."""
        return {
            "session_id": self.session_id,
            "brand_id": self.brand_id,
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "last_error": self.last_error,
            "last_error_time": self.last_error_time,
            "tokens_used_total": self.tokens_used_total,
            "compactions_count": self.compactions_count,
            "session_resets": self.session_resets,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserializa desde diccionario."""
        return cls(
            session_id=data.get("session_id", ""),
            brand_id=data.get("brand_id", ""),
            consecutive_errors=data.get("consecutive_errors", 0),
            total_errors=data.get("total_errors", 0),
            total_calls=data.get("total_calls", 0),
            successful_calls=data.get("successful_calls", 0),
            last_error=data.get("last_error"),
            last_error_time=data.get("last_error_time"),
            tokens_used_total=data.get("tokens_used_total", 0),
            compactions_count=data.get("compactions_count", 0),
            session_resets=data.get("session_resets", 0),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
        )


# Cache global de estados de sesión
_session_states: Dict[str, SessionState] = {}
_session_states_lock = threading.Lock()


def get_session_state(session_id: str, brand_id: str) -> SessionState:
    """Obtiene o crea el estado de una sesión."""
    key = f"{brand_id}_{session_id}"
    with _session_states_lock:
        if key not in _session_states:
            _session_states[key] = SessionState(
                session_id=session_id,
                brand_id=brand_id,
            )
        return _session_states[key]


def reset_session_state(session_id: str, brand_id: str) -> SessionState:
    """Reinicia el estado de una sesión (tras errores persistentes)."""
    key = f"{brand_id}_{session_id}"
    with _session_states_lock:
        old_state = _session_states.get(key)
        new_state = SessionState(
            session_id=session_id,
            brand_id=brand_id,
        )
        if old_state:
            new_state.session_resets = old_state.session_resets + 1
            new_state.total_errors = old_state.total_errors
            new_state.total_calls = old_state.total_calls
        _session_states[key] = new_state
        return new_state


# ---------------------------------------------------------------------------
# Reintentos con backoff exponencial
# ---------------------------------------------------------------------------
def calculate_retry_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """Calcula el delay para reintentos con backoff exponencial.
    
    Args:
        attempt: Número de intento (0-based)
        base_delay: Delay base en segundos
        max_delay: Delay máximo en segundos
        
    Returns:
        Delay en segundos
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


# ---------------------------------------------------------------------------
# Generación de resumen para rotación de sesión
# ---------------------------------------------------------------------------
def generate_session_summary(messages: List[Dict[str, Any]], adn_fields: dict) -> str:
    """Genera un resumen compacto de la sesión para usar en una nueva sesión.
    
    Este resumen se usa cuando se necesita reiniciar la sesión pero se quiere
    preservar el conocimiento adquirido.
    
    Args:
        messages: Historial completo de la sesión
        adn_fields: Campos del ADN actual
        
    Returns:
        Resumen textual compacto
    """
    if not messages:
        return ""
    
    # Extraer insights clave de las respuestas del usuario
    user_insights = []
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content and len(content) > 10:  # Ignorar respuestas muy cortas
                # Tomar los primeros 200 chars de cada respuesta
                user_insights.append(content[:200])
    
    # Construir resumen
    summary_parts = [
        "RESUMEN DE SESIÓN ANTERIOR (la sesión se reinició para optimizar el contexto):",
        f"- Se intercambiaron {len(messages)} mensajes",
        f"- El usuario proporcionó {len(user_insights)} respuestas sustanciales",
    ]
    
    # Incluir los insights más relevantes (últimos 5)
    if user_insights:
        summary_parts.append("\nINSIGHTS CLAVE DEL USUARIO:")
        for insight in user_insights[-5:]:
            summary_parts.append(f"  • {insight}")
    
    # Incluir estado actual del ADN
    filled_fields = [k for k, v in adn_fields.items() if v and str(v).strip()]
    empty_fields = [k for k, v in adn_fields.items() if not v or not str(v).strip()]
    
    summary_parts.append(f"\nESTADO DEL ADN:")
    summary_parts.append(f"  - Campos completados: {', '.join(filled_fields[:8])}")
    if empty_fields:
        summary_parts.append(f"  - Campos pendientes: {', '.join(empty_fields[:8])}")
    
    return "\n".join(summary_parts)


# ---------------------------------------------------------------------------
# Métricas de auditoría mejoradas
# ---------------------------------------------------------------------------
def calculate_audit_metrics(
    system_prompt: str,
    user_message: str,
    response: str,
    model: str,
    latency_ms: int,
) -> dict:
    """Calcula métricas detalladas para el registro de auditoría.
    
    Args:
        system_prompt: Prompt del sistema usado
        user_message: Mensaje enviado al LLM
        response: Respuesta recibida del LLM
        model: Modelo usado
        latency_ms: Latencia en milisegundos
        
    Returns:
        Dict con métricas calculadas
    """
    input_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_message)
    output_tokens = estimate_tokens(response)
    total_tokens = input_tokens + output_tokens
    
    # Estimación de costos cloud equivalentes (para mostrar ahorro)
    # Precios de referencia: GPT-4o $2.50/$10 por 1M tokens, Claude 3.5 $3/$15 por 1M tokens
    gpt4o_cost = (input_tokens * 2.50 / 1_000_000) + (output_tokens * 10.0 / 1_000_000)
    claude_cost = (input_tokens * 3.0 / 1_000_000) + (output_tokens * 15.0 / 1_000_000)
    avg_cloud_cost = (gpt4o_cost + claude_cost) / 2
    
    context_limit = get_context_limit(model)
    context_usage_pct = (input_tokens / context_limit * 100) if context_limit > 0 else 0
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cloud_cost_usd": round(avg_cloud_cost, 6),
        "context_limit": context_limit,
        "context_usage_pct": round(context_usage_pct, 1),
        "latency_ms": latency_ms,
        "model": model,
        "tokens_per_second": round(output_tokens / (latency_ms / 1000), 1) if latency_ms > 0 else 0,
    }
