# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — backend FastAPI sidecar for Tauri desktop.
# MUST bundle repo app/ (UI) into _MEIPASS/app for frozen StaticFiles.
#
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(SPECPATH).resolve()
DESKTOP = BACKEND_DIR.parent
ROOT = DESKTOP.parent
SERVER = ROOT / "server"

_pyi = {}
try:
    with open(DESKTOP / "smartsuite.config.json", encoding="utf-8") as _f:
        _pyi = (json.load(_f) or {}).get("pyinstaller", {}) or {}
except Exception:
    _pyi = {}

APP_DIR = ROOT / "app"
if not APP_DIR.is_dir() or not (APP_DIR / "index.html").is_file():
    print(f"FATAL: {APP_DIR}/index.html missing — desktop sidecar cannot serve UI.", file=sys.stderr)
    raise SystemExit(1)

datas = [(str(APP_DIR), "app")]
SPLASH_UI = DESKTOP / "ui"
if SPLASH_UI.is_dir() and (SPLASH_UI / "index.html").is_file():
    datas.append((str(SPLASH_UI), "splash_ui"))
else:
    print(f"WARNING: splash ui missing at {SPLASH_UI}", file=sys.stderr)

_defaults = ROOT / "defaults"
if _defaults.is_dir():
    datas.append((str(_defaults), "defaults"))

for _d in _pyi.get("extraDatas", []):
    _p = ROOT / _d
    if _p.exists():
        datas.append((str(_p), _d))

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "database",
    "models",
    "orchestration",
    "pipeline_agent",
    "analytics",
    "security",
    "hardware",
    "hardware_profile",
    "ollama_client",
]

a = Analysis(
    [str(SERVER / "app.py")],
    pathex=[str(SERVER)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"] + list(_pyi.get("excludes", [])),
    noarchive=False,
)

_FORBIDDEN_PARTS = {".cursor", "node_modules", "__pycache__"}

def _datas_allowed(entry) -> bool:
    dest = str(entry[0]).replace("\\", "/")
    parts = {p for p in dest.split("/") if p}
    return _FORBIDDEN_PARTS.isdisjoint(parts)

a.datas = [entry for entry in a.datas if _datas_allowed(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
