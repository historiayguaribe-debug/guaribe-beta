# core/orchestrator.py
from utils.logger import logger
from .api_clients import llamar_api

PROMPT_BASE = """
Eres Guaribe, asistente venezolano con identidad llanera.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
"""

def orquestar(consulta, categoria, contexto, perfil):
    logger.info("🔄 Orquestador llamado para: %s", consulta[:30])
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
    mensajes = [{"role": "system", "content": system_prompt}, {"role": "user", "content": consulta}]
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        logger.info("✅ Respuesta obtenida")
        return respuesta
    return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"
