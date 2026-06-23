from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(m.chat.id, "🏓 Bot activo. Escribe cualquier cosa y te responderé.")

@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    logger.info(f"📩 Mensaje recibido de {chat_id}: {texto[:50]}...")
    try:
        bot.send_message(chat_id, f"🏓 Pong! Recibí: {texto}")
    except Exception as e:
        logger.error(f"❌ Error enviando respuesta: {e}")

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
    return jsonify({"status": "ok", "bot": "Guaribe - Modo Pong"}), 200

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port)
else:
    # En producción con gunicorn
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado en producción")
