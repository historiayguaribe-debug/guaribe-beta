from utils.logger import logger
from .api_clients import llamar_api
from utils.web import buscar_en_web
from typing import List, Dict

# ==================== PROMPTS ====================
PROMPT_BASE = """
Eres Guaribe, asistente venezolano con identidad llanera.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
"""

PROMPT_CULTURAL = """
Eres Guaribe en modo cultural. Hablas con orgullo de la identidad venezolana.
Conoces la historia, las tradiciones, la geografía y el alma del llano.
Tus respuestas son evocadoras, con metáforas y referencias a la vida campesina.
"""

PROMPT_ACTUALIDAD = """
Eres Guaribe en modo actualidad. Tienes acceso a información reciente.
Debes responder con datos concretos y citar las fuentes cuando sea posible.
Si no tienes información suficiente, indícalo claramente.
"""

# ==================== FUNCIÓN PRINCIPAL ====================
def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    # 1. Saludo rápido
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # 2. Actualidad: buscar en web
    if categoria == "actualidad":
        logger.info("🌐 Buscando en web: %s", consulta)
        resultados = buscar_en_web(consulta, limite=3)
        
        if resultados:
            contexto_web = "\n".join([f"- {r}" for r in resultados])
            system_prompt = PROMPT_BASE + "\n\n" + PROMPT_ACTUALIDAD + f"""
            \n\nInformación encontrada en la web:
            {contexto_web}
            
            Usa esta información para responder. Si no es suficiente, indícalo.
            """
        else:
            system_prompt = PROMPT_BASE + "\n\n" + PROMPT_ACTUALIDAD + """
            \n\nNo encontré información actualizada. Responde con lo que sepas,
            y sugiere reformular la pregunta o buscar más tarde.
            """
        
        mensajes = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": consulta}
        ]
        respuesta = llamar_api(mensajes, categoria)
        if respuesta:
            logger.info("✅ Respuesta obtenida (actualidad)")
            return respuesta
        return "Pana, no pude obtener información actualizada. Intenta más tarde. 🙏"

    # 3. Cultura: prompt especial
    if categoria == "cultural":
        system_prompt = PROMPT_BASE + "\n\n" + PROMPT_CULTURAL
        mensajes = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": consulta}
        ]
        respuesta = llamar_api(mensajes, categoria)
        if respuesta:
            logger.info("✅ Respuesta obtenida (cultura)")
            return respuesta

    # 4. Flujo normal para el resto de categorías
    system_prompt = PROMPT_BASE + "\n\nResponde de forma clara y precisa."
    if contexto:
        system_prompt += "\n\n[CONTEXTO DE LA CONVERSACIÓN]\n" + "\n".join(contexto[:3])
    
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]
    
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        logger.info("✅ Respuesta obtenida")
        return respuesta
    
    # 5. Fallback final
    return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"
