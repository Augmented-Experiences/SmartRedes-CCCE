"""Nombres de archivo confinados a una carpeta de la aplicación."""
from __future__ import annotations

import re
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class PathRejected(ValueError):
    """El nombre no puede usarse como ruta local."""


def safe_image_basename(filename: str) -> str:
    """Basename de imagen. Rechaza .., absolutas, separadores y %2f literal."""
    raw = (filename or "").split("?", 1)[0].strip()
    if not raw or raw != Path(raw).name:
        raise PathRejected("Nombre de archivo inválido.")
    if ".." in raw or "/" in raw or "\\" in raw or "\x00" in raw or "%" in raw:
        raise PathRejected("Nombre de archivo inválido.")
    if Path(raw).is_absolute() or raw.startswith("."):
        raise PathRejected("Nombre de archivo inválido.")
    if not _SAFE_NAME.fullmatch(raw):
        raise PathRejected("Nombre de archivo inválido.")
    if Path(raw).suffix.lower() not in IMAGE_EXTENSIONS:
        raise PathRejected("Extensión de archivo no permitida.")
    return raw


def safe_child_name(name: str) -> str:
    """Un solo segmento de ruta, sin separadores."""
    raw = (name or "").strip()
    if not raw or raw != Path(raw).name or ".." in raw or "/" in raw or "\\" in raw or "\x00" in raw:
        raise PathRejected("Nombre de ruta inválido.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", raw):
        raise PathRejected("Nombre de ruta inválido.")
    return raw


def confined_file(root: Path, filename: str, *, image: bool = False) -> Path:
    """Resuelve el archivo y exige que quede dentro de root, sin symlink que escape."""
    name = safe_image_basename(filename) if image else safe_child_name(filename)
    root_resolved = root.resolve()
    candidate = root_resolved / name
    if candidate.is_symlink():
        target = candidate.resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError as exc:
            raise PathRejected("El enlace sale de la carpeta permitida.") from exc
        return target
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathRejected("Ruta de archivo no permitida.") from exc
    return resolved
