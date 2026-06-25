import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

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

def buscar_noticias():
    fuentes = [
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("VTV", "https://www.vtv.gob.ve/feed"),
        ("Correo del Orinoco", "https://www.correodelorinoco.gob.ve/feed"),
        ("AVN", "https://www.avn.info.ve/feed"),
        ("TeleSUR", "https://www.telesurtv.net/rss"),
        ("Noticiero Digital", "https://noticierodigital.com/feed"),
        ("RunRun.es", "https://runrun.es/feed"),
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
            logger.warning(f"Error obteniendo noticias de {nombre}: {e}")
            continue
    return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:10]) if noticias else "📰 No encontré noticias en este momento."

def buscar_en_web(consulta: str, limite: int = 3) -> list:
    """Busca en DuckDuckGo Lite (sin API key)."""
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
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
        return resultados
    except Exception as e:
        logger.warning(f"Error en búsqueda web: {e}")
        return []
