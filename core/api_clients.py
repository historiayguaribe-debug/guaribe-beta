import os
import requests
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ==================== LECTURA DE CLAVES ====================
GROQ_API_KEYS = os.environ.get("GROQ_API_KEY", "").split(",")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY = os.environ.get("SAMBANOVA_API_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")

# ==================== URLS ====================
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GITHUB_API_URL = "https://api.github.com/models/meta-llama-3.3-70b-instruct/chat/completions"  # Corregido para PAT de GitHub
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
SAMBANOVA_API_URL = "https://api.sambanova.ai/v1/chat/completions"

# ==================== MODELOS POR API ====================
def llamar_github(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """GitHub Models - con PAT de GitHub (corregido)."""
    if not GITHUB_MODELS_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {GITHUB_MODELS_KEY}", "Content-Type": "application/json"}
        payload = {"messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(GITHUB_API_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ GitHub Models respondió")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"GitHub falló: {e}")
        return None

def llamar_cerebras(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Cerebras - modelo llama-3.3-70b (corregido)."""
    if not CEREBRAS_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.3-70b", "messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(CEREBRAS_API_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Cerebras respondió")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Cerebras falló: {e}")
        return None

def llamar_sambanova(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """SambaNova - modelo Llama-3.3-70B-Instruct (corregido)."""
    if not SAMBANOVA_API_KEY:
        return None
    try:
        headers = {"Authorization": f"Bearer {SAMBANOVA_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "Llama-3.3-70B-Instruct", "messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(SAMBANOVA_API_URL, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ SambaNova respondió")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"SambaNova falló: {e}")
        return None

def llamar_mistral(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not MISTRAL_API_KEY:
        return None
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "mistral-small-latest", "messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Mistral respondió")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Mistral falló: {e}")
        return None

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
            logger.info(f"✅ Groq: clave {idx+1} respondió")
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"⚠️ Groq clave {idx+1} falló: {e}")
            continue
    return None

def llamar_cohere(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not COHERE_API_KEY:
        return None
    try:
        url = "https://api.cohere.com/v2/chat"
        headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "command-a", "messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ Cohere respondió")
        return response.json()["message"]["content"]
    except Exception as e:
        logger.warning(f"Cohere falló: {e}")
        return None

def llamar_ernie(mensajes: List[Dict], timeout: int = 20) -> Optional[str]:
    if not AI_STUDIO_TOKEN:
        return None
    try:
        url = "https://aistudio.baidu.com/llm/lmapi/v3/chat/completions"
        headers = {"Authorization": f"Bearer {AI_STUDIO_TOKEN}", "Content-Type": "application/json"}
        payload = {"model": "ernie-4.5-21b-a3b", "messages": mensajes, "max_tokens": 500, "temperature": 0.7}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("✅ ERNIE respondió")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"ERNIE falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS (con nuevo orden) ====================
def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    """
    Orquestador de APIs con fallback automático.
    Prioriza GitHub, Cerebras, SambaNova, Mistral, Cohere, Groq.
    """
    # Prioridad según categoría
    if categoria in ["simple", "actualidad"]:
        proveedores = [
            ("github", llamar_github),
            ("mistral", llamar_mistral),
            ("grok", llamar_grok),
        ]
    elif categoria in ["creativa", "cultural"]:
        proveedores = [
            ("github", llamar_github),
            ("mistral", llamar_mistral),
            ("cohere", llamar_cohere),
            ("grok", llamar_grok),
        ]
    else:  # compleja
        proveedores = [
            ("github", llamar_github),
            ("ernie", llamar_ernie),
            ("mistral", llamar_mistral),
            ("cohere", llamar_cohere),
            ("grok", llamar_grok),
        ]

    for nombre, funcion in proveedores:
        logger.info(f"🔄 Intentando con {nombre}...")
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")

    logger.error("❌ Todas las APIs fallaron")
    return None
