import os
import requests
import logging
from typing import List, Dict, Optional
from groq import Groq

logger = logging.getLogger(__name__)

# ==================== LECTURA DE CLAVES ====================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
HF_API_KEY = os.environ.get("HF_API_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")

# ==================== FUNCIONES POR API ====================

def llamar_grok(mensajes: List[Dict], timeout: int = 10) -> Optional[str]:
    """Groq - Rápido y liviano."""
    if not GROQ_API_KEY:
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            max_tokens=2000,
            timeout=timeout
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq falló: {e}")
        return None

def llamar_mistral(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Mistral AI - Creatividad y razonamiento."""
    if not MISTRAL_API_KEY:
        return None
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "mistral-small-4", "messages": mensajes, "max_tokens": 2000}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Mistral falló: {e}")
        return None

def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    """Intenta las APIs en orden de prioridad según categoría."""
    proveedores = [
        ("grok", llamar_grok),
        ("mistral", llamar_mistral),
    ]
    # Si es compleja o cultural, priorizar Mistral
    if categoria in ["compleja", "cultural"]:
        proveedores = [("mistral", llamar_mistral), ("grok", llamar_grok)]
    
    for nombre, funcion in proveedores:
        logger.info(f"🔄 Intentando con {nombre}...")
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
