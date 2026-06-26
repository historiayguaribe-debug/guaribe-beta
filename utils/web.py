import requests
from bs4 import BeautifulSoup
import re
import logging
import os
import concurrent.futures
from typing import List

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
LANGSEARCH_API_KEY = os.environ.get("LANGSEARCH_API_KEY")

# ==================== FUENTE 1: LangSearch (principal) ====================
def buscar_langsearch(consulta: str, limite: int = 3) -> List[str]:
    """Búsqueda en LangSearch (requiere API key)."""
    if not LANGSEARCH_API_KEY:
        logger.warning("⚠️ LangSearch: API key no configurada")
        return []

    try:
        url = "https://api.langsearch.com/v1/web-search"
        headers = {
            "Authorization": f"Bearer {LANGSEARCH_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {"query": consulta, "limit": limite}
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        response.raise_for_status()
        data = response.json()

        resultados = []
        for item in data.get('results', [])[:limite]:
            titulo = item.get('title', '').strip()
            if titulo:
                resultados.append(titulo[:200])

        if resultados:
            logger.info("✅ LangSearch respondió")
        return resultados
    except Exception as e:
        logger.warning(f"⚠️ LangSearch falló: {e}")
        return []

# ==================== FUENTE 2: DuckDuckGo Lite (respaldo) ====================
def buscar_duckduckgo(consulta: str, limite: int = 3) -> List[str]:
    """Búsqueda en DuckDuckGo Lite (sin API key)."""
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=8)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        resultados = []
        for a in soup.find_all('a'):
            texto = a.get_text().strip()
            if 40 < len(texto) < 300 and texto not in resultados:
                texto = re.sub(r'\s+', ' ', texto).strip()
                resultados.append(texto[:200])
                if len(resultados) >= limite:
                    break
        if resultados:
            logger.info("✅ DuckDuckGo respondió")
        return resultados
    except requests.Timeout:
        logger.warning("⏱️ DuckDuckGo: timeout")
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo falló: {e}")
        return []

# ==================== FUENTE 3: SearXNG (respaldo) ====================
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://searx.tiekoetter.com",
    "https://search.privacytools.io",
]

def buscar_searxng(consulta: str, limite: int = 3) -> List[str]:
    """Búsqueda en SearXNG (sin API key)."""
    for instance in SEARXNG_INSTANCES:
        try:
            url = f"{instance}/search?q={consulta.replace(' ', '+')}&format=json"
            response = requests.get(url, timeout=8)
            response.raise_for_status()
            data = response.json()
            resultados = []
            for result in data.get('results', [])[:limite]:
                titulo = result.get('title', '').strip()
                if titulo:
                    resultados.append(titulo[:200])
            if resultados:
                logger.info(f"✅ SearXNG ({instance}) respondió")
                return resultados
        except Exception as e:
            logger.warning(f"SearXNG ({instance}) falló: {e}")
            continue
    return []

# ==================== ORQUESTADOR DE BÚSQUEDA (con failover) ====================
FUENTES_BUSQUEDA = [
    ("LangSearch", buscar_langsearch),
    ("DuckDuckGo", buscar_duckduckgo),
    ("SearXNG", buscar_searxng),
]

def buscar_en_web(consulta: str, limite: int = 3) -> List[str]:
    """
    Busca en múltiples fuentes en paralelo.
    Devuelve los resultados de la primera fuente que responda.
    Si todas fallan, devuelve lista vacía.
    """
    logger.info(f"🌐 Buscando: {consulta[:50]}...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(FUENTES_BUSQUEDA)) as executor:
        future_to_fuente = {
            executor.submit(func, consulta, limite): nombre
            for nombre, func in FUENTES_BUSQUEDA
        }

        for future in concurrent.futures.as_completed(future_to_fuente):
            nombre = future_to_fuente[future]
            try:
                resultados = future.result(timeout=10)
                if resultados:
                    logger.info(f"✅ {nombre} respondió primero")
                    return resultados
            except Exception as e:
                logger.warning(f"{nombre} falló: {e}")

    logger.warning("❌ Todas las fuentes de búsqueda fallaron")
    return []

# ==================== NOTICIAS (optimizado) ====================
def buscar_noticias() -> str:
    """Busca noticias de Venezuela desde múltiples fuentes RSS."""
    fuentes = [
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("Noticiero Digital", "https://noticierodigital.com/feed"),
        ("RunRun.es", "https://runrun.es/feed"),
        ("TeleSUR", "https://www.telesurtv.net/rss"),
    ]
    noticias = []
    for nombre, url in fuentes:
        try:
            response = requests.get(url, timeout=10, verify=False)
            soup = BeautifulSoup(response.text, 'xml')
            for item in soup.find_all('item')[:2]:
                titulo = item.find('title').text if item.find('title') else ""
                if titulo and len(titulo) > 10:
                    t = titulo.replace("Venezuela", "").strip() or titulo
                    if len(t) > 100:
                        t = t[:97] + "..."
                    noticias.append(f"▪️ {t} ({nombre})")
        except Exception as e:
            logger.warning(f"Error en {nombre}: {e}")
            continue
    return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:10]) if noticias else "📰 No encontré noticias en este momento."

# ==================== TASA BCV ====================
def obtener_tasa():
    try:
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("fuente") == "oficial":
                    return f"💰 *Tasa oficial BCV:* {item['promedio']} Bs/USD"
        return "💰 No pude obtener la tasa."
    except:
        return "💰 Error al consultar la tasa."
