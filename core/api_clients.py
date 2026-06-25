import os
import requests
import json
import logging
from typing import List, Dict, Optional
from groq import Groq

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")
HF_API_KEY = os.environ.get("HF_API_KEY")
AION_API_KEY = os.environ.get("AION_API_KEY")
GITHUB_MODELS_KEY = os.environ.get("GITHUB_MODELS_KEY")
AI_STUDIO_TOKEN = os.environ.get("AI_STUDIO_TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY = os.environ.get("SAMBANOVA_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")

# ==================== FUNCIONES POR API ====================

def llamar_grok(mensajes: List[Dict], timeout: int = 10) -> Optional[str]:
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

def llamar_aion(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not AION_API_KEY:
        return None
    try:
        # Aion Labs se sirve a través de OpenRouter
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {AION_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "aion-labs/aion-1.0",
            "messages": mensajes,
            "max_tokens": 2000,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Aion Labs falló: {e}")
        return None

def llamar_github_models(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not GITHUB_MODELS_KEY:
        return None
    try:
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {"Authorization": f"Bearer {GITHUB_MODELS_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "meta-llama/Llama-3.2-3B-Instruct",
            "messages": mensajes,
            "max_tokens": 2000
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"GitHub Models falló: {e}")
        return None

def llamar_ai_studio(mensajes: List[Dict], timeout: int = 20) -> Optional[str]:
    if not AI_STUDIO_TOKEN:
        return None
    try:
        url = "https://aistudio.baidu.com/llm/lmapi/v3/chat/completions"
        headers = {"Authorization": f"Bearer {AI_STUDIO_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": "ernie-4.5-21b-a3b",
            "messages": mensajes,
            "max_tokens": 2000,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"AI Studio (ERNIE) falló: {e}")
        return None

def llamar_cerebras(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not CEREBRAS_API_KEY:
        return None
    try:
        url = "https://api.cerebras.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "llama3.3-70b",
            "messages": mensajes,
            "max_tokens": 2000,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Cerebras falló: {e}")
        return None

def llamar_sambanova(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not SAMBANOVA_API_KEY:
        return None
    try:
        url = "https://api.sambanova.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {SAMBANOVA_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "Llama-3.3-70B",
            "messages": mensajes,
            "max_tokens": 2000,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"SambaNova falló: {e}")
        return None

def llamar_google(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
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

def llamar_deepseek(mensajes: List[Dict], timeout: int = 15) -> Optional[str]:
    if not DEEPSEEK_TOKEN:
        return None
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": mensajes,
            "max_tokens": 2000,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"DeepSeek falló: {e}")
        return None

# ==================== ORQUESTADOR DE APIS ====================

# Definir la prioridad de APIs según la categoría
PRIORIDAD = {
    "simple": [llamar_grok, llamar_mistral, llamar_cohere, llamar_huggingface, llamar_github_models],
    "compleja": [llamar_cohere, llamar_mistral, llamar_grok, llamar_huggingface, llamar_github_models],
    "creativa": [llamar_aion, llamar_mistral, llamar_cohere, llamar_huggingface, llamar_github_models],
    "contexto_largo": [llamar_cerebras, llamar_sambanova, llamar_huggingface, llamar_cohere],
    "multimodal": [llamar_ai_studio, llamar_google, llamar_huggingface],
    "default": [llamar_grok, llamar_mistral, llamar_cohere, llamar_huggingface, llamar_github_models]
}

def llamar_api(mensajes: List[Dict], categoria: str = "simple") -> Optional[str]:
    """
    Llama a las APIs en orden de prioridad según la categoría.
    Si una falla, pasa a la siguiente.
    """
    # Seleccionar la lista de funciones según la categoría
    lista_funciones = PRIORIDAD.get(categoria, PRIORIDAD["default"])
    
    for funcion in lista_funciones:
        # Obtener el nombre de la función para el log
        nombre_funcion = funcion.__name__.replace("llamar_", "")
        respuesta = funcion(mensajes)
        if respuesta:
            logger.info(f"✅ {nombre_funcion} respondió correctamente")
            return respuesta
        logger.warning(f"⚠️ {nombre_funcion} falló, probando siguiente...")
    
    logger.error("❌ Todas las APIs fallaron")
    return None
