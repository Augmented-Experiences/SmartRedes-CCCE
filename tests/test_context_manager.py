"""
Tests del módulo de gestión de contexto LLM
============================================
Valida la estimación de tokens, compactación de historial,
gestión de sesiones y construcción de contexto.

Ejecutar con:
    cd server && python -m pytest ../tests/test_context_manager.py -v
"""

import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

# Agregar el directorio server al path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from context_manager import (
    estimate_tokens,
    estimate_messages_tokens,
    get_context_limit,
    compact_history,
    build_context_for_interview,
    get_session_state,
    reset_session_state,
    generate_session_summary,
    calculate_audit_metrics,
    SessionState,
    MODEL_CONTEXT_LIMITS,
    DEFAULT_CONTEXT_LIMIT,
    MAX_CONSECUTIVE_ERRORS,
    COMPACTION_THRESHOLD,
)


# ============================================================
# Tests de estimación de tokens
# ============================================================

class TestEstimateTokens:
    """Tests para la función estimate_tokens."""

    def test_empty_string(self):
        """Texto vacío debe retornar 0 tokens."""
        assert estimate_tokens("") == 0

    def test_none_string(self):
        """None debe retornar 0 tokens."""
        assert estimate_tokens(None) == 0

    def test_short_text(self):
        """Texto corto debe estimar al menos 1 token."""
        result = estimate_tokens("Hola")
        assert result >= 1

    def test_medium_text(self):
        """Texto medio debe dar una estimación razonable."""
        text = "Esta es una oración de prueba con varias palabras en español."
        result = estimate_tokens(text)
        # ~60 chars / 3.8 ≈ 15-16 tokens
        assert 10 <= result <= 25

    def test_long_text(self):
        """Texto largo debe escalar proporcionalmente."""
        text = "palabra " * 1000  # ~8000 chars
        result = estimate_tokens(text)
        # ~8000 / 3.8 ≈ 2105
        assert 1500 <= result <= 3000

    def test_json_text(self):
        """JSON debe estimarse correctamente."""
        data = {"key1": "value1", "key2": "value2", "list": [1, 2, 3]}
        text = json.dumps(data)
        result = estimate_tokens(text)
        assert result > 0

    def test_proportionality(self):
        """Textos más largos deben tener más tokens."""
        short = estimate_tokens("Hola mundo")
        long = estimate_tokens("Hola mundo " * 100)
        assert long > short


class TestEstimateMessagesTokens:
    """Tests para estimate_messages_tokens."""

    def test_empty_messages(self):
        """Lista vacía debe retornar 0."""
        assert estimate_messages_tokens([]) == 0

    def test_single_message(self):
        """Un solo mensaje debe incluir overhead."""
        messages = [{"role": "user", "content": "Hola"}]
        result = estimate_messages_tokens(messages)
        # 4 (overhead) + estimate_tokens("Hola")
        assert result >= 5

    def test_multiple_messages(self):
        """Múltiples mensajes deben acumular tokens."""
        messages = [
            {"role": "user", "content": "Hola, soy una empresa de tecnología"},
            {"role": "assistant", "content": "Excelente, cuéntame más sobre tu empresa"},
            {"role": "user", "content": "Nos dedicamos al desarrollo de software"},
        ]
        result = estimate_messages_tokens(messages)
        # Debe ser > 0 y razonable
        assert result > 20

    def test_messages_with_empty_content(self):
        """Mensajes con contenido vacío solo cuentan overhead."""
        messages = [{"role": "user", "content": ""}]
        result = estimate_messages_tokens(messages)
        assert result == 4  # Solo overhead


# ============================================================
# Tests de límites de contexto por modelo
# ============================================================

class TestGetContextLimit:
    """Tests para get_context_limit."""

    def test_known_model(self):
        """Modelo conocido debe retornar su límite específico."""
        assert get_context_limit("llama3.1:8b") == 6000

    def test_unknown_model(self):
        """Modelo desconocido debe retornar el default."""
        assert get_context_limit("modelo_inexistente:latest") == DEFAULT_CONTEXT_LIMIT

    def test_model_base_match(self):
        """Debe matchear por base del modelo (sin tag)."""
        # "llama3.1:8b" está en la tabla, "llama3.1:latest" debería matchear
        result = get_context_limit("llama3.1:latest")
        assert result == 6000

    def test_small_model(self):
        """Modelo pequeño debe tener límite menor."""
        assert get_context_limit("llama3.2:3b") == 4000

    def test_large_model(self):
        """Modelo grande debe tener límite mayor."""
        assert get_context_limit("llama3.1:70b") == 12000


# ============================================================
# Tests de compactación de historial
# ============================================================

class TestCompactHistory:
    """Tests para compact_history."""

    def test_short_history_no_compaction(self):
        """Historial corto no debe compactarse."""
        messages = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola, ¿en qué puedo ayudarte?"},
        ]
        result, summary = compact_history(messages, max_tokens=5000)
        assert len(result) == 2
        assert summary == ""

    def test_long_history_compaction(self):
        """Historial largo debe compactarse."""
        messages = []
        for i in range(20):
            messages.append({"role": "user", "content": f"Mensaje del usuario número {i} " * 20})
            messages.append({"role": "assistant", "content": f"Respuesta del agente número {i} " * 20})
        
        result, summary = compact_history(messages, max_tokens=500, preserve_last_n=4)
        # Debe haber menos mensajes que el original
        assert len(result) < len(messages)
        # Debe preservar los últimos 4
        assert len(result) >= 4

    def test_preserves_recent_messages(self):
        """Debe preservar los mensajes más recientes."""
        messages = [
            {"role": "user", "content": "Mensaje antiguo " * 50},
            {"role": "assistant", "content": "Respuesta antigua " * 50},
            {"role": "user", "content": "Mensaje reciente"},
            {"role": "assistant", "content": "Respuesta reciente"},
        ]
        result, _ = compact_history(messages, max_tokens=200, preserve_last_n=2)
        # Los últimos 2 mensajes deben estar presentes
        recent_contents = [m["content"] for m in result if not m.get("_compacted")]
        assert "Mensaje reciente" in recent_contents
        assert "Respuesta reciente" in recent_contents

    def test_empty_history(self):
        """Historial vacío debe retornar vacío."""
        result, summary = compact_history([], max_tokens=5000)
        assert result == []
        assert summary == ""

    def test_very_few_messages(self):
        """Con muy pocos mensajes, debe truncar contenido."""
        messages = [
            {"role": "user", "content": "X" * 2000},
            {"role": "assistant", "content": "Y" * 2000},
        ]
        result, _ = compact_history(messages, max_tokens=100, preserve_last_n=4)
        # Debe haber mensajes pero con contenido truncado
        assert len(result) > 0
        for msg in result:
            assert len(msg["content"]) <= 503  # 500 + "..."


# ============================================================
# Tests de construcción de contexto para entrevista
# ============================================================

class TestBuildContextForInterview:
    """Tests para build_context_for_interview."""

    def test_basic_context_build(self):
        """Debe construir un contexto válido."""
        system_prompt = "Eres un consultor de branding."
        adn_context = json.dumps({"sector": "Tecnología"})
        history = [
            {"role": "user", "content": "Somos una empresa de software"},
            {"role": "assistant", "content": "Interesante, cuéntame más"},
        ]
        user_message = "Nos especializamos en IA"
        
        result_msg, result_history, was_compacted = build_context_for_interview(
            system_prompt, adn_context, history, user_message, "llama3.1:8b"
        )
        
        assert "MENSAJE DEL USUARIO: Nos especializamos en IA" in result_msg
        assert "CONTEXTO DEL ADN ACTUAL:" in result_msg
        assert not was_compacted

    def test_context_with_long_history_triggers_compaction(self):
        """Historial largo debe activar compactación."""
        system_prompt = "Eres un consultor." * 50  # System prompt largo
        adn_context = json.dumps({"field": "value" * 100})
        history = []
        for i in range(20):
            history.append({"role": "user", "content": f"Respuesta detallada {i} " * 30})
            history.append({"role": "assistant", "content": f"Pregunta {i} " * 30})
        user_message = "Mi nueva respuesta"
        
        result_msg, result_history, was_compacted = build_context_for_interview(
            system_prompt, adn_context, history, user_message, "llama3.2:3b"
        )
        
        # Con un modelo pequeño y mucho historial, debe compactar
        assert was_compacted or len(result_history) < len(history)

    def test_context_includes_user_message(self):
        """El mensaje del usuario siempre debe estar presente."""
        result_msg, _, _ = build_context_for_interview(
            "System", "{}", [], "Mi mensaje importante", "llama3.1:8b"
        )
        assert "Mi mensaje importante" in result_msg


# ============================================================
# Tests de gestión de sesiones
# ============================================================

class TestSessionState:
    """Tests para SessionState."""

    def test_initial_state(self):
        """Estado inicial debe tener contadores en 0."""
        state = SessionState(session_id="test-1", brand_id="brand-1")
        assert state.consecutive_errors == 0
        assert state.total_errors == 0
        assert state.total_calls == 0
        assert state.successful_calls == 0

    def test_record_success(self):
        """record_success debe incrementar contadores y resetear errores consecutivos."""
        state = SessionState(session_id="test-1", brand_id="brand-1")
        state.consecutive_errors = 2
        state.record_success(tokens_used=100)
        
        assert state.consecutive_errors == 0
        assert state.total_calls == 1
        assert state.successful_calls == 1
        assert state.tokens_used_total == 100

    def test_record_error(self):
        """record_error debe incrementar contadores de error."""
        state = SessionState(session_id="test-1", brand_id="brand-1")
        state.record_error("Connection timeout")
        
        assert state.consecutive_errors == 1
        assert state.total_errors == 1
        assert state.total_calls == 1
        assert state.last_error == "Connection timeout"

    def test_needs_reset_threshold(self):
        """needs_reset debe ser True cuando se alcanza el umbral de errores."""
        state = SessionState(session_id="test-1", brand_id="brand-1")
        
        # No necesita reset con pocos errores
        state.consecutive_errors = MAX_CONSECUTIVE_ERRORS - 1
        assert not state.needs_reset()
        
        # Necesita reset al alcanzar el umbral
        state.consecutive_errors = MAX_CONSECUTIVE_ERRORS
        assert state.needs_reset()

    def test_serialization(self):
        """to_dict y from_dict deben ser inversos."""
        state = SessionState(session_id="test-1", brand_id="brand-1")
        state.record_success(50)
        state.record_error("test error")
        
        data = state.to_dict()
        restored = SessionState.from_dict(data)
        
        assert restored.session_id == state.session_id
        assert restored.brand_id == state.brand_id
        assert restored.total_calls == state.total_calls
        assert restored.total_errors == state.total_errors


class TestSessionManagement:
    """Tests para funciones de gestión de sesiones."""

    def test_get_session_state_creates_new(self):
        """get_session_state debe crear un estado nuevo si no existe."""
        state = get_session_state("new-session", "new-brand")
        assert state.session_id == "new-session"
        assert state.brand_id == "new-brand"
        assert state.total_calls == 0

    def test_get_session_state_returns_existing(self):
        """get_session_state debe retornar el mismo estado para la misma sesión."""
        state1 = get_session_state("persist-session", "persist-brand")
        state1.record_success(100)
        
        state2 = get_session_state("persist-session", "persist-brand")
        assert state2.total_calls == 1

    def test_reset_session_state(self):
        """reset_session_state debe crear un nuevo estado limpio."""
        state = get_session_state("reset-test", "reset-brand")
        state.record_error("error 1")
        state.record_error("error 2")
        state.record_error("error 3")
        
        new_state = reset_session_state("reset-test", "reset-brand")
        assert new_state.consecutive_errors == 0
        assert new_state.session_resets == 1
        assert new_state.total_errors == 3  # Preserva historial total


# ============================================================
# Tests de generación de resumen de sesión
# ============================================================

class TestGenerateSessionSummary:
    """Tests para generate_session_summary."""

    def test_empty_messages(self):
        """Sin mensajes debe retornar string vacío."""
        result = generate_session_summary([], {})
        assert result == ""

    def test_with_messages(self):
        """Con mensajes debe generar un resumen."""
        messages = [
            {"role": "user", "content": "Somos una empresa de tecnología con 10 años de experiencia"},
            {"role": "assistant", "content": "Interesante, cuéntame más sobre tu propuesta de valor"},
            {"role": "user", "content": "Nos especializamos en soluciones de IA para PYMEs"},
        ]
        adn_fields = {"sector": "Tecnología", "tone": "", "target_audience": ""}
        
        result = generate_session_summary(messages, adn_fields)
        assert "RESUMEN DE SESIÓN ANTERIOR" in result
        assert "INSIGHTS CLAVE" in result
        assert "ESTADO DEL ADN" in result

    def test_summary_includes_field_status(self):
        """El resumen debe indicar campos completados y pendientes."""
        messages = [{"role": "user", "content": "Información relevante sobre la marca"}]
        adn_fields = {
            "sector": "Tecnología",
            "tone": "profesional",
            "target_audience": "",
            "visual_style": "",
        }
        
        result = generate_session_summary(messages, adn_fields)
        assert "Campos completados" in result
        assert "Campos pendientes" in result


# ============================================================
# Tests de métricas de auditoría
# ============================================================

class TestCalculateAuditMetrics:
    """Tests para calculate_audit_metrics."""

    def test_basic_metrics(self):
        """Debe calcular métricas básicas correctamente."""
        metrics = calculate_audit_metrics(
            system_prompt="Eres un consultor de branding.",
            user_message="Cuéntame sobre tu empresa.",
            response="Claro, somos una empresa de tecnología.",
            model="llama3.1:8b",
            latency_ms=1500,
        )
        
        assert metrics["input_tokens"] > 0
        assert metrics["output_tokens"] > 0
        assert metrics["total_tokens"] == metrics["input_tokens"] + metrics["output_tokens"]
        assert metrics["estimated_cloud_cost_usd"] > 0
        assert metrics["context_limit"] == 6000
        assert 0 <= metrics["context_usage_pct"] <= 100
        assert metrics["latency_ms"] == 1500
        assert metrics["tokens_per_second"] > 0

    def test_zero_latency(self):
        """Con latencia 0, tokens_per_second debe ser 0."""
        metrics = calculate_audit_metrics(
            system_prompt="Test",
            user_message="Test",
            response="Test",
            model="llama3.1:8b",
            latency_ms=0,
        )
        assert metrics["tokens_per_second"] == 0

    def test_context_usage_percentage(self):
        """El porcentaje de uso de contexto debe ser razonable."""
        # Con un prompt largo, el uso debe ser alto
        long_prompt = "X" * 20000  # ~5263 tokens
        metrics = calculate_audit_metrics(
            system_prompt=long_prompt,
            user_message="short",
            response="short",
            model="llama3.2:3b",  # límite 4000
            latency_ms=1000,
        )
        # Debería exceder 100% (indicando overflow)
        assert metrics["context_usage_pct"] > 100
