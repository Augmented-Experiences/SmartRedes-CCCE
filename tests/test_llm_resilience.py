"""
Tests del módulo de resiliencia para llamadas LLM
==================================================
Valida reintentos, detección de errores y fallbacks.

Ejecutar con:
    cd server && python -m pytest ../tests/test_llm_resilience.py -v
"""

import sys
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from concurrent.futures import ThreadPoolExecutor

import pytest

# Agregar el directorio server al path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from llm_resilience import (
    is_context_exhaustion_error,
    is_unrecoverable_error,
    call_ollama_with_retry,
    _emergency_truncate,
    _generate_fallback_response,
    MAX_RETRIES,
    CONTEXT_EXHAUSTION_ERRORS,
    UNRECOVERABLE_ERRORS,
)
from context_manager import SessionState, MAX_CONSECUTIVE_ERRORS


# ============================================================
# Tests de detección de errores
# ============================================================

class TestErrorDetection:
    """Tests para funciones de detección de tipo de error."""

    def test_context_exhaustion_detected(self):
        """Debe detectar errores de agotamiento de contexto."""
        assert is_context_exhaustion_error("context length exceeded for model")
        assert is_context_exhaustion_error("Maximum context window reached")
        assert is_context_exhaustion_error("too many tokens in request")
        assert is_context_exhaustion_error("Error: out of memory")
        assert is_context_exhaustion_error("OOM killed")

    def test_context_exhaustion_not_detected(self):
        """No debe detectar errores normales como agotamiento de contexto."""
        assert not is_context_exhaustion_error("Connection timeout")
        assert not is_context_exhaustion_error("Internal server error")
        assert not is_context_exhaustion_error("Invalid JSON response")

    def test_unrecoverable_error_detected(self):
        """Debe detectar errores irrecuperables."""
        assert is_unrecoverable_error("Connection refused")
        assert is_unrecoverable_error("Ollama no está disponible")
        assert is_unrecoverable_error("model not found: llama3.1:8b")

    def test_unrecoverable_error_not_detected(self):
        """No debe detectar errores recuperables como irrecuperables."""
        assert not is_unrecoverable_error("timeout")
        assert not is_unrecoverable_error("Internal server error")
        assert not is_unrecoverable_error("context length exceeded")

    def test_case_insensitive_detection(self):
        """La detección debe ser case-insensitive."""
        assert is_context_exhaustion_error("CONTEXT LENGTH EXCEEDED")
        assert is_unrecoverable_error("CONNECTION REFUSED")


# ============================================================
# Tests de truncamiento de emergencia
# ============================================================

class TestEmergencyTruncate:
    """Tests para _emergency_truncate."""

    def test_short_message_unchanged(self):
        """Mensajes cortos no deben truncarse."""
        msg = "Hola mundo"
        result = _emergency_truncate(msg)
        assert result == msg

    def test_long_message_truncated(self):
        """Mensajes largos deben truncarse."""
        msg = "X" * 5000
        result = _emergency_truncate(msg)
        assert len(result) < len(msg)

    def test_preserves_user_message_section(self):
        """Debe preservar la sección MENSAJE DEL USUARIO."""
        msg = (
            "CONTEXTO DEL ADN ACTUAL:\n" + "X" * 3000 + "\n\n"
            "HISTORIAL DE CONVERSACIÓN:\n" + "Y" * 3000 + "\n\n"
            "MENSAJE DEL USUARIO: Esta es mi pregunta importante"
        )
        result = _emergency_truncate(msg)
        assert "Esta es mi pregunta importante" in result
        assert "MENSAJE DEL USUARIO:" in result

    def test_truncation_reduces_context(self):
        """El truncamiento debe reducir significativamente el tamaño."""
        msg = "CONTEXTO: " + "X" * 5000 + "\n\nMENSAJE DEL USUARIO: pregunta"
        result = _emergency_truncate(msg)
        assert len(result) < len(msg) * 0.7  # Al menos 30% de reducción


# ============================================================
# Tests de respuesta de fallback
# ============================================================

class TestFallbackResponse:
    """Tests para _generate_fallback_response."""

    def test_fallback_without_session(self):
        """Sin sesión debe dar respuesta genérica."""
        result = _generate_fallback_response(None)
        assert len(result) > 0
        assert "problema" in result.lower() or "error" in result.lower() or "siento" in result.lower()

    def test_fallback_with_many_errors(self):
        """Con muchos errores debe mencionar reinicio."""
        state = SessionState(session_id="test", brand_id="test")
        state.consecutive_errors = MAX_CONSECUTIVE_ERRORS
        
        result = _generate_fallback_response(state)
        assert "reinici" in result.lower() or "contexto" in result.lower()

    def test_fallback_with_few_errors(self):
        """Con pocos errores debe sugerir reintentar."""
        state = SessionState(session_id="test", brand_id="test")
        state.consecutive_errors = 1
        
        result = _generate_fallback_response(state)
        assert "intenta" in result.lower() or "nuevamente" in result.lower() or "problema" in result.lower()


# ============================================================
# Tests de llamada con reintentos (async)
# ============================================================

class TestCallOllamaWithRetry:
    """Tests para call_ollama_with_retry."""

    @pytest.fixture
    def thread_pool(self):
        """ThreadPoolExecutor para tests."""
        pool = ThreadPoolExecutor(max_workers=2)
        yield pool
        pool.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_successful_first_attempt(self, thread_pool):
        """Debe retornar resultado si la primera llamada es exitosa."""
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            return "Respuesta exitosa del LLM"
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="User message",
            thread_pool=thread_pool,
        )
        
        assert response == "Respuesta exitosa del LLM"
        assert metadata["attempts"] == 1
        assert metadata["final_error"] is None

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, thread_pool):
        """Debe reintentar si la primera llamada falla."""
        call_count = [0]
        
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Temporary error")
            return "Respuesta después de reintentos"
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="User message",
            thread_pool=thread_pool,
        )
        
        assert response == "Respuesta después de reintentos"
        assert metadata["attempts"] == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self, thread_pool):
        """Si todos los reintentos fallan, debe retornar fallback."""
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            raise Exception("Persistent error")
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="User message",
            thread_pool=thread_pool,
        )
        
        assert metadata["attempts"] == MAX_RETRIES
        assert metadata["final_error"] is not None
        assert metadata.get("is_fallback") == True
        assert len(response) > 0  # Debe haber respuesta de fallback

    @pytest.mark.asyncio
    async def test_unrecoverable_error_no_retry(self, thread_pool):
        """Errores irrecuperables no deben reintentarse."""
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            raise Exception("Connection refused")
        
        with pytest.raises(Exception, match="Connection refused"):
            await call_ollama_with_retry(
                call_fn=mock_call,
                model="llama3.1:8b",
                system_prompt="System",
                user_message="User message",
                thread_pool=thread_pool,
            )

    @pytest.mark.asyncio
    async def test_context_exhaustion_triggers_truncation(self, thread_pool):
        """Error de contexto debe activar truncamiento."""
        call_count = [0]
        
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("context length exceeded")
            return "Respuesta con contexto reducido"
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="X" * 5000 + "\n\nMENSAJE DEL USUARIO: pregunta",
            thread_pool=thread_pool,
        )
        
        assert metadata["context_exhaustion_detected"] == True
        assert response == "Respuesta con contexto reducido"

    @pytest.mark.asyncio
    async def test_empty_response_triggers_retry(self, thread_pool):
        """Respuesta vacía debe provocar reintento."""
        call_count = [0]
        
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return ""  # Respuesta vacía
            return "Respuesta válida"
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="User message",
            thread_pool=thread_pool,
        )
        
        assert response == "Respuesta válida"
        assert metadata["attempts"] == 2

    @pytest.mark.asyncio
    async def test_session_state_tracking(self, thread_pool):
        """Debe actualizar el estado de sesión correctamente."""
        def mock_call(model, system, user, temperature=0.7, timeout=None):
            return "Respuesta exitosa"
        
        response, metadata = await call_ollama_with_retry(
            call_fn=mock_call,
            model="llama3.1:8b",
            system_prompt="System",
            user_message="User message",
            session_id="tracking-test",
            brand_id="tracking-brand",
            thread_pool=thread_pool,
        )
        
        from context_manager import get_session_state
        state = get_session_state("tracking-test", "tracking-brand")
        assert state.successful_calls >= 1
        assert state.consecutive_errors == 0
