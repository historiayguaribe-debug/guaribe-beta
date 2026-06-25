import logging
from typing import List, Dict
import os

# Importar memoria si está disponible
try:
    from core.memory import buscar_contexto
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False

from .api_clients import llamar_api, llamar_ernie, llamar_mistral

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

PROMPT_CULTURAL = """
Eres Guaribe en modo cultural. Hablas con orgullo de la identidad venezolana.
Conoces la historia, las tradiciones, la geografía y el alma del llano.
Tus respuestas son evocadoras, con metáforas y referencias a la vida campesina.
Reconoces la resistencia cultural y la riqueza del pueblo venezolano.
"""

# ==================== DETECCIÓN DE PALABRAS CLAVE ====================
PALABRAS_CULTURALES = [
    "llano", "llanero", "cultura", "historia", "tradición", "folklore",
    "venezolano", "venezuela", "costumbre", "campesino", "criollo",
    "arepa", "joropo", "sabana", "arpa", "copla"
]

def es_pregunta_cultural(consulta: str) -> bool:
    """Detecta si la pregunta es sobre cultura, historia o identidad venezolana."""
    consulta_lower = consulta.lower()
    for palabra in PALABRAS_CULTURALES:
        if palabra in consulta_lower:
            return True
    return False

# ==================== CONSTRUCCIÓN DE PROMPT ====================
def seleccionar_tono(categoria: str, consulta: str) -> str:
    if categoria == "saludo":
        return "Saludo rápido sin IA."
    if categoria == "cultural":
        return PROMPT_CULTURAL
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

# ==================== ORQUESTADOR PRINCIPAL ====================
def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    """
    Orquestador distribuido con fallback inteligente, detección cultural y memoria.
    """
    logger.info("🔄 Entrando al orquestador con categoría: %s", categoria)

    # 1. Respuestas rápidas sin IA
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # 2. Si es imagen o archivo, se maneja en main.py
    if categoria in ["imagen", "archivo"]:
        return categoria

    # 3. DETECCIÓN CULTURAL POR PALABRAS CLAVE
    if es_pregunta_cultural(consulta) or categoria == "cultural":
        logger.info("🔄 Pregunta cultural detectada. Usando ERNIE/Mistral con prompt crítico.")
        # Consultar memoria para contexto adicional
        contexto_extra = []
        if MEMORY_AVAILABLE:
            try:
                # Buscar contexto en memoria si existe
                from core.memory import get_connection
                conn = get_connection()
                contexto_extra = buscar_contexto(perfil.get('chat_id'), consulta, conn)
                conn.close()
                if contexto_extra:
                    logger.info(f"🧠 Inyectando {len(contexto_extra)} fragmentos de memoria")
            except Exception as e:
                logger.warning(f"Error consultando memoria: {e}")
        
        # Construir prompt con tono cultural
        system_prompt = PROMPT_IDENTIDAD + "\n\n" + PROMPT_CULTURAL + "\n\n"
        if contexto_extra:
            system_prompt += "[CONTEXTO PREVIO]\n" + "\n".join(contexto_extra[:2]) + "\n"
        mensajes = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": consulta}
        ]
        
        # Intentar con ERNIE primero (mejor para cultura)
        respuesta = llamar_ernie(mensajes, timeout=20)
        if respuesta:
            logger.info("✅ ERNIE respondió a pregunta cultural")
            return respuesta
        
        # Fallback a Mistral
        respuesta = llamar_mistral(mensajes, timeout=15)
        if respuesta:
            logger.info("✅ Mistral respondió a pregunta cultural")
            return respuesta
        
        # Si fallan, seguir al flujo normal
        logger.warning("⚠️ ERNIE y Mistral fallaron para pregunta cultural, pasando a flujo general")

    # 4. FLUJO NORMAL (según categoría)
    # Construir prompt del sistema
    system_prompt = construir_prompt_system(categoria, consulta, contexto)
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]

    # 5. Llamar a las APIs según la categoría
    logger.info("🔄 Llamando a las APIs para categoría: %s", categoria)
    respuesta = llamar_api(mensajes, categoria)
    
    if respuesta:
        logger.info("✅ Orquestador obtuvo respuesta de una API")
        return respuesta

    # 6. FALLBACK INTELIGENTE (ya no repite la última respuesta)
    logger.error("❌ Orquestador: todas las APIs fallaron")
    
    # Intentar buscar en memoria como último recurso
    if MEMORY_AVAILABLE:
        try:
            from core.memory import get_connection
            conn = get_connection()
            contexto_extra = buscar_contexto(perfil.get('chat_id'), consulta, conn)
            conn.close()
            if contexto_extra:
                # Responder con el fragmento de memoria más relevante
                respuesta = "Pana, no pude generar una respuesta nueva, pero recuerdo esto de nuestra conversación anterior:\n\n" + contexto_extra[0]
                logger.info("✅ Fallback usó memoria para responder")
                return respuesta
        except Exception as e:
            logger.warning(f"Error en fallback de memoria: {e}")
    
    # Si no hay memoria, devolver mensaje claro
    return "Pana, no tengo una respuesta para eso ahora mismo. Si me das más contexto o reformulas la pregunta, puedo intentarlo de nuevo. 🙏"
