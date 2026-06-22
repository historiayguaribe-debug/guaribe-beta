import os
import requests
import json
import logging
from groq import Groq
from .personality import obtener_prompt

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Inicializar Groq
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
    except:
        pass

def llamar_deepseek(mensajes: list, usar_busqueda: bool = False) -> str:
    """Llama a DeepSeek (gratis)."""
    if not DEEPSEEK_TOKEN:
        return None
    payload = {
        "model": "deepseek",
        "messages": mensajes,
        "stream": False,
        "max_tokens": 2000,
        "search": usar_busqueda
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=50)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"DeepSeek falló: {e}")
        return None

def llamar_grok(mensajes: list) -> str:
    """Llama a Groq como fallback (gratis)."""
    if not groq_client:
        return None
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq falló: {e}")
        return None

def orquestar(consulta: str, categoria: str, contexto: list, perfil: dict) -> str:
    """
    Construye la respuesta usando el mejor modelo disponible.
    """
    # 1. Respuestas instantáneas sin IA
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe, tu asistente llanero. ¿En qué te ayudo hoy? 🤠"
    
    # 2. Obtener prompt adecuado según categoría y personalidad
    system_prompt = obtener_prompt(categoria, perfil)
    
    # 3. Construir mensajes
    mensajes = [
        {"role": "system", "content": system_prompt}
    ]
    
    # 4. Agregar contexto (memoria + documentos)
    if contexto:
        contexto_texto = "\n".join([f"- {c}" for c in contexto])
        mensajes.append({
            "role": "system", 
            "content": f"Contexto relevante de conversaciones anteriores:\n{contexto_texto}"
        })
    
    # 5. Agregar la consulta del usuario
    mensajes.append({"role": "user", "content": consulta})
    
    # 6. Decidir si usar búsqueda web
    usar_busqueda = categoria in ["pregunta_persona", "noticias", "compleja"]
    
    # 7. Intentar con DeepSeek
    respuesta = llamar_deepseek(mensajes, usar_busqueda)
    if respuesta:
        return respuesta
    
    # 8. Fallback a Groq
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta
    
    # 9. Último recurso: respuesta predefinida
    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. Si es urgente, dime y busco otra forma. 🙏"
