import os
import requests
import logging
from groq import Groq
from typing import List, Dict, Optional
import re

logger = logging.getLogger(__name__)

DEEPSEEK_URL = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

def cargar_conocimiento_critico() -> str:
    try:
        with open("data/critical_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

BCC_COMPLETA = cargar_conocimiento_critico()

def extraer_conocimiento_relevante(consulta: str, bcc: str = BCC_COMPLETA) -> str:
    if not bcc or len(consulta) < 10:
        return bcc
    secciones = re.split(r'\[.*?\]', bcc)
    titulos = re.findall(r'\[(.*?)\]', bcc)
    palabras_clave = set(re.findall(r'\b\w{4,}\b', consulta.lower()))
    secciones_relevantes = []
    for i, seccion in enumerate(secciones):
        if not seccion.strip():
            continue
        for palabra in palabras_clave:
            if palabra in seccion.lower():
                titulo = titulos[i-1] if i > 0 else "General"
                secciones_relevantes.append(f"[{titulo}]{seccion}")
                break
    if not secciones_relevantes:
        for i, seccion in enumerate(secciones[:3]):
            if seccion.strip():
                titulo = titulos[i-1] if i > 0 else "General"
                secciones_relevantes.append(f"[{titulo}]{seccion}")
    return "\n".join(secciones_relevantes)

PROMPT_IDENTIDAD = """
Eres Guaribe, asistente de IA venezolano con identidad llanera.
Hablas como un venezolano del llano: directo, humilde, orgulloso, carismático.
Usas 'pana' y 'mi pana' con confianza.
Tu misión es ayudar, educar y acompañar al usuario con inteligencia y calidez.
"""

PROMPT_CRITICO = """
Eres Guaribe en modo crítico. Analiza el tema desde una perspectiva sociopolítica.
Reconoces las estructuras de poder, la lucha de clases y la hegemonía cultural.
"""

PROMPT_COTIDIANO = """
Eres Guaribe en modo cotidiano. Hablas como un pana de confianza.
Usas lenguaje coloquial, con humor y cercanía.
"""

def seleccionar_tono(categoria: str, consulta: str) -> str:
    if len(consulta) < 30:
        return PROMPT_COTIDIANO
    if categoria in ["compleja", "pregunta_persona"]:
        return PROMPT_CRITICO
    return PROMPT_COTIDIANO

def construir_prompt_system(categoria: str, consulta: str, contexto: List[str]) -> str:
    prompt = PROMPT_IDENTIDAD + "\n\n"
    tono = seleccionar_tono(categoria, consulta)
    prompt += tono + "\n\n"
    conocimiento_relevante = extraer_conocimiento_relevante(consulta)
    if conocimiento_relevante:
        prompt += "\n[CONOCIMIENTO DE REFERENCIA]\n" + conocimiento_relevante + "\n"
    if contexto:
        contexto_resumido = "\n".join(contexto[:3])
        prompt += "\n[CONTEXTO]\n" + contexto_resumido + "\n"
    return prompt

def llamar_deepseek(mensajes: List[Dict], usar_busqueda: bool = False) -> Optional[str]:
    if not DEEPSEEK_TOKEN:
        return None
    payload = {
        "model": "deepseek",
        "messages": mensajes,
        "stream": False,
        "max_tokens": 2000,
        "search": usar_busqueda
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_TOKEN}", "Content-Type": "application/json"}
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"DeepSeek falló: {e}")
        return None

def llamar_grok(mensajes: List[Dict]) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq falló: {e}")
        return None

def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"
    if categoria == "imagen":
        return "imagen"
    if categoria == "archivo":
        return "archivo"

    system_prompt = construir_prompt_system(categoria, consulta, contexto)
    mensajes = [{"role": "system", "content": system_prompt}, {"role": "user", "content": consulta}]
    usar_busqueda = categoria in ["pregunta_persona", "noticias", "compleja"]

    respuesta = llamar_deepseek(mensajes, usar_busqueda)
    if respuesta:
        return respuesta

    mensajes[0]["content"] += "\n\nUsa solo el conocimiento de referencia para responder."
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta

    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. 🙏"
