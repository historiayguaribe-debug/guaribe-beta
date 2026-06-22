import os
import time
import telebot
import logging
import requests
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ==================== FUNCIONES ====================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

def obtener_tasa():
    try:
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("fuente") == "oficial":
                    return f"💰 *Tasa oficial BCV:* {item['promedio']} Bs/USD"
        return "💰 No pude obtener la tasa."
    except:
        return "💰 Error al consultar la tasa."

def buscar_noticias():
    from bs4 import BeautifulSoup
    fuentes = [
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("VTV", "https://www.vtv.gob.ve/feed"),
        ("AVN", "https://www.avn.info.ve/feed"),
        ("TeleSUR", "https://www.telesurtv.net/rss"),
    ]
    noticias = []
    for nombre, url in fuentes:
        try:
            soup = BeautifulSoup(requests.get(url, timeout=10).text, 'xml')
            for item in soup.find_all('item')[:2]:
                titulo = item.find('title').text if item.find('title') else ""
                if titulo and len(titulo) > 10:
                    t = titulo.replace("Venezuela", "").strip() or titulo
                    if len(t) > 100:
                        t = t[:97] + "..."
                    noticias.append(f"▪️ {t} ({nombre})")
        except:
            continue
    return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:10]) if noticias else "📰 No encontré noticias."

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.send_message(m.chat.id, 
        "¡Epale! Soy **Guaribe**, tu asistente llanero.\n\n"
        "Usa los botones:\n"
        "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n🎙️ Voz\n\n"
        "¡Seguimos razonando! 🇻🇪🤠🏛️",
        parse_mode='Markdown', reply_markup=menu_principal()
    )

@bot.message_handler(commands=['status'])
def cmd_status(m):
    bot.send_message(m.chat.id, "✅ Guaribe está vivo y funcionando correctamente.\n\nVersión: 2.0 (Prueba)\nEstado: ✅ Activo")

@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    if not texto or len(texto) < 2:
        return
    
    logger.info(f"Mensaje de {chat_id}: {texto[:50]}...")
    
    try:
        # --- SALUDOS ---
        if texto.lower() in ["hola", "buenas", "hey", "saludos", "epa"]:
            bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
            return
        
        # --- ACCIONES RÁPIDAS ---
        if "tasa" in texto.lower() or "bcv" in texto.lower() or "dólar" in texto.lower():
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return
        
        if "noticias" in texto.lower() or "qué pasó" in texto.lower():
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return
        
        # --- BOTONES ---
        if texto == "💰 Tasa BCV":
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return
        if texto == "📰 Noticias":
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return
        if texto == "🔮 Analizar":
            bot.send_message(chat_id, "🔮 Modo análisis en construcción. Pronto podré profundizar en cualquier tema.")
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Pronto podré responderte con audio.")
            return
        
        # --- RESPUESTA GENÉRICA ---
        bot.send_message(chat_id, 
            "¡Gracias por tu mensaje, pana! Puedo ayudarte con:\n"
            "💰 Tasa BCV\n📰 Noticias\n\n"
            "Escribe 'hola', 'tasa' o 'noticias'.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

# ==================== FLASK ====================
@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "ok", "bot": "Guaribe Beta - Prueba"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ok', 200

# ==================== CONFIGURACIÓN DEL WEBHOOK ====================
def configurar_webhook():
    webhook_url = f"https://guaribe-beta.onrender.com/webhook"
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook configurado en {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Error configurando webhook: {e}")

# ==================== EJECUCIÓN ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    configurar_webhook()
    app.run(host='0.0.0.0', port=port)
else:
    # En producción con gunicorn
    configurar_webhook()
    logger.info("✅ Servidor listo para recibir peticiones")
