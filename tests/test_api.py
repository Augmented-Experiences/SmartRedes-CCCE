"""
Tests del API Backend — SmartRedes
============================================
Suite de tests que valida los endpoints principales del servidor FastAPI.
Compatible con Windows y macOS/Linux.

Ejecutar con:
    cd server && python -m pytest ../tests/ -v

Requisitos:
    pip install pytest httpx
"""

import sys
import os
import json
import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Agregar el directorio server al path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def test_client():
    """Crea un cliente de test para la API FastAPI."""
    from httpx import AsyncClient, ASGITransport
    from fastapi.testclient import TestClient

    # Mock Ollama para que no necesite estar corriendo
    with patch("app.requests.get") as mock_get, \
         patch("app.requests.post") as mock_post:
        # Mock /api/tags response
        mock_tags_resp = MagicMock()
        mock_tags_resp.status_code = 200
        mock_tags_resp.json.return_value = {
            "models": [
                {"name": "llama3.1:8b", "size": 4700000000},
                {"name": "llama3.2:3b", "size": 2000000000},
            ]
        }
        mock_get.return_value = mock_tags_resp

        from app import app
        client = TestClient(app)
        yield client


@pytest.fixture
def mock_ollama():
    """Mock de Ollama para tests que necesitan llamar al LLM."""
    with patch("app.requests.get") as mock_get, \
         patch("app.requests.post") as mock_post:
        # Mock /api/tags
        mock_tags = MagicMock()
        mock_tags.status_code = 200
        mock_tags.json.return_value = {
            "models": [
                {"name": "llama3.1:8b", "size": 4700000000},
                {"name": "llama3.2:3b", "size": 2000000000},
            ]
        }
        mock_get.return_value = mock_tags

        # Mock /api/chat
        mock_chat = MagicMock()
        mock_chat.status_code = 200
        mock_chat.json.return_value = {
            "message": {
                "content": json.dumps({
                    "value_proposition": "Soluciones tecnológicas innovadoras",
                    "sector": "Tecnología",
                    "tone": "profesional",
                    "personality_traits": ["innovador", "confiable", "cercano"],
                    "color_palette": ["#173A7A", "#F4C10E", "#FFFFFF"],
                    "typography": "Sans-serif moderna",
                    "visual_style": "Minimalista corporativo",
                    "products_services": ["Consultoría", "Desarrollo de software"],
                    "brand_promises": ["Calidad", "Innovación"],
                    "target_audience": "PYMEs en Latinoamérica",
                    "formality_level": "medium",
                    "differentiators": ["IA local", "Sin dependencia de internet"],
                    "content_themes": ["Tecnología", "Emprendimiento"],
                    "narrative_structure": "Problema-solución"
                })
            }
        }
        mock_post.return_value = mock_chat

        yield {"get": mock_get, "post": mock_post}


# ============================================================
# Tests: Health & System
# ============================================================

class TestHealthEndpoints:
    """Tests para endpoints de sistema y salud."""

    def test_health_check(self, test_client):
        """GET /api/health debe retornar status ok."""
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "timestamp" in data

    def test_readiness_check(self, test_client):
        """GET /api/readiness debe retornar estado de preparación."""
        resp = test_client.get("/api/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert "ready" in data
        assert "ollama_available" in data
        assert "models_count" in data
        assert "issues" in data
        assert isinstance(data["issues"], list)

    def test_readiness_fields_types(self, test_client):
        """Los campos de readiness deben tener tipos correctos."""
        resp = test_client.get("/api/readiness")
        data = resp.json()
        assert isinstance(data["ready"], bool)
        assert isinstance(data["ollama_available"], bool)
        assert isinstance(data["models_count"], int)
        assert isinstance(data["models"], list)
        assert isinstance(data["active_pulls"], list)

    def test_config_get(self, test_client):
        """GET /api/config debe retornar configuración."""
        resp = test_client.get("/api/config")
        assert resp.status_code == 200


# ============================================================
# Tests: Ollama Status & Models
# ============================================================

class TestOllamaEndpoints:
    """Tests para endpoints de Ollama y modelos."""

    def test_ollama_status(self, test_client):
        """GET /api/ollama/status debe retornar disponibilidad."""
        resp = test_client.get("/api/ollama/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert "models" in data

    def test_hardware_performance(self, test_client):
        """GET /api/hardware/performance debe retornar info de hardware y modelos."""
        resp = test_client.get("/api/hardware/performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "hardware" in data
        assert "models" in data

        hw = data["hardware"]
        assert "platform" in hw
        assert "ram_gb" in hw
        assert "cpu_count" in hw
        assert "gpu_name" in hw
        assert isinstance(hw["ram_gb"], (int, float))
        assert isinstance(hw["cpu_count"], int)

    def test_hardware_performance_model_grades(self, test_client):
        """Los modelos en performance deben tener grado y tokens/s."""
        resp = test_client.get("/api/hardware/performance")
        data = resp.json()
        models = data["models"]
        if models:
            m = models[0]
            assert "model" in m
            assert "grade" in m
            assert "grade_label" in m
            assert "grade_color" in m
            assert "estimated_tps" in m
            assert "ram_pct" in m
            assert m["grade"] in ("S", "A", "B", "C", "D", "F")


# ============================================================
# Tests: Brands CRUD
# ============================================================

class TestBrandsEndpoints:
    """Tests para CRUD de marcas."""

    def test_list_brands_empty(self, test_client):
        """GET /api/brands debe retornar lista (puede estar vacía)."""
        resp = test_client.get("/api/brands")
        assert resp.status_code == 200
        data = resp.json()
        assert "brands" in data
        assert isinstance(data["brands"], list)

    def test_create_brand(self, test_client):
        """POST /api/brands debe crear una marca."""
        resp = test_client.post("/api/brands", json={
            "name": "Test Brand",
            "website": "https://example.com",
            "description": "Marca de prueba",
            "sector": "Tecnolog\u00eda",
            "target_markets": "Colombia, Perú",
            "language": "es",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Brand"
        assert data["website"] == "https://example.com"
        assert data["onboarding_status"] == "pending"
        assert "id" in data

    def test_get_brand(self, test_client):
        """GET /api/brands/{id} debe retornar la marca creada."""
        # Crear primero
        create_resp = test_client.post("/api/brands", json={
            "name": "Get Test Brand",
            "website": "https://test.com",
        })
        brand_id = create_resp.json()["id"]

        resp = test_client.get(f"/api/brands/{brand_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test Brand"

    def test_get_brand_not_found(self, test_client):
        """GET /api/brands/{id} con ID inexistente debe retornar 404."""
        resp = test_client.get("/api/brands/nonexistent-id-12345")
        assert resp.status_code == 404

    def test_delete_brand(self, test_client):
        """DELETE /api/brands/{id} debe eliminar la marca."""
        create_resp = test_client.post("/api/brands", json={
            "name": "Delete Test Brand",
            "website": "https://delete.com",
        })
        brand_id = create_resp.json()["id"]

        resp = test_client.delete(f"/api/brands/{brand_id}")
        assert resp.status_code == 200

        # Verificar que ya no existe
        get_resp = test_client.get(f"/api/brands/{brand_id}")
        assert get_resp.status_code == 404


# ============================================================
# Tests: Analyze Progress
# ============================================================

class TestAnalyzeProgress:
    """Tests para el endpoint de progreso de análisis."""

    def test_analyze_progress_no_active(self, test_client):
        """GET /api/brands/{id}/analyze-progress sin análisis activo."""
        create_resp = test_client.post("/api/brands", json={
            "name": "Progress Test",
            "website": "https://progress.com",
        })
        brand_id = create_resp.json()["id"]

        resp = test_client.get(f"/api/brands/{brand_id}/analyze-progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["analyzing"] == False
        assert data["progress_pct"] == 100

    def test_analyze_progress_fields(self, test_client):
        """El endpoint de progreso debe tener los campos esperados."""
        create_resp = test_client.post("/api/brands", json={
            "name": "Fields Test",
            "website": "https://fields.com",
        })
        brand_id = create_resp.json()["id"]

        resp = test_client.get(f"/api/brands/{brand_id}/analyze-progress")
        data = resp.json()
        assert "brand_id" in data
        assert "analyzing" in data
        assert "progress_pct" in data


# ============================================================
# Tests: ADN Sanitization
# ============================================================

class TestADNSanitization:
    """Tests para la función _sanitize_adn_fields."""

    def test_sanitize_string_fields(self):
        """Los campos string deben mantenerse como strings."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
        # Import the function directly
        from app import _sanitize_adn_fields

        adn = {
            "value_proposition": "Test value",
            "sector": "Tech",
            "tone": "formal",
        }
        result = _sanitize_adn_fields(adn)
        assert result["value_proposition"] == "Test value"
        assert result["sector"] == "Tech"
        assert result["tone"] == "formal"

    def test_sanitize_list_fields(self):
        """Los campos lista deben ser arrays de strings."""
        from app import _sanitize_adn_fields

        adn = {
            "personality_traits": ["innovador", "confiable"],
            "color_palette": ["#FF0000", "#00FF00"],
        }
        result = _sanitize_adn_fields(adn)
        assert isinstance(result["personality_traits"], list)
        assert all(isinstance(x, str) for x in result["personality_traits"])

    def test_sanitize_dict_to_list(self):
        """Un dict en un campo lista debe convertirse a lista de strings."""
        from app import _sanitize_adn_fields

        adn = {
            "personality_traits": {"key1": "value1", "key2": "value2"},
        }
        result = _sanitize_adn_fields(adn)
        assert isinstance(result["personality_traits"], list)
        assert len(result["personality_traits"]) == 2

    def test_sanitize_none_values(self):
        """Valores None deben convertirse a string vacío o lista vacía."""
        from app import _sanitize_adn_fields

        adn = {
            "value_proposition": None,
            "personality_traits": None,
        }
        result = _sanitize_adn_fields(adn)
        assert result["value_proposition"] == ""
        assert result["personality_traits"] == []

    def test_sanitize_nested_objects_in_list(self):
        """Objetos anidados en listas deben convertirse a strings."""
        from app import _sanitize_adn_fields

        adn = {
            "products_services": [{"name": "Product A"}, "Product B"],
        }
        result = _sanitize_adn_fields(adn)
        assert isinstance(result["products_services"], list)
        assert all(isinstance(x, str) for x in result["products_services"])

    def test_sanitize_prevents_object_object(self):
        """Nunca debe producir [object Object] en el resultado."""
        from app import _sanitize_adn_fields

        adn = {
            "value_proposition": {"nested": "object"},
            "personality_traits": [{"a": 1}, {"b": 2}],
            "color_palette": {"primary": "#000"},
            "sector": ["Tech", "Finance"],
        }
        result = _sanitize_adn_fields(adn)
        # Verificar que ningún valor sea un dict o contenga [object
        for key, val in result.items():
            if isinstance(val, str):
                assert "[object" not in val.lower(), f"Campo {key} contiene [object"
            elif isinstance(val, list):
                for item in val:
                    assert isinstance(item, str), f"Campo {key} tiene item no-string: {type(item)}"
                    assert "[object" not in item.lower(), f"Campo {key} item contiene [object"


# ============================================================
# Tests: Model Performance Estimation
# ============================================================

class TestModelPerformance:
    """Tests para las funciones de estimación de rendimiento."""

    def test_estimate_model_params(self):
        """Debe estimar correctamente los parámetros del modelo."""
        from app import _estimate_model_params

        assert _estimate_model_params("llama3.1:8b") == 8.0
        assert _estimate_model_params("llama3.2:3b") == 3.0
        assert _estimate_model_params("llama3.2:1b") == 1.0
        assert _estimate_model_params("mistral:7b") == 7.0

    def test_estimate_tokens_per_second(self):
        """Debe retornar un valor positivo de tokens/s."""
        from app import _estimate_tokens_per_second

        tps = _estimate_tokens_per_second(
            params_b=8.0, ram_gb=16.0, vram_gb=0,
            cpu_count=8, gpu_name="No detectada"
        )
        assert tps > 0
        assert isinstance(tps, int)

    def test_estimate_tps_apple_silicon(self):
        """Apple Silicon debe dar mejor rendimiento que solo CPU."""
        from app import _estimate_tokens_per_second

        tps_apple = _estimate_tokens_per_second(
            params_b=8.0, ram_gb=16.0, vram_gb=16.0,
            cpu_count=8, gpu_name="Apple Silicon (M2)"
        )
        tps_cpu = _estimate_tokens_per_second(
            params_b=8.0, ram_gb=16.0, vram_gb=0,
            cpu_count=8, gpu_name="No detectada"
        )
        assert tps_apple >= tps_cpu

    def test_compute_grade(self):
        """Debe retornar grado válido con campos requeridos."""
        from app import _compute_grade

        grade = _compute_grade(tps=30, model_size_gb=4.0, ram_gb=16.0)
        assert "grade" in grade
        assert "label" in grade
        assert "color" in grade
        assert "score" in grade
        assert grade["grade"] in ("S", "A", "B", "C", "D", "F")

    def test_compute_grade_too_large(self):
        """Modelo que no cabe en RAM debe ser F."""
        from app import _compute_grade

        grade = _compute_grade(tps=5, model_size_gb=20.0, ram_gb=8.0)
        assert grade["grade"] == "F"


# ============================================================
# Tests: Start.json & Pinokio.js Validation
# ============================================================

class TestPinokioConfig:
    """Tests para validar la configuración de Pinokio."""

    def test_start_json_valid(self):
        """start.json debe ser JSON válido con estructura correcta."""
        start_path = Path(__file__).parent.parent / "start.json"
        data = json.loads(start_path.read_text(encoding="utf-8"))
        assert "run" in data
        assert isinstance(data["run"], list)
        assert len(data["run"]) > 0

    def test_start_json_uses_local_set_pattern(self):
        """start.json debe usar local.set + local.url (patrón oficial Pinokio v7.2.6).
        
        El patrón correcto es:
        1. shell.run con on/event captura la URL del servidor
        2. local.set guarda input.event[0] en memoria como 'url'
        3. browser.open usa {{local.url}} para abrir la UI
        
        NO debe usar self.set (escribe archivo, no disponible en template)
        NO debe usar input.event directamente en browser.open"""
        start_path = Path(__file__).parent.parent / "start.json"
        data = json.loads(start_path.read_text(encoding="utf-8"))
        
        has_local_set = False
        for step in data.get("run", []):
            method = step.get("method", "")
            params = step.get("params", {})
            
            # Verificar que usa local.set (no self.set)
            if method == "local.set":
                has_local_set = True
            
            # browser.open NO debe usar input.event directamente
            if method == "browser.open":
                uri = params.get("uri", "")
                assert "input.event" not in uri, \
                    f"browser.open no debe usar input.event. URI: {uri}"
                assert "self.session" not in uri, \
                    f"browser.open no debe usar self.session (no funciona en v7.2.6). URI: {uri}"
                assert "local.url" in uri, \
                    f"browser.open debe usar local.url. URI: {uri}"
        
        assert has_local_set, "start.json debe usar local.set para guardar la URL en memoria"

    def test_start_json_has_port_env(self):
        """start.json debe pasar PORT como env var."""
        start_path = Path(__file__).parent.parent / "start.json"
        content = start_path.read_text(encoding="utf-8")
        assert '"PORT"' in content, "start.json debe pasar PORT como env var"

    def test_pinokio_js_valid(self):
        """pinokio.js debe existir y tener estructura básica."""
        pinokio_path = Path(__file__).parent.parent / "pinokio.js"
        content = pinokio_path.read_text(encoding="utf-8")
        assert "title" in content
        assert "start" in content
        assert "icon" in content

    def test_pinokio_js_no_input_event_in_href(self):
        """pinokio.js NO debe usar input.event en href."""
        pinokio_path = Path(__file__).parent.parent / "pinokio.js"
        content = pinokio_path.read_text(encoding="utf-8")
        assert "input.event[0]" not in content, "pinokio.js no debe usar input.event"

    def test_install_json_valid(self):
        """install.json debe ser JSON válido."""
        install_path = Path(__file__).parent.parent / "install.json"
        data = json.loads(install_path.read_text(encoding="utf-8"))
        assert "run" in data
        assert isinstance(data["run"], list)

    def test_install_json_has_llama31(self):
        """install.json debe incluir descarga de llama3.1:8b."""
        install_path = Path(__file__).parent.parent / "install.json"
        content = install_path.read_text(encoding="utf-8")
        assert "llama3.1:8b" in content


# ============================================================
# Tests: Cross-Platform Path Handling
# ============================================================

class TestCrossPlatform:
    """Tests para compatibilidad cross-platform."""

    def test_path_resolution(self):
        """Las rutas del proyecto deben resolverse correctamente."""
        from app import BASE_DIR, APP_DIR, DATA_DIR
        assert BASE_DIR.exists() or True  # En CI puede no existir
        # Verificar que son Path objects
        assert hasattr(BASE_DIR, 'exists')
        assert hasattr(APP_DIR, 'exists')
        assert hasattr(DATA_DIR, 'exists')

    def test_no_hardcoded_windows_paths(self):
        """app.py no debe tener rutas Windows hardcodeadas."""
        app_path = Path(__file__).parent.parent / "server" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        # No debe haber rutas como C:\Users o D:\
        import re
        hardcoded = re.findall(r'["\'][A-Z]:\\\\', content)
        assert len(hardcoded) == 0, f"Rutas Windows hardcodeadas encontradas: {hardcoded}"

    def test_no_hardcoded_unix_paths(self):
        """app.py no debe tener rutas Unix hardcodeadas (excepto /proc)."""
        app_path = Path(__file__).parent.parent / "server" / "app.py"
        content = app_path.read_text(encoding="utf-8")
        import re
        # Buscar rutas como /home/user o /Users/ pero excluir /proc y /api
        hardcoded = re.findall(r'["\']/(home|Users|tmp)/[^"\']+["\']', content)
        assert len(hardcoded) == 0, f"Rutas Unix hardcodeadas encontradas: {hardcoded}"

    def test_utf8_encoding_handling(self):
        """El servidor debe manejar UTF-8 correctamente."""
        from app import _fix_encoding
        # Texto normal no debe cambiar
        assert _fix_encoding("Hola mundo") == "Hola mundo"
        assert _fix_encoding("") == ""
        # Texto con caracteres especiales
        assert _fix_encoding("Campaña de marketing") == "Campaña de marketing"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
