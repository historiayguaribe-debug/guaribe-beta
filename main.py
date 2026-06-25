from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
from flask import Flask, request, jsonify
from utils.logger import logger

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no configurado")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
logger.info("✅ Bot de Telegram inicializado")

# ==================== MENÚ ====================
def menu_principal():
    from telebot.types import ReplyKeyboardMarkup, KeyboardButton
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
        "🎨 Puedes pedirme imágenes: 'genera una imagen de...'\n"
        "📰 Noticias: 'noticias' o 'qué pasó hoy'\n"
        "🔮 Análisis: 'analiza' o 'analizar'\n"
        "📸 Envía fotos para analizar.\n"
        "🎙️ Envía mensajes de voz.\n\n"
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
        # Importar módulos
        from core.classifier import clasificador
        from core.orchestrator import orquestar
        from utils.web import obtener_tasa, buscar_noticias
        from utils.media import generar_imagen
        
        # Detectar acciones rápidas (sin clasificador)
        if "tasa" in texto.lower() or "bcv" in texto.lower() or "dólar" in texto.lower():
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return
        
        if "noticias" in texto.lower() or "qué pasó" in texto.lower():
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return
        
        if "genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower()):
            bot.send_message(chat_id, "🎨 Generando imagen... (puede tomar unos segundos)")
            img = generar_imagen(texto)
            if img:
                bot.send_photo(chat_id, img, caption=f"🎨 *{texto[:50]}...*", parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "❌ No pude generar la imagen. Intenta con otro prompt.")
            return
        
        # Clasificar
        categoria = clasificador.clasificar(texto)
        logger.info(f"📋 Categoría: {categoria}")
        
        # Orquestar
        respuesta = orquestar(texto, categoria, [], {})
        bot.send_message(chat_id, respuesta, parse_mode='Markdown')
        logger.info(f"✅ Respuesta enviada a {chat_id}")
        
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
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.0"}), 200

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

# ==================== EJECUCIÓN ====================
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
