# Plan de Remediación y Mejoras de Seguridad: SmartRedes

Este documento categoriza y prioriza las falencias reportadas en el *Análisis de código y seguridad (v0.3.0)*, ajustadas al contexto de ejecución on-premise (localhost, single-user) a través de Pinokio.

## Criterio de Priorización (Contexto Pinokio)

Varias vulnerabilidades clásicas (ej. falta de autenticación, TLS local, CORS estricto) se consideran de **bajo riesgo** o **riesgo aceptado** dado que el plugin corre localmente en la máquina del usuario.
La priorización se centra en:
1. **Corrupción de datos:** Errores que puedan sobrescribir, mezclar o destruir información local del usuario (concurrencia, IDOR local).
2. **Estabilidad y Disponibilidad:** Errores silenciosos, consumo desmedido de RAM/disco, payloads excesivos.
3. **Ejecución de código arbitrario:** XSS vía archivos subidos, SSRF, inyección de prompts.
4. **Mantenibilidad:** Limpieza de dependencias, logs, constantes mágicas.

---

## Falencias Descartadas (No Aplican a Plugin On-Premise)

Las siguientes recomendaciones del análisis se **ignoran intencionalmente** por no tener sentido en un plugin que corre en localhost dentro de Pinokio:

| Hallazgo | Razón de Descarte |
|:---|:---|
| Falta de autenticación en API | La API solo es accesible desde localhost; el usuario ya está autenticado en su propia máquina |
| Falta de TLS/HTTPS | El tráfico es localhost-to-localhost, no cruza la red |
| CORS demasiado permisivo | Solo el frontend local accede a la API local |
| Rate limiting en endpoints | Un solo usuario en su propia máquina no necesita rate limiting |
| Tokens/JWT para sesiones | No hay múltiples usuarios; el plugin es single-user |
| Hardening de headers HTTP (HSTS, CSP estricto) | No hay exposición a internet |

---

## Sprint 1: Correcciones Críticas (Estabilidad y Corrupción de Datos) - COMPLETADO

**Objetivo:** Asegurar que los datos locales del usuario no se corrompan y que el sistema no colapse por errores básicos de concurrencia o validación.

| ID | Hallazgo | Estado | Remediación Implementada |
|:---|:---|:---:|:---|
| **S1-01** | Búsqueda de campaña por substring (IDOR local) | ✅ | Creada función `_find_campaign_dir()` con igualdad estricta. Reemplazadas 8 instancias del patrón inseguro. |
| **S1-02** | Importación de JSON sin esquema ni límite | ✅ | Agregada validación de tamaño (100MB máx) en endpoint `/api/import`. |
| **S1-03** | Escritura de `plan.json` sin file-lock | ✅ | Reemplazadas llamadas `save_json` por `save_json_safe` (con `asyncio.Lock`) en `_generate_single_publication`. |
| **S1-04** | Variables globales concurrentes sin cleanup | ✅ | Agregado `shutdown` event handler que cierra `ThreadPoolExecutor` y cancela `Timer` del TTL. |
| **S1-05** | Upload de imagen: consumo de RAM antes de validar | ✅ | Lectura en chunks de 64KB con validación de tamaño progresiva (máx 10MB). |
| **S1-06** | Sanitización de SVG (XSS local) | ✅ | SVG rechazado explícitamente con HTTP 400 en upload de imágenes. |

---

## Sprint 2: Mejoras Importantes (Resiliencia y Control de Flujo) - COMPLETADO

**Objetivo:** Mejorar la observabilidad de errores, evitar fallos silenciosos y proteger contra abusos locales.

| ID | Hallazgo | Estado | Remediación Implementada |
|:---|:---|:---:|:---|
| **S2-01** | Eliminación de `except Exception: pass` | ✅ | Reemplazadas 14+ capturas silenciosas por `logger.debug/error` con variable `as e`. |
| **S2-02** | Fuga de threads y Timer | ✅ | Shutdown event handler cierra `_thread_pool.shutdown(wait=False)` y cancela `_ttl_timer`. |
| **S2-03** | Logs sin rotación (crecimiento ilimitado) | ✅ | Agregado `RotatingFileHandler` (10MB, 5 backups) en `data/audit/app.log`. |
| **S2-04** | Permisos de archivos sensibles | ✅ | Directorios de datos creados con `chmod 0o700` en startup. |
| **S2-05** | Mitigación SSRF residual en web_scraper | ✅ | Función `_validate_redirect_target()` verifica IP final post-redirect contra redes privadas. |

---

## Sprint 3: Mejoras Menores, Optimizaciones y Deuda Técnica - COMPLETADO

**Objetivo:** Limpiar código, centralizar configuraciones y mejorar la mantenibilidad.

| ID | Hallazgo | Estado | Remediación Implementada |
|:---|:---|:---:|:---|
| **S3-01** | Patrones de inyección insuficientes | ✅ | Agregados 8 nuevos patrones (DAN, jailbreak, developer mode, override, etc.) |
| **S3-02** | Sin límite de longitud de input | ✅ | Constante `_MAX_USER_INPUT_LENGTH = 10000` con truncado automático. |
| **S3-03** | Versión hardcodeada en múltiples lugares | ✅ | Constante `APP_VERSION = "0.3.0"` centralizada. |
| **S3-04** | Health check sin info de dependencias | ✅ | Endpoint `/api/health` ahora reporta versión, Ollama status, image engine, Python version. |

---

## Suite de Tests Creada

Se crearon **57 tests** distribuidos en 2 archivos:

### `tests/test_security_remediation.py` (37 tests)

| Clase | Tests | Verifica |
|:---|:---:|:---|
| `TestCampaignLookupIDOR` | 6 | S1-01: Igualdad estricta, sin colisiones por substring |
| `TestSVGRejection` | 2 | S1-06: SVG rechazado, PNG aceptado |
| `TestUploadSizeLimit` | 1 | S1-05: Imágenes >10MB rechazadas |
| `TestSSRFProtection` | 6 | S2-05: Redirecciones a IPs privadas bloqueadas |
| `TestInputSanitization` | 9 | S3-01/S3-02: Inyección filtrada, texto legítimo preservado |
| `TestImportSizeLimit` | 1 | S1-02: Importaciones >100MB rechazadas |
| `TestHealthCheck` | 3 | S3-04: Versión, status, dependencias |
| `TestDirectoryPermissions` | 1 | S2-04: Permisos 0o700 |
| `TestLoggingConfiguration` | 1 | S2-03: Logger configurado correctamente |
| `TestURLValidation` | 4 | Validación anti-SSRF en app.py |
| `TestCampaignDirEdgeCases` | 3 | Edge cases con UUIDs y prefijos similares |

### `tests/test_concurrency_and_integration.py` (20 tests)

| Clase | Tests | Verifica |
|:---|:---:|:---|
| `TestConcurrentFileWrites` | 5 | S1-03: Escritura atómica, sin corrupción, sin .tmp residuales |
| `TestDataIntegrity` | 3 | Archivos corruptos/vacíos/inexistentes manejados |
| `TestThreadPoolManagement` | 2 | S1-04: Pool existe y tiene límite de workers |
| `TestAppConfiguration` | 5 | Constantes y configuración correcta |
| `TestAuditLogging` | 3 | Auditoría crea entradas, append, errores |
| `TestSaveJsonSafeAsync` | 2 | S1-03: Async locks funcionan correctamente |

---

## Ejecución

```bash
# Ejecutar todos los tests de remediación
python3 -m pytest tests/test_security_remediation.py tests/test_concurrency_and_integration.py -v

# Resultado esperado: 57 passed
```

---

## Commits

| Commit | Descripción |
|:---|:---|
| `42fc646` | Sprint 1 - Correcciones críticas de seguridad |
| `903607f` | Sprint 2 - Mejoras de robustez y seguridad |
| `31ea0bb` | Sprint 3 - Mejoras menores y optimizaciones |
| `80c917e` | Suite completa de tests |
| `1cfc7be` | Estabilización de test concurrente |

Branch: `fix/security-audit-remediation`
