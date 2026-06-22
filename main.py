from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== IMPORTS CON FALLBACK ====================
try:
    from core.memory import guardar_mensaje, buscar_contexto, buscar_resumenes, guardar_resumen, get_connection
    MEMORY_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo core.memory no disponible: {e}")
    MEMORY_AVAILABLE = False

try:
    from core.classifier import clasificador
    CLASSIFIER_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo core.classifier no disponible: {e}")
    CLASSIFIER_AVAILABLE = False

try:
    from core.orchestrator import orquestar
    ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo core.orchestrator no disponible: {e}")
    ORCHESTRATOR_AVAILABLE = False

try:
    from core.strategist import estratega
    STRATEGIST_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo core.strategist no disponible: {e}")
    STRATEGIST_AVAILABLE = False

try:
    from utils.web import obtener_tasa, buscar_noticias, buscar_en_web
    WEB_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo utils.web no disponible: {e}")
    WEB_AVAILABLE = False

try:
    from utils.media import generar_imagen, generar_audio, transcribir_audio
    MEDIA_AVAILABLE = True
except ImportError as e:
    logging.warning(f"⚠️ Módulo utils.media no disponible: {e}")
    MEDIA_AVAILABLE = False

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
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

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
    status_msg += f"   {'✅' if MEMORY_AVAILABLE else '❌'} Memoria (core.memory)\n"
    status_msg += f"   {'✅' if CLASSIFIER_AVAILABLE else '❌'} Clasificador (core.classifier)\n"
    status_msg += f"   {'✅' if ORCHESTRATOR_AVAILABLE else '❌'} Orquestador (core.orchestrator)\n"
    status_msg += f"   {'✅' if STRATEGIST_AVAILABLE else '❌'} Estratega (core.strategist)\n"
    status_msg += f"   {'✅' if WEB_AVAILABLE else '❌'} Web (utils.web)\n"
    status_msg += f"   {'✅' if MEDIA_AVAILABLE else '❌'} Media (utils.media)\n"

    # Base de datos
    if MEMORY_AVAILABLE:
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM mensajes;")
                count_msg = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM resumenes;")
                count_res = cur.fetchone()[0]
            conn.close()
            status_msg += f"\n💾 *Base de datos:* ✅ Conectada\n"
            status_msg += f"   - Mensajes: {count_msg}\n"
            status_msg += f"   - Resúmenes: {count_res}\n"
        except Exception as e:
            status_msg += f"\n💾 *Base de datos:* ❌ Error: {str(e)[:50]}\n"
    else:
        status_msg += "\n💾 *Base de datos:* ⚠️ No disponible\n"

    # APIs
    deepseek_token = os.environ.get("DEEPSEEK_TOKEN")
    groq_key = os.environ.get("GROQ_API_KEY")
    status_msg += "\n🔑 *APIs:*\n"
    status_msg += f"   {'✅' if deepseek_token else '❌'} DeepSeek (token: ...{deepseek_token[-4:] if deepseek_token else 'no'})\n"
    status_msg += f"   {'✅' if groq_key else '❌'} Groq (clave: ...{groq_key[-4:] if groq_key else 'no'})\n"

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

        # --- 3. MODO ANÁLISIS ---
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
                respuesta = orquestar(
                    consulta=tema,
                    categoria="compleja",
                    contexto=[contexto_texto] if contexto_texto else [],
                    perfil={}
                )
                bot.send_message(chat_id, respuesta, parse_mode='Markdown')
            else:
                bot.send_message(chat_id, f"🔮 Mi análisis preliminar sobre '{tema}': \n\n(Modo análisis en construcción, pronto tendré respuestas más profundas)")
            return

        # --- 4. BOTONES ---
        if texto == "💰 Tasa BCV":
            if WEB_AVAILABLE:
                bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "⚠️ Función de tasa no disponible.")
            return
        if texto == "📰 Noticias":
            if WEB_AVAILABLE:
                bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "⚠️ Función de noticias no disponible.")
            return
        if texto == "🔮 Analizar":
            modo_analisis[chat_id] = True
            bot.send_message(chat_id, "🔮 Envíame el tema a analizar.")
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Pronto podré responderte con audio. Por ahora, solo texto.")
            return

        # --- 5. CLASIFICAR (si está disponible) ---
        categoria = "simple"
        if CLASSIFIER_AVAILABLE:
            categoria = clasificador.clasificar(texto)
            logger.info(f"Clasificado como: {categoria}")

        # --- 6. BUSCAR CONTEXTO (si memoria disponible) ---
        contexto = []
        if MEMORY_AVAILABLE:
            try:
                conn = get_connection()
                historial = buscar_contexto(chat_id, texto, conn)
                resumenes = buscar_resumenes(chat_id, texto, conn)
                conn.close()
                contexto = historial + resumenes
            except Exception as e:
                logger.warning(f"Error buscando contexto: {e}")

        # --- 7. ORQUESTAR (si disponible) ---
        if ORCHESTRATOR_AVAILABLE:
            respuesta = orquestar(texto, categoria, contexto, {})
        else:
            # Respuesta genérica si no hay orquestador
            respuesta = f"Pana, recibí tu mensaje: '{texto}'. Estoy aprendiendo, pero por ahora puedo ayudarte con tasa, noticias e imágenes. Usa los botones o escribe 'tasa', 'noticias' o 'genera una imagen de...'"

        # --- 8. ENVIAR RESPUESTA ---
        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')

        # --- 9. FEEDBACK ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

        # --- 10. GUARDAR EN MEMORIA (async) ---
        if MEMORY_AVAILABLE:
            def guardar():
                try:
                    conn = get_connection()
                    guardar_mensaje(chat_id, "usuario", texto, conn)
                    guardar_mensaje(chat_id, "asistente", respuesta, conn)
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error guardando mensaje: {e}")
            threading.Thread(target=guardar).start()

        # --- 11. APRENDER PATRONES ---
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
        msg_id = int(msg_id)
        puntuacion = int(puntuacion)
        # Aquí podrías guardar el feedback en la base de datos
        bot.answer_callback_query(call.id, "¡Gracias por tu feedback! 👍")
        bot.edit_message_reply_markup(call.message.chat.id, msg_id, reply_markup=None)
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
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.0 - Completo"}), 200

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

# ==================== EJECUCIÓN ====================
def configurar_webhook():
    """Configura el webhook con reintentos."""
    url = f"https://guaribe-beta.onrender.com/webhook"
    for i in range(3):
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=url)
            logger.info(f"✅ Webhook configurado en {url}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Intento {i+1} falló: {e}")
            time.sleep(2 ** i)
    logger.error("❌ No se pudo configurar el webhook después de 3 intentos.")
    return False

if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe Beta 2.0 (modo desarrollo)...")
    port = int(os.environ.get("PORT", 10000))
    configurar_webhook()
    app.run(host='0.0.0.0', port=port)
else:
    # En producción con gunicorn, configuramos webhook al inicio
    logger.info("🚀 Iniciando Guaribe Beta 2.0 (modo producción)...")
    configurar_webhook()
    logger.info("✅ Servidor listo para recibir peticiones")
