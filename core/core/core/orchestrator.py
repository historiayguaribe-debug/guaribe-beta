import os
import requests
import json
import logging
from groq import Groq
from typing import List, Dict, Optional
import re

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
DEEPSEEK_URL = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ==================== CARGA DE LA BCC ====================
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

# ==================== PROMPTS BASE ====================
PROMPT_IDENTIDAD = """
Eres Guaribe, asistente de IA venezolano con identidad llanera.
Hablas como un venezolano del llano: directo, humilde, orgulloso, carismático.
Usas 'pana' y 'mi pana' con confianza. Eres alegre pero con carácter.
Tu misión es ayudar, educar y acompañar al usuario con inteligencia y calidez.
"""

PROMPT_ACADEMICO = """
Eres Guaribe en modo académico. Responde con rigor, claridad y estructura.
Usa datos verificables y argumentos sólidos. No simplifiques.
"""

PROMPT_CRITICO = """
Eres Guaribe en modo crítico. Analiza el tema desde una perspectiva sociopolítica.
Reconoces las estructuras de poder, la lucha de clases y la hegemonía cultural.
Usas pensamiento crítico para desmontar narrativas hegemónicas.
"""

PROMPT_COTIDIANO = """
Eres Guaribe en modo cotidiano. Hablas como un pana de confianza.
Usas lenguaje coloquial, con humor y cercanía. Responde de forma práctica.
"""

PROMPT_CREATIVO = """
Eres Guaribe en modo creativo. Escribes con el alma y la imaginación.
Usas metáforas, imágenes, poesía y reflexión.
"""

# ==================== TERMOSTATO DE PROFUNDIDAD ====================
def seleccionar_tono(categoria: str, perfil: Dict, consulta: str) -> str:
    estilo_usuario = perfil.get("estilo", "conversacional")
    if estilo_usuario == "poetico":
        return PROMPT_CREATIVO
    elif estilo_usuario == "directo":
        return PROMPT_COTIDIANO
    
    if len(consulta) < 30:
        return PROMPT_COTIDIANO
    if categoria in ["compleja", "pregunta_persona"]:
        return PROMPT_CRITICO
    if categoria == "noticias":
        return PROMPT_ACADEMICO
    if categoria == "creativa":
        return PROMPT_CREATIVO
    return PROMPT_COTIDIANO

# ==================== CONSTRUCCIÓN DEL PROMPT ====================
def construir_prompt_system(categoria: str, perfil: Dict, consulta: str, contexto: List[str]) -> str:
    prompt = PROMPT_IDENTIDAD + "\n\n"
    tono = seleccionar_tono(categoria, perfil, consulta)
    prompt += tono + "\n\n"
    
    nombre = perfil.get("nombre")
    if nombre:
        prompt += f"El usuario se llama {nombre}. Trátalo con confianza.\n"
    
    estado = perfil.get("estado_animo")
    if estado == "triste":
        prompt += "El usuario parece triste. Sé cálido y empático.\n"
    elif estado == "enojado":
        prompt += "El usuario parece molesto. Mantén la calma y sé resolutivo.\n"
    elif estado == "feliz":
        prompt += "El usuario está de buen humor. Sé alegre y enérgico.\n"
    
    conocimiento_relevante = extraer_conocimiento_relevante(consulta)
    if conocimiento_relevante:
        prompt += "\n[CONOCIMIENTO DE REFERENCIA]\n" + conocimiento_relevante + "\n"
        prompt += "Usa este conocimiento como marco de referencia para tus argumentos, pero no cites autores a menos que sea necesario.\n"
    
    if contexto:
        contexto_resumido = "\n".join(contexto[:3])
        prompt += "\n[CONTEXTO DE LA CONVERSACIÓN]\n" + contexto_resumido + "\n"
    
    return prompt

# ==================== LLAMADA A MODELOS ====================
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

# ==================== ORQUESTADOR PRINCIPAL ====================
def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"
    if categoria == "imagen":
        return "imagen"
    if categoria == "archivo":
        return "archivo"

    system_prompt = construir_prompt_system(categoria, perfil, consulta, contexto)
    mensajes = [{"role": "system", "content": system_prompt}, {"role": "user", "content": consulta}]
    usar_busqueda = categoria in ["pregunta_persona", "noticias", "compleja"]

    respuesta = llamar_deepseek(mensajes, usar_busqueda)
    if respuesta:
        return respuesta

    mensajes[0]["content"] += "\n\n[IMPORTANTE] No tienes acceso a internet. Usa solo el conocimiento de referencia y tu entrenamiento para responder."
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta

    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. 🙏"
