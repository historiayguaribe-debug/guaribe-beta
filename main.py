from gevent import monkey
monkey.patch_all()

import os
# === FUERZA 1 WORKER PARA AHORRAR MEMORIA ===
os.environ["GUNICORN_CMD_ARGS"] = "--workers 1 --timeout 120"
os.environ["WEB_CONCURRENCY"] = "1"

import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== IMPORTS CON FALLBACK ====================
# Intentamos importar los módulos de core y utils. Si fallan, los desactivamos.

MEMORY_AVAILABLE = False
CLASSIFIER_AVAILABLE = False
ORCHESTRATOR_AVAILABLE = False
STRATEGIST_AVAILABLE = False
WEB_AVAILABLE = False
MEDIA_AVAILABLE = False

try:
    from core.memory import guardar_mensaje, buscar_contexto, buscar_resumenes, get_connection
    MEMORY_AVAILABLE = True
    logging.info("✅ core.memory cargado")
except ImportError as e:
    logging.warning(f"⚠️ core.memory no disponible: {e}")

try:
    from core.classifier import clasificador
    CLASSIFIER_AVAILABLE = True
    logging.info("✅ core.classifier cargado")
except ImportError as e:
    logging.warning(f"⚠️ core.classifier no disponible: {e}")

try:
    from core.orchestrator import orquestar
    ORCHESTRATOR_AVAILABLE = True
    logging.info("✅ core.orchestrator cargado")
except ImportError as e:
    logging.warning(f"⚠️ core.orchestrator no disponible: {e}")

try:
    from core.strategist import estratega
    STRATEGIST_AVAILABLE = True
    logging.info("✅ core.strategist cargado")
except ImportError as e:
    logging.warning(f"⚠️ core.strategist no disponible: {e}")

try:
    from utils.web import obtener_tasa, buscar_noticias, buscar_en_web
    WEB_AVAILABLE = True
    logging.info("✅ utils.web cargado")
except ImportError as e:
    logging.warning(f"⚠️ utils.web no disponible: {e}")

try:
    from utils.media import generar_imagen, generar_audio, transcribir_audio
    MEDIA_AVAILABLE = True
    logging.info("✅ utils.media cargado")
except ImportError as e:
    logging.warning(f"⚠️ utils.media no disponible: {e}")

# ==================== CONFIGURACIÓN ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado en variables de entorno.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
modo_analisis = {}

# ==================== FUNCIONES AUXILIARES ====================
def menu_principal():
    """Crea el teclado personalizado con los botones principales."""
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

def configurar_webhook():
    """Configura el webhook UNA SOLA VEZ usando variable de entorno."""
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

# ==================== HANDLERS DE TELEGRAM ====================
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
        # --- 1. SALUDOS (sin IA) ---
        if texto.lower() in ["hola", "buenas", "hey", "saludos", "epa"]:
            bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
            return

        # --- 2. ACCIONES RÁPIDAS (tasa, noticias, imagen) ---
        # Estas funciones son ligeras y no requieren cargar el modelo pesado.
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

        # --- 3. MODO ANÁLISIS (activado por el botón) ---
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
                # Nota: orquestar podría cargar el modelo de memoria si lo necesita, pero solo aquí.
                respuesta = orquestar(tema, "compleja", [contexto_texto] if contexto_texto else [], {})
                bot.send_message(chat_id, respuesta, parse_mode='Markdown')
            else:
                bot.send_message(chat_id, f"🔮 Análisis en construcción. Tema: '{tema}'")
            return

        # --- 4. BOTONES (son capturados aquí después de las acciones rápidas) ---
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

        # --- 5. RESPUESTA CON ORQUESTADOR (para mensajes complejos) ---
        # Esta es la parte que podría activar la memoria, el clasificador, etc.
        categoria = "simple"
        if CLASSIFIER_AVAILABLE:
            categoria = clasificador.clasificar(texto)

        contexto = []
        if MEMORY_AVAILABLE:
            try:
                # NOTA: get_connection() y buscar_contexto() pueden cargar el modelo de embeddings
                # la primera vez que se llamen, pero eso será bajo demanda.
                conn = get_connection()
                contexto = buscar_contexto(chat_id, texto, conn) + buscar_resumenes(chat_id, texto, conn)
                conn.close()
            except Exception as e:
                logger.warning(f"Error en memoria: {e}")

        if ORCHESTRATOR_AVAILABLE:
            respuesta = orquestar(texto, categoria, contexto, {})
        else:
            # FALLBACK: respuesta tipo "Pong" si no hay orquestador
            respuesta = f"🏓 Pong! Recibí: {texto}\n\n(Modo orquestador no disponible)"

        # --- ENVIAR RESPUESTA ---
        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')

        # --- FEEDBACK (botones de calificación) ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

        # --- GUARDAR EN MEMORIA (en un hilo para no bloquear) ---
        if MEMORY_AVAILABLE:
            def guardar():
                try:
                    # Aquí es donde se cargará el modelo de embeddings si no se ha cargado antes
                    conn = get_connection()
                    guardar_mensaje(chat_id, "usuario", texto, conn)
                    guardar_mensaje(chat_id, "asistente", respuesta, conn)
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error guardando en memoria: {e}")
            threading.Thread(target=guardar).start()

        # --- ESTRATEGA (aprender patrones, en segundo plano) ---
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

# ==================== FEEDBACK (callbacks de los botones) ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('fb_'))
def handle_feedback(call):
    try:
        _, msg_id, puntuacion = call.data.split('_')
        # Aquí podríamos guardar el feedback en la base de datos para mejorar el clasificador
        bot.answer_callback_query(call.id, "¡Gracias por tu feedback! 👍")
        bot.edit_message_reply_markup(call.message.chat.id, int(msg_id), reply_markup=None)
    except Exception as e:
        logger.error(f"Error en feedback: {e}")

# ==================== APLICACIÓN FLASK ====================
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
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe (modo desarrollo)...")
    configurar_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
else:
    # ==== PRODUCCIÓN ====
    # El webhook ya se configurará en la primera solicitud o al iniciar.
    # No bloqueamos el arranque con configurar_webhook() aquí.
    logger.info("🚀 Iniciando Guaribe (modo producción)...")
    # Intentamos configurar el webhook en segundo plano para no bloquear el arranque
    threading.Thread(target=configurar_webhook).start()
    logger.info("✅ Servidor listo para recibir peticiones")
