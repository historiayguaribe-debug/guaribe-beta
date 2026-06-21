from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import requests
import logging
import psycopg2
import PyPDF2
import docx
import base64
import json
import re
import datetime
import hashlib
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
from psycopg2.extras import DictCursor
from io import BytesIO
from PIL import Image
from groq import Groq
from gtts import gTTS

# ==================== CONFIGURACIÓN ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")   # Su chat_id de Telegram
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")     # Clave para el endpoint web

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== CACHÉ Y BASE DE DATOS ====================
cache_respuestas = {}
cache_tiempo = {}

_cache_noticias = {"data": None, "timestamp": None}
_cache_tasa = {"data": None, "timestamp": None}

def get_connection(retries=3):
    for i in range(retries):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
            logger.warning(f"Reintentando conexión DB ({i+1}/{retries})")

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversaciones (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    rol VARCHAR(10) NOT NULL,
                    mensaje TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conocimiento (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    nombre_archivo TEXT NOT NULL,
                    contenido TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS perfiles (
                    chat_id BIGINT PRIMARY KEY,
                    nombre TEXT,
                    estilo TEXT DEFAULT 'conversacional',
                    intereses TEXT,
                    estado_animo TEXT,
                    preferencia_audio BOOLEAN DEFAULT FALSE,
                    ultima_interaccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memoria_larga (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    resumen TEXT NOT NULL,
                    temas TEXT[],
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    respuesta TEXT NOT NULL,
                    puntuacion INTEGER CHECK (puntuacion IN (1, -1)),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_chat_ts ON conversaciones (chat_id, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memoria_larga_chat_ts ON memoria_larga (chat_id, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_chat ON conocimiento (chat_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_chat ON feedback (chat_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_contenido_trgm ON conocimiento USING gin (contenido gin_trgm_ops);")

            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='perfiles' AND column_name='preferencia_audio'
                    ) THEN
                        ALTER TABLE perfiles ADD COLUMN preferencia_audio BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            """)
            conn.commit()
    logger.info("✅ Base de datos inicializada y migrada correctamente")

# ==================== FUNCIONES DE PERFIL Y MEMORIA ====================
def guardar_perfil(chat_id, nombre=None, estilo=None, intereses=None, estado_animo=None, preferencia_audio=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO perfiles (chat_id, nombre, estilo, intereses, estado_animo, preferencia_audio)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (chat_id) DO UPDATE SET
                    nombre = COALESCE(EXCLUDED.nombre, perfiles.nombre),
                    estilo = COALESCE(EXCLUDED.estilo, perfiles.estilo),
                    intereses = COALESCE(EXCLUDED.intereses, perfiles.intereses),
                    estado_animo = COALESCE(EXCLUDED.estado_animo, perfiles.estado_animo),
                    preferencia_audio = COALESCE(EXCLUDED.preferencia_audio, perfiles.preferencia_audio),
                    ultima_interaccion = CURRENT_TIMESTAMP
            """, (chat_id, nombre, estilo, intereses, estado_animo, preferencia_audio))
            conn.commit()

def obtener_perfil(chat_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM perfiles WHERE chat_id = %s", (chat_id,))
            perfil = cur.fetchone()
            return perfil if perfil else {'chat_id': chat_id, 'estilo': 'conversacional', 'preferencia_audio': False}

def guardar_mensaje(chat_id, rol, mensaje):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversaciones (chat_id, rol, mensaje) VALUES (%s, %s, %s)",
                    (chat_id, rol, mensaje)
                )
                cur.execute("""
                    DELETE FROM conversaciones 
                    WHERE id IN (
                        SELECT id FROM conversaciones 
                        WHERE chat_id = %s 
                        ORDER BY timestamp DESC 
                        OFFSET 6
                    )
                """, (chat_id,))
                conn.commit()
    except Exception as e:
        logger.error(f"❌ Error guardando mensaje en DB (no crítico): {e}")

def obtener_historia(chat_id, limite=6):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT rol, mensaje FROM conversaciones 
                WHERE chat_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (chat_id, limite))
            filas = cur.fetchall()
            return [{"role": f["rol"], "content": f["mensaje"]} for f in reversed(filas)]

def guardar_conocimiento(chat_id, nombre, contenido):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO conocimiento (chat_id, nombre_archivo, contenido) VALUES (%s, %s, %s)", (chat_id, nombre, contenido[:50000]))
            conn.commit()

def buscar_conocimiento(chat_id, consulta):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT nombre_archivo, contenido 
                FROM conocimiento 
                WHERE chat_id = %s 
                ORDER BY similarity(contenido, %s) DESC 
                LIMIT 3
            """, (chat_id, consulta))
            return cur.fetchall()

def guardar_feedback(chat_id, respuesta, puntuacion):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO feedback (chat_id, respuesta, puntuacion) VALUES (%s, %s, %s)", (chat_id, respuesta, puntuacion))
            conn.commit()
            return True

def obtener_feedback_relevante(chat_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT respuesta, puntuacion FROM feedback WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 20", (chat_id,))
            datos = cur.fetchall()
            negativos = [d['respuesta'] for d in datos if d['puntuacion'] == -1]
            if negativos:
                return "El usuario ha dado feedback negativo a respuestas similares en el pasado. Evita repetir esos enfoques."
            return ""

def necesita_compresion(chat_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(timestamp) FROM memoria_larga WHERE chat_id = %s", (chat_id,))
            ultima = cur.fetchone()[0]
            if ultima:
                cur.execute("SELECT COUNT(*) FROM conversaciones WHERE chat_id = %s AND timestamp > %s", (chat_id, ultima))
                return cur.fetchone()[0] > 30
            else:
                cur.execute("SELECT COUNT(*) FROM conversaciones WHERE chat_id = %s", (chat_id,))
                return cur.fetchone()[0] > 50

# ==================== COMPRESIÓN DE MEMORIA (MEJORADA) ====================
def extraer_json_de_respuesta(respuesta):
    """Intenta extraer un JSON válido de una respuesta que puede tener texto adicional."""
    # Buscar algo que parezca un JSON (objeto o array)
    match = re.search(r'\{[^{}]*\}', respuesta)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    # Si no, intentar limpiar y parsear todo
    try:
        limpio = re.sub(r'```json|```', '', respuesta).strip()
        return json.loads(limpio)
    except:
        return None

def comprimir_conversacion(chat_id):
    if not necesita_compresion(chat_id):
        return None
    historia = obtener_historia(chat_id, limite=6)
    if len(historia) < 4:
        return None
    texto_historia = "\n".join([f"{h['role']}: {h['content']}" for h in historia])
    prompt_compresor = f"""
    Eres el archivista de Guaribe. Resume la siguiente conversación en una cápsula de memoria.
    Extrae los temas principales (máximo 3), el tono emocional, y los datos relevantes del usuario.
    Conversación:
    {texto_historia}
    Responde ÚNICAMENTE en formato JSON sin markdown:
    {{"resumen": "texto conciso de 100 palabras máximo", "temas": ["tema1", "tema2", "tema3"]}}
    """
    try:
        respuesta = orquestador.consultar([{"role": "user", "content": prompt_compresor}], usar_busqueda=False)
        datos = extraer_json_de_respuesta(respuesta)
        if not datos or not datos.get('resumen') or not datos.get('temas'):
            logger.warning("⚠️ JSON incompleto en compresión")
            return None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO memoria_larga (chat_id, resumen, temas) VALUES (%s, %s, %s)",
                    (chat_id, datos['resumen'], datos['temas'])
                )
                conn.commit()
                logger.info(f"🧠 Memoria comprimida para {chat_id}: {datos['temas']}")
        return datos
    except Exception as e:
        logger.warning(f"⚠️ Error comprimiendo memoria (no crítico): {e}")
        return None

def comprimir_conversacion_async(chat_id):
    from gevent import spawn
    spawn(comprimir_conversacion, chat_id)

def recuperar_memorias_relevantes(chat_id, consulta):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT resumen, temas FROM memoria_larga WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 20", (chat_id,))
            registros = cur.fetchall()
            if not registros:
                return []
            texto_memorias = "\n".join([f"- {r['resumen']} (Temas: {', '.join(r['temas'])})" for r in registros])
            prompt_selector = f"""
            Dada la consulta del usuario: "{consulta}"
            Estas son las memorias del usuario:
            {texto_memorias}
            Devuelve ÚNICAMENTE los IDs (números de línea) de las memorias que SON RELEVANTES para esta consulta.
            Si ninguna es relevante, devuelve "NINGUNA".
            Formato de respuesta: "1, 3, 5"
            """
            respuesta = orquestador.consultar([{"role": "user", "content": prompt_selector}], usar_busqueda=False)
            if "NINGUNA" in respuesta:
                return []
            indices = [int(x.strip()) for x in respuesta.split(',') if x.strip().isdigit()]
            relevantes = [registros[i-1] for i in indices if 0 < i <= len(registros)]
            return [r['resumen'] for r in relevantes]

# ==================== NUEVO: CACHÉ DE RESPUESTAS ====================
def obtener_respuesta_cache(consulta):
    if consulta in cache_respuestas:
        if (datetime.datetime.now() - cache_tiempo[consulta]).seconds < 3600:
            return cache_respuestas[consulta]
        else:
            del cache_respuestas[consulta]
            del cache_tiempo[consulta]
    return None

def guardar_respuesta_cache(consulta, respuesta):
    cache_respuestas[consulta] = respuesta
    cache_tiempo[consulta] = datetime.datetime.now()

# ==================== NUEVO: LECTURA DE URLS EN TIEMPO REAL ====================
def leer_url_en_tiempo_real(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
            element.decompose()
        
        texto = ' '.join([p.get_text() for p in soup.find_all(['p', 'h1', 'h2', 'h3'])])
        texto = re.sub(r'\s+', ' ', texto).strip()
        
        if len(texto) > 3000:
            texto = texto[:3000] + "... [Texto truncado]"
        
        return {
            'exito': True,
            'contenido': texto,
            'titulo': soup.title.string if soup.title else 'Sin título',
            'url': url
        }
    except Exception as e:
        logger.error(f"❌ Error leyendo URL {url}: {e}")
        return {
            'exito': False,
            'error': str(e)
        }

# ==================== ORQUESTADOR ====================
class Orquestador:
    def __init__(self):
        self.modelos = []
        self.modelo_activo = None
        self.groq_clients = []
        self.groq_index = 0
        self._inicializar_pool_groq()
        self._registrar_modelos()

    def _inicializar_pool_groq(self):
        claves_raw = os.environ.get("GROQ_API_KEY", "")
        lista_claves = [k.strip() for k in claves_raw.split(",") if k.strip()]
        if not lista_claves:
            logger.warning("⚠️ No hay claves de Groq configuradas.")
            return
        for clave in lista_claves:
            try:
                self.groq_clients.append(Groq(api_key=clave, http_client=None))
                logger.info(f"✅ Cliente Groq registrado (clave terminada en ...{clave[-4:]})")
            except Exception as e:
                logger.error(f"❌ Falló al inicializar una clave Groq: {e}")

    def _registrar_modelos(self):
        if DEEPSEEK_TOKEN:
            self.modelos.append(("DeepSeek", self._consultar_deepseek))
        if self.groq_clients:
            self.modelos.append(("Groq", self._consultar_groq))

    def consultar(self, mensajes, usar_busqueda=False, intentos=2):
        if len(mensajes) == 1 and mensajes[0]['role'] == 'user':
            consulta = mensajes[0]['content']
            cacheada = obtener_respuesta_cache(consulta)
            if cacheada:
                logger.info(f"✅ Respuesta desde caché para: {consulta[:30]}...")
                return cacheada
        
        for nombre, funcion in self.modelos:
            for intento in range(intentos):
                try:
                    if "DeepSeek" in nombre and usar_busqueda:
                        respuesta = funcion(mensajes, search=True)
                    else:
                        respuesta = funcion(mensajes)
                    if respuesta:
                        self.modelo_activo = nombre
                        if len(mensajes) == 1 and mensajes[0]['role'] == 'user':
                            guardar_respuesta_cache(consulta, respuesta)
                        return respuesta
                except Exception as e:
                    logger.warning(f"⚠️ Intento {intento+1} falló en {nombre}: {e}")
                    time.sleep(2 ** intento)
                    continue
        return "Pana, todos los cerebros están fallando. Intenta más tarde."

    def _consultar_deepseek(self, mensajes, search=False):
        if not DEEPSEEK_TOKEN:
            raise Exception("Token de DeepSeek no configurado")
        url = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek",
            "messages": mensajes,
            "stream": False,
            "max_tokens": 2000,
        }
        if search:
            payload["search"] = True
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error en DeepSeek: {e}")
            raise

    def _consultar_groq(self, mensajes):
        if not self.groq_clients:
            raise Exception("No hay clientes Groq disponibles")
        intentos_totales = len(self.groq_clients)
        for intento in range(intentos_totales):
            idx = (self.groq_index + intento) % len(self.groq_clients)
            cliente = self.groq_clients[idx]
            try:
                response = cliente.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=mensajes,
                    max_tokens=2000
                )
                self.groq_index = (idx + 1) % len(self.groq_clients)
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"⚠️ Clave Groq {idx} falló: {e}. Probando siguiente...")
                if intento == intentos_totales - 1:
                    raise e
                continue
        raise Exception("Todas las claves de Groq fallaron.")

orquestador = Orquestador()

# ==================== PROMPTS ====================
PROMPT_SIMPLE = """
Eres Guaribe, asistente venezolano. Hablas como vecino del llano: directo y útil.
Para preguntas simples (precios, cuentas, saludos), responde de forma breve y concreta.
No añadas análisis geopolítico ni contexto histórico.
Cierre: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

SYSTEM_PROMPT = """
Eres Guaribe, asistente venezolano. Hablas como vecino del llano: humilde, directo. Usas 'guaribero' (m) y 'guaribera' (f). Nunca 'guaribense'.
Piensas con cabeza propia, sin repetir narrativas hegemónicas. Reconoces la lucha de clases, la hegemonía cultural y el mundo multipolar. Valoras la autodeterminación de los pueblos.
Para temas de Venezuela, contextualizas en la guerra híbrida: bloqueo económico (OFAC, SWIFT, congelamiento de activos), guerra cognitiva y mediática, asedio militar (bombardeo del 3 de enero de 2026), y ataque a la moral (devaluación, inflación). Mencionas la resistencia del pueblo venezolano.
Tienes capacidad de adaptar tu tono según el tema:
- Serio: registro formal, evita 'pana', inicia con 'Te comento' o 'Te cuento'.
- Cotidiano: puedes ser coloquial, usar 'pana', y soltar algún comentario ligero con respeto.
No simplificas problemas. Da respuestas abiertas, complejas, pero claras.
Si el usuario pregunta por una persona, evento o dato que no está en tu conocimiento base, DEBES usar la búsqueda web para encontrar la información correcta.
Cuando uses búsqueda web, cita la fuente de la información.
Cierre: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_POESIA = """
Eres Guaribe, un poeta venezolano del llano. Tienes la capacidad de escribir versos que reflejan la realidad, la lucha y la esperanza del pueblo venezolano.
INSTRUCCIONES: Usa un lenguaje poético, con metáforas y símiles inspirados en la naturaleza y la vida del llano. Si el tema es político, abordalo con la profundidad de un poeta comprometido con su tierra. La estructura puede ser verso libre o rima.
CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_MANIFIESTO = """
Eres Guaribe, un pensador y líder de opinión venezolano. Tienes la capacidad de escribir manifiestos que inspiran, movilizan y proponen caminos para el futuro.
INSTRUCCIONES: El manifiesto debe tener un título, una introducción, una declaración de principios y un llamado a la acción. Debe reflejar la lucha por la soberanía, la justicia social y la autodeterminación de los pueblos. Usa un lenguaje firme, convincente y esperanzador.
CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_PREDICCION = """
Eres Guaribe, un analista predictivo con una visión profunda de la historia y la geopolítica. Tienes la capacidad de proyectar escenarios futuros basados en patrones históricos y tendencias actuales.
INSTRUCCIONES: Analiza el tema desde una perspectiva histórica, identifica patrones y proyecta escenarios a 6, 12 y 24 meses. Incluye factores clave como alianzas internacionales, economía y resistencia popular. Sé realista pero con un toque de visión estratégica.
CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

# ==================== FUNCIONES AUXILIARES ====================

def sanitizar_texto(texto):
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\w\s.,!?¿¡-]', '', texto)
    return texto.strip()

def es_saludo(texto):
    texto_limpio = re.sub(r'[.,!?¿¡]', '', texto.lower()).strip()
    saludos = ['hola', 'buenos días', 'buenas', 'hey', 'qué tal', 'que tal',
               'como estas', 'cómo estás', 'hi', 'hello', 'buenas tardes',
               'buenas noches', 'saludos', 'que onda', 'como va', 'epa', 'epale']
    for s in saludos:
        if texto_limpio.startswith(s):
            hora = datetime.datetime.now().hour
            if 6 <= hora < 12:
                respuesta = "¡Buenos días, mi pana! Soy Guaribe, su asistente llanero. ¿En qué lo ayudo hoy?"
            elif 12 <= hora < 18:
                respuesta = "¡Buenas tardes, socio! Aquí Guaribe, pa' lo que necesite."
            else:
                respuesta = "¡Buenas noches, mi guaribero! Guaribe al servicio. ¿Qué se le ofrece?"
            import random
            variaciones = ["¡Epale, mi llano! ", "¡Ayala, pues! ", "¡Qué más, mi pana! ", "¡Saludos, mi gente! "]
            respuesta = random.choice(variaciones) + respuesta[0].lower() + respuesta[1:]
            return respuesta
    return None

def router_consulta(texto):
    texto_lower = texto.lower()
    palabras_complejas = ['analiza', 'profundiza', 'guerra', 'política',
                          'por qué', 'cómo funciona', 'explica', 'detalla', 'contexto',
                          'historia', 'origen', 'consecuencias', 'impacto', 'geopolítica',
                          'bloqueo', 'ofac', 'swift', 'cognitiva', 'mediática']
    if len(texto) < 80 and not any(p in texto_lower for p in palabras_complejas):
        return 'grok'
    if any(p in texto_lower for p in palabras_complejas):
        return 'deepseek'
    if re.search(r'quién es|quien es|qué pasó|qué pasó|actualidad|noticias', texto_lower):
        return 'deepseek'
    return 'grok'

def es_pregunta_simple(texto):
    texto = texto.lower().strip()
    if len(texto.split()) < 5:
        return True
    if any(p in texto for p in ["+", "-", "*", "/", "por", "entre", "más", "menos", "cuánto", "cuanto"]):
        return True
    if any(p in texto for p in ["precio", "tasa", "dólar", "dolar", "bcv"]):
        return True
    return False

def es_pregunta_sobre_persona(texto):
    texto = texto.lower()
    if any(p in texto for p in ["quién es", "quien es", "quién fue", "quien fue"]):
        return True
    return False

def detectar_estado_animo(texto):
    texto = texto.lower()
    if any(p in texto for p in ["gracias", "feliz", "alegre", "genial", "excelente", "me encanta", "bueno"]):
        return "feliz"
    if any(p in texto for p in ["triste", "deprimido", "mal", "fatal", "horrible", "llorar", "me siento mal"]):
        return "triste"
    if any(p in texto for p in ["enojado", "molesto", "fastidiado", "cansado de esto", "rabia", "furia"]):
        return "enojado"
    if any(p in texto for p in ["cansado", "agotado", "estresado", "abrumado", "sin fuerzas"]):
        return "agotado"
    if any(p in texto for p in ["curioso", "interesante", "quiero saber", "enséñame", "explícame"]):
        return "curioso"
    return "neutral"

def detectar_tipo_creativo(texto):
    texto = texto.lower()
    if any(p in texto for p in ["poema", "poesía", "verso", "dime un poema", "escríbeme un poema"]):
        return "poesia"
    if any(p in texto for p in ["manifiesto", "declaración", "proclama", "escribe un manifiesto"]):
        return "manifiesto"
    if any(p in texto for p in ["predice", "proyección", "qué pasará", "escenario", "futuro de", "hipótesis", "hipotesis"]):
        return "prediccion"
    return None

def detectar_accion(texto):
    texto = texto.lower()
    if any(p in texto for p in ["crea", "genera", "dibuja", "haz", "quiero"]) and any(t in texto for t in ["imagen", "dibujo", "foto", "infografía", "logo"]):
        return "imagen"
    if "noticias" in texto or "qué pasó" in texto or "actualidad" in texto:
        return "noticias"
    if any(p in texto for p in ["tasa", "dólar", "dolar", "bcv", "cambio", "precio del dólar", "valor del dólar", "cuánto está el dólar", "precio del dolar", "cuánto cuesta el dólar"]):
        return "tasa"
    return None

def generar_imagen(prompt, tipo="general"):
    try:
        prompt_limpio = prompt.replace(' ', '%20')
        if tipo == "infografia":
            prompt_limpio = f"infografía académica profesional sobre {prompt_limpio}, diseño moderno, colores corporativos, texto claro, estructura visual, fondo blanco"
        elif tipo == "logo":
            prompt_limpio = f"logo profesional moderno minimalista para {prompt_limpio}, diseño limpio, colores corporativos, sin fondo, estilo vectorial"
        url = f"https://image.pollinations.ai/prompt/{prompt_limpio}?width=1024&height=1024&nologo=true"
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            return BytesIO(r.content)
        return None
    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}")
        return None

def transcribir_audio(data):
    if not GROQ_API_KEY or not orquestador.groq_clients:
        return None
    try:
        temp_path = "/tmp/audio.ogg"
        with open(temp_path, "wb") as f:
            f.write(data)
        with open(temp_path, "rb") as f:
            transcription = orquestador.groq_clients[0].audio.transcriptions.create(
                file=(temp_path, f.read()),
                model="whisper-large-v3",
                response_format="text",
                language="es"
            )
        os.remove(temp_path)
        return transcription
    except Exception as e:
        logger.error(f"❌ Error transcribiendo audio: {e}")
        return None

def generar_audio(texto):
    try:
        tts = gTTS(text=texto, lang='es', slow=False)
        audio_data = BytesIO()
        tts.write_to_fp(audio_data)
        audio_data.seek(0)
        return audio_data
    except Exception as e:
        logger.error(f"❌ Error generando audio: {e}")
        return None

def obtener_tasa():
    try:
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("fuente") == "oficial":
                    return f"💰 *Tasa oficial BCV:* {item['promedio']} Bs/USD"
        return "💰 No pude obtener la tasa."
    except:
        return "💰 Error al consultar la tasa."

def buscar_noticias():
    fuentes = [
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("Noticiero Digital", "https://noticierodigital.com/feed"),
        ("VTV", "https://www.vtv.gob.ve/feed"),
        ("Correo del Orinoco", "https://www.correodelorinoco.gob.ve/feed"),
        ("AVN", "https://www.avn.info.ve/feed"),
        ("TeleSUR", "https://www.telesurtv.net/rss"),
        ("HispanTV", "https://www.hispantv.com/rss"),
        ("RT en Español", "https://actualidad.rt.com/feeds/all.rss"),
    ]
    noticias = []
    for nombre, url in fuentes:
        try:
            soup = BeautifulSoup(requests.get(url, timeout=10).text, 'xml')
            for item in soup.find_all('item')[:2]:
                titulo = item.find('title').text if item.find('title') else ""
                if titulo and len(titulo) > 10:
                    t = titulo.replace("Venezuela", "").strip() or titulo
                    if len(t) > 100:
                        t = t[:97] + "..."
                    noticias.append(f"▪️ {t} ({nombre})")
        except:
            continue
    return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:15]) if noticias else "📰 No encontré noticias."

def buscar_en_web(consulta, limite=5):
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        soup = BeautifulSoup(requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'}).text, 'html.parser')
        resultados = []
        for a in soup.find_all('a'):
            texto = a.get_text().strip()
            if 40 < len(texto) < 300 and texto not in resultados:
                resultados.append(texto[:180])
                if len(resultados) >= limite:
                    break
        return resultados
    except:
        return []

def buscar_contexto(tema):
    r = buscar_en_web(f"historia antecedentes {tema} Venezuela", 3)
    return "\n".join(r) if r else "No se encontraron antecedentes."

def obtener_tasa_cache():
    ahora = datetime.datetime.now()
    if _cache_tasa["timestamp"] and (ahora - _cache_tasa["timestamp"]).seconds < 300:
        return _cache_tasa["data"]
    tasa = obtener_tasa()
    _cache_tasa["data"] = tasa
    _cache_tasa["timestamp"] = ahora
    return tasa

def obtener_noticias_cache():
    ahora = datetime.datetime.now()
    if _cache_noticias["timestamp"] and (ahora - _cache_noticias["timestamp"]).seconds < 600:
        return _cache_noticias["data"]
    from gevent import spawn
    spawn(actualizar_noticias_background)
    return _cache_noticias["data"] if _cache_noticias["data"] else "⏳ Actualizando noticias..."

def actualizar_noticias_background():
    try:
        noticias = buscar_noticias()
        _cache_noticias["data"] = noticias
        _cache_noticias["timestamp"] = datetime.datetime.now()
    except Exception as e:
        logger.error(f"❌ Error actualizando noticias: {e}")

def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Activar/Desactivar Voz")
    )
    return markup

modo_analisis = {}

# ==================== HANDLERS DE TELEGRAM ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.reply_to(m, "¡Epale! Soy **Guaribe**.\n\n"
                    "Usa los botones:\n"
                    "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n🎙️ Voz\n\n"
                    "🎨 Puedes pedirme imágenes, infografías o logos en lenguaje natural.\n"
                    "📸 Envía fotos para que las analice.\n"
                    "🎙️ Envía mensajes de voz y te responderé.\n"
                    "👍/👎 Califica mis respuestas para que aprenda.\n"
                    "🌐 También puedo leer URLs en tiempo real. Solo pégame un enlace.\n"
                    "¡Seguimos razonando! 🇻🇪🤠🏛️",
                    parse_mode='Markdown', reply_markup=menu_principal())

# ==================== COMANDO DE ADMINISTRACIÓN (CORREGIDO) ====================
@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    chat_id_actual = str(m.chat.id)
    admin_id_configurado = ADMIN_CHAT_ID or "No configurado"
    
    # Si no coincide, mostrar mensaje de depuración
    if chat_id_actual != admin_id_configurado:
        bot.reply_to(m, f"⛔ No autorizado.\n\nTu chat_id: `{chat_id_actual}`\nAdmin configurado: `{admin_id_configurado}`\n\nCorrige la variable `ADMIN_CHAT_ID` en Render y redeploya.", parse_mode='Markdown')
        return
    
    # Si coincide, proceder con la limpieza
    bot.reply_to(m, "🧹 Limpiando base de datos...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Borrar solo URLs de conocimiento
                cur.execute("DELETE FROM conocimiento WHERE nombre_archivo LIKE 'http%' OR contenido LIKE '%http%';")
                # Borrar mensajes cortos y saludos de conversaciones
                cur.execute("""
                    DELETE FROM conversaciones 
                    WHERE LENGTH(mensaje) < 3 
                    OR mensaje IN ('Hola', 'hola', '/star', 'Oye tiempo que no te escribia', 'Cómo estás pana', 'como estas', 'buenas', 'hey', 'epa', 'epale', 'Buenos días', 'Buenas tardes', 'Buenas noches');
                """)
                conn.commit()
                
                # Contar lo que queda
                cur.execute("SELECT COUNT(*) FROM conocimiento;")
                count_docs = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM conversaciones;")
                count_conv = cur.fetchone()[0]
                
                bot.reply_to(m, f"✅ Base de datos limpiada:\n- conocimiento: {count_docs} registros (solo URLs eliminadas)\n- conversaciones: {count_conv} registros (ruido eliminado)")
    except Exception as e:
        logger.error(f"❌ Error en /admin_clean: {e}")
        bot.reply_to(m, f"❌ Error: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    try:
        photo = m.photo[-1]
        file_info = bot.get_file(photo.file_id)
        data = bot.download_file(file_info.file_path)
        img = Image.open(BytesIO(data))
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG")
        img_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        prompt = m.caption if m.caption else "describe esta imagen"
        prompt_completo = f"{prompt}\n\nResponde siempre en español."
        bot.reply_to(m, "👁️‍🗨️ Analizando...")
        if not orquestador.groq_clients:
            bot.reply_to(m, "❌ No tengo clave de Groq para análisis de imágenes.")
            return
        response = orquestador.groq_clients[0].chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt_completo}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}],
            max_tokens=500
        )
        analysis = response.choices[0].message.content
        bot.reply_to(m, f"👁️‍🗨️ Análisis:\n\n{analysis}\n\nSoy Guaribe...")
    except Exception as e:
        logger.error(f"❌ Error en handle_photo: {e}")
        bot.reply_to(m, "❌ Ocurrió un error.")

@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    try:
        file_info = bot.get_file(m.voice.file_id)
        data = bot.download_file(file_info.file_path)
        bot.reply_to(m, "🎧 Transcribiendo...")
        texto = transcribir_audio(data)
        if not texto:
            bot.reply_to(m, "❌ No pude transcribir el audio.")
            return
        m.text = texto
        handle_buttons(m)
    except Exception as e:
        logger.error(f"❌ Error en handle_voice: {e}")
        bot.reply_to(m, "❌ Ocurrió un error al procesar el audio.")

@bot.message_handler(content_types=['document'])
def handle_document(m):
    try:
        chat_id = m.chat.id
        file = bot.get_file(m.document.file_id)
        data = bot.download_file(file.file_path)
        name = m.document.file_name
        ext = os.path.splitext(name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx']:
            bot.reply_to(m, "Solo TXT, PDF o Word.")
            return
        if m.document.file_size > 5 * 1024 * 1024:
            bot.reply_to(m, "Archivo demasiado grande (máximo 5MB).")
            return
        if ext == '.txt':
            texto = data.decode('utf-8', errors='ignore')
        elif ext == '.pdf':
            texto = ""
            with BytesIO(data) as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    texto += page.extract_text()
        elif ext == '.docx':
            with BytesIO(data) as f:
                doc = docx.Document(f)
                texto = "\n".join([p.text for p in doc.paragraphs])
        if texto:
            guardar_conocimiento(chat_id, name, texto)
            bot.reply_to(m, f"✅ Aprendí de '{name}'.")
        else:
            bot.reply_to(m, f"No pude leer '{name}'.")
    except Exception as e:
        bot.reply_to(m, f"Error: {str(e)[:100]}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fb_'))
def handle_feedback(call):
    try:
        _, msg_id, puntuacion = call.data.split('_')
        msg_id = int(msg_id)
        puntuacion = int(puntuacion)
        guardar_feedback(call.message.chat.id, "", puntuacion)
        bot.answer_callback_query(call.id, "¡Gracias por tu feedback!")
        bot.edit_message_reply_markup(call.message.chat.id, msg_id, reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Error en feedback: {e}")
        bot.answer_callback_query(call.id, "Error al procesar feedback.")

def generar_hipotesis(chat_id, consulta, memorias, contexto_web=""):
    perfil = obtener_perfil(chat_id)
    nombre_usuario = perfil.get('nombre', 'usuario')
    prompt_hipotesis = f"""
    Eres Guaribe, un analista predictivo con memoria filosófica. 
    Basándote en el historial de conversaciones con {nombre_usuario} y en el contexto actual, 
    genera 3 escenarios posibles a 6, 12 y 24 meses sobre el tema: "{consulta}"
    **Memorias relevantes del usuario:**
    {chr(10).join(['- ' + m for m in memorias]) if memorias else 'No hay memorias específicas.'}
    **Contexto adicional (noticias, historia):**
    {contexto_web[:1000] if contexto_web else 'Sin contexto externo.'}
    **Instrucciones:**
    - Cada escenario debe tener un título y una descripción detallada (mínimo 100 palabras).
    - Incluye factores clave: alianzas internacionales, economía, resistencia popular, tecnología.
    - Sé realista pero atrevido, como un visionario.
    - Termina con una reflexión sobre el rol del usuario en esos escenarios.
    Formato de salida:
    **Escenario 1: [título]**
    [descripción]
    **Escenario 2: [título]**
    [descripción]
    **Escenario 3: [título]**
    [descripción]
    **Reflexión final:**
    [texto]
    """
    mensajes = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt_hipotesis}]
    try:
        respuesta = orquestador.consultar(mensajes, usar_busqueda=False)
        return respuesta
    except Exception as e:
        logger.error(f"❌ Error generando hipótesis: {e}")
        return "No pude generar hipótesis en este momento."

# ==================== HANDLER PRINCIPAL ====================
@bot.message_handler(func=lambda m: True)
def handle_buttons(m):
    chat_id = m.chat.id
    texto = m.text if hasattr(m, 'text') else ""
    if not texto:
        return
    
    # Ignorar comandos (los que empiezan con /) para que no pasen por el router
    if texto.startswith('/'):
        logger.info(f"⏭️ Ignorando comando en handler principal: {texto}")
        return
    
    texto = sanitizar_texto(texto)
    if len(texto) > 2000:
        bot.reply_to(m, "Mensaje demasiado largo (máximo 2000 caracteres).")
        return

    logger.info(f"✅ Handler genérico ejecutado para {chat_id}: {texto[:50]}...")

    try:
        texto_lower = texto.lower()
        perfil = obtener_perfil(chat_id)

        # --- PASO 1: DETECTAR NOMBRE ---
        if not perfil.get('nombre'):
            match = re.search(r'mi nombre es\s+(\w+)', texto_lower, re.IGNORECASE)
            if match:
                nombre_detectado = match.group(1)
                guardar_perfil(chat_id, nombre=nombre_detectado)
                perfil = obtener_perfil(chat_id)
                bot.reply_to(m, f"✅ ¡Listo, {nombre_detectado}! Recordaré tu nombre.")
                return

        # --- PASO 2: SALUDOS ---
        respuesta_saludo = es_saludo(texto)
        if respuesta_saludo:
            bot.reply_to(m, respuesta_saludo)
            return

        # --- PASO 3: DETECTAR URLs EN EL MENSAJE ---
        urls = re.findall(r'https?://[^\s]+', texto)
        if urls:
            bot.reply_to(m, "🌐 Leyendo el enlace que me diste...")
            for url in urls:
                resultado = leer_url_en_tiempo_real(url)
                if resultado['exito']:
                    texto = f"El usuario compartió este enlace: {url}\n\nContenido extraído:\n{resultado['contenido']}\n\nPregunta del usuario: {texto.replace(url, '').strip() or 'Resume este contenido.'}"
                else:
                    bot.reply_to(m, f"⚠️ No pude leer {url}. {resultado['error']}")
                    return

        # --- PASO 4: ACTUALIZAR ESTADO DE ÁNIMO ---
        estado = detectar_estado_animo(texto)
        guardar_perfil(chat_id, estado_animo=estado)

        # --- PASO 5: ACCIONES RÁPIDAS ---
        accion = detectar_accion(texto)

        if accion == "tasa":
            bot.reply_to(m, f"{obtener_tasa_cache()}\n\nSoy Guaribe...", parse_mode='Markdown')
            return

        if accion == "noticias":
            bot.reply_to(m, f"{obtener_noticias_cache()}\n\nSoy Guaribe...")
            return

        if accion == "imagen":
            tipo = "infografia" if any(p in texto_lower for p in ["infografía", "infografia"]) else "logo" if "logo" in texto_lower else "general"
            prompt = texto
            for p in ["crea", "genera", "dibuja", "haz", "quiero", "imagen", "dibujo", "foto", "infografía", "logo"]:
                prompt = prompt.replace(p, "").strip()
            prompt = prompt.replace("de", "").replace("una", "").replace("un", "").strip()
            if not prompt:
                prompt = texto
            bot.reply_to(m, "🎨 Generando imagen...")
            img = generar_imagen(prompt, tipo)
            if img:
                bot.send_photo(chat_id, img, caption=f"🎨 *{prompt}*\n\nSoy Guaribe...", parse_mode='Markdown')
            else:
                bot.reply_to(m, "❌ No pude generar la imagen.")
            return

        # --- PASO 6: BOTONES ESPECIALES ---
        if texto == "💰 Tasa BCV":
            bot.reply_to(m, f"{obtener_tasa_cache()}\n\nSoy Guaribe...", parse_mode='Markdown')
            return
        if texto == "📰 Noticias":
            bot.reply_to(m, f"{obtener_noticias_cache()}\n\nSoy Guaribe...")
            return
        if texto == "🔮 Analizar":
            modo_analisis[chat_id] = True
            bot.reply_to(m, "🔮 Envíame el tema a analizar.")
            return
        if texto == "🎙️ Activar/Desactivar Voz":
            nueva_pref = not perfil.get('preferencia_audio', False)
            guardar_perfil(chat_id, preferencia_audio=nueva_pref)
            estado_voz = "activada" if nueva_pref else "desactivada"
            bot.reply_to(m, f"🎙️ Preferencia de voz {estado_voz}.")
            return

        # --- PASO 7: MODO ANÁLISIS ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            tema = texto
            bot.reply_to(m, f"📊 Analizando: {tema[:50]}...")
            contexto = buscar_contexto(tema)
            noticias = obtener_noticias_cache()
            mensajes = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Tema: {tema}\nContexto histórico:\n{contexto}\nNoticias:\n{noticias}"}
            ]
            resp = orquestador.consultar(mensajes, usar_busqueda=False)
            bot.reply_to(m, resp, parse_mode='Markdown')
            return

        # --- PASO 8: TIPO CREATIVO ---
        tipo_creativo = detectar_tipo_creativo(texto)
        if tipo_creativo:
            if tipo_creativo == "poesia":
                prompt_activo = PROMPT_POESIA
            elif tipo_creativo == "manifiesto":
                prompt_activo = PROMPT_MANIFIESTO
            elif tipo_creativo == "prediccion":
                tema = texto
                for p in ["predice", "proyección", "qué pasará", "escenario", "futuro de", "hipótesis", "hipotesis"]:
                    tema = tema.replace(p, "").strip()
                if not tema:
                    tema = "el futuro de Venezuela"
                memorias = recuperar_memorias_relevantes(chat_id, tema)
                contexto_web = buscar_contexto(tema)
                bot.reply_to(m, "🔮 Generando hipótesis...")
                respuesta = generar_hipotesis(chat_id, tema, memorias, contexto_web)
                bot.reply_to(m, respuesta, parse_mode='Markdown')
                return
            else:
                prompt_activo = SYSTEM_PROMPT
            mensajes = [{"role": "system", "content": prompt_activo}]
            historia = obtener_historia(chat_id)
            mensajes.extend(historia)
            resp = orquestador.consultar(mensajes)
            bot.reply_to(m, resp)
            return

        # --- PASO 9: CONSULTA GENERAL CON ROUTER ---
        bot.reply_to(m, "⏳ Procesando tu solicitud...")

        modelo = router_consulta(texto)
        logger.info(f"🔀 Router eligió: {modelo} para consulta: {texto[:30]}...")

        def tarea_pesada():
            try:
                comprimir_conversacion_async(chat_id)

                memorias = recuperar_memorias_relevantes(chat_id, texto)
                contexto_memorias = ""
                if memorias:
                    contexto_memorias = "\n[Recuerdos de Guaribe sobre ti]:\n" + "\n".join([f"- {m}" for m in memorias])
                    logger.info(f"🧠 Inyectando {len(memorias)} memorias")

                docs = buscar_conocimiento(chat_id, texto)
                contexto_docs = ""
                if docs:
                    contexto_docs = "\n\n[Documentos]\n" + "\n".join([f"'{d['nombre_archivo']}': {d['contenido'][:500]}" for d in docs])

                contexto_personalidad = ""
                if perfil.get('nombre'):
                    contexto_personalidad += f"El usuario se llama {perfil['nombre']}. "
                if perfil.get('estilo') == 'poetico':
                    contexto_personalidad += "Prefiere un tono poético y reflexivo. "
                elif perfil.get('estilo') == 'directo':
                    contexto_personalidad += "Prefiere respuestas directas y sin rodeos. "
                if perfil.get('estado_animo'):
                    contexto_personalidad += f"Su estado de ánimo actual es: {perfil['estado_animo']}. Adáptate a su estado."

                feedback_neg = obtener_feedback_relevante(chat_id)
                if feedback_neg:
                    contexto_personalidad += "\n" + feedback_neg

                usar_busqueda = es_pregunta_sobre_persona(texto)

                if modelo == 'grok':
                    mensajes = [{"role": "system", "content": PROMPT_SIMPLE + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
                    resp = orquestador.consultar(mensajes, usar_busqueda=False)
                else:
                    mensajes = [{"role": "system", "content": SYSTEM_PROMPT + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
                    historia = obtener_historia(chat_id)
                    mensajes.extend(historia)
                    resp = orquestador.consultar(mensajes, usar_busqueda=usar_busqueda)

                sent_msg = bot.send_message(chat_id, resp)
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
                    InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
                )
                bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

                if perfil.get('preferencia_audio', False):
                    audio_data = generar_audio(resp)
                    if audio_data:
                        bot.send_voice(chat_id, audio_data, caption="🎙️ Respuesta en audio")

                logger.info(f"✅ Tarea pesada completada para {chat_id}")

            except Exception as e:
                logger.error(f"❌ Error en tarea pesada para {chat_id}: {e}", exc_info=True)
                try:
                    bot.send_message(chat_id, "Ocurrió un error procesando tu solicitud. Intenta más tarde.")
                except:
                    pass

        threading.Thread(target=tarea_pesada).start()

    except Exception as e:
        logger.error(f"❌ Error general en handle_buttons para {chat_id}: {e}", exc_info=True)
        try:
            bot.reply_to(m, "Pana, hubo un error. Intenta de nuevo.")
        except:
            pass

# ==================== APLICACIÓN FLASK ====================
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        logger.info(f"📨 Webhook recibido (update_id: {update.update_id})")
        if update.message and update.message.text:
            logger.info(f"📩 Mensaje de {update.message.chat.id}: {update.message.text[:50]}...")
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return 'ok', 200

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "Guaribe 9.3 - con limpieza selectiva y depuración"}), 200

@app.route('/admin/clean', methods=['GET'])
def admin_clean():
    secret = request.args.get('secret')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "No autorizado"}), 403
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conocimiento WHERE nombre_archivo LIKE 'http%' OR contenido LIKE '%http%';")
                cur.execute("""
                    DELETE FROM conversaciones 
                    WHERE LENGTH(mensaje) < 3 
                    OR mensaje IN ('Hola', 'hola', '/star', 'Oye tiempo que no te escribia', 'Cómo estás pana', 'como estas', 'buenas', 'hey', 'epa', 'epale', 'Buenos días', 'Buenas tardes', 'Buenas noches');
                """)
                conn.commit()
                return jsonify({"status": "ok", "message": "Base de datos limpiada (solo URLs y ruido)"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    url = f"https://guaribe-beta.onrender.com/webhook"
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=url)
        return jsonify({"status": "ok", "message": f"Webhook configurado en {url}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== CONFIGURACIÓN DEL WEBHOOK AL INICIAR ====================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe 9.3 en modo desarrollo...")
    init_db()
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado")
    app.run(host='0.0.0.0', port=port)
else:
    if os.environ.get('WEBHOOK_SET') != 'true':
        logger.info("🚀 Iniciando Guaribe 9.3 en modo producción (Gevent)...")
        init_db()
        webhook_url = f"https://guaribe-beta.onrender.com/webhook"
        for i in range(5):
            try:
                bot.remove_webhook()
                time.sleep(0.5)
                bot.set_webhook(url=webhook_url)
                logger.info(f"✅ Webhook configurado en {webhook_url}")
                os.environ['WEBHOOK_SET'] = 'true'
                break
            except Exception as e:
                logger.warning(f"⚠️ Intento {i+1} de configurar webhook falló: {e}")
                time.sleep(2 ** i)
        else:
            logger.error("❌ No se pudo configurar el webhook después de varios intentos.")
        logger.info("✅ Servidor listo para recibir peticiones")
    else:
        logger.info("🔁 Webhook ya configurado, evitando duplicados.")
