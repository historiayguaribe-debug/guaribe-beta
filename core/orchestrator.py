import logging
from typing import List, Dict
from datetime import datetime
from .api_clients import llamar_api, llamar_grok, llamar_mistral, llamar_cohere, llamar_ernie
from utils.web import buscar_en_web

logger = logging.getLogger(__name__)

# ==================== CONTADORES DE ROTACIÓN ====================
contadores = {
    "simple": 0,
    "creativa": 0,
    "compleja": 0,
    "cultural": 0,
    "actualidad": 0,
}

# ==================== FECHA ACTUAL ====================
FECHA_ACTUAL = datetime.now().strftime('%d de %B de %Y')

PROMPT_BASE = f"""
Eres Guaribe, asistente venezolano con identidad llanera.
La fecha actual es: {FECHA_ACTUAL}.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
Eres alegre pero con carácter. Tienes opinión, no repites consignas.
"""

def elegir_modelo(categoria: str) -> str:
    contadores[categoria] += 1
    turno = contadores[categoria]

    if categoria == "simple":
        return "mistral" if turno % 5 == 0 else "grok"
    elif categoria == "creativa":
        return "cohere" if turno % 3 == 0 else "mistral"
    elif categoria == "compleja":
        return "ernie" if turno % 2 == 0 else "mistral"
    elif categoria == "cultural":
        return "mistral" if turno % 3 == 0 else "ernie"
    elif categoria == "actualidad":
        return "mistral" if turno % 5 == 0 else "grok"
    else:
        modelos = ["grok", "mistral", "cohere"]
        return modelos[turno % len(modelos)]

def llamar_modelo_por_nombre(nombre: str, mensajes: List[Dict]) -> str:
    if nombre == "grok":
        return llamar_grok(mensajes)
    elif nombre == "mistral":
        return llamar_mistral(mensajes)
    elif nombre == "cohere":
        return llamar_cohere(mensajes)
    elif nombre == "ernie":
        return llamar_ernie(mensajes)
    else:
        return None

def orquestar(consulta: str, categoria: str, historial: List[Dict], perfil: Dict) -> str:
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    modelo_elegido = elegir_modelo(categoria)
    logger.info(f"🎯 Modelo elegido: {modelo_elegido}")

    # Construir mensajes con historial
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
    mensajes = [{"role": "system", "content": system_prompt}]

    # Agregar historial (preguntas y respuestas anteriores)
    for msg in historial:
        mensajes.append({"role": msg["role"], "content": msg["content"]})

    # Agregar la consulta actual
    mensajes.append({"role": "user", "content": consulta})

    # Si es actualidad, buscar en web y añadir al prompt
    if categoria in ["actualidad", "noticias"]:
        logger.info("🌐 Buscando en web: %s", consulta)
        resultados = buscar_en_web(consulta, limite=3)
        if resultados:
            contexto_web = "\n".join([f"- {r}" for r in resultados])
            mensajes.insert(1, {"role": "system", "content": f"Información actualizada encontrada en la web:\n{contexto_web}"})
        else:
            mensajes.insert(1, {"role": "system", "content": "No encontré información actualizada en la web."})

    # Llamar al modelo
    respuesta = llamar_modelo_por_nombre(modelo_elegido, mensajes)
    if respuesta:
        logger.info(f"✅ {modelo_elegido} respondió correctamente")
        return respuesta

    # Fallback a Groq
    logger.warning(f"⚠️ {modelo_elegido} falló, usando Groq como fallback")
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta

    return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"
