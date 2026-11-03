"""Guardia SSRF para las descargas que pide el usuario.

Solo http y https. Rechaza loopback, privadas, link-local, reservadas y
metadata de cloud, incluida 169.254.169.254. SMARTREDES_ALLOW_PRIVATE_URLS=1
desactiva ese rechazo; sin la variable, lo privado se bloquea siempre.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import time
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 5
TOTAL_TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 2_000_000
HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "application/xml",
    "text/xml",
}


class SsrfBlocked(ValueError):
    """La URL no se puede pedir."""


def private_urls_allowed() -> bool:
    value = os.environ.get("SMARTREDES_ALLOW_PRIVATE_URLS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _unwrap(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    ip = _unwrap(ip)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address) and str(ip) == "169.254.169.254":
        return True
    return False


def _blocked_hostname(hostname: str) -> bool:
    name = hostname.strip().lower().rstrip(".")
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    blocked = {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
    }
    return name in blocked


def assert_public_http_url(url: str) -> str:
    """Valida esquema y todas las IP resueltas. Devuelve la URL recortada."""
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise SsrfBlocked(
            f"Esquema no permitido: '{parsed.scheme or ''}'. Solo http y https."
        )
    hostname = parsed.hostname
    if not hostname:
        raise SsrfBlocked("URL inválida: no tiene hostname.")
    if _blocked_hostname(hostname):
        raise SsrfBlocked(f"Redirección a host local bloqueada: {hostname}")

    literals = []
    try:
        literals.append(ipaddress.ip_address(hostname))
    except ValueError:
        literals = []

    if literals:
        addresses = literals
    else:
        try:
            infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            raise SsrfBlocked(f"No se pudo resolver el hostname: '{hostname}'.") from exc
        addresses = []
        for item in infos:
            try:
                addresses.append(ipaddress.ip_address(item[4][0]))
            except ValueError:
                continue
        if not addresses:
            raise SsrfBlocked(f"No se pudo resolver el hostname: '{hostname}'.")

    if not private_urls_allowed():
        for ip in addresses:
            if _is_blocked_ip(ip):
                raise SsrfBlocked(
                    f"URL bloqueada: '{hostname}' resuelve a IP privada/local ({ip})."
                )
    return cleaned


def _content_type(response: requests.Response) -> str:
    raw = response.headers.get("content-type", "")
    return raw.split(";", 1)[0].strip().lower()


def _read_limited(response: requests.Response, limit: int) -> bytes:
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            response.close()
            raise SsrfBlocked(
                f"La respuesta supera el máximo de {limit} bytes."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def safe_fetch(
    url: str,
    *,
    headers: dict | None = None,
    timeout: int = TOTAL_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_types: set[str] | None = None,
    method: str = "GET",
) -> requests.Response:
    """Pide una URL pública, revalida cada redirección y limita el cuerpo."""
    current = assert_public_http_url(url)
    deadline = time.monotonic() + timeout
    session = requests.Session()
    try:
        for hop in range(MAX_REDIRECTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SsrfBlocked("Tiempo de espera agotado al pedir la URL.")
            response = session.request(
                method,
                current,
                headers=headers,
                timeout=remaining,
                allow_redirects=False,
                stream=True,
            )
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location or hop >= MAX_REDIRECTS:
                    raise SsrfBlocked("Demasiadas redirecciones.")
                current = assert_public_http_url(urljoin(current, location))
                continue
            if allowed_types is not None:
                ctype = _content_type(response)
                if ctype not in allowed_types:
                    response.close()
                    raise SsrfBlocked(
                        f"Content-Type no permitido: '{ctype or 'vacío'}'."
                    )
            body = _read_limited(response, max_bytes)
            response._content = body
            return response
        raise SsrfBlocked("Demasiadas redirecciones.")
    finally:
        session.close()
