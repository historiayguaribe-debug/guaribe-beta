import requests
from bs4 import BeautifulSoup
import re
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
LANGSEARCH_API_KEY = os.environ.get("LANGSEARCH_API_KEY")

# ==================== FUENTE 1: LangSearch API ====================
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
        payload = {
            "query": consulta,
            "limit": limite
        }
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        resultados = []
        for item in data.get('results', [])[:limite]:
            titulo = item.get('title', '').strip()
            if titulo:
                resultados.append(titulo[:200])
        
        if resultados:
            logger.info("✅ LangSearch respondió correctamente")
        return resultados
    except Exception as e:
        logger.warning(f"LangSearch falló: {e}")
        return []

# ==================== FUENTE 2: SearXNG (meta-buscador) ====================
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

# ==================== FUENTE 3: DuckDuckGo Lite (scraping, último recurso) ====================
def buscar_duckduckgo(consulta: str, limite: int = 3) -> List[str]:
    """Búsqueda en DuckDuckGo Lite (sin API key, último recurso)."""
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
            logger.info("✅ DuckDuckGo respondió (como último recurso)")
        return resultados
    except Exception as e:
        logger.warning(f"DuckDuckGo falló: {e}")
        return []

# ==================== ORQUESTADOR DE BÚSQUEDA (CON PRIORIDADES) ====================
def buscar_en_web(consulta: str, limite: int = 3) -> List[str]:
    """
    Busca en múltiples fuentes con prioridad:
    1. LangSearch (más estable)
    2. SearXNG (sin API key)
    3. DuckDuckGo (último recurso)
    """
    logger.info(f"🌐 Buscando: {consulta[:50]}...")

    # 1. LangSearch
    resultados = buscar_langsearch(consulta, limite)
    if resultados:
        return resultados

    # 2. SearXNG
    resultados = buscar_searxng(consulta, limite)
    if resultados:
        return resultados

    # 3. DuckDuckGo (último recurso)
    resultados = buscar_duckduckgo(consulta, limite)
    if resultados:
        return resultados

    logger.warning("❌ Todas las fuentes de búsqueda fallaron")
    return []

# ==================== NOTICIAS (USANDO BÚSQUEDA) ====================
def buscar_noticias() -> str:
    """Busca noticias de Venezuela usando el orquestador de búsqueda."""
    consulta = "noticias Venezuela hoy"
    resultados = buscar_en_web(consulta, limite=5)
    
    if resultados:
        noticias = "\n".join([f"▪️ {r}" for r in resultados])
        return f"📰 **Noticias de Venezuela**\n\n{noticias}"
    return "📰 No encontré noticias en este momento."

# ==================== TASA BCV (sin cambios) ====================
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
