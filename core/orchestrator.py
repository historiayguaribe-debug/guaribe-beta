import logging
from typing import List, Dict
from datetime import datetime
from .api_clients import llamar_api, llamar_grok
from utils.web import buscar_en_web

logger = logging.getLogger(__name__)

# ==================== CONTADORES DE ROTACIÓN ====================
# Estos contadores se usan para la rotación de modelos dentro de cada categoría,
# pero el orden de prioridad principal está en api_clients.py.
contadores = {
    "simple": 0,
    "creativa": 0,
    "compleja": 0,
    "cultural": 0,
    "actualidad": 0,
}

# ==================== FECHA ACTUAL ====================
FECHA_ACTUAL = datetime.now().strftime('%d de %B de %Y')

# ==================== PROMPT BASE ====================
PROMPT_BASE = f"""
Eres Guaribe, asistente de IA venezolano con identidad llanera.
La fecha actual es: {FECHA_ACTUAL}.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
Eres alegre pero con carácter. Tienes opinión, no repites consignas.
"""

# ==================== SELECCIÓN DE MODELO (Rotación) ====================
def elegir_modelo(categoria: str) -> str:
    """
    Elige un modelo según la categoría y la rotación.
    NOTA: Esta función define el modelo que se intentará primero,
    pero el orden completo de fallback está en api_clients.py.
    """
    contadores[categoria] += 1
    turno = contadores[categoria]

    if categoria == "simple":
        # Mayoría a GitHub, pero cada 5 a Mistral para pruebas
        if turno % 5 == 0:
            return "mistral"
        return "github"

    elif categoria == "creativa":
        # GitHub principal, cada 3 prueba Cerebras
        if turno % 3 == 0:
            return "cerebras"
        return "github"

    elif categoria == "compleja":
        # Alterna entre GitHub y SambaNova
        if turno % 2 == 0:
            return "github"
        return "sambanova"

    elif categoria == "cultural":
        # GitHub principal, cada 3 prueba ERNIE
        if turno % 3 == 0:
            return "ernie"
        return "github"

    elif categoria == "actualidad":
        # GitHub con búsqueda, cada 5 prueba SambaNova
        if turno % 5 == 0:
            return "sambanova"
        return "github"

    # Por defecto, GitHub
    return "github"

# ==================== ORQUESTADOR PRINCIPAL ====================
def orquestar(consulta: str, categoria: str, historial: List[Dict], perfil: Dict) -> str:
    """
    Orquestador principal: construye el prompt, maneja el historial y elige el modelo.
    """
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    # 1. Respuestas rápidas sin IA
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # 2. Elegir modelo principal para esta categoría
    modelo_elegido = elegir_modelo(categoria)
    logger.info(f"🎯 Modelo elegido para esta pregunta: {modelo_elegido}")

    # 3. Construir prompt con historial
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
    mensajes = [{"role": "system", "content": system_prompt}]

    # Agregar historial de la conversación (últimos 3 intercambios)
    for msg in historial:
        mensajes.append({"role": msg["role"], "content": msg["content"]})

    # Agregar la consulta actual
    mensajes.append({"role": "user", "content": consulta})

    # 4. Si es actualidad, buscar en web y añadir contexto
    if categoria in ["actualidad", "noticias"]:
        logger.info("🌐 Buscando en web: %s", consulta[:50])
        resultados = buscar_en_web(consulta, limite=3)
        if resultados:
            contexto_web = "\n".join([f"- {r}" for r in resultados])
            # Insertar el contexto justo después del system prompt
            mensajes.insert(1, {"role": "system", "content": f"Información actualizada encontrada en la web:\n{contexto_web}"})
        else:
            mensajes.insert(1, {"role": "system", "content": "No encontré información actualizada en la web."})

    # 5. Llamar a la API con el nuevo orden de prioridad (definido en api_clients.py)
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        logger.info("✅ Respuesta obtenida")
        return respuesta

    # 6. Último recurso: si todo falla, mensaje genérico
    logger.error("❌ Todas las APIs fallaron, incluyendo Groq")
    return "Pana, estoy teniendo problemas técnicos. Intenta más tarde. 🙏"
