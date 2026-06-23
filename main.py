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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== IMPORTS CON FALLBACK ====================
logger.info("🔄 Cargando módulos core...")

try:
    from core.memory import guardar_mensaje, buscar_contexto, buscar_resumenes, get_connection
    MEMORY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ core.memory no disponible: {e}")
    MEMORY_AVAILABLE = False

try:
    from core.classifier import clasificador
    CLASSIFIER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ core.classifier no disponible: {e}")
    CLASSIFIER_AVAILABLE = False

try:
    from core.orchestrator import orquestar
    ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ core.orchestrator no disponible: {e}")
    ORCHESTRATOR_AVAILABLE = False

try:
    from core.strategist import estratega
    STRATEGIST_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ core.strategist no disponible: {e}")
    STRATEGIST_AVAILABLE = False

try:
    from utils.web import obtener_tasa, buscar_noticias, buscar_en_web
    WEB_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ utils.web no disponible: {e}")
    WEB_AVAILABLE = False

try:
    from utils.media import generar_imagen, generar_audio, transcribir_audio
    MEDIA_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ utils.media no disponible: {e}")
    MEDIA_AVAILABLE = False

logger.info("✅ Imports básicos cargados")

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado en variables de entorno.")

logger.info("✅ Token de Telegram verificado")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
modo_analisis = {}

logger.info("✅ Bot de Telegram inicializado")

# ==================== FUNCIONES AUXILIARES ====================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

def configurar_webhook():
    """Configura el webhook UNA SOLA VEZ."""
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
        "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n🎙️ Voz\n\n"
        "🎨 Puedes pedirme imágenes, infografías o logos.\n"
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
    status_msg += f"   {'✅' if MEMORY_AVAILABLE else '❌'} Memoria\n"
    status_msg += f"   {'✅' if CLASSIFIER_AVAILABLE else '❌'} Clasificador\n"
    status_msg += f"   {'✅' if ORCHESTRATOR_AVAILABLE else '❌'} Orquestador\n"
    status_msg += f"   {'✅' if STRATEGIST_AVAILABLE else '❌'} Estratega\n"
    status_msg += f"   {'✅' if WEB_AVAILABLE else '❌'} Web\n"
    status_msg += f"   {'✅' if MEDIA_AVAILABLE else '❌'} Media\n"
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
        # --- SALUDOS ---
        if texto.lower() in ["hola", "buenas", "hey", "saludos", "epa"]:
            bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
            return

        # --- ACCIONES RÁPIDAS ---
        if WEB_AVAILABLE:
            if "tasa" in texto.lower() or "bcv" in texto.lower() or "dólar" in texto.lower():
                bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
                return
            if "noticias" in texto.lower() or "qué pasó" in texto.lower():
                bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
                return

        if MEDIA_AVAILABLE:
            if "genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower()):
                bot.send_message(chat_id, "🎨 Generando imagen...")
                img = generar_imagen(texto)
                if img:
                    bot.send_photo(chat_id, img, caption=f"🎨 *{texto[:50]}...*", parse_mode='Markdown')
                else:
                    bot.send_message(chat_id, "❌ No pude generar la imagen.")
                return

        # --- MODO ANÁLISIS ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            tema = texto
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
            bot.send_message(chat_id, obtener_tasa() if WEB_AVAILABLE else "⚠️ No disponible.")
            return
        if texto == "📰 Noticias":
            bot.send_message(chat_id, buscar_noticias() if WEB_AVAILABLE else "⚠️ No disponible.")
            return
        if texto == "🔮 Analizar":
            modo_analisis[chat_id] = True
            bot.send_message(chat_id, "🔮 Envíame el tema a analizar.")
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Pronto podré responderte con audio.")
            return

        # --- RESPUESTA CON ORQUESTADOR ---
        categoria = "simple"
        if CLASSIFIER_AVAILABLE:
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

        # --- GUARDAR EN MEMORIA ---
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
logger.info("📦 Creando app Flask...")
app = Flask(__name__)

logger.info("📦 Registrando rutas Flask...")

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

logger.info("✅ Rutas Flask registradas")

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe (modo desarrollo)...")
    configurar_webhook()
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"📡 Escuchando en puerto {port}...")
    app.run(host='0.0.0.0', port=port)
else:
    # ==== PRODUCCIÓN: NO CONFIGURAR WEBHOOK AUTOMÁTICAMENTE ====
    logger.info("🚀 Iniciando Guaribe (modo producción)...")
    logger.info("✅ Servidor listo para recibir peticiones")
    # El webhook se configurará manualmente desde /set_webhook
   
