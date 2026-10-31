"""
SmartRedes — Web Scraper Multi-Estrategia
====================================================
Módulo de extracción de contenido web con soporte para:
  - Sitios estáticos (HTML puro, WordPress, etc.)
  - SPAs con JavaScript (React, Vue, Angular, Next.js, Taskade, etc.)
  - Sitios con protección anti-bot
  - Sitios con contenido detrás de lazy-loading

Estrategias en cascada (de menor a mayor costo):
  1. requests + BeautifulSoup  → sitios estáticos, rápido, sin JS
  2. Jina Reader API           → proxy gratuito que renderiza JS en la nube
  3. Playwright headless       → renderizado JS local completo
  4. Extracción enriquecida    → meta tags, JSON-LD, og:image + análisis visual
  5. Síntesis final            → combina todos los datos disponibles

Compatibilidad: Windows, macOS, Linux (cross-platform).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger("smartredes")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_DEFAULT_HEADERS = {
    "User-Agent": _DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
_MIN_CONTENT_LENGTH = 300   # mínimo de chars para considerar que el scrape fue exitoso
_JINA_BASE = "https://r.jina.ai/"


def _validate_redirect_target(response: requests.Response) -> None:
    """Valida que la URL final tras redirecciones no apunte a una IP privada/local (anti-SSRF)."""
    import ipaddress
    import socket
    final_url = response.url
    parsed = urlparse(final_url)
    hostname = parsed.hostname
    if not hostname:
        return
    blocked_hosts = {"localhost", "localhost.localdomain", "0.0.0.0", "[::]"}
    if hostname.lower() in blocked_hosts:
        raise ValueError(f"Redirección a host local bloqueada: {hostname}")
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
        blocked_networks = [
            ipaddress.ip_network("127.0.0.0/8"),
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("169.254.0.0/16"),
            ipaddress.ip_network("0.0.0.0/8"),
            ipaddress.ip_network("::1/128"),
        ]
        for family, _, _, _, sockaddr in resolved_ips:
            ip_obj = ipaddress.ip_address(sockaddr[0])
            for network in blocked_networks:
                if ip_obj in network:
                    raise ValueError(f"Redirección a IP privada bloqueada: {sockaddr[0]}")
    except socket.gaierror:
        pass  # No se puede resolver, dejar pasar (el request fallará de todas formas)


# ---------------------------------------------------------------------------
# Resultado estructurado del scraper
# ---------------------------------------------------------------------------
class ScrapeResult:
    """Resultado enriquecido del scraping con todos los datos extraídos."""

    def __init__(self):
        self.url: str = ""
        self.title: str = ""
        self.description: str = ""
        self.main_text: str = ""          # texto principal del sitio
        self.headings: list[str] = []     # h1, h2, h3
        self.meta_keywords: str = ""
        self.og_title: str = ""
        self.og_description: str = ""
        self.og_image: str = ""
        self.twitter_title: str = ""
        self.twitter_description: str = ""
        self.json_ld: list[dict] = []     # datos estructurados Schema.org
        self.css_colors: list[str] = []   # colores detectados en CSS
        self.fonts: list[str] = []        # fuentes detectadas
        self.nav_items: list[str] = []    # ítems de navegación
        self.cta_texts: list[str] = []    # textos de botones/CTA
        self.strategy_used: str = ""      # qué estrategia funcionó
        self.screenshot_url: str = ""     # URL del screenshot si existe
        self.error: Optional[str] = None

    def to_text(self) -> str:
        """Convierte el resultado a texto enriquecido para el LLM."""
        parts = []

        if self.title:
            parts.append(f"TÍTULO DEL SITIO: {self.title}")
        if self.og_title and self.og_title != self.title:
            parts.append(f"TÍTULO OG: {self.og_title}")
        if self.description:
            parts.append(f"DESCRIPCIÓN: {self.description}")
        if self.og_description and self.og_description != self.description:
            parts.append(f"DESCRIPCIÓN OG: {self.og_description}")
        if self.meta_keywords:
            parts.append(f"PALABRAS CLAVE: {self.meta_keywords}")

        # JSON-LD (datos estructurados)
        for jld in self.json_ld:
            jtype = jld.get("@type", "")
            if jtype in ("Organization", "LocalBusiness", "Store", "WebSite", "Product"):
                parts.append(f"\nDATOS ESTRUCTURADOS ({jtype}):")
                for k, v in jld.items():
                    if k.startswith("@") or not v:
                        continue
                    if isinstance(v, str):
                        parts.append(f"  {k}: {v}")
                    elif isinstance(v, dict):
                        name = v.get("name") or v.get("@type", "")
                        if name:
                            parts.append(f"  {k}: {name}")

        if self.headings:
            parts.append(f"\nTÍTULOS Y ENCABEZADOS:\n" + "\n".join(f"  - {h}" for h in self.headings[:20]))

        if self.nav_items:
            parts.append(f"\nNAVEGACIÓN: {', '.join(self.nav_items[:10])}")

        if self.cta_texts:
            parts.append(f"\nCALLS TO ACTION: {', '.join(self.cta_texts[:8])}")

        if self.main_text:
            # Limitar el texto principal para no exceder el contexto del LLM
            text_preview = self.main_text[:4000]
            parts.append(f"\nCONTENIDO PRINCIPAL:\n{text_preview}")

        if self.css_colors:
            parts.append(f"\nCOLORES DETECTADOS EN CSS: {', '.join(self.css_colors[:15])}")

        if self.fonts:
            parts.append(f"FUENTES DETECTADAS: {', '.join(self.fonts[:8])}")

        if self.screenshot_url:
            parts.append(f"\nSCREENSHOT DISPONIBLE: {self.screenshot_url}")

        parts.append(f"\n[Estrategia de extracción: {self.strategy_used}]")

        return "\n".join(parts)

    def is_sufficient(self) -> bool:
        """Determina si el contenido extraído es suficiente para análisis de marca."""
        total = len(self.main_text) + len(self.description) + len(self.title)
        has_real_content = (
            self.main_text and len(self.main_text) > _MIN_CONTENT_LENGTH
        ) or (
            len(self.headings) >= 3
        )
        return has_real_content or total > _MIN_CONTENT_LENGTH


# ---------------------------------------------------------------------------
# Estrategia 1: requests + BeautifulSoup (sitios estáticos)
# ---------------------------------------------------------------------------
def _scrape_static(url: str, result: ScrapeResult) -> bool:
    """
    Extracción básica con requests + BeautifulSoup.
    Funciona para sitios estáticos, WordPress, Shopify con SSR, etc.
    """
    try:
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=20, allow_redirects=True)
        _validate_redirect_target(resp)  # Anti-SSRF: validar destino final
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extraer meta datos
        _extract_meta(soup, result)
        _extract_json_ld(soup, result)
        _extract_colors_from_html(html, result)
        _extract_fonts_from_html(html, result)

        # Eliminar elementos no informativos
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "path"]):
            tag.decompose()

        # Extraer navegación
        nav = soup.find("nav")
        if nav:
            result.nav_items = [
                a.get_text(strip=True) for a in nav.find_all("a")
                if a.get_text(strip=True) and len(a.get_text(strip=True)) < 50
            ][:15]

        # Extraer encabezados
        result.headings = [
            tag.get_text(strip=True)
            for tag in soup.find_all(["h1", "h2", "h3"])
            if tag.get_text(strip=True)
        ][:30]

        # Extraer CTAs (botones y links prominentes)
        result.cta_texts = list({
            tag.get_text(strip=True)
            for tag in soup.find_all(["button", "a"])
            if tag.get_text(strip=True) and 3 < len(tag.get_text(strip=True)) < 60
            and any(kw in tag.get_text(strip=True).lower()
                    for kw in ["shop", "buy", "get", "start", "contact", "learn",
                               "comprar", "ver", "conocer", "contacto", "comenzar",
                               "now", "ahora", "más", "more", "demo", "free", "gratis"])
        })[:10]

        # Extraer texto principal
        texts = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "blockquote"]):
            text = tag.get_text(separator=" ", strip=True)
            if len(text) > 15:
                texts.append(text)

        result.main_text = "\n".join(dict.fromkeys(texts))  # deduplicar manteniendo orden

        result.strategy_used = "static-requests"
        return result.is_sufficient()

    except Exception as e:
        logger.debug(f"[scraper] Estrategia estática falló: {e}")
        return False


# ---------------------------------------------------------------------------
# Estrategia 2: Jina Reader API (proxy cloud que renderiza JS)
# ---------------------------------------------------------------------------
def _scrape_jina(url: str, result: ScrapeResult) -> bool:
    """
    Usa Jina.ai Reader (r.jina.ai) como proxy gratuito que renderiza
    JavaScript en la nube y devuelve el contenido en Markdown.
    No requiere instalación adicional, solo conexión a internet.
    """
    try:
        jina_url = f"{_JINA_BASE}{url}"
        headers = {
            "User-Agent": _DEFAULT_UA,
            "Accept": "text/plain, text/markdown, */*",
            "X-Return-Format": "markdown",
            "X-Timeout": "20",
        }
        resp = requests.get(jina_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            return False

        content = resp.text.strip()
        if not content or len(content) < _MIN_CONTENT_LENGTH:
            return False

        # Extraer título del markdown (primera línea # ...)
        lines = content.split("\n")
        for line in lines[:5]:
            if line.startswith("# "):
                if not result.title:
                    result.title = line[2:].strip()
                break

        # Extraer encabezados del markdown
        result.headings = [
            line.lstrip("#").strip()
            for line in lines
            if line.startswith(("#", "##", "###")) and len(line.lstrip("#").strip()) > 3
        ][:30]

        result.main_text = content[:6000]
        if not result.strategy_used:
            result.strategy_used = "jina-reader"
        else:
            result.strategy_used += "+jina-reader"

        return result.is_sufficient()

    except Exception as e:
        logger.debug(f"[scraper] Jina Reader falló: {e}")
        return False


# ---------------------------------------------------------------------------
# Estrategia 3: Playwright headless (renderizado JS local completo)
# ---------------------------------------------------------------------------
def _run_playwright_in_thread(url: str) -> ScrapeResult:
    """
    Ejecuta Playwright en un thread separado para evitar conflictos con
    el loop asyncio de FastAPI. Retorna un ScrapeResult con el contenido.
    """
    result = ScrapeResult()
    result.url = url
    _scrape_playwright_sync(url, result)
    return result


def _scrape_playwright(url: str, result: ScrapeResult) -> bool:
    """
    Usa Playwright con Chromium headless para renderizar completamente
    el JavaScript del sitio. Es la estrategia más potente pero más lenta.
    Funciona con React, Vue, Angular, Next.js, Taskade, Webflow, etc.

    Detecta automáticamente si hay un loop asyncio activo y en ese caso
    ejecuta Playwright en un thread separado para evitar conflictos.
    """
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Estamos dentro de un loop asyncio (FastAPI background task)
        # Ejecutar Playwright en un ThreadPoolExecutor para evitar el conflicto
        import concurrent.futures
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_playwright_in_thread, url)
                pw_result = future.result(timeout=60)
                # Copiar resultados al result original
                result.title = pw_result.title or result.title
                result.description = pw_result.description or result.description
                result.og_title = pw_result.og_title or result.og_title
                result.og_description = pw_result.og_description or result.og_description
                result.og_image = pw_result.og_image or result.og_image
                result.meta_keywords = pw_result.meta_keywords or result.meta_keywords
                result.headings = pw_result.headings or result.headings
                result.nav_items = pw_result.nav_items or result.nav_items
                result.cta_texts = pw_result.cta_texts or result.cta_texts
                result.main_text = pw_result.main_text or result.main_text
                result.css_colors = pw_result.css_colors or result.css_colors
                result.fonts = pw_result.fonts or result.fonts
                result.strategy_used = pw_result.strategy_used or "playwright-thread"
                return result.is_sufficient()
        except Exception as e:
            logger.warning(f"[scraper] Playwright en thread falló: {e}")
            return False
    else:
        # Sin loop asyncio activo, usar sync_playwright directamente
        return _scrape_playwright_sync(url, result)


def _scrape_playwright_sync(url: str, result: ScrapeResult) -> bool:
    """
    Implementación síncrona de Playwright. Llamar solo desde threads
    o cuando no hay un loop asyncio activo.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

        # Flags de Chromium: --no-sandbox y --disable-setuid-sandbox solo en Linux
        # En Windows y macOS no son necesarios y pueden causar warnings
        chromium_args = [
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
        ]
        if sys.platform == "linux":
            chromium_args += ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=chromium_args,
            )
            context = browser.new_context(
                user_agent=_DEFAULT_UA,
                viewport={"width": 1280, "height": 900},
                locale="es-ES",
                extra_http_headers={
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                },
            )
            page = context.new_page()

            # Bloquear recursos pesados que no aportan contenido
            page.route("**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot,mp4,mp3,pdf}", 
                       lambda route: route.abort())
            page.route("**/analytics*", lambda route: route.abort())
            page.route("**/gtag*", lambda route: route.abort())
            page.route("**/hotjar*", lambda route: route.abort())
            page.route("**/intercom*", lambda route: route.abort())

            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
            except PlaywrightTimeout:
                # Si timeout en domcontentloaded, intentar con load
                try:
                    page.goto(url, timeout=20000, wait_until="load")
                except PlaywrightTimeout:
                    browser.close()
                    return False

            # Esperar a que el contenido principal aparezca
            _wait_for_content(page)

            # Extraer título
            result.title = page.title() or result.title

            # Extraer meta tags desde el DOM renderizado
            meta_data = page.evaluate("""() => {
                try {
                    const get = (sel, attr) => {
                        try {
                            const el = document.querySelector(sel);
                            return el ? (el.getAttribute(attr) || el.content || '') : '';
                        } catch(e) { return ''; }
                    };
                    return {
                        description: get('meta[name="description"]', 'content'),
                        og_title: get('meta[property="og:title"]', 'content'),
                        og_desc: get('meta[property="og:description"]', 'content'),
                        og_image: get('meta[property="og:image"]', 'content'),
                        tw_title: get('meta[name="twitter:title"]', 'content'),
                        tw_desc: get('meta[name="twitter:description"]', 'content'),
                        keywords: get('meta[name="keywords"]', 'content'),
                    };
                } catch(e) { return {}; }
            }""")
            if meta_data.get("description") and not result.description:
                result.description = meta_data["description"]
            if meta_data.get("og_title") and not result.og_title:
                result.og_title = meta_data["og_title"]
            if meta_data.get("og_desc") and not result.og_description:
                result.og_description = meta_data["og_desc"]
            if meta_data.get("og_image") and not result.og_image:
                result.og_image = meta_data["og_image"]
            if meta_data.get("keywords") and not result.meta_keywords:
                result.meta_keywords = meta_data["keywords"]

            # Extraer encabezados
            headings = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('h1,h2,h3'))
                    .map(el => (el.innerText || el.textContent || '').trim())
                    .filter(t => t && t.length > 3 && t.length < 200);
            }""")
            if headings:
                result.headings = headings[:30]

            # Extraer navegación
            nav_items = page.evaluate("""() => {
                const navEl = document.querySelector('nav, [role="navigation"], header');
                if (!navEl) return [];
                return Array.from(navEl.querySelectorAll('a, button'))
                    .map(el => (el.innerText || el.textContent || '').trim())
                    .filter(t => t && t.length > 1 && t.length < 50);
            }""")
            if nav_items:
                result.nav_items = list(dict.fromkeys(nav_items))[:15]

            # Extraer CTAs
            cta_texts = page.evaluate("""() => {
                const keywords = ['shop','buy','get','start','contact','learn','order',
                                  'comprar','ver','conocer','contacto','comenzar','pedir',
                                  'now','ahora','más','more','demo','free','gratis','try'];
                return Array.from(document.querySelectorAll('button, a[class*="btn"], a[class*="cta"], [class*="button"]'))
                    .map(el => (el.innerText || el.textContent || '').trim())
                    .filter(t => t && t.length > 2 && t.length < 80
                        && keywords.some(k => t.toLowerCase().includes(k)));
            }""")
            if cta_texts:
                result.cta_texts = list(dict.fromkeys(cta_texts))[:10]

            # Extraer texto principal (todos los elementos de contenido)
            main_text = page.evaluate("""() => {
                // Ocultar elementos de UI que no son contenido
                const skip = ['script','style','noscript','iframe','nav','footer',
                              '[class*="cookie"]','[class*="popup"]','[class*="modal"]',
                              '[class*="banner"]','[id*="cookie"]','[id*="popup"]'];
                skip.forEach(sel => {
                    try {
                        document.querySelectorAll(sel).forEach(el => el.setAttribute('data-skip','1'));
                    } catch(e) {}
                });
                
                const texts = [];
                const seen = new Set();
                const els = document.querySelectorAll(
                    'h1,h2,h3,h4,p,li,td,th,blockquote,figcaption,[class*="description"],[class*="content"],[class*="text"],[class*="copy"]'
                );
                for (const el of els) {
                    try {
                        if (el.closest('[data-skip="1"]')) continue;
                        const t = (el.innerText || el.textContent || '').trim();
                        if (t && t.length > 15 && !seen.has(t)) {
                            seen.add(t);
                            texts.push(t);
                        }
                        if (texts.length >= 150) break;
                    } catch(e) { continue; }
                }
                return texts.join('\\n');
            }""")
            if main_text:
                result.main_text = main_text[:6000]

            # Extraer colores del CSS computado
            colors = page.evaluate("""() => {
                try {
                    const colorSet = new Set();
                    const hexRgb = /^(#[0-9a-fA-F]{3,8}|rgb[a]?\\([^)]+\\))$/;
                    const rootStyle = getComputedStyle(document.documentElement);
                    const varNames = ['--primary','--secondary','--accent','--brand',
                                      '--color-primary','--color-secondary','--theme-color',
                                      '--main-color','--bg-color','--text-color',
                                      '--background','--foreground'];
                    for (const v of varNames) {
                        try {
                            const val = rootStyle.getPropertyValue(v).trim();
                            if (val && hexRgb.test(val)) colorSet.add(val);
                        } catch(e) {}
                    }
                    const prominent = document.querySelectorAll(
                        'header, nav, h1, h2, button'
                    );
                    for (const el of prominent) {
                        try {
                            const cs = getComputedStyle(el);
                            if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)'
                                && cs.backgroundColor !== 'transparent') {
                                colorSet.add(cs.backgroundColor);
                            }
                            if (cs.color && cs.color !== 'rgba(0, 0, 0, 0)') {
                                colorSet.add(cs.color);
                            }
                        } catch(e) {}
                    }
                    return Array.from(colorSet).slice(0, 20);
                } catch(e) { return []; }
            }""")
            if colors:
                result.css_colors = colors

            # Extraer fuentes
            fonts = page.evaluate("""() => {
                try {
                    const fontSet = new Set();
                    const els = document.querySelectorAll('body, h1, h2, p, button');
                    for (const el of els) {
                        try {
                            const ff = getComputedStyle(el).fontFamily;
                            if (ff) {
                                ff.split(',').forEach(f => {
                                    const clean = f.trim().replace(/['"]/g, '');
                                    if (clean && !['serif','sans-serif','monospace','cursive','fantasy',
                                                   'system-ui','-apple-system','BlinkMacSystemFont'].includes(clean)) {
                                        fontSet.add(clean);
                                    }
                                });
                            }
                        } catch(e) {}
                    }
                    return Array.from(fontSet).slice(0, 8);
                } catch(e) { return []; }
            }""")
            if fonts:
                result.fonts = fonts

            browser.close()

        result.strategy_used = "playwright-headless"
        return result.is_sufficient()

    except ImportError:
        logger.debug("[scraper] Playwright no disponible")
        return False
    except Exception as e:
        logger.warning(f"[scraper] Playwright falló: {e}")
        return False


def _wait_for_content(page) -> None:
    """Espera inteligente para que el contenido JS se renderice."""
    # Intentar esperar por selectores comunes de contenido
    selectors_to_try = [
        "h1", "h2", "main", "article",
        "[class*='hero']", "[class*='banner']", "[class*='content']",
        "[class*='product']", "[class*='feature']", "[class*='section']",
    ]
    for sel in selectors_to_try:
        try:
            page.wait_for_selector(sel, timeout=5000)
            break
        except Exception:
            continue

    # Espera adicional para lazy-loading y animaciones
    time.sleep(2)

    # Scroll suave para activar lazy-loading
    try:
        page.evaluate("""() => {
            return new Promise(resolve => {
                let pos = 0;
                const step = () => {
                    pos += 300;
                    window.scrollTo(0, pos);
                    if (pos < document.body.scrollHeight * 0.5) {
                        setTimeout(step, 100);
                    } else {
                        window.scrollTo(0, 0);
                        resolve();
                    }
                };
                step();
            });
        }""")
        time.sleep(1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Estrategia 4: Extracción enriquecida de meta tags + og:image
# ---------------------------------------------------------------------------
def _scrape_meta_enriched(url: str, result: ScrapeResult) -> bool:
    """
    Extracción máxima de meta tags, Open Graph, Twitter Cards, JSON-LD
    y screenshot si está disponible (como en Taskade _internal/screenshot).
    Siempre se ejecuta como complemento de otras estrategias.
    """
    try:
        from bs4 import BeautifulSoup

        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=20, allow_redirects=True)
        _validate_redirect_target(resp)  # Anti-SSRF: validar destino final
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        _extract_meta(soup, result)
        _extract_json_ld(soup, result)
        _extract_colors_from_html(html, result)
        _extract_fonts_from_html(html, result)

        # Buscar screenshot interno (patrón Taskade y similares)
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        screenshot_candidates = [
            f"{base}/_internal/screenshot",
            f"{base}/og-image.png",
            f"{base}/og-image.jpg",
            f"{base}/social-preview.png",
        ]
        if result.og_image:
            screenshot_candidates.insert(0, result.og_image)

        for sc_url in screenshot_candidates[:3]:
            try:
                head = requests.head(sc_url, headers=_DEFAULT_HEADERS, timeout=5, allow_redirects=True)
                if head.status_code == 200 and "image" in head.headers.get("content-type", ""):
                    result.screenshot_url = sc_url
                    break
            except Exception:
                continue

        # Si no hay texto pero hay JSON-LD, construir texto desde él
        if not result.main_text and result.json_ld:
            jld_texts = []
            for jld in result.json_ld:
                for k, v in jld.items():
                    if k.startswith("@"):
                        continue
                    if isinstance(v, str) and len(v) > 10:
                        jld_texts.append(f"{k}: {v}")
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str) and len(item) > 10:
                                jld_texts.append(item)
                            elif isinstance(item, dict):
                                name = item.get("name") or item.get("description", "")
                                if name:
                                    jld_texts.append(name)
            if jld_texts:
                result.main_text = "\n".join(jld_texts)

        if not result.strategy_used:
            result.strategy_used = "meta-enriched"
        else:
            result.strategy_used += "+meta"

        return bool(result.title or result.description or result.og_description)

    except Exception as e:
        logger.debug(f"[scraper] Meta enriched falló: {e}")
        return False


# ---------------------------------------------------------------------------
# Helpers de extracción
# ---------------------------------------------------------------------------
def _extract_meta(soup, result: ScrapeResult) -> None:
    """Extrae todos los meta tags relevantes del BeautifulSoup."""
    def get_meta(*attrs):
        for attr_name, attr_val in attrs:
            tag = soup.find("meta", {attr_name: attr_val})
            if tag:
                return tag.get("content", "").strip()
        return ""

    if not result.title:
        title_tag = soup.find("title")
        result.title = title_tag.get_text(strip=True) if title_tag else ""

    result.description = result.description or get_meta(
        ("name", "description"), ("property", "og:description"), ("name", "twitter:description")
    )
    result.og_title = result.og_title or get_meta(
        ("property", "og:title"), ("name", "og:title")
    )
    result.og_description = result.og_description or get_meta(
        ("property", "og:description"), ("name", "og:description")
    )
    result.og_image = result.og_image or get_meta(
        ("property", "og:image"), ("name", "og:image"), ("name", "twitter:image")
    )
    result.twitter_title = result.twitter_title or get_meta(("name", "twitter:title"))
    result.twitter_description = result.twitter_description or get_meta(("name", "twitter:description"))
    result.meta_keywords = result.meta_keywords or get_meta(("name", "keywords"))


def _extract_json_ld(soup, result: ScrapeResult) -> None:
    """Extrae y parsea todos los bloques JSON-LD del HTML."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                result.json_ld.append(data)
            elif isinstance(data, list):
                result.json_ld.extend(data)
        except (json.JSONDecodeError, TypeError):
            continue


def _extract_colors_from_html(html: str, result: ScrapeResult) -> None:
    """Extrae colores hex y rgb del HTML/CSS inline."""
    if result.css_colors:
        return  # ya extraídos por Playwright
    # Colores hex
    hex_colors = re.findall(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', html)
    # Filtrar colores muy comunes/genéricos
    skip = {"ffffff", "000000", "fff", "000", "cccccc", "333333", "666666",
            "999999", "eeeeee", "f0f0f0", "e5e5e5", "d9d9d9", "f5f5f5"}
    unique_colors = list(dict.fromkeys(
        f"#{c}" for c in hex_colors if c.lower() not in skip
    ))[:15]
    if unique_colors:
        result.css_colors = unique_colors


def _extract_fonts_from_html(html: str, result: ScrapeResult) -> None:
    """Extrae nombres de fuentes del HTML/CSS."""
    if result.fonts:
        return
    # Google Fonts
    gf = re.findall(r'fonts\.googleapis\.com/css[^"\']*family=([^&"\'|]+)', html)
    fonts = []
    for f in gf:
        name = f.split(":")[0].replace("+", " ").strip()
        if name:
            fonts.append(name)
    # font-family en CSS inline
    ff = re.findall(r'font-family\s*:\s*["\']?([^;,"\']+)["\']?', html)
    for f in ff:
        name = f.strip().strip("'\"")
        if name and name not in ["serif", "sans-serif", "monospace", "inherit", "initial"]:
            fonts.append(name)
    result.fonts = list(dict.fromkeys(fonts))[:8]


# ---------------------------------------------------------------------------
# Función principal de scraping
# ---------------------------------------------------------------------------
def scrape_website(url: str) -> str:
    """
    Función principal. Intenta extraer el contenido de un sitio web
    usando múltiples estrategias en cascada.

    Retorna un texto enriquecido listo para ser procesado por el LLM.
    """
    # Normalizar URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    result = ScrapeResult()
    result.url = url

    logger.info(f"[scraper] Iniciando scraping de: {url}")

    # --- Estrategia 1: Estática (rápida, sin JS) ---
    static_ok = _scrape_static(url, result)
    logger.debug(f"[scraper] Estrategia estática: {'OK' if static_ok else 'insuficiente'} "
                 f"({len(result.main_text)} chars)")

    # --- Siempre enriquecer con meta tags ---
    _scrape_meta_enriched(url, result)

    if static_ok and result.is_sufficient():
        logger.info(f"[scraper] Contenido suficiente con estrategia estática ({len(result.main_text)} chars)")
        return result.to_text()

    # --- Estrategia 2: Jina Reader (cloud, renderiza JS) ---
    logger.info(f"[scraper] Contenido insuficiente ({len(result.main_text)} chars), intentando Jina Reader...")
    jina_result = ScrapeResult()
    jina_result.url = url
    jina_ok = _scrape_jina(url, jina_result)

    if jina_ok and jina_result.is_sufficient():
        # Combinar: usar texto de Jina + meta de estática
        jina_result.description = jina_result.description or result.description
        jina_result.og_title = jina_result.og_title or result.og_title
        jina_result.og_description = jina_result.og_description or result.og_description
        jina_result.og_image = jina_result.og_image or result.og_image
        jina_result.css_colors = jina_result.css_colors or result.css_colors
        jina_result.fonts = jina_result.fonts or result.fonts
        jina_result.json_ld = jina_result.json_ld or result.json_ld
        jina_result.screenshot_url = result.screenshot_url
        logger.info(f"[scraper] Jina Reader exitoso ({len(jina_result.main_text)} chars)")
        return jina_result.to_text()

    # --- Estrategia 3: Playwright headless (JS local completo) ---
    logger.info(f"[scraper] Jina insuficiente, intentando Playwright headless...")
    pw_result = ScrapeResult()
    pw_result.url = url
    pw_ok = _scrape_playwright(url, pw_result)

    if pw_ok and pw_result.is_sufficient():
        # Combinar con meta datos previos
        pw_result.description = pw_result.description or result.description
        pw_result.og_image = pw_result.og_image or result.og_image
        pw_result.json_ld = pw_result.json_ld or result.json_ld
        pw_result.screenshot_url = result.screenshot_url
        logger.info(f"[scraper] Playwright exitoso ({len(pw_result.main_text)} chars)")
        return pw_result.to_text()

    # --- Fallback final: combinar todo lo disponible ---
    logger.warning(f"[scraper] Todas las estrategias produjeron contenido limitado. "
                   f"Usando síntesis de datos disponibles.")

    # Usar el resultado más rico disponible
    best = max([result, jina_result, pw_result],
               key=lambda r: len(r.main_text) + len(r.description))

    # Enriquecer con datos de los otros
    for other in [result, jina_result, pw_result]:
        if other is best:
            continue
        best.headings = best.headings or other.headings
        best.css_colors = best.css_colors or other.css_colors
        best.fonts = best.fonts or other.fonts
        best.json_ld = best.json_ld or other.json_ld
        best.og_image = best.og_image or other.og_image
        best.screenshot_url = best.screenshot_url or other.screenshot_url
        if not best.main_text and other.main_text:
            best.main_text = other.main_text

    best.strategy_used = "fallback-synthesis"

    if not best.main_text and not best.description and not best.title:
        best.main_text = f"[No se pudo extraer contenido del sitio {url}. " \
                         f"El sitio puede requerir autenticación o estar temporalmente inaccesible.]"

    return best.to_text()
