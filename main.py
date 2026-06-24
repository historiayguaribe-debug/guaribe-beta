from gevent import monkey
monkey.patch_all()

import os
os.environ["GUNICORN_CMD_ARGS"] = "--workers 1 --timeout 120"
os.environ["WEB_CONCURRENCY"] = "1"

import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== CONFIGURACIÓN DE LOGGING ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== IMPORTS CON FALLBACK Y LAZY LOADING ====================
# Memoria (se carga bajo demanda)
MEMORY_AVAILABLE = False
guardar_mensaje = None
buscar_contexto = None
buscar_resumenes = None
get_connection = None

def cargar_memoria():
    global MEMORY_AVAILABLE, guardar_mensaje, buscar_contexto, buscar_resumenes, get_connection
    if not MEMORY_AVAILABLE:
        try:
            from core.memory import guardar_mensaje as _gm, buscar_contexto as _bc, buscar_resumenes as _br, get_connection as _gc
            guardar_mensaje = _gm
            buscar_contexto = _bc
            buscar_resumenes = _br
            get_connection = _gc
            MEMORY_AVAILABLE = True
            logger.info("✅ Memoria cargada bajo demanda")
        except ImportError as e:
            logger.warning(f"⚠️ Memoria no disponible: {e}")

# Clasificador (se carga bajo demanda)
CLASSIFIER_AVAILABLE = False
clasificador = None

def cargar_clasificador():
    global CLASSIFIER_AVAILABLE, clasificador
    if not CLASSIFIER_AVAILABLE:
        try:
            from core.classifier import clasificador as _clf
            clasificador = _clf
            CLASSIFIER_AVAILABLE = True
            logger.info("✅ Clasificador cargado bajo demanda")
        except ImportError as e:
            logger.warning(f"⚠️ Clasificador no disponible: {e}")

# Orquestador
try:
    from core.orchestrator import orquestar
    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    ORCHESTRATOR_AVAILABLE = False
    logger.warning("⚠️ Orquestador no disponible")

# Estratega
try:
    from core.strategist import estratega
    STRATEGIST_AVAILABLE = True
except ImportError:
    STRATEGIST_AVAILABLE = False
    logger.warning("⚠️ Estratega no disponible")

# Web (se carga bajo demanda)
WEB_AVAILABLE = False
obtener_tasa = None
buscar_noticias = None
buscar_en_web = None

def cargar_web():
    global WEB_AVAILABLE, obtener_tasa, buscar_noticias, buscar_en_web
    if not WEB_AVAILABLE:
        try:
            from utils.web import obtener_tasa as _ot, buscar_noticias as _bn, buscar_en_web as _bw
            obtener_tasa = _ot
            buscar_noticias = _bn
            buscar_en_web = _bw
            WEB_AVAILABLE = True
            logger.info("✅ Módulo web cargado bajo demanda")
        except ImportError as e:
            logger.warning(f"⚠️ utils.web no disponible: {e}")

# Media (se carga bajo demanda)
MEDIA_AVAILABLE = False
generar_imagen = None
generar_audio = None
transcribir_audio = None

def cargar_media():
    global MEDIA_AVAILABLE, generar_imagen, generar_audio, transcribir_audio
    if not MEDIA_AVAILABLE:
        try:
            from utils.media import generar_imagen as _gi, generar_audio as _ga, transcribir_audio as _ta
            generar_imagen = _gi
            generar_audio = _ga
            transcribir_audio = _ta
            MEDIA_AVAILABLE = True
            logger.info("✅ Módulo media cargado bajo demanda")
        except ImportError as e:
            logger.warning(f"⚠️ utils.media no disponible: {e}")

# ==================== CONFIGURACIÓN DEL BOT ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado en variables de entorno.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
modo_analisis = {}

# ==================== MENÚ PRINCIPAL ====================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

# ==================== FUNCIONES AUXILIARES ====================
def configurar_webhook():
    if os.environ.get("WEBHOOK_CONFIGURED") == "true":
        logger.info("⏭️ Webhook ya configurado, saltando...")
        return True
    url = "https://guaribe-beta.onrender.com/webhook"
    for i in range(3):
        try:
            bot.remove_webhook()
            time.sleep(0.5)
            bot.set_webhook(url=url)
            os.environ["WEBHOOK_CONFIGURED"] = "true"
            logger.info(f"✅ Webhook configurado en {url}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Intento {i+1} falló: {e}")
            time.sleep(1)
    logger.error("❌ No se pudo configurar el webhook después de 3 intentos.")
    return False

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(m.chat.id,
        "¡Epale! Soy **Guaribe**, tu asistente llanero.\n\n"
        "Usa los botones:\n"
        "💰 Tasa BCV\n🎙️ Voz\n\n"
        "🎨 Puedes pedirme imágenes con 'genera una imagen de...'.\n"
        "📰 Para noticias escribe 'noticias' o 'qué pasó hoy'.\n"
        "🔮 Para análisis escribe 'analiza' o 'analizar'.\n"
        "📸 Envía fotos para que las analice.\n"
        "🎙️ Envía mensajes de voz.\n"
        "👍/👎 Califica mis respuestas.\n\n"
        "¡Seguimos razonando! 🇻🇪🤠🏛️",
        parse_mode='Markdown', reply_markup=menu_principal()
    )

@bot.message_handler(commands=['status'])
def cmd_status(m):
    chat_id = m.chat.id
    if str(chat_id) != ADMIN_CHAT_ID:
        bot.send_message(chat_id, "⛔ Este comando es solo para administradores.")
        return

    status_msg = "📁 *ESTADO DE GUARIBE BETA*\n\n"
    status_msg += "✅ *Módulos disponibles:*\n"
    status_msg += f"   {'✅' if MEMORY_AVAILABLE else '⏳'} Memoria\n"
    status_msg += f"   {'✅' if CLASSIFIER_AVAILABLE else '⏳'} Clasificador\n"
    status_msg += f"   {'✅' if ORCHESTRATOR_AVAILABLE else '❌'} Orquestador\n"
    status_msg += f"   {'✅' if STRATEGIST_AVAILABLE else '❌'} Estratega\n"
    status_msg += f"   {'✅' if WEB_AVAILABLE else '⏳'} Web\n"
    status_msg += f"   {'✅' if MEDIA_AVAILABLE else '⏳'} Media\n"
    status_msg += f"\n🌐 Webhook: {'✅' if os.environ.get('WEBHOOK_CONFIGURED') == 'true' else '❌'}\n"
    bot.send_message(chat_id, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "⛔ No autorizado.")
        return
    if not MEMORY_AVAILABLE:
        bot.send_message(m.chat.id, "⚠️ Memoria no disponible.")
        return
    bot.send_message(m.chat.id, "🧹 Limpiando base de datos...")
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mensajes;")
            cur.execute("DELETE FROM resumenes;")
            conn.commit()
        bot.send_message(m.chat.id, "✅ Base de datos limpiada.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Error: {e}")

# ==================== HANDLER PRINCIPAL ====================
@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    if not texto or len(texto) < 2:
        return

    logger.info(f"📩 Mensaje de {chat_id}: {texto[:50]}...")

    try:
        # --- SALUDOS MUY BÁSICOS (sin IA) ---
        if texto.lower() in ["hola", "epa", "hey"]:
            bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
            return

        # --- CARGA DE MÓDULOS BAJO DEMANDA ---
        # Cargar web solo si es necesario (tasa, noticias)
        if not WEB_AVAILABLE and ("tasa" in texto.lower() or "bcv" in texto.lower() or 
                                  "dólar" in texto.lower() or "noticias" in texto.lower() or 
                                  "qué pasó" in texto.lower() or "actualidad" in texto.lower()):
            cargar_web()

        # Cargar media solo si es necesario (imagen, audio)
        if not MEDIA_AVAILABLE and ("genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower())):
            cargar_media()

        # Cargar clasificador solo si es necesario (cualquier cosa que no sea saludo)
        if not CLASSIFIER_AVAILABLE and not texto.lower() in ["hola", "epa", "hey"]:
            cargar_clasificador()

        # --- ACCIONES RÁPIDAS ---
        # Tasa BCV
        if WEB_AVAILABLE and ("tasa" in texto.lower() or "bcv" in texto.lower() or "dólar" in texto.lower()):
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return

        # Noticias (por lenguaje natural)
        if WEB_AVAILABLE and ("noticias" in texto.lower() or "qué pasó" in texto.lower() or "actualidad" in texto.lower()):
            bot.send_message(chat_id, "📰 Buscando noticias...")
            noticias = buscar_noticias()
            bot.send_message(chat_id, noticias, parse_mode='Markdown')
            return

        # Imágenes
        if MEDIA_AVAILABLE and ("genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower())):
            bot.send_message(chat_id, "🎨 Generando imagen... (puede tomar unos segundos)")
            img = generar_imagen(texto)
            if img:
                bot.send_photo(chat_id, img, caption=f"🎨 *{texto[:50]}...*", parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "❌ No pude generar la imagen. Intenta con otro prompt.")
            return

        # Modo análisis (por lenguaje natural)
        if "analizar" in texto.lower() or "analiza" in texto.lower():
            tema = texto.replace("analizar", "").replace("analiza", "").strip()
            if not tema:
                bot.send_message(chat_id, "🔮 Envíame el tema a analizar.")
                return
            bot.send_message(chat_id, f"📊 Analizando: {tema[:50]}...")
            if WEB_AVAILABLE:
                contexto_web = buscar_en_web(tema, 3)
                contexto_texto = "\n".join(contexto_web) if contexto_web else ""
            else:
                contexto_texto = ""
            if ORCHESTRATOR_AVAILABLE:
                respuesta = orquestar(tema, "compleja", [contexto_texto] if contexto_texto else [], {})
                bot.send_message(chat_id, respuesta, parse_mode='Markdown')
            else:
                bot.send_message(chat_id, f"🔮 Análisis en construcción. Tema: '{tema}'")
            return

        # --- BOTONES ---
        if texto == "💰 Tasa BCV":
            if not WEB_AVAILABLE:
                cargar_web()
            bot.send_message(chat_id, obtener_tasa() if WEB_AVAILABLE else "⚠️ No disponible.", parse_mode='Markdown')
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Función de voz activa. Envía un mensaje de voz o recibe respuestas en audio.")
            return

        # --- CARGA DE MEMORIA (si es necesario) ---
        if not MEMORY_AVAILABLE and ORCHESTRATOR_AVAILABLE:
            cargar_memoria()

        # --- RESPUESTA CON ORQUESTADOR (para todo lo demás) ---
        categoria = "simple"
        if CLASSIFIER_AVAILABLE and clasificador is not None:
            categoria = clasificador.clasificar(texto)

        contexto = []
        if MEMORY_AVAILABLE:
            try:
                conn = get_connection()
                contexto = buscar_contexto(chat_id, texto, conn) + buscar_resumenes(chat_id, texto, conn)
                conn.close()
            except Exception as e:
                logger.warning(f"Error en memoria: {e}")

        if ORCHESTRATOR_AVAILABLE:
            respuesta = orquestar(texto, categoria, contexto, {})
        else:
            respuesta = f"🏓 Pong! Recibí: {texto}\n\n(Modo orquestador no disponible)"

        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')

        # --- FEEDBACK ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

        # --- GUARDAR EN MEMORIA (async) ---
        if MEMORY_AVAILABLE:
            def guardar():
                try:
                    conn = get_connection()
                    guardar_mensaje(chat_id, "usuario", texto, conn)
                    guardar_mensaje(chat_id, "asistente", respuesta, conn)
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error guardando: {e}")
            threading.Thread(target=guardar).start()

        # --- ESTRATEGA ---
        if STRATEGIST_AVAILABLE:
            try:
                estratega.aprender(chat_id, texto, respuesta)
                sugerencia = estratega.sugerir(chat_id, texto)
                if sugerencia:
                    time.sleep(1)
                    bot.send_message(chat_id, f"💡 {sugerencia}")
            except Exception as e:
                logger.warning(f"Error en estratega: {e}")

    except Exception as e:
        logger.error(f"Error en handle_message: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

# ==================== FEEDBACK ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('fb_'))
def handle_feedback(call):
    try:
        _, msg_id, puntuacion = call.data.split('_')
        bot.answer_callback_query(call.id, "¡Gracias por tu feedback! 👍")
        bot.edit_message_reply_markup(call.message.chat.id, int(msg_id), reply_markup=None)
    except Exception as e:
        logger.error(f"Error en feedback: {e}")

# ==================== FLASK ====================
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return 'ok', 200

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.0"}), 200

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    if configurar_webhook():
        return jsonify({"status": "ok", "message": "Webhook configurado"}), 200
    return jsonify({"status": "error", "message": "Falló configuración"}), 500

# ==================== EJECUCIÓN ====================
def precargar_memoria():
    """Precarga la memoria en segundo plano para que esté lista cuando se necesite."""
    logger.info("🔄 Precargando memoria en segundo plano...")
    cargar_memoria()
    logger.info("✅ Memoria precargada")

if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe (modo desarrollo)...")
    configurar_webhook()
    # Precargar memoria en segundo plano
    threading.Thread(target=precargar_memoria).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
else:
    logger.info("🚀 Iniciando Guaribe (modo producción)...")
    # Precargar memoria en segundo plano (no bloquea el arranque)
    threading.Thread(target=precargar_memoria).start()
    logger.info("✅ Servidor listo para recibir peticiones")
