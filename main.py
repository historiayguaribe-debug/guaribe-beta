from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # Tu chat_id para comandos de admin

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN no está configurado en las variables de entorno.")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
modo_analisis = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== FUNCIONES AUXILIARES (con fallbacks) ====================
def obtener_tasa():
    """Obtiene la tasa BCV desde DolarAPI (con fallback)."""
    try:
        import requests
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("fuente") == "oficial":
                    return f"💰 *Tasa oficial BCV:* {item['promedio']} Bs/USD"
        return "💰 No pude obtener la tasa en este momento."
    except Exception as e:
        logger.error(f"Error obteniendo tasa: {e}")
        return "💰 Error al consultar la tasa."

def buscar_noticias():
    """Scrapea noticias de Venezuela (con fallback)."""
    try:
        import requests
        from bs4 import BeautifulSoup
        fuentes = [
            ("El Universal", "https://www.eluniversal.com/rss"),
            ("VTV", "https://www.vtv.gob.ve/feed"),
            ("AVN", "https://www.avn.info.ve/feed"),
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
        if noticias:
            return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:10])
        return "📰 No encontré noticias en este momento."
    except Exception as e:
        logger.error(f"Error buscando noticias: {e}")
        return "📰 Error al buscar noticias."

def generar_imagen(prompt):
    """Genera imagen con Pollinations.ai (con fallback)."""
    try:
        import requests
        from io import BytesIO
        prompt_limpio = prompt.replace(' ', '%20')
        url = f"https://image.pollinations.ai/prompt/{prompt_limpio}?width=1024&height=1024&nologo=true"
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            return BytesIO(r.content)
        return None
    except Exception as e:
        logger.error(f"Error generando imagen: {e}")
        return None

def menu_principal():
    """Crea el teclado con los botones principales."""
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar"),
        KeyboardButton("🎙️ Voz")
    )
    return markup

# ==================== HANDLERS DE TELEGRAM ====================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    """Mensaje de bienvenida con los botones."""
    bot.send_message(
        m.chat.id,
        "¡Epale! Soy **Guaribe**, tu asistente llanero.\n\n"
        "Usa los botones:\n"
        "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n🎙️ Voz\n\n"
        "🎨 Puedes pedirme imágenes escribiendo 'genera una imagen de ...'.\n"
        "📸 Envía fotos para que las analice (pronto).\n"
        "🎙️ Envía mensajes de voz (pronto).\n"
        "👍/👎 Califica mis respuestas (pronto).\n\n"
        "¡Seguimos razonando! 🇻🇪🤠🏛️",
        parse_mode='Markdown',
        reply_markup=menu_principal()
    )

@bot.message_handler(commands=['status'])
def cmd_status(m):
    """Comando para verificar el estado del bot (solo admin)."""
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "⛔ Este comando es solo para administradores.")
        return
    
    # Verificar módulos principales
    mensaje = "📁 *ESTADO DE GUARIBE*\n\n"
    mensaje += "✅ Bot activo\n"
    
    # Verificar módulos
    try:
        from core.memory import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        mensaje += "✅ Base de datos conectada\n"
    except:
        mensaje += "❌ Base de datos no conectada\n"
    
    try:
        from core.classifier import clasificador
        mensaje += f"✅ Clasificador cargado (ejemplos: {len(clasificador.ejemplos)})\n"
    except:
        mensaje += "❌ Clasificador no disponible\n"
    
    mensaje += "\n🔑 *APIs:*\n"
    deepseek_token = os.environ.get("DEEPSEEK_TOKEN")
    groq_key = os.environ.get("GROQ_API_KEY")
    mensaje += f"   {'✅' if deepseek_token else '❌'} DeepSeek: {'configurada' if deepseek_token else 'no configurada'}\n"
    mensaje += f"   {'✅' if groq_key else '❌'} Groq: {'configurada' if groq_key else 'no configurada'}\n"
    
    mensaje += "\n📦 *Versión:* Guaribe Estable 2.0"
    bot.send_message(m.chat.id, mensaje, parse_mode='Markdown')

@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    """Limpia la base de datos (solo admin)."""
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "⛔ No autorizado.")
        return
    
    bot.send_message(m.chat.id, "🧹 Limpiando base de datos...")
    try:
        from core.memory import get_connection
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
    """Procesa todos los mensajes que no son comandos."""
    chat_id = m.chat.id
    texto = m.text or ""
    
    if not texto or len(texto) < 2:
        return
    
    logger.info(f"📩 Mensaje de {chat_id}: {texto[:50]}...")
    
    try:
        # --- 1. SALUDOS (sin IA) ---
        saludos = ["hola", "buenas", "hey", "saludos", "epa", "buen día", "buenas tardes", "buenas noches"]
        if texto.lower() in saludos or any(texto.lower().startswith(s) for s in saludos):
            bot.send_message(chat_id, "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠")
            return

        # --- 2. ACCIONES RÁPIDAS ---
        if "tasa" in texto.lower() or "bcv" in texto.lower() or "dólar" in texto.lower():
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return

        if "noticias" in texto.lower() or "qué pasó" in texto.lower():
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return

        # --- 3. IMÁGENES ---
        if "genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower()):
            bot.send_message(chat_id, "🎨 Generando imagen...")
            img = generar_imagen(texto)
            if img:
                bot.send_photo(chat_id, img, caption=f"🎨 *{texto[:50]}...*", parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "❌ No pude generar la imagen.")
            return

        # --- 4. MODO ANÁLISIS (activado con el botón 🔮 Analizar) ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            bot.send_message(chat_id, f"📊 Analizando: {texto[:50]}...")
            # Respuesta básica mientras no tengamos el motor completo
            bot.send_message(chat_id, f"🔮 Este es un análisis preliminar de: **{texto}**\n\n"
                                     f"Por ahora, puedo decirte que es un tema interesante. ¿Quieres que profundice en algo específico?",
                                     parse_mode='Markdown')
            return

        # --- 5. RESPUESTA PARA BOTONES ESPECIALES ---
        if texto == "💰 Tasa BCV":
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return
        if texto == "📰 Noticias":
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return
        if texto == "🔮 Analizar":
            modo_analisis[chat_id] = True
            bot.send_message(chat_id, "🔮 Envíame el tema que quieres analizar.")
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Pronto podré responderte con audio. ¡Estamos trabajando en ello!")
            return

        # --- 6. RESPUESTA GENÉRICA (cuando no encaja en nada) ---
        bot.send_message(
            chat_id,
            "¡Gracias por tu mensaje, pana! Estoy aprendiendo. Por ahora, puedo ayudarte con:\n"
            "💰 Tasa BCV\n📰 Noticias\n🎨 Imágenes (escribe 'genera una imagen de...')\n🔮 Análisis (usa el botón)\n\n"
            "Escribe 'hola', 'tasa', 'noticias' o 'genera una imagen de...'"
        )

    except Exception as e:
        logger.error(f"❌ Error en handle_message: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

# ==================== FEEDBACK (pronto) ====================
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
    return jsonify({"status": "ok", "bot": "Guaribe Estable 2.0"}), 200

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
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # Configurar webhook al iniciar
    for _ in range(3):
        try:
            bot.remove_webhook()
            time.sleep(0.5)
            bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
            break
        except Exception as e:
            logger.warning(f"⚠️ Error configurando webhook: {e}. Reintentando...")
            time.sleep(2)
    logger.info("✅ Webhook configurado en desarrollo")
    app.run(host='0.0.0.0', port=port)
else:
    # En producción con gunicorn, solo configurar webhook una vez
    for _ in range(3):
        try:
            bot.remove_webhook()
            time.sleep(0.5)
            bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
            logger.info("✅ Webhook configurado en producción")
            break
        except Exception as e:
            logger.warning(f"⚠️ Error configurando webhook: {e}. Reintentando...")
            time.sleep(2)
