import os
import requests
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ==================== CLAVES ====================
GROQ_API_KEYS = os.environ.get("GROQ_API_KEY", "").split(",")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
HF_API_KEY = os.environ.get("HF_API_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ==================== GROQ ====================
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

# ==================== MISTRAL ====================
def llamar_mistral(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not MISTRAL_API_KEY:
        return None
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mistral-small-latest",
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

# ==================== COHERE ====================
def llamar_cohere(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not COHERE_API_KEY:
        logger.warning("⚠️ COHERE_API_KEY no configurada")
        return None
    try:
        url = "https://api.cohere.com/v2/chat"
        headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "command-a",
            "messages": mensajes,
            "max_tokens": 500,
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Cohere respondió correctamente")
        return response.json()["message"]["content"]
    except Exception as e:
        logger.warning(f"Cohere falló: {e}")
        return None

# ==================== ERNIE (Baidu AI Studio) ====================
def llamar_ernie(mensajes: List[Dict], timeout: int = 20) -> Optional[str]:
    if not AI_STUDIO_TOKEN:
        logger.warning("⚠️ AI_STUDIO_TOKEN no configurado")
        return None
    try:
        url = "https://aistudio.baidu.com/llm/lmapi/v3/chat/completions"
        headers = {"Authorization": f"Bearer {AI_STUDIO_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": "ernie-4.5-21b-a3b",
            "messages": mensajes,
            "max_tokens": 500,
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ ERNIE respondió correctamente")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"ERNIE falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS (fallback) ====================
def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    # Esta función se usa como fallback general
    proveedores = [
        ("grok", llamar_grok),
        ("mistral", llamar_mistral),
        ("cohere", llamar_cohere),
        ("ernie", llamar_ernie),
    ]
    
    for nombre, funcion in proveedores:
        logger.info(f"🔄 Intentando con {nombre}...")
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
