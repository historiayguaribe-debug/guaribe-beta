import os
import logging
from typing import List, Dict
from .api_clients import llamar_api

logger = logging.getLogger(__name__)

# ... (mantén los prompts y funciones auxiliares iguales) ...

def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    """Versión con orquestador distribuido."""
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"
    
    # Construir prompt del sistema
    system_prompt = construir_prompt_system(categoria, perfil, consulta, contexto)
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]
    
    # Llamar a las APIs según la categoría
    respuesta = llamar_api(mensajes, categoria)
    if respuesta:
        return respuesta
    
    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. 🙏"
