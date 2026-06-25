import os
import requests
import logging
from typing import List, Dict, Optional
from groq import Groq

logger = logging.getLogger(__name__)

GROQ_API_KEYS = os.environ.get("GROQ_API_KEY", "").split(",")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
HF_API_KEY = os.environ.get("HF_API_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def llamar_grok(mensajes: List[Dict], timeout: int = 10) -> Optional[str]:
    for idx, key in enumerate(GROQ_API_KEYS):
        key = key.strip()
        if not key:
            continue
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.1-8b-instant", "messages": mensajes, "max_tokens": 500}
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            logger.info(f"✅ Groq: clave {idx+1} respondió correctamente")
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"⚠️ Groq clave {idx+1} falló: {e}")
            continue
    return None

def llamar_mistral(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not MISTRAL_API_KEY:
        return None
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mistral-small-4",
            "messages": mensajes,
            "max_tokens": 500,
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Mistral respondió correctamente")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Mistral falló: {e}")
        return None

def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    proveedores = [
        ("grok", llamar_grok),
        ("mistral", llamar_mistral),
    ]
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
