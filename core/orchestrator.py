import logging
from typing import List, Dict
from datetime import datetime
from .api_clients import llamar_api, llamar_mistral, llamar_grok
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

FECHA_ACTUAL = datetime.now().strftime('%d de %B de %Y')

PROMPT_BASE = f"""
Eres Guaribe, asistente de IA venezolano con identidad llanera.
La fecha actual es: {FECHA_ACTUAL}.
Hablas claro, directo y con respeto. Respondes con precisión y sin rodeos.
Eres alegre pero con carácter. Tienes opinión, no repites consignas.
"""

def elegir_modelo(categoria: str) -> str:
    contadores[categoria] += 1
    turno = contadores[categoria]

    if categoria == "simple":
        return "mistral" if turno % 5 == 0 else "mistral"
    elif categoria == "creativa":
        return "mistral"
    elif categoria == "compleja":
        return "mistral" if turno % 2 == 0 else "ernie"
    elif categoria == "cultural":
        return "ernie" if turno % 3 == 0 else "mistral"
    elif categoria == "actualidad":
        return "mistral" if turno % 5 == 0 else "mistral"
    else:
        return "mistral"

def orquestar(consulta: str, categoria: str, historial: List[Dict], perfil: Dict) -> str:
    logger.info("🔄 Orquestador llamado con categoría: %s", categoria)

    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"

    # Para preguntas simples, ignorar historial y usar ruta directa
    if categoria in ["simple", "saludo"]:
        logger.info("⚡ Pregunta simple: ignorando historial y usando ruta directa")
        system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."
        mensajes = [{"role": "system", "content": system_prompt}]
        mensajes.append({"role": "user", "content": consulta})
        
        # Intentar con Mistral primero
        respuesta = llamar_mistral(mensajes)
        if respuesta:
            return respuesta
        # Si Mistral falla, intentar con Grok
        respuesta = llamar_grok(mensajes)
        if respuesta:
            return respuesta
        return "Pana, no pude procesar tu pregunta. Intenta de nuevo. 🙏"

    # Para el resto de categorías, usar historial como contexto (no como mensajes)
    modelo_elegido = elegir_modelo(categoria)
    logger.info(f"🎯 Modelo elegido para esta pregunta: {modelo_elegido}")

    # Construir prompt del sistema con historial como contexto
    system_prompt = PROMPT_BASE + "\n\nResponde de forma breve y precisa."

    # Agregar historial como contexto (solo los 2 mensajes más recientes)
    if historial and len(historial) > 0:
        # Limitar a los 2 mensajes más relevantes (los últimos)
        historial_relevante = historial[-2:] if len(historial) > 2 else historial
        contexto_texto = "\n".join([f"- {msg['content']}" for msg in historial_relevante if msg['role'] == 'user'])
        if contexto_texto:
            system_prompt += f"\n\nContexto de la conversación:\n{contexto_texto}"

    mensajes = [{"role": "system", "content": system_prompt}]
    mensajes.append({"role": "user", "content": consulta})

    # Si es actualidad, buscar en web
    if categoria in ["actualidad", "noticias"]:
        logger.info("🌐 Buscando en web: %s", consulta[:50])
        resultados = buscar_en_web(consulta, limite=3)
        if resultados:
            contexto_web = "\n".join([f"- {r}" for r in resultados])
            mensajes.insert(1, {"role": "system", "content": f"Información actualizada encontrada en la web:\n{contexto_web}"})
        else:
            mensajes.insert(1, {"role": "system", "content": "No encontré información actualizada en la web."})

    # Llamar a la API con el orden de prioridad definido
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        logger.info("✅ Respuesta obtenida")
        return respuesta

    logger.error("❌ Todas las APIs fallaron")
    return "Pana, estoy teniendo problemas técnicos. Intenta más tarde. 🙏"
