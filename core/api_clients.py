import os
import requests
from utils.logger import logger

# ==================== CONFIGURACIÓN DE APIS ====================
# Groq (múltiples claves)
GROQ_API_KEYS = os.environ.get("GROQ_API_KEY", "").split(",")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Otras APIs (de momento solo declaradas, se irán integrando)
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
# ... más APIs según se vayan añadiendo

# ==================== FUNCIONES POR API ====================
def llamar_grok(mensajes, timeout=15):
    """Intenta llamar a Groq con la primera clave que funcione."""
    if not GROQ_API_KEYS or GROQ_API_KEYS == ['']:
        logger.error("❌ No hay claves de Groq configuradas")
        return None
    
    for idx, api_key in enumerate(GROQ_API_KEYS):
        api_key = api_key.strip()
        if not api_key:
            continue
        try:
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.1-8b-instant", "messages": mensajes, "max_tokens": 500}
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            logger.info(f"✅ Groq: clave {idx+1} respondió correctamente")
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"⚠️ Groq: clave {idx+1} falló: {e}")
            continue
    
    logger.error("❌ Todas las claves de Groq fallaron")
    return None

def llamar_mistral(mensajes, timeout=15):
    """Mistral (pendiente de implementación completa)."""
    if not MISTRAL_API_KEY:
        return None
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "mistral-small-4", "messages": mensajes, "max_tokens": 500}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Mistral falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS ====================
def llamar_api(mensajes, categoria="simple"):
    """
    Intenta llamar a las APIs en orden de prioridad según la categoría.
    """
    proveedores = [
        ("grok", llamar_grok),
        ("mistral", llamar_mistral),
        # Añadir más APIs aquí (cohere, ernie, etc.)
    ]
    
    # Reordenar según categoría
    if categoria in ["compleja", "cultural", "actualidad"]:
        # Priorizar Mistral para preguntas complejas o culturales
        proveedores = [("mistral", llamar_mistral), ("grok", llamar_grok)]
    elif categoria in ["simple", "noticias", "saludo"]:
        proveedores = [("grok", llamar_grok), ("mistral", llamar_mistral)]
    
    for nombre, funcion in proveedores:
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
