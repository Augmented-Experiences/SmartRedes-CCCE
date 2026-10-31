"""
Tests de integración para concurrencia y robustez del SmartRedes.

Verifica:
- S1-03: Escritura concurrente con save_json (escritura atómica)
- S1-04: Limpieza de recursos en shutdown
- S2-02: Thread pool shutdown
- Integridad de datos bajo carga concurrente
"""
import sys
import os
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

import pytest

# Agregar server al path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))


# ============================================================================
# S1-03: Tests de escritura concurrente con save_json (atómica)
# ============================================================================

class TestConcurrentFileWrites:
    """Verifica que save_json maneja correctamente escrituras concurrentes."""

    def setup_method(self, method):
        """Crea un directorio temporal para pruebas."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="smartredes_test_concurrent_"))

    def teardown_method(self, method):
        """Limpia directorios temporales."""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_concurrent_writes_no_corruption(self):
        """Múltiples escrituras concurrentes a archivos DIFERENTES no deben fallar.
        Cada thread escribe a su propio archivo para evitar race conditions
        en el rename atómico (que es el comportamiento esperado de save_json).
        La protección real de concurrencia se da via save_json_safe (async locks).
        """
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json

            errors = []
            write_count = 50

            def write_data(i):
                try:
                    target_file = self.tmp_dir / f"concurrent_test_{i}.json"
                    data = {"index": i, "data": f"value_{i}", "items": list(range(i % 10))}
                    save_json(target_file, data)
                except Exception as e:
                    errors.append(str(e))

            # Ejecutar escrituras concurrentes a archivos diferentes
            threads = []
            for i in range(write_count):
                t = threading.Thread(target=write_data, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=10)

            # Verificar que no hubo errores
            assert len(errors) == 0, f"Errores durante escritura concurrente: {errors}"

            # Verificar que todos los archivos son JSON válido
            for i in range(write_count):
                target_file = self.tmp_dir / f"concurrent_test_{i}.json"
                assert target_file.exists(), f"Archivo {i} no existe"
                content = target_file.read_text(encoding="utf-8")
                data = json.loads(content)
                assert data["index"] == i
                assert data["data"] == f"value_{i}"

    def test_concurrent_reads_and_writes(self):
        """Lecturas y escrituras simultáneas no deben causar errores."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json, load_json

            target_file = self.tmp_dir / "rw_test.json"
            # Inicializar el archivo
            save_json(target_file, {"counter": 0})

            errors = []
            read_results = []

            def write_data(i):
                try:
                    save_json(target_file, {"counter": i, "timestamp": time.time()})
                except Exception as e:
                    errors.append(f"write error: {e}")

            def read_data():
                try:
                    data = load_json(target_file, {})
                    read_results.append(data)
                except Exception as e:
                    errors.append(f"read error: {e}")

            # Mezclar lecturas y escrituras
            threads = []
            for i in range(30):
                if i % 3 == 0:
                    t = threading.Thread(target=read_data)
                else:
                    t = threading.Thread(target=write_data, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join(timeout=10)

            assert len(errors) == 0, f"Errores: {errors}"
            # Todas las lecturas deben retornar JSON válido
            for result in read_results:
                assert isinstance(result, dict)

    def test_save_json_creates_parent_dirs(self):
        """save_json debe crear directorios padre si no existen."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json

            nested_file = self.tmp_dir / "deep" / "nested" / "dir" / "test.json"
            save_json(nested_file, {"test": True})
            assert nested_file.exists()
            assert json.loads(nested_file.read_text()) == {"test": True}

    def test_save_json_atomic_write(self):
        """save_json debe escribir atómicamente (no dejar archivos parciales)."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json

            target_file = self.tmp_dir / "atomic_test.json"
            # Escribir datos iniciales
            save_json(target_file, {"version": 1, "data": "initial"})

            # Verificar que el contenido es completo
            content = json.loads(target_file.read_text())
            assert content["version"] == 1

            # Sobreescribir con datos nuevos
            save_json(target_file, {"version": 2, "data": "updated"})
            content = json.loads(target_file.read_text())
            assert content["version"] == 2

    def test_no_tmp_files_left_after_write(self):
        """No deben quedar archivos .tmp después de una escritura exitosa."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json

            target_file = self.tmp_dir / "clean_test.json"
            save_json(target_file, {"clean": True})

            # Verificar que no hay archivos .tmp
            tmp_files = list(self.tmp_dir.glob("*.tmp"))
            assert len(tmp_files) == 0


# ============================================================================
# Tests de integridad de datos
# ============================================================================

class TestDataIntegrity:
    """Verifica la integridad de datos en operaciones comunes."""

    def setup_method(self, method):
        """Crea un directorio temporal."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="smartredes_test_integrity_"))

    def teardown_method(self, method):
        """Limpia directorios temporales."""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_load_json_with_corrupted_file(self):
        """load_json debe retornar default si el archivo está corrupto."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import load_json

            corrupted_file = self.tmp_dir / "corrupted.json"
            corrupted_file.write_text("{ invalid json content !!!", encoding="utf-8")

            result = load_json(corrupted_file, {"default": True})
            assert result == {"default": True}

    def test_load_json_with_empty_file(self):
        """load_json debe retornar default si el archivo está vacío."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import load_json

            empty_file = self.tmp_dir / "empty.json"
            empty_file.write_text("", encoding="utf-8")

            result = load_json(empty_file, [])
            assert result == []

    def test_load_json_nonexistent_file(self):
        """load_json debe retornar default si el archivo no existe."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import load_json

            result = load_json(self.tmp_dir / "nonexistent.json", {"empty": True})
            assert result == {"empty": True}


# ============================================================================
# Tests del ThreadPoolExecutor
# ============================================================================

class TestThreadPoolManagement:
    """Verifica que el ThreadPoolExecutor se gestiona correctamente."""

    def test_thread_pool_exists(self):
        """El _thread_pool global debe existir."""
        from app import _thread_pool
        assert _thread_pool is not None
        assert isinstance(_thread_pool, ThreadPoolExecutor)

    def test_thread_pool_max_workers(self):
        """El _thread_pool debe tener un número limitado de workers."""
        from app import _thread_pool
        # Verificar que tiene un límite razonable (no ilimitado)
        assert _thread_pool._max_workers is not None
        assert _thread_pool._max_workers <= 20  # No más de 20 workers


# ============================================================================
# Tests de configuración de la aplicación
# ============================================================================

class TestAppConfiguration:
    """Verifica la configuración correcta de la aplicación."""

    def test_app_version_defined(self):
        """APP_VERSION debe estar definida."""
        from app import APP_VERSION
        assert APP_VERSION is not None
        assert isinstance(APP_VERSION, str)
        assert len(APP_VERSION) > 0

    def test_app_version_format(self):
        """APP_VERSION debe seguir formato semver."""
        from app import APP_VERSION
        parts = APP_VERSION.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()

    def test_max_user_input_length_defined(self):
        """_MAX_USER_INPUT_LENGTH debe estar definida y ser razonable."""
        from app import _MAX_USER_INPUT_LENGTH
        assert _MAX_USER_INPUT_LENGTH > 0
        assert _MAX_USER_INPUT_LENGTH <= 50000  # No más de 50K chars

    def test_prompt_injection_patterns_not_empty(self):
        """Los patrones de inyección deben existir."""
        from app import _PROMPT_INJECTION_PATTERNS
        assert len(_PROMPT_INJECTION_PATTERNS) > 10  # Al menos 10 patrones

    def test_blocked_ip_networks_defined(self):
        """Las redes bloqueadas deben estar definidas."""
        from app import _BLOCKED_IP_NETWORKS
        assert len(_BLOCKED_IP_NETWORKS) >= 7  # Al menos las 7 redes básicas


# ============================================================================
# Tests de audit logging
# ============================================================================

class TestAuditLogging:
    """Verifica que el sistema de auditoría funciona correctamente."""

    def setup_method(self, method):
        """Crea un directorio temporal."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="smartredes_test_audit_"))
        (self.tmp_dir / "audit").mkdir(parents=True)

    def teardown_method(self, method):
        """Limpia directorios temporales."""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_log_audit_creates_entry(self):
        """log_audit debe crear una entrada en el archivo de auditoría."""
        with patch("app.DATA_DIR", self.tmp_dir):
            from app import log_audit
            log_audit("test_agent", "test_action",
                      {"key": "value"}, "output_text",
                      "test-model", 100, True)

            # Verificar que se creó un archivo de auditoría
            audit_files = list((self.tmp_dir / "audit").glob("*.jsonl"))
            assert len(audit_files) >= 1

            # Verificar contenido
            content = audit_files[0].read_text(encoding="utf-8").strip()
            entry = json.loads(content)
            assert entry["agent_id"] == "test_agent"
            assert entry["task"] == "test_action"
            assert entry["model"] == "test-model"
            assert entry["success"] is True

    def test_log_audit_appends(self):
        """log_audit debe agregar entradas, no sobreescribir."""
        with patch("app.DATA_DIR", self.tmp_dir):
            from app import log_audit
            log_audit("agent1", "action1", {}, "out1", "model1", 50, True)
            log_audit("agent2", "action2", {}, "out2", "model2", 60, True)

            audit_files = list((self.tmp_dir / "audit").glob("*.jsonl"))
            assert len(audit_files) >= 1

            lines = audit_files[0].read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2

    def test_log_audit_with_error(self):
        """log_audit debe registrar errores correctamente."""
        with patch("app.DATA_DIR", self.tmp_dir):
            from app import log_audit
            log_audit("agent1", "action1", {}, "", "model1", 100, False,
                      error="Connection timeout")

            audit_files = list((self.tmp_dir / "audit").glob("*.jsonl"))
            content = audit_files[0].read_text(encoding="utf-8").strip()
            entry = json.loads(content)
            assert entry["success"] is False
            assert entry["error"] == "Connection timeout"


# ============================================================================
# Tests de save_json_safe (async)
# ============================================================================

class TestSaveJsonSafeAsync:
    """Verifica que save_json_safe funciona correctamente en contexto async."""

    def setup_method(self, method):
        """Crea un directorio temporal."""
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="smartredes_test_async_"))

    def teardown_method(self, method):
        """Limpia directorios temporales."""
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_save_json_safe_basic(self):
        """save_json_safe debe guardar datos correctamente."""
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json_safe
            target_file = self.tmp_dir / "async_test.json"
            await save_json_safe(target_file, {"async": True, "value": 42})
            assert target_file.exists()
            data = json.loads(target_file.read_text())
            assert data["async"] is True
            assert data["value"] == 42

    @pytest.mark.asyncio
    async def test_save_json_safe_concurrent_async(self):
        """Múltiples llamadas async concurrentes no deben corromper datos."""
        import asyncio
        with patch.dict(os.environ, {"SMARTREDES_DATA_DIR": str(self.tmp_dir)}):
            from app import save_json_safe
            target_file = self.tmp_dir / "async_concurrent.json"

            async def write(i):
                await save_json_safe(target_file, {"index": i})

            # Ejecutar 20 escrituras concurrentes
            await asyncio.gather(*[write(i) for i in range(20)])

            # El archivo debe ser JSON válido
            data = json.loads(target_file.read_text())
            assert "index" in data
