"""
Configuración de pytest para SmartRedes.
"""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Agregar server al path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

# Usar directorio temporal para DATA_DIR durante tests
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="smartredes_test_"))


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    """Configura variables de entorno para tests."""
    # Usar un directorio temporal para datos
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SMARTREDES_DATA_DIR", str(tmp_path))

    # Mock de Ollama para que no necesite estar corriendo
    with patch("app.OLLAMA_URL", "http://localhost:11434"):
        yield


@pytest.fixture
def sample_brand():
    """Datos de ejemplo para una marca."""
    return {
        "name": "Marca de Prueba",
        "website": "https://example.com",
        "description": "Una marca de prueba para tests",
        "sector": "Tecnología",
        "target_markets": ["Colombia", "Perú"],
        "language": "es",
    }


@pytest.fixture
def sample_adn():
    """Datos de ejemplo para un ADN de marca."""
    return {
        "value_proposition": "Soluciones innovadoras para PYMEs",
        "sector": "Tecnología",
        "tone": "profesional pero cercano",
        "formality_level": "medium",
        "target_audience": "PYMEs en Latinoamérica",
        "visual_style": "Minimalista corporativo",
        "typography": "Sans-serif moderna",
        "personality_traits": ["innovador", "confiable", "cercano"],
        "products_services": ["Consultoría IA", "Desarrollo de plugins"],
        "brand_promises": ["Calidad", "Simplicidad", "Offline-first"],
        "differentiators": ["IA local", "Sin dependencia de internet"],
        "content_themes": ["Tecnología", "Emprendimiento", "Productividad"],
        "color_palette": ["#173A7A", "#F4C10E", "#FFFFFF", "#1A2340"],
    }
