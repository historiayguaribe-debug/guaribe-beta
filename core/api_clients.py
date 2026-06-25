# core/api_clients.py
import os
import requests
from utils.logger import logger

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def llamar_api(mensajes, categoria="simple"):
    if not GROQ_API_KEY:
        logger.error("❌ GROQ_API_KEY no configurada")
        return None

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "llama-3.1-8b-instant", "messages": mensajes, "max_tokens": 500}
        response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"❌ Error en Groq: {e}")
        return None
