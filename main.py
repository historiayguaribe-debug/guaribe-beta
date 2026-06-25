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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
logger.info("✅ Bot de Telegram inicializado")

# ==================== MENÚ ====================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(m.chat.id,
        "¡Epale! Soy **Guaribe**, tu asistente llanero.\n\n"
        "Usa los botones:\n💰 Tasa BCV\n🎙️ Voz\n\n"
        "¡Seguimos razonando! 🇻🇪🤠🏛️",
        parse_mode='Markdown', reply_markup=menu_principal()
    )

# ==================== HANDLER DE SALUDO (INDEPENDIENTE) ====================
@bot.message_handler(func=lambda m: m.text and m.text.lower() in ["hola", "epa", "hey"])
def handle_saludo(m):
    chat_id = m.chat.id
    logger.info(f"📩 Saludo de {chat_id}: {m.text}")
    bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")

# ==================== HANDLER PRINCIPAL (CON LOGS) ====================
@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    if not texto or len(texto) < 2:
        return
    logger.info(f"📩 Mensaje de {chat_id}: {texto[:50]}...")

    try:
        # Importar módulos bajo demanda con logs
        logger.info("🔄 Cargando módulos...")
        try:
            from core.orchestrator import orquestar
            ORCHESTRATOR_AVAILABLE = True
            logger.info("✅ Orquestador cargado")
        except Exception as e:
            logger.error(f"❌ Error cargando orquestador: {e}")
            ORCHESTRATOR_AVAILABLE = False

        if not ORCHESTRATOR_AVAILABLE:
            bot.send_message(chat_id, "⚠️ Orquestador no disponible. Intenta más tarde.")
            return

        # Clasificar y orquestar
        try:
            from core.classifier import clasificador
            categoria = clasificador.clasificar(texto)
            logger.info(f"📋 Categoría: {categoria}")
        except Exception as e:
            logger.error(f"❌ Error clasificando: {e}")
            categoria = "simple"

        contexto = []
        respuesta = orquestar(texto, categoria, contexto, {})
        logger.info(f"✅ Respuesta generada: {respuesta[:100]}...")
        bot.send_message(chat_id, respuesta, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"❌ Error en handle_message: {e}")
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
    bot.set_webhook(url="https://guaribe-beta.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port)
else:
    # En producción, solo configurar webhook
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url="https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado en producción")
    logger.info("✅ Servidor listo para recibir peticiones")
