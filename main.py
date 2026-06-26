from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from utils.logger import logger

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== MENÚ ====================
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
        "🎨 Puedes pedirme imágenes con 'genera una imagen de...'.\n"
        "📸 Envía fotos para que las analice.\n"
        "🎙️ Envía mensajes de voz.\n"
        "👍/👎 Califica mis respuestas.\n\n"
        "¡Seguimos razonando! 🇻🇪🤠🏛️",
        parse_mode='Markdown', reply_markup=menu_principal()
    )

@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["hola", "epa", "hey"])
def handle_saludo(m):
    bot.send_message(m.chat.id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
    logger.info(f"✅ Saludo respondido a {m.chat.id}")

@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    if not texto or len(texto) < 2:
        return

    logger.info(f"📩 Mensaje de {chat_id}: {texto[:50]}...")

    try:
        from core.orchestrator import orquestar
        from core.classifier import clasificador
        logger.info("✅ Orquestador y clasificador importados")

        # Clasificar
        categoria = clasificador.clasificar(texto)
        logger.info(f"📋 Categoría: {categoria}")

        # Obtener respuesta
        respuesta = orquestar(texto, categoria, [], {})
        logger.info(f"✅ Respuesta: {respuesta[:50]}...")

        # Enviar con Markdown, y si falla, sin formato
        try:
            sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"⚠️ Error con Markdown, enviando sin formato: {e}")
            sent_msg = bot.send_message(chat_id, respuesta)

        # Feedback
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

        logger.info(f"✅ Respuesta enviada a {chat_id}")

    except Exception as e:
        logger.error(f"❌ Error en handle_message: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

@bot.callback_query_handler(func=lambda call: call.data.startswith('fb_'))
def handle_feedback(call):
    try:
        _, msg_id, puntuacion = call.data.split('_')
        bot.answer_callback_query(call.id, "¡Gracias por tu feedback! 👍")
        bot.edit_message_reply_markup(call.message.chat.id, int(msg_id), reply_markup=None)
    except Exception as e:
        logger.error(f"❌ Error en feedback: {e}")

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
    return jsonify({"status": "ok", "bot": "Guaribe Beta"}), 200

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    url = "https://guaribe-beta.onrender.com/webhook"
    try:
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=url)
        return jsonify({"status": "ok", "message": f"Webhook configurado en {url}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url="https://guaribe-beta.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port)
else:
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url="https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado en producción")
    logger.info("✅ Servidor listo para recibir peticiones")
