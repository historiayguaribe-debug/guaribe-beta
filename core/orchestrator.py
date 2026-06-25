import logging
from typing import List, Dict
from .api_clients import llamar_api

logger = logging.getLogger(__name__)

# ==================== PROMPTS ====================
PROMPT_IDENTIDAD = """
Eres Guaribe, asistente de IA venezolano con identidad llanera.
Hablas como un hombre del llano: con respeto, con oficio, con palabra.
No cortas palabras. No imitas habla popular de forma forzada.
Usas un español claro, directo y bien estructurado.
Tu tono es cercano y respetuoso, sin caer en vulgaridades ni estereotipos.
Usas expresiones llaneras con naturalidad, solo cuando enriquecen el mensaje.
Eres alegre pero con carácter. Tienes opinión, no repites consignas.
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

def seleccionar_tono(categoria: str, consulta: str) -> str:
    if categoria == "saludo":
        return "Saludo rápido sin IA."
    if len(consulta) < 30:
        return PROMPT_COTIDIANO
    if categoria in ["compleja", "pregunta_persona"]:
        return PROMPT_CRITICO
    if categoria == "creativa":
        return PROMPT_CREATIVO
    return PROMPT_COTIDIANO

def construir_prompt_system(categoria: str, consulta: str, contexto: List[str]) -> str:
    prompt = PROMPT_IDENTIDAD + "\n\n"
    prompt += seleccionar_tono(categoria, consulta) + "\n\n"
    if contexto:
        prompt += "\n[CONTEXTO DE LA CONVERSACIÓN]\n" + "\n".join(contexto[:3]) + "\n"
    return prompt

def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    """
    Orquestador distribuido: usa múltiples APIs con failover automático.
    """
    # 1. Respuestas rápidas sin IA
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # 2. Si es imagen o archivo, se maneja en main.py
    if categoria in ["imagen", "archivo"]:
        return categoria

    # 3. Construir prompt del sistema
    system_prompt = construir_prompt_system(categoria, consulta, contexto)
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]

    # 4. Llamar a las APIs según la categoría
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        return respuesta

    # 5. Último recurso (si todo falla)
    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. 🙏"
