# ================== PARCHE DE EVENTLET (DEBE IR PRIMERO) ==================
import eventlet
eventlet.monkey_patch(thread=True, socket=True, select=True, time=True)

# ================== RESTO DE IMPORTACIONES ==================
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
import smtplib
import datetime
import hashlib
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
from psycopg2.extras import DictCursor
from io import BytesIO
from PIL import Image
from groq import Groq
from gtts import gTTS
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ================== CONFIGURACIÓN ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ================== CONEXIÓN A DB (OPTIMIZADA) ==================
def get_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.error(f"❌ Error DB: {e}")
        raise

# ================== CACHÉ EN BASE DE DATOS ==================
def init_cache_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    hash TEXT PRIMARY KEY,
                    respuesta TEXT NOT NULL,
                    expira TIMESTAMP NOT NULL
                )
            """)
            conn.commit()

def obtener_cache(consulta_str):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT respuesta FROM cache WHERE hash = %s AND expira > NOW()", (h,))
            row = cur.fetchone()
            if row:
                logger.info("✅ Caché DB hit")
                return row[0]
    return None

def guardar_cache(consulta_str, respuesta):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    expira = datetime.datetime.now() + datetime.timedelta(minutes=5)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cache (hash, respuesta, expira)
                VALUES (%s, %s, %s)
                ON CONFLICT (hash) DO UPDATE SET respuesta = EXCLUDED.respuesta, expira = EXCLUDED.expira
            """, (h, respuesta, expira))
            conn.commit()

def limpiar_cache_expirado():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache WHERE expira < NOW()")
            conn.commit()

# ================== FUNCIONES DE BASE DE DATOS ==================
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
                CREATE TABLE IF NOT EXISTS notas (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    texto TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS recordatorios (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    texto TEXT NOT NULL,
                    fecha_hora TIMESTAMP NOT NULL,
                    enviado BOOLEAN DEFAULT FALSE,
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_chat_ts ON conversaciones (chat_id, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memoria_larga_chat_ts ON memoria_larga (chat_id, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_chat ON conocimiento (chat_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_chat ON feedback (chat_id);")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_contenido_trgm ON conocimiento USING gin (contenido gin_trgm_ops);")
            conn.commit()
    init_cache_table()
    logger.info("✅ Base de datos inicializada con caché")

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
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO conversaciones (chat_id, rol, mensaje) VALUES (%s, %s, %s)", (chat_id, rol, mensaje))
            conn.commit()

def obtener_historia(chat_id, limite=10):
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

def guardar_nota(chat_id, texto):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO notas (chat_id, texto) VALUES (%s, %s)", (chat_id, texto))
            conn.commit()
            return "✅ Nota guardada."

def obtener_notas(chat_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT texto, timestamp FROM notas WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 10", (chat_id,))
            notas = cur.fetchall()
            if not notas:
                return "📝 No tienes notas guardadas."
            return "📝 Tus últimas notas:\n" + "\n".join([f"- {n['texto']} ({n['timestamp'].strftime('%d/%m/%Y %H:%M')})" for n in notas])

def guardar_recordatorio(chat_id, texto, fecha_hora):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO recordatorios (chat_id, texto, fecha_hora) VALUES (%s, %s, %s)", (chat_id, texto, fecha_hora))
            conn.commit()
            return f"✅ Recordatorio guardado para {fecha_hora.strftime('%d/%m/%Y %H:%M')}."

def revisar_recordatorios():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            ahora = datetime.datetime.now()
            cur.execute("SELECT id, chat_id, texto, fecha_hora FROM recordatorios WHERE enviado = FALSE AND fecha_hora <= %s", (ahora,))
            pendientes = cur.fetchall()
            for r in pendientes:
                try:
                    bot.send_message(r['chat_id'], f"⏰ *Recordatorio:* {r['texto']}\n\n(Programado para {r['fecha_hora'].strftime('%d/%m/%Y %H:%M')})", parse_mode='Markdown')
                    cur.execute("UPDATE recordatorios SET enviado = TRUE WHERE id = %s", (r['id'],))
                    conn.commit()
                except Exception as e:
                    logger.error(f"❌ Error enviando recordatorio {r['id']}: {e}")
            return f"✅ Revisados {len(pendientes)} recordatorios."

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

# ================== ORQUESTADOR CON ROTACIÓN DE CLAVES GROQ ==================
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
                # Parche: Forzar http_client=None para evitar error de proxies
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
        consulta_str = json.dumps(mensajes) + str(usar_busqueda)
        cacheado = obtener_cache(consulta_str)
        if cacheado:
            logger.info("✅ Respuesta desde caché")
            return cacheado

        for nombre, funcion in self.modelos:
            for intento in range(intentos):
                try:
                    if "DeepSeek" in nombre and usar_busqueda:
                        respuesta = funcion(mensajes, search=True)
                    else:
                        respuesta = funcion(mensajes)
                    if respuesta:
                        self.modelo_activo = nombre
                        guardar_cache(consulta_str, respuesta)
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

# ================== PROMPTS ==================
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

# ================== FUNCIONES AUXILIARES ==================
def es_pregunta_simple(texto):
    texto = texto.lower()
    if texto in ["hola", "buenos días", "buenas", "hey", "qué tal", "como estás"]:
        return True
    if any(p in texto for p in ["+", "-", "*", "/", "por", "entre", "más", "menos", "cuánto", "cuanto"]):
        return True
    if any(p in texto for p in ["precio", "tasa", "dólar", "dolar", "bcv"]):
        return True
    if len(texto.split()) < 5:
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
    if "enviar correo" in texto or "mandar email" in texto or "email a" in texto:
        return "email"
    if "guardar nota" in texto or "nota:" in texto or "apunta esto" in texto:
        return "nota"
    if "recordatorio" in texto or "recuérdame" in texto or "recordar" in texto:
        return "recordatorio"
    if any(p in texto for p in ["crea", "genera", "dibuja", "haz", "quiero"]) and any(t in texto for t in ["imagen", "dibujo", "foto", "infografía", "logo"]):
        return "imagen"
    if "noticias" in texto or "qué pasó" in texto or "actualidad" in texto:
        return "noticias"
    if any(p in texto for p in ["tasa", "dólar", "dolar", "bcv", "cambio"]):
        return "tasa"
    return None

# ================== FUNCIONES DE IMAGEN, VOZ, CORREO, etc. ==================
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

def enviar_correo(destino, asunto, cuerpo):
    if not EMAIL_USER or not EMAIL_PASSWORD:
        return "⚠️ El servicio de correo no está configurado."
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USER
        msg['To'] = destino
        msg['Subject'] = asunto
        msg.attach(MIMEText(cuerpo, 'plain'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_USER, destino, msg.as_string())
        server.quit()
        return "✅ Correo enviado exitosamente."
    except Exception as e:
        logger.error(f"❌ Error enviando correo: {e}")
        return f"❌ Error enviando correo: {str(e)[:100]}"

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
        ("Efecto Cocuyo", "https://efectococuyo.com/feed"),
        ("Tal Cual", "https://talcualdigital.com/feed"),
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("El Nacional", "https://www.elnacional.com/rss"),
        ("RunRun.es", "https://runrun.es/feed"),
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

# ================== CACHE DE NOTICIAS Y TASAS ==================
_cache_noticias = {"data": None, "timestamp": None}
_cache_tasa = {"data": None, "timestamp": None}

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
    eventlet.spawn(actualizar_noticias_background)
    return _cache_noticias["data"] if _cache_noticias["data"] else "⏳ Actualizando noticias..."

def actualizar_noticias_background():
    try:
        noticias = buscar_noticias()
        _cache_noticias["data"] = noticias
        _cache_noticias["timestamp"] = datetime.datetime.now()
    except Exception as e:
        logger.error(f"❌ Error actualizando noticias: {e}")

def comprimir_conversacion_async(chat_id):
    eventlet.spawn(comprimir_conversacion, chat_id)

def comprimir_conversacion(chat_id):
    # Esta función está definida en el bloque de funciones DB, pero la movemos aquí para claridad
    pass

# ================== MENÚ PRINCIPAL ==================
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

# ================== HANDLERS ==================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.reply_to(m, "¡Epale! Soy **Guaribe**.\n\n"
                    "Usa los botones:\n"
                    "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n🎙️ Voz\n\n"
                    "🎨 Puedes pedirme imágenes, infografías o logos en lenguaje natural.\n"
                    "📧 Dime 'enviar correo a ...' y te ayudaré.\n"
                    "📝 Dime 'guarda nota: ...' o 'apunta esto'.\n"
                    "⏰ Dime 'recordatorio ... para el ...' y te avisaré.\n"
                    "🔮 Pregúntame por hipótesis o escenarios futuros.\n"
                    "📸 Envía fotos para que las analice.\n"
                    "🎙️ Envía mensajes de voz y te responderé.\n"
                    "👍/👎 Califica mis respuestas para que aprenda.\n"
                    "¡Seguimos razonando! 🇻🇪🤠🏛️",
                    parse_mode='Markdown', reply_markup=menu_principal())

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

# ================== HANDLER PRINCIPAL ==================
@bot.message_handler(func=lambda m: True)
def handle_buttons(m):
    chat_id = m.chat.id
    texto = m.text if hasattr(m, 'text') else ""
    if not texto:
        return

    texto_lower = texto.lower()

    perfil = obtener_perfil(chat_id)
    if not perfil.get('nombre'):
        if "mi nombre es" in texto_lower:
            partes = texto.split("mi nombre es")
            if len(partes) > 1:
                nombre_detectado = partes[1].strip().split()[0]
                guardar_perfil(chat_id, nombre=nombre_detectado)
                perfil = obtener_perfil(chat_id)
                bot.reply_to(m, f"✅ ¡Listo, {nombre_detectado}! Recordaré tu nombre.")
                return

    estado = detectar_estado_animo(texto)
    guardar_perfil(chat_id, estado_animo=estado)

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
    
    if accion == "email":
        try:
            partes = texto.split("a ")[1] if "a " in texto else None
            if not partes:
                bot.reply_to(m, "📧 Para enviar un correo, dime: 'enviar correo a correo@ejemplo.com asunto ...'")
                return
            destino = partes.split(" ")[0]
            resto = " ".join(partes.split(" ")[1:])
            if " asunto " in resto:
                asunto = resto.split(" asunto ")[1].split(" cuerpo ")[0] if " cuerpo " in resto else resto.split(" asunto ")[1]
                cuerpo = resto.split(" cuerpo ")[1] if " cuerpo " in resto else ""
            else:
                asunto = "Mensaje desde Guaribe"
                cuerpo = resto
            bot.reply_to(m, "📧 Enviando correo...")
            resultado = enviar_correo(destino, asunto, cuerpo)
            bot.reply_to(m, resultado)
        except Exception:
            bot.reply_to(m, "❌ No entendí el correo. Usa: 'enviar correo a email@ejemplo.com asunto ...'")
        return
    
    if accion == "nota":
        texto_nota = texto
        for p in ["guardar nota", "nota:", "apunta esto"]:
            texto_nota = texto_nota.replace(p, "").strip()
        if not texto_nota:
            bot.reply_to(m, "📝 Escribe algo para guardar: 'guarda nota: ...'")
            return
        resultado = guardar_nota(chat_id, texto_nota)
        bot.reply_to(m, resultado)
        return
    
    if accion == "recordatorio":
        try:
            partes = texto.split(" para el ")
            if len(partes) < 2:
                bot.reply_to(m, "⏰ Usa: 'recordatorio ... para el YYYY-MM-DD HH:MM'")
                return
            texto_rec = partes[0].replace("recordatorio", "").replace("recuérdame", "").replace("recordar", "").strip()
            fecha_str = partes[1].strip()
            fecha_hora = datetime.datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
            if fecha_hora < datetime.datetime.now():
                bot.reply_to(m, "⚠️ La fecha debe ser futura.")
                return
            resultado = guardar_recordatorio(chat_id, texto_rec, fecha_hora)
            bot.reply_to(m, resultado)
        except ValueError:
            bot.reply_to(m, "❌ Formato de fecha inválido. Usa: YYYY-MM-DD HH:MM")
        except Exception as e:
            bot.reply_to(m, f"❌ Error: {str(e)[:100]}")
        return

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

        if es_pregunta_simple(texto):
            mensajes = [{"role": "system", "content": PROMPT_SIMPLE + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
            resp = orquestador.consultar(mensajes, usar_busqueda=False)
        else:
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
            historia = obtener_historia(chat_id)
            mensajes.extend(historia)
            resp = orquestador.consultar(mensajes, usar_busqueda=usar_busqueda)

        sent_msg = bot.reply_to(m, resp)

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

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        bot.reply_to(m, "Pana, hubo un error.")

# ================== SERVIDOR FLASK ==================
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode('utf-8'))])
        return 'ok', 200
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")
        return 'error', 500

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "Guaribe 9.0 Optimizado"}), 200

@app.route('/check_reminders', methods=['GET'])
def check_reminders():
    resultado = revisar_recordatorios()
    return jsonify({"status": "ok", "result": resultado}), 200

# ================== EJECUCIÓN ==================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe 9.0 Optimizado (modo desarrollo)...")
    init_db()
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado")
    app.run(host='0.0.0.0', port=port)
else:
    logger.info("🚀 Iniciando Guaribe 9.0 Optimizado en Gunicorn...")
    init_db()
    logger.info("✅ Webhook configurado previamente")
