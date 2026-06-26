import logging
from typing import List, Dict
from .api_clients import llamar_api
from utils.web import buscar_en_web

logger = logging.getLogger(__name__)

PROMPT_BASE = """
Eres Guaribe, asistente venezolano con identidad llanera.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
Eres alegre pero con carácter. Tienes opinión, no repites consignas.
"""

def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # Búsqueda web para actualidad
    if categoria in ["actualidad", "noticias"]:
        logger.info("🌐 Buscando en web: %s", consulta)
        resultados = buscar_en_web(consulta, limite=3)

        if resultados:
            contexto_web = "\n".join([f"- {r}" for r in resultados])
            system_prompt = PROMPT_BASE + f"""
            \n\nInformación actualizada encontrada en la web:
            {contexto_web}

            Usa esta información para responder al usuario. Si la información no es suficiente, indica que no encontraste datos actualizados.
            """
        else:
            system_prompt = PROMPT_BASE + "\n\nNo encontré información actualizada sobre tu pregunta en la web. Responde con lo que sepas, y sugiere al usuario que intente reformular la pregunta."

        mensajes = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": consulta}
        ]
        respuesta = llamar_api(mensajes, categoria)
        if respuesta:
            logger.info("✅ Respuesta obtenida con búsqueda web")
            return respuesta
        return "Pana, no pude obtener información actualizada. Intenta más tarde. 🙏"

    # Flujo normal
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        logger.info("✅ Respuesta obtenida")
        return respuesta
    return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"
