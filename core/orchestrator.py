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

# ==================== PESOS DE MODELOS (se actualizan con feedback) ====================
pesos_modelos = {
    "grok": 1.0,
    "mistral": 1.0,
    "cohere": 0.5,
    "ernie": 0.8,
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
    """
    Elige un modelo según la categoría y la rotación.
    """
    contadores[categoria] += 1
    turno = contadores[categoria]

    if categoria == "simple":
        # Groq siempre, pero cada 5 usa Mistral
        if turno % 5 == 0:
            return "mistral"
        return "grok"

    elif categoria == "creativa":
        # Mistral principal, cada 3 prueba Cohere
        if turno % 3 == 0:
            return "cohere"
        return "mistral"

    elif categoria == "compleja":
        # Alterna entre ERNIE y Mistral
        if turno % 2 == 0:
            return "ernie"
        return "mistral"

    elif categoria == "cultural":
        # ERNIE principal, cada 3 prueba Mistral
        if turno % 3 == 0:
            return "mistral"
        return "ernie"

    elif categoria == "actualidad":
        # Groq con búsqueda, cada 5 prueba Mistral
        if turno % 5 == 0:
            return "mistral"
        return "grok"

    # Por defecto, round-robin entre grok, mistral, cohere
    modelos = ["grok", "mistral", "cohere"]
    return modelos[turno % len(modelos)]

def llamar_modelo_por_nombre(nombre: str, mensajes: List[Dict]) -> str:
    """Llama al modelo correspondiente por nombre."""
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

def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # Elegir modelo según rotación
    modelo_elegido = elegir_modelo(categoria)
    logger.info(f"🎯 Modelo elegido para {categoria}: {modelo_elegido}")

    # Si es actualidad, buscar en web primero
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
        respuesta = llamar_modelo_por_nombre(modelo_elegido, mensajes)
        if respuesta:
            logger.info(f"✅ {modelo_elegido} respondió (actualidad)")
            return respuesta
        # Fallback a Groq si el modelo elegido falla
        logger.warning(f"⚠️ {modelo_elegido} falló, usando Groq como fallback")
        respuesta = llamar_grok(mensajes)
        if respuesta:
            return respuesta
        return "Pana, no pude obtener información actualizada. Intenta más tarde. 🙏"

    # Flujo normal
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]
    respuesta = llamar_modelo_por_nombre(modelo_elegido, mensajes)
    if respuesta:
        logger.info(f"✅ {modelo_elegido} respondió correctamente")
        return respuesta

    # Fallback: intentar con Groq
    logger.warning(f"⚠️ {modelo_elegido} falló, usando Groq como fallback")
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta

    return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"
