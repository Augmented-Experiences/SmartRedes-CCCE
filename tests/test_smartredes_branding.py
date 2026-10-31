"""Pruebas de identidad SmartRedes-CCCE.

Validan que las superficies visibles y técnicas usen SmartRedes con el kit
visual y la atribución de la Cámara Colombiana de Comercio Electrónico.
"""
from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
SERVER_DIR = ROOT / "server"

HISTORICAL_REPOSITORY_URL = "https://github.com/vtomasv/ccs-brand-assistant"

LEGACY_PRODUCT_TERMS = (
    "CCS " + "Brand " + "Assistant",
    "CSS " + "Brand " + "Assistant",
    "Brand " + "Assistant",
)

CORPORATE_CSS_TOKENS = {
    "--ccce-azul-oscuro": "#173A7A",
    "--ccce-rojo": "#CE1126",
    "--ccce-dorado": "#F4C10E",
}

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".txt",
}


def _tracked_text_files() -> list[Path]:
    """Devuelve archivos de texto versionados, excluyendo artefactos de Git."""
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and "node_modules" not in path.parts
        and path.suffix.lower() in TEXT_SUFFIXES
    ]


def _read_without_historical_url(path: Path) -> str:
    """Elimina la única URL técnica permitida antes de revisar nombres visibles."""
    return path.read_text(encoding="utf-8").replace(HISTORICAL_REPOSITORY_URL, "")


class TestSmartRedesPresentation:
    """Comprueba las superficies de nombre que ve o consume el usuario."""

    def test_pinokio_menu_uses_smartredes(self):
        content = (ROOT / "pinokio.js").read_text(encoding="utf-8")
        assert 'title: "SmartRedes"' in content
        assert "Cámara Colombiana de Comercio Electrónico" in content

    @pytest.mark.parametrize("filename", ["install.json", "start.json", "stop.json", "reset.json"])
    def test_lifecycle_scripts_are_valid_and_named_smartredes(self, filename: str):
        path = ROOT / filename
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(parsed["run"], list)
        assert "SmartRedes" in path.read_text(encoding="utf-8")

    def test_frontend_title_and_sidebar_identify_smartredes(self):
        content = (APP_DIR / "index.html").read_text(encoding="utf-8")
        assert "<title>SmartRedes — Cámara Colombiana de Comercio Electrónico (CCCE)</title>" in content
        assert '<div class="sidebar-logo-text">SmartRedes</div>' in content
        assert "smartredes_export.json" in content

    def test_backend_metadata_uses_smartredes(self):
        if str(SERVER_DIR) not in sys.path:
            sys.path.insert(0, str(SERVER_DIR))
        app_module = importlib.import_module("app")
        assert app_module.app.title == "SmartRedes"
        assert app_module.app.openapi()["info"]["title"] == "SmartRedes"
        source = (SERVER_DIR / "app.py").read_text(encoding="utf-8")
        assert '"plugin_name": "smartredes"' in source
        assert "smartredes_export_" in source
        assert "Cámara Colombiana de Comercio Electrónico" in source

    def test_no_legacy_product_name_remains_in_versioned_text(self):
        legacy_matches: list[str] = []
        for path in _tracked_text_files():
            content = _read_without_historical_url(path)
            for term in LEGACY_PRODUCT_TERMS:
                if term in content:
                    legacy_matches.append(f"{path.relative_to(ROOT)}: {term}")
        assert not legacy_matches, "Referencias heredadas encontradas:\n" + "\n".join(legacy_matches)


class TestCorporateIdentityCCCE:
    """Asegura la identidad visual de la CCCE en la UI y los activos."""

    def test_ccce_logo_assets_are_present(self):
        assert (APP_DIR / "logo-ccce.png").is_file()
        assert (APP_DIR / "logo-ccce-full.png").is_file()
        assert (APP_DIR / "favicon.ico").is_file()
        assert (ROOT / "icon.png").is_file()
        assert not (APP_DIR / "logo-ccs.svg").exists()

    def test_corporate_palette_and_logo_reference_are_present(self):
        content = (APP_DIR / "index.html").read_text(encoding="utf-8")
        for token, color in CORPORATE_CSS_TOKENS.items():
            assert re.search(rf"{re.escape(token)}:\s*{re.escape(color)};", content)
        assert 'src="logo-ccce.png"' in content
        assert "Cámara Colombiana de Comercio Electrónico" in content
        assert "Ej: Colombia, Perú, México" in content

    def test_install_and_start_keep_the_ccce_visual_style(self):
        install = (ROOT / "install.json").read_text(encoding="utf-8")
        start = (ROOT / "start.json").read_text(encoding="utf-8")
        for content in (install, start):
            assert "linear-gradient(135deg,#173A7A,#F4C10E)" in content
            assert ">S</div>" in content


class TestSmartRedesStorageMigration:
    """Verifica el identificador actual y la carpeta de datos del escritorio."""

    def test_data_dir_respects_desktop_and_smartredes_variables(self):
        source = (SERVER_DIR / "app.py").read_text(encoding="utf-8")
        desktop_variable = 'os.environ.get("DATA_DIR")'
        product_variable = 'os.environ.get("SMARTREDES_DATA_DIR")'
        assert desktop_variable in source
        assert product_variable in source
        assert source.index(desktop_variable) < source.index(product_variable)
        assert "_IS_FROZEN" in source
        assert "_MEIPASS" in source

    def test_tests_are_configured_with_the_new_environment_variable(self):
        test_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "tests").glob("test_*.py")
        )
        assert "SMARTREDES_DATA_DIR" in test_sources

    def test_platform_validation_scripts_follow_current_pinokio_pattern(self):
        for filename in ("test_mac.sh", "test_windows.ps1"):
            content = (ROOT / "tests" / filename).read_text(encoding="utf-8")
            assert "SmartRedes" in content
            assert "local.set" in content
            assert "local.url" in content
            if filename == "test_mac.sh":
                assert "kernel.memory.local" in content
                assert "! grep -q 'self.session.url'" in content
            else:
                assert "kernel\\.memory\\.local" in content
                assert '-not ($content -match "self\\.session\\.url")' in content
