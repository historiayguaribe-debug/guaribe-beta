import os
import requests
import json
import logging
from typing import List, Dict, Optional
from groq import Groq

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.environ.get("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/chat/completions")

# ==================== CLIENTES INDIVIDUALES ====================
def llamar_grok(mensajes: List[Dict], timeout: int = 10) -> Optional[str]:
    """Llama a Groq (rápido, liviano)."""
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

def llamar_google(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Llama a Gemini 2.5 Flash (contexto enorme)."""
    if not GOOGLE_API_KEY:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GOOGLE_API_KEY}"
        payload = {"contents": [{"parts": [{"text": mensajes[0]['content']}]}]}
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.warning(f"Google Gemini falló: {e}")
        return None

def llamar_mistral(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Llama a Mistral Small 4 (alto rendimiento)."""
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

def llamar_openrouter(mensajes: List[Dict], timeout: int = 20) -> Optional[str]:
    """Llama a OpenRouter (unifica modelos)."""
    if not OPENROUTER_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "openrouter/auto", "messages": mensajes, "max_tokens": 2000}
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"OpenRouter falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS ====================
PROVEEDORES = [
    ("grok", llamar_grok),
    ("google", llamar_google),
    ("mistral", llamar_mistral),
    ("openrouter", llamar_openrouter)
]

def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    """
    Llama a las APIs en orden de prioridad según la categoría.
    Si una falla, pasa a la siguiente.
    """
    # Reordenar prioridad según categoría
    if categoria == "compleja":
        prioridad = [("google", llamar_google), ("mistral", llamar_mistral), ("grok", llamar_grok), ("openrouter", llamar_openrouter)]
    elif categoria == "creativa":
        prioridad = [("mistral", llamar_mistral), ("openrouter", llamar_openrouter), ("google", llamar_google), ("grok", llamar_grok)]
    else:  # simple
        prioridad = [("grok", llamar_grok), ("google", llamar_google), ("mistral", llamar_mistral), ("openrouter", llamar_openrouter)]
    
    for nombre, funcion in prioridad:
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
