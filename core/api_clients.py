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
AION_API_KEY = os.environ.get("AION_API_KEY")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY = os.environ.get("SAMBANOVA_API_KEY")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")  # Por si acaso

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

def llamar_cohere(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Cohere - Razonamiento y embeddings."""
    if not COHERE_API_KEY:
        return None
    try:
        url = "https://api.cohere.com/v2/chat"
        headers = {"Authorization": f"Bearer {COHERE_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "command-a", "messages": mensajes, "max_tokens": 2000}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["message"]["content"]
    except Exception as e:
        logger.warning(f"Cohere falló: {e}")
        return None

def llamar_huggingface(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """Hugging Face - Modelos especializados."""
    if not HF_API_KEY:
        return None
    try:
        model = "meta-llama/Llama-3.2-3B-Instruct"
        url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {HF_API_KEY}"}
        prompt = mensajes[0]['content']
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 500}}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("generated_text", "").replace(prompt, "").strip()
        elif isinstance(data, dict):
            return data.get("generated_text", "").replace(prompt, "").strip()
        return None
    except Exception as e:
        logger.warning(f"Hugging Face falló: {e}")
        return None

def llamar_ernie(mensajes: List[Dict], timeout: int = 20) -> Optional[str]:
    """ERNIE (Baidu AI Studio) - 1M tokens gratis."""
    if not AI_STUDIO_TOKEN:
        return None
    try:
        url = "https://aistudio.baidu.com/llm/lmapi/v3/chat/completions"
        headers = {"Authorization": f"Bearer {AI_STUDIO_TOKEN}", "Content-Type": "application/json"}
        payload = {"model": "ernie-4.5-21b-a3b", "messages": mensajes, "max_tokens": 2000}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"ERNIE falló: {e}")
        return None

def llamar_github_models(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    """GitHub Models - 50 requests/día."""
    if not GITHUB_MODELS_KEY:
        return None
    try:
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {"Authorization": f"Bearer {GITHUB_MODELS_KEY}", "Content-Type": "application/json"}
        payload = {"model": "meta-llama-3.3-70b-instruct", "messages": mensajes, "max_tokens": 2000}
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"GitHub Models falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS ====================

PROVEEDORES_POR_CATEGORIA = {
    "simple": [
        ("groq", llamar_grok),
        ("mistral", llamar_mistral),
        ("github", llamar_github_models),
        ("cohere", llamar_cohere),
    ],
    "compleja": [
        ("ernie", llamar_ernie),
        ("mistral", llamar_mistral),
        ("cohere", llamar_cohere),
        ("huggingface", llamar_huggingface),
        ("github", llamar_github_models),
    ],
    "creativa": [
        ("mistral", llamar_mistral),
        ("cohere", llamar_cohere),
        ("github", llamar_github_models),
        ("ernie", llamar_ernie),
    ],
    "noticias": [
        ("groq", llamar_grok),
        ("github", llamar_github_models),
        ("mistral", llamar_mistral),
    ],
}

def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    """
    Intenta llamar a las APIs en orden de prioridad según la categoría.
    Si una falla, pasa a la siguiente.
    """
    proveedores = PROVEEDORES_POR_CATEGORIA.get(categoria, PROVEEDORES_POR_CATEGORIA["simple"])
    
    for nombre, funcion in proveedores:
        logger.info(f"🔄 Intentando con {nombre}...")
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
