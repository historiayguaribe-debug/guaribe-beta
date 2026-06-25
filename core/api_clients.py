import os
import requests
import logging
from groq import Groq

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

def llamar_api(mensajes, categoria="simple"):
    """Versión mínima: solo usa Groq."""
    if not GROQ_API_KEY:
        logger.error("❌ GROQ_API_KEY no configurada")
        return None
    
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Error en Groq: {e}")
        return None
