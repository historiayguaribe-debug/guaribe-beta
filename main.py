from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
from flask import Flask, request, jsonify

# ==================== CONFIGURACIÓN DE LOGGING ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== HANDLERS ====================
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
        logger.info("✅ Orquestador importado")
        respuesta = orquestar(texto, "simple", [], {})
        logger.info(f"✅ Respuesta: {respuesta[:50]}...")
        bot.send_message(chat_id, respuesta, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

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
