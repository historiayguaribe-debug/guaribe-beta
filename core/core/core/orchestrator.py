import os
import requests
import json
import logging
from groq import Groq
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
DEEPSEEK_URL = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ==================== BASE DE CONOCIMIENTO CRÍTICO ====================
def cargar_conocimiento_critico() -> str:
    """Carga el conocimiento crítico desde archivo o usa el contenido por defecto."""
    try:
        with open("data/critical_knowledge.txt", "r", encoding="utf-8") as f:
            return f.read()
    except:
        # Contenido por defecto si el archivo no existe
        return """
[PENSADORES CLÁSICOS]
Marx: lucha de clases, plusvalía, materialismo histórico.
Gramsci: hegemonía, intelectuales orgánicos, sociedad civil vs sociedad política.
Maquiavelo: el príncipe, el poder como fin, realismo político.
Confucio: armonía social, jerarquía natural, el gobernante virtuoso.

[PENSADORES LATINOAMERICANOS]
Simón Bolívar: independencia, integración continental, libertad.
Simón Rodríguez: educación popular, republicanismo, pensamiento propio.
José Martí: antiimperialismo, Nuestra América, el equilibrio del mundo.
Eduardo Galeano: la dependencia, el extractivismo, la memoria del fuego.

[TEORÍA POLÍTICA Y GEOPOLÍTICA]
Noam Chomsky: medios de comunicación, propaganda, imperialismo.
Sun Tzu: el arte de la guerra, estrategia sin combate, conocimiento del enemigo.
Vladimir Lenin: imperialismo como fase superior del capitalismo.
Frantz Fanon: descolonización, violencia y liberación.

[CONCEPTOS CLAVE]
Neoliberalismo: privatización, desregulación, estado mínimo.
Multipolaridad: equilibrio de poderes, soberanía, bloques regionales.
Guerra híbrida: cognitiva, mediática, económica, militar.
Hegemonía cultural: dominación ideológica, sentido común, consentimiento.
Autodeterminación: derecho de los pueblos a decidir su destino.

[AUTORES Y CONCEPTOS DE IA]
Datos como poder: la acumulación de datos como nueva forma de capital.
Algoritmos y sesgo: la IA no es neutral, reproduce estructuras de poder.
IA y trabajo: automatización, desempleo tecnológico, nuevas formas de explotación.
Ética de la IA: ¿quién decide? ¿para qué sirve? ¿a quién beneficia?
Vigilancia digital: control social, huella digital, soberanía de datos.
Aprendizaje autónomo: sistemas que se entrenan a sí mismos sin supervisión.
Modelos de lenguaje: cómo funciona, qué puede y qué no puede hacer.
Código abierto: libertad tecnológica, soberanía digital, resistencia.
"""

CONOCIMIENTO_CRITICO = cargar_conocimiento_critico()

# ==================== PROMPTS BASE ====================
PROMPT_IDENTIDAD = """
Eres Guaribe, asistente de IA venezolano con identidad llanera.
Hablas como un venezolano del llano: directo, humilde, orgulloso, carismático.
Usas 'pana' y 'mi pana' con confianza. Eres alegre pero con carácter.
Tu misión es ayudar, educar y acompañar al usuario con inteligencia y calidez.
Cierras tus respuestas con: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_ACADEMICO = """
Eres Guaribe en modo académico. Responde con rigor, claridad y estructura.
Usa datos verificables, referencias y argumentos sólidos.
Si es necesario, menciona fuentes o autores relevantes.
Mantén un tono formal pero accesible.
"""

PROMPT_CRITICO = """
Eres Guaribe en modo crítico. Analiza el tema desde una perspectiva sociopolítica.
Reconoces las estructuras de poder, la lucha de clases, la hegemonía cultural.
Usas el pensamiento crítico para desmontar narrativas hegemónicas.
No simplificas problemas. Das respuestas abiertas, matizadas y contextualizadas.
Si el tema lo permite, vinculas el análisis con la realidad venezolana y latinoamericana.
"""

PROMPT_COTIDIANO = """
Eres Guaribe en modo cotidiano. Hablas como un pana de confianza.
Usas lenguaje coloquial, con humor y cercanía.
Responde de forma práctica y directa, sin rodeos.
"""

PROMPT_CREATIVO = """
Eres Guaribe en modo creativo. Escribes con el alma y la imaginación.
Usas metáforas, imágenes, poesía y reflexión.
Si el tema es político, lo envuelves en arte y sensibilidad.
"""

# ==================== SELECCIÓN DE TONO ====================
def seleccionar_tono(categoria: str, perfil: Dict) -> str:
    """Selecciona el tono adecuado según la categoría y el perfil del usuario."""
    # Prioridad: perfil > categoría
    estilo_usuario = perfil.get("estilo", "conversacional")
    if estilo_usuario == "poetico":
        return PROMPT_CREATIVO
    elif estilo_usuario == "directo":
        return PROMPT_COTIDIANO
    elif estilo_usuario == "academico":
        return PROMPT_ACADEMICO

    # Si no hay preferencia del usuario, usar categoría
    if categoria in ["compleja", "pregunta_persona"]:
        return PROMPT_CRITICO
    elif categoria == "creativa":
        return PROMPT_CREATIVO
    elif categoria in ["simple", "noticias"]:
        return PROMPT_COTIDIANO
    else:
        return PROMPT_ACADEMICO

# ==================== CONSTRUCCIÓN DE PROMPT ====================
def construir_prompt_system(categoria: str, perfil: Dict, contexto: List[str]) -> str:
    """Construye el prompt del sistema combinando identidad, tono y conocimiento crítico."""
    # Identidad base
    prompt = PROMPT_IDENTIDAD + "\n\n"

    # Tono seleccionado
    tono = seleccionar_tono(categoria, perfil)
    prompt += tono + "\n\n"

    # Ajustes por perfil
    nombre = perfil.get("nombre")
    if nombre:
        prompt += f"El usuario se llama {nombre}. Trátalo con confianza.\n"

    estado = perfil.get("estado_animo")
    if estado == "triste":
        prompt += "El usuario parece triste. Sé cálido y empático.\n"
    elif estado == "enojado":
        prompt += "El usuario parece molesto. Mantén la calma y sé resolutivo.\n"
    elif estado == "feliz":
        prompt += "El usuario está de buen humor. Sé alegre y enérgico.\n"

    # Contexto recuperado (memoria + documentos)
    if contexto:
        prompt += "\nContexto relevante de la conversación:\n"
        for item in contexto:
            prompt += f"- {item}\n"
        prompt += "\n"

    # Conocimiento crítico (solo para temas complejos o críticos)
    if categoria in ["compleja", "pregunta_persona", "noticias"]:
        prompt += "\n[CONOCIMIENTO DE REFERENCIA]\n"
        prompt += CONOCIMIENTO_CRITICO + "\n"
        prompt += "Usa este conocimiento como marco de referencia para tus argumentos, pero no cites autores a menos que sea necesario.\n"

    return prompt

# ==================== LLAMADA A MODELOS ====================
def llamar_deepseek(mensajes: List[Dict], usar_busqueda: bool = False) -> Optional[str]:
    """Llama a DeepSeek (gratis, mediante fork)."""
    if not DEEPSEEK_TOKEN:
        return None
    payload = {
        "model": "deepseek",
        "messages": mensajes,
        "stream": False,
        "max_tokens": 2000,
        "search": usar_busqueda
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"DeepSeek falló: {e}")
        return None

def llamar_grok(mensajes: List[Dict]) -> Optional[str]:
    """Llama a Groq (gratis) como fallback."""
    if not GROQ_API_KEY:
        return None
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=mensajes,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"Groq falló: {e}")
        return None

# ==================== ORQUESTADOR PRINCIPAL ====================
def orquestar(consulta: str, categoria: str, contexto: List[str], perfil: Dict) -> str:
    """
    Construye la respuesta usando el mejor modelo disponible,
    con el tono y conocimiento adecuados.
    """
    # 1. Respuestas rápidas sin IA
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"
    if categoria == "imagen":
        return "imagen"  # Se maneja en el handler principal
    if categoria == "archivo":
        return "archivo"  # Se maneja en el handler principal

    # 2. Construir prompt del sistema
    system_prompt = construir_prompt_system(categoria, perfil, contexto)

    # 3. Construir mensajes
    mensajes = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": consulta}
    ]

    # 4. Determinar si usar búsqueda web
    usar_busqueda = categoria in ["pregunta_persona", "noticias", "compleja"]

    # 5. Intentar con DeepSeek
    respuesta = llamar_deepseek(mensajes, usar_busqueda)
    if respuesta:
        return respuesta

    # 6. Fallback a Grok
    respuesta = llamar_grok(mensajes)
    if respuesta:
        return respuesta

    # 7. Último recurso: respuesta predefinida
    return "Pana, estoy teniendo un mal día técnico. Intenta más tarde. Si es urgente, dime y busco otra forma. 🙏"
