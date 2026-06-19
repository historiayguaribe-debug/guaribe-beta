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
import threading
from collections import deque

# ================== CONFIGURACIÓN ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
# Soporte para múltiples claves de Groq separadas por comas
GROQ_API_KEYS = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
if not GROQ_API_KEYS and os.environ.get("GROQ_API_KEY"):
    GROQ_API_KEYS = [os.environ.get("GROQ_API_KEY")]
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))

# ================== INICIALIZACIÓN DEL BOT ==================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Clientes Groq con rotación round-robin
groq_clients = []
if GROQ_API_KEYS:
    for key in GROQ_API_KEYS:
        groq_clients.append(Groq(api_key=key))
    logger.info(f"✅ {len(groq_clients)} clientes Groq inicializados")
groq_index = 0

def get_groq_client():
    global groq_index
    if not groq_clients:
        return None
    client = groq_clients[groq_index]
    groq_index = (groq_index + 1) % len(groq_clients)
    return client

# ================== CACHÉ EN MEMORIA ==================
cache_memoria = {}  # {hash: (respuesta, timestamp)}
CACHE_TTL = 300  # 5 minutos

def obtener_cache_memoria(consulta_str):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    if h in cache_memoria:
        resp, ts = cache_memoria[h]
        if datetime.datetime.now() - ts < datetime.timedelta(seconds=CACHE_TTL):
            return resp
        else:
            del cache_memoria[h]
    return None

def guardar_cache_memoria(consulta_str, respuesta):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    cache_memoria[h] = (respuesta, datetime.datetime.now())

# ================== CACHÉ EN POSTGRESQL ==================
def init_cache_table():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_respuestas (
                hash TEXT PRIMARY KEY,
                respuesta TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON cache_respuestas (timestamp);")
        conn.commit()
    finally:
        conn.close()

def obtener_cache_db(consulta_str):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT respuesta FROM cache_respuestas WHERE hash = %s AND timestamp > NOW() - INTERVAL '5 minutes'", (h,))
        row = cursor.fetchone()
        if row:
            return row['respuesta']
        return None
    finally:
        conn.close()

def guardar_cache_db(consulta_str, respuesta):
    h = hashlib.md5(consulta_str.encode()).hexdigest()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO cache_respuestas (hash, respuesta) VALUES (%s, %s) ON CONFLICT (hash) DO UPDATE SET respuesta = EXCLUDED.respuesta, timestamp = CURRENT_TIMESTAMP",
            (h, respuesta)
        )
        conn.commit()
    finally:
        conn.close()

# ================== ORQUESTADOR CON CACHÉ Y ROTACIÓN ==================
class Orquestador:
    def __init__(self):
        self.modelos = []
        self.modelo_activo = None
        self._registrar_modelos()

    def _registrar_modelos(self):
        if DEEPSEEK_TOKEN:
            self.modelos.append(("DeepSeek", self._consultar_deepseek))
        if groq_clients:
            self.modelos.append(("Groq", self._consultar_groq))

    def consultar(self, mensajes, usar_busqueda=False):
        # Generar clave de caché
        consulta_str = json.dumps(mensajes) + str(usar_busqueda)
        # Primero caché en memoria
        cacheado = obtener_cache_memoria(consulta_str)
        if cacheado:
            logger.info("✅ Respuesta desde caché en memoria")
            return cacheado
        # Luego caché en DB
        cacheado_db = obtener_cache_db(consulta_str)
        if cacheado_db:
            logger.info("✅ Respuesta desde caché en DB")
            guardar_cache_memoria(consulta_str, cacheado_db)  # actualizar memoria
            return cacheado_db

        # Si no está en caché, consultar modelos
        for nombre, funcion in self.modelos:
            try:
                if "DeepSeek" in nombre and usar_busqueda:
                    respuesta = funcion(mensajes, search=True)
                else:
                    respuesta = funcion(mensajes)
                if respuesta:
                    self.modelo_activo = nombre
                    # Guardar en caché
                    guardar_cache_memoria(consulta_str, respuesta)
                    guardar_cache_db(consulta_str, respuesta)
                    return respuesta
            except Exception as e:
                logger.error(f"❌ Error en {nombre}: {e}")
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
        client = get_groq_client()
        if not client:
            raise Exception("No hay clientes Groq disponibles")
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=mensajes,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error en Groq: {e}")
            raise

orquestador = Orquestador()

# ================== CONSTANTES Y PROMPTS (igual que antes) ==================
# ... (mantener los mismos prompts y funciones auxiliares)
# Por brevedad no los repito, pero están en el código completo final.

# ================== FUNCIONES DE BASE DE DATOS CON POOL (opcional) ==================
# Mantenemos el pool para eficiencia, pero si falla, usamos conexiones directas.
db_pool = None

def init_db_pool():
    global db_pool
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)
        logger.info("✅ Pool de conexiones creado")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo crear pool, usando conexiones directas: {e}")
        db_pool = None

def get_connection():
    if db_pool:
        return db_pool.getconn()
    else:
        return psycopg2.connect(DATABASE_URL)

def return_connection(conn):
    if db_pool:
        db_pool.putconn(conn)
    else:
        conn.close()

# ================== INICIALIZACIÓN DE TABLAS ==================
def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Tablas existentes (conversaciones, conocimiento, perfiles, memoria_larga, notas, recordatorios, feedback)
        # ... (código de creación de tablas igual que antes)
        # Añadir tabla de caché
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_respuestas (
                hash TEXT PRIMARY KEY,
                respuesta TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON cache_respuestas (timestamp);")
        # Índices adicionales
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_chat_ts ON conversaciones (chat_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memoria_larga_chat_ts ON memoria_larga (chat_id, timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_chat ON conocimiento (chat_id);")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_contenido_trgm ON conocimiento USING gin (contenido gin_trgm_ops);")
        conn.commit()
        logger.info("✅ Base de datos inicializada con todas las tablas e índices")
    except Exception as e:
        logger.error(f"❌ Error inicializando DB: {e}")
        raise
    finally:
        return_connection(conn)

# ================== FUNCIONES AUXILIARES (detección de intención) ==================
def detectar_intencion(texto):
    """Detecta la intención del usuario en lenguaje natural"""
    texto_lower = texto.lower()
    
    # Email
    if re.search(r'(enviar|mandar|email|correo)\s+(a|para)\s+[\w\.-]+@[\w\.-]+', texto_lower):
        return "email"
    
    # Nota
    if re.search(r'(guardar|anota|nota|apunta)\s+', texto_lower):
        return "nota"
    
    # Recordatorio
    if re.search(r'(recordar|recordatorio|recuérdame|alarma)\s+', texto_lower):
        return "recordatorio"
    
    # Imagen
    if re.search(r'(crea|genera|dibuja|haz|quiero)\s+(una\s+)?(imagen|dibujo|foto|infografía|logo)', texto_lower):
        return "imagen"
    
    # Poesía
    if re.search(r'(poema|poesía|verso|dime un poema|escríbeme un poema)', texto_lower):
        return "poesia"
    
    # Manifiesto
    if re.search(r'(manifiesto|declaración|proclama)', texto_lower):
        return "manifiesto"
    
    # Hipótesis
    if re.search(r'(hipótesis|hipotesis|predice|proyección|qué pasará|escenario|futuro de)', texto_lower):
        return "hipotesis"
    
    # Análisis profundo
    if re.search(r'(análisis profundo|analiza a fondo|estudio detallado)', texto_lower):
        return "analisis"
    
    # Tasa/BCV
    if re.search(r'(tasa|dólar|dolar|bcv|cambio|precio del dólar)', texto_lower):
        return "tasa"
    
    # Noticias
    if re.search(r'(noticias|actualidad|qué pasa en venezuela)', texto_lower):
        return "noticias"
    
    # Voz (activar/desactivar)
    if re.search(r'(voz|audio|responder con voz)', texto_lower):
        return "voz"
    
    return "conversacion"

# ================== FUNCIONES DE ACCIONES (email, notas, recordatorios) ==================
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
        return f"❌ Error: {str(e)[:100]}"

def guardar_nota(chat_id, texto):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO notas (chat_id, texto) VALUES (%s, %s)", (chat_id, texto))
        conn.commit()
        return "✅ Nota guardada."
    finally:
        return_connection(conn)

def guardar_recordatorio(chat_id, texto, fecha_hora):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recordatorios (chat_id, texto, fecha_hora) VALUES (%s, %s, %s)",
            (chat_id, texto, fecha_hora)
        )
        conn.commit()
        return f"✅ Recordatorio guardado para {fecha_hora.strftime('%d/%m/%Y %H:%M')}."
    finally:
        return_connection(conn)

# ================== HANDLER PRINCIPAL CON LENGUAJE NATURAL ==================
@bot.message_handler(func=lambda m: True)
def handle_buttons(m):
    chat_id = m.chat.id
    texto = m.text if hasattr(m, 'text') else ""
    if not texto:
        return

    # Detectar intención
    intencion = detectar_intencion(texto)
    logger.info(f"🔍 Intención detectada: {intencion}")

    # ========== PERFIL Y ESTADO DE ÁNIMO ==========
    perfil = obtener_perfil(chat_id)
    if not perfil.get('nombre'):
        if "mi nombre es" in texto.lower():
            partes = texto.split("mi nombre es")
            if len(partes) > 1:
                nombre = partes[1].strip().split()[0]
                guardar_perfil(chat_id, nombre=nombre)
                bot.reply_to(m, f"✅ ¡Listo, {nombre}! Recordaré tu nombre.")
                return

    estado = detectar_estado_animo(texto)
    guardar_perfil(chat_id, estado_animo=estado)

    # ========== ACCIONES SEGÚN INTENCIÓN ==========
    if intencion == "email":
        # Extraer destino, asunto, cuerpo
        match = re.search(r'(enviar|mandar|email|correo)\s+(a|para)\s+([\w\.-]+@[\w\.-]+)', texto.lower())
        if not match:
            bot.reply_to(m, "📧 No entendí el destino. Ejemplo: 'envía correo a juan@ejemplo.com asunto hola cuerpo cómo estás'")
            return
        destino = match.group(3)
        resto = texto[match.end():].strip()
        # Intentar extraer asunto y cuerpo
        if "asunto" in resto.lower():
            partes = resto.split("asunto", 1)
            cuerpo_inicio = partes[1].strip()
            if "cuerpo" in cuerpo_inicio.lower():
                asunto, cuerpo = cuerpo_inicio.split("cuerpo", 1)
                asunto = asunto.strip()
                cuerpo = cuerpo.strip()
            else:
                asunto = "Mensaje desde Guaribe"
                cuerpo = cuerpo_inicio
        else:
            asunto = "Mensaje desde Guaribe"
            cuerpo = resto
        bot.reply_to(m, "📧 Enviando correo...")
        resultado = enviar_correo(destino, asunto, cuerpo)
        bot.reply_to(m, resultado)
        return

    if intencion == "nota":
        # Extraer texto de la nota
        texto_nota = re.sub(r'(guardar|anota|nota|apunta)\s+', '', texto, flags=re.IGNORECASE).strip()
        if not texto_nota:
            bot.reply_to(m, "📝 ¿Qué quieres guardar?")
            return
        resultado = guardar_nota(chat_id, texto_nota)
        bot.reply_to(m, resultado)
        return

    if intencion == "recordatorio":
        # Extraer fecha y texto
        # Patrón: "recordatorio texto en YYYY-MM-DD HH:MM"
        match = re.search(r'(recordar|recordatorio|recuérdame|alarma)\s+(.+?)\s+(en|para|el)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', texto, re.IGNORECASE)
        if not match:
            bot.reply_to(m, "⏰ No entendí la fecha. Ejemplo: 'recordatorio reunión en 2025-12-31 15:30'")
            return
        texto_rec = match.group(2).strip()
        fecha_str = match.group(4)
        try:
            fecha_hora = datetime.datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
            if fecha_hora < datetime.datetime.now():
                bot.reply_to(m, "⚠️ La fecha debe ser futura.")
                return
            resultado = guardar_recordatorio(chat_id, texto_rec, fecha_hora)
            bot.reply_to(m, resultado)
        except ValueError:
            bot.reply_to(m, "❌ Formato de fecha inválido. Usa: YYYY-MM-DD HH:MM")
        return

    if intencion == "imagen":
        # Extraer descripción
        prompt = re.sub(r'(crea|genera|dibuja|haz|quiero)\s+(una\s+)?(imagen|dibujo|foto|infografía|logo)\s+', '', texto, flags=re.IGNORECASE).strip()
        if not prompt:
            prompt = "paisaje venezolano"
        bot.reply_to(m, "🎨 Generando imagen...")
        img = generar_imagen(prompt, "general")
        if img:
            bot.send_photo(chat_id, img, caption=f"🎨 *{prompt}*\n\nSoy Guaribe...", parse_mode='Markdown')
        else:
            bot.reply_to(m, "❌ No pude generar la imagen.")
        return

    if intencion == "poesia":
        prompt_activo = PROMPT_POESIA
        mensajes = [{"role": "system", "content": prompt_activo}]
        historia = obtener_historia(chat_id)
        mensajes.extend(historia)
        resp = orquestador.consultar(mensajes)
        bot.reply_to(m, resp)
        return

    if intencion == "manifiesto":
        prompt_activo = PROMPT_MANIFIESTO
        mensajes = [{"role": "system", "content": prompt_activo}]
        historia = obtener_historia(chat_id)
        mensajes.extend(historia)
        resp = orquestador.consultar(mensajes)
        bot.reply_to(m, resp)
        return

    if intencion == "hipotesis":
        tema = re.sub(r'(hipótesis|hipotesis|predice|proyección|qué pasará|escenario|futuro de)\s+', '', texto, flags=re.IGNORECASE).strip()
        if not tema:
            tema = "el futuro de Venezuela"
        memorias = recuperar_memorias_relevantes(chat_id, tema)
        contexto_web = buscar_contexto(tema)
        bot.reply_to(m, "🔮 Generando hipótesis...")
        respuesta = generar_hipotesis(chat_id, tema, memorias, contexto_web)
        bot.reply_to(m, respuesta, parse_mode='Markdown')
        return

    if intencion == "analisis":
        tema = re.sub(r'(análisis profundo|analiza a fondo|estudio detallado)\s+', '', texto, flags=re.IGNORECASE).strip()
        if not tema:
            tema = texto
        bot.reply_to(m, f"📊 Analizando: {tema[:50]}...")
        contexto = buscar_contexto(tema)
        noticias = buscar_noticias()
        mensajes = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Tema: {tema}\nContexto histórico:\n{contexto}\nNoticias:\n{noticias}"}
        ]
        resp = orquestador.consultar(mensajes, usar_busqueda=False)
        bot.reply_to(m, resp, parse_mode='Markdown')
        return

    if intencion == "tasa":
        bot.reply_to(m, f"{obtener_tasa()}\n\nSoy Guaribe...", parse_mode='Markdown')
        return

    if intencion == "noticias":
        bot.reply_to(m, f"{buscar_noticias()}\n\nSoy Guaribe...")
        return

    if intencion == "voz":
        nueva_pref = not perfil.get('preferencia_audio', False)
        guardar_perfil(chat_id, preferencia_audio=nueva_pref)
        estado = "activada" if nueva_pref else "desactivada"
        bot.reply_to(m, f"🎙️ Preferencia de voz {estado}.")
        return

    # ========== CONVERSACIÓN NORMAL ==========
    try:
        # Compresión condicional de memoria
        comprimir_conversacion(chat_id)

        # Recuperar memorias relevantes
        memorias = recuperar_memorias_relevantes(chat_id, texto)
        contexto_memorias = ""
        if memorias:
            contexto_memorias = "\n[Recuerdos de Guaribe sobre ti]:\n" + "\n".join([f"- {m}" for m in memorias])
            logger.info(f"🧠 Inyectando {len(memorias)} memorias")

        # Búsqueda en documentos
        docs = buscar_conocimiento(chat_id, texto)
        contexto_docs = ""
        if docs:
            contexto_docs = "\n\n[Documentos]\n" + "\n".join([f"'{d['nombre_archivo']}': {d['contenido'][:500]}" for d in docs])

        # Contexto de perfil
        contexto_personalidad = ""
        if perfil.get('nombre'):
            contexto_personalidad += f"El usuario se llama {perfil['nombre']}. "
        if perfil.get('estilo') == 'poetico':
            contexto_personalidad += "Prefiere un tono poético y reflexivo. "
        elif perfil.get('estilo') == 'directo':
            contexto_personalidad += "Prefiere respuestas directas y sin rodeos. "
        if perfil.get('estado_animo'):
            contexto_personalidad += f"Su estado de ánimo actual es: {perfil['estado_animo']}. Adáptate a su estado."

        # Feedback negativo
        feedback_neg = obtener_feedback_relevante(chat_id)
        if feedback_neg:
            contexto_personalidad += "\n" + feedback_neg

        usar_busqueda = es_pregunta_sobre_persona(texto)

        if es_pregunta_simple(texto):
            mensajes = [{"role": "system", "content": PROMPT_SIMPLE + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
        else:
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT + contexto_docs + "\n\n" + contexto_personalidad + contexto_memorias}]
            historia = obtener_historia(chat_id)
            mensajes.extend(historia)

        resp = orquestador.consultar(mensajes, usar_busqueda=usar_busqueda)
        sent_msg = bot.reply_to(m, resp)

        # Botones de feedback
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

        # Audio si está activado
        if perfil.get('preferencia_audio', False):
            audio_data = generar_audio(resp)
            if audio_data:
                bot.send_voice(chat_id, audio_data, caption="🎙️ Respuesta en audio")

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        bot.reply_to(m, "Pana, hubo un error.")

# ================== MANEJO DE ARCHIVOS (sin disco) ==================
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
        # Procesar en memoria
        if ext == '.txt':
            texto = data.decode('utf-8', errors='ignore')
        elif ext == '.pdf':
            texto = ""
            with BytesIO(data) as f:
                for p in PyPDF2.PdfReader(f).pages:
                    texto += p.extract_text()
        elif ext == '.docx':
            with BytesIO(data) as f:
                doc = docx.Document(f)
                texto = "\n".join([p.text for p in doc.paragraphs])
        else:
            texto = ""
        if texto:
            guardar_conocimiento(chat_id, name, texto)
            bot.reply_to(m, f"✅ Aprendí de '{name}'.")
        else:
            bot.reply_to(m, f"No pude leer '{name}'.")
    except Exception as e:
        bot.reply_to(m, f"Error: {str(e)[:100]}")

# ================== MANEJO DE VOZ ==================
@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    try:
        logger.info("🎤 Recibido mensaje de voz")
        file_info = bot.get_file(m.voice.file_id)
        data = bot.download_file(file_info.file_path)
        bot.reply_to(m, "🎧 Transcribiendo...")
        # Usar Groq Whisper
        client = get_groq_client()
        if not client:
            bot.reply_to(m, "❌ No hay clientes Groq disponibles para transcripción.")
            return
        temp_path = "/tmp/audio.ogg"
        with open(temp_path, "wb") as f:
            f.write(data)
        with open(temp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(temp_path, f.read()),
                model="whisper-large-v3",
                response_format="text",
                language="es"
            )
        os.remove(temp_path)
        texto = transcription
        # Simular que el usuario escribió ese texto
        m.text = texto
        handle_buttons(m)
    except Exception as e:
        logger.error(f"❌ Error en handle_voice: {e}")
        bot.reply_to(m, "❌ Ocurrió un error al procesar el audio.")

# ================== FEEDBACK CALLBACK ==================
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
    return jsonify({"status": "ok", "bot": "Guaribe 9.0 - Unificado y Escalable"}), 200

@app.route('/check_reminders', methods=['GET'])
def check_reminders():
    # Llamar a función que revisa recordatorios (implementar con pool)
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        ahora = datetime.datetime.now()
        cursor.execute(
            "SELECT id, chat_id, texto, fecha_hora FROM recordatorios WHERE enviado = FALSE AND fecha_hora <= %s",
            (ahora,)
        )
        pendientes = cursor.fetchall()
        for r in pendientes:
            try:
                bot.send_message(r['chat_id'], f"⏰ *Recordatorio:* {r['texto']}\n\n(Programado para {r['fecha_hora'].strftime('%d/%m/%Y %H:%M')})", parse_mode='Markdown')
                cursor.execute("UPDATE recordatorios SET enviado = TRUE WHERE id = %s", (r['id'],))
                conn.commit()
            except Exception as e:
                logger.error(f"❌ Error enviando recordatorio {r['id']}: {e}")
        return jsonify({"status": "ok", "result": f"Revisados {len(pendientes)} recordatorios."})
    finally:
        return_connection(conn)

# ================== MAIN ==================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe 9.0 (Unificado, escalable, lenguaje natural)...")
    init_db_pool()
    init_db()
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado")
    logger.info(f"🧠 Cerebros disponibles: DeepSeek, {len(groq_clients)} clientes Groq")
    logger.info("⚡ Optimizaciones: caché en memoria y DB, rotación de claves, lenguaje natural, sin disco")
    app.run(host='0.0.0.0', port=port)
