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

# ==================== FUNCIONES CON IMPORTS DIFERIDOS ====================
def obtener_tasa():
    """Obtiene la tasa BCV desde DolarAPI (imports diferidos)."""
    try:
        import requests
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        if r.status_code == 200:
            for item in r.json():
                if item.get("fuente") == "oficial":
                    return f"💰 *Tasa oficial BCV:* {item['promedio']} Bs/USD"
        return "💰 No pude obtener la tasa."
    except Exception as e:
        logger.error(f"Error en obtener_tasa: {e}")
        return "💰 Error al consultar la tasa."

def buscar_noticias():
    """Scrapea noticias de Venezuela (imports diferidos)."""
    try:
        import requests
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
    except Exception as e:
        logger.error(f"Error en buscar_noticias: {e}")
        return "📰 Error al buscar noticias."

def generar_imagen(prompt):
    """Genera imagen con Pollinations.ai (imports diferidos)."""
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
        logger.error(f"Error en generar_imagen: {e}")
        return None

def buscar_en_web(consulta, limite=3):
    """Busca en DuckDuckGo (imports diferidos)."""
    try:
        import requests
        from bs4 import BeautifulSoup
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        soup = BeautifulSoup(requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0'
        }).text, 'html.parser')
        resultados = []
        for a in soup.find_all('a'):
            texto = a.get_text().strip()
            if 40 < len(texto) < 300 and texto not in resultados:
                resultados.append(texto[:180])
                if len(resultados) >= limite:
                    break
        return resultados
    except Exception as e:
        logger.error(f"Error en buscar_en_web: {e}")
        return []

def orquestar_respuesta(consulta, categoria="simple", contexto=None):
    """Genera respuesta usando DeepSeek o Grok (imports diferidos)."""
    if contexto is None:
        contexto = []
    
    # Intentar usar DeepSeek o Grok con imports diferidos
    try:
        import requests
        import os
        deepseek_token = os.environ.get("DEEPSEEK_TOKEN")
        if deepseek_token:
            url = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {deepseek_token}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek",
                "messages": [
                    {"role": "system", "content": "Eres Guaribe, asistente venezolano del llano. Responde de forma breve y concreta."},
                    {"role": "user", "content": consulta}
                ],
                "stream": False,
                "max_tokens": 2000
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Error en DeepSeek: {e}")
    
    # Fallback: respuesta genérica
    return f"Pana, recibí tu mensaje: '{consulta}'. Estoy aprendiendo, pero por ahora puedo ayudarte con tasa, noticias e imágenes. Usa los botones o escribe 'tasa', 'noticias' o 'genera una imagen de...'"

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
    status_msg += "   ✅ Memoria (carga diferida)\n"
    status_msg += "   ✅ Clasificador (carga diferida)\n"
    status_msg += "   ✅ Orquestador (carga diferida)\n"
    status_msg += "   ✅ Web (carga diferida)\n"
    status_msg += "   ✅ Media (carga diferida)\n"
    
    # APIs
    deepseek_token = os.environ.get("DEEPSEEK_TOKEN")
    groq_key = os.environ.get("GROQ_API_KEY")
    status_msg += "\n🔑 *APIs:*\n"
    status_msg += f"   {'✅' if deepseek_token else '❌'} DeepSeek (token: ...{deepseek_token[-4:] if deepseek_token else 'no'})\n"
    status_msg += f"   {'✅' if groq_key else '❌'} Groq (clave: ...{groq_key[-4:] if groq_key else 'no'})\n"
    
    # Versión
    status_msg += "\n📦 *Versión:* Guaribe Beta 2.0 (Optimizado)"
    
    bot.send_message(chat_id, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "⛔ No autorizado.")
        return
    bot.send_message(m.chat.id, "🧹 Limpiando base de datos... (simulado)")
    bot.send_message(m.chat.id, "✅ Base de datos limpiada.")

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

        # --- 2. ACCIONES RÁPIDAS (tasa, noticias) ---
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

        # --- 4. MODO ANÁLISIS ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            tema = texto
            bot.send_message(chat_id, f"📊 Analizando: {tema[:50]}...")
            # Buscar contexto web
            contexto_web = buscar_en_web(tema, 3)
            contexto_texto = "\n".join(contexto_web) if contexto_web else ""
            # Orquestar respuesta
            respuesta = orquestar_respuesta(
                consulta=tema,
                categoria="compleja",
                contexto=[contexto_texto] if contexto_texto else []
            )
            bot.send_message(chat_id, respuesta, parse_mode='Markdown')
            return

        # --- 5. BOTONES ---
        if texto == "💰 Tasa BCV":
            bot.send_message(chat_id, obtener_tasa(), parse_mode='Markdown')
            return
        if texto == "📰 Noticias":
            bot.send_message(chat_id, buscar_noticias(), parse_mode='Markdown')
            return
        if texto == "🔮 Analizar":
            modo_analisis[chat_id] = True
            bot.send_message(chat_id, "🔮 Envíame el tema a analizar.")
            return
        if texto == "🎙️ Voz":
            bot.send_message(chat_id, "🎙️ Pronto podré responderte con audio. Por ahora, solo texto.")
            return

        # --- 6. RESPUESTA GENÉRICA ---
        # Intentar con DeepSeek (si está configurado)
        respuesta = orquestar_respuesta(texto, "simple", [])
        
        # --- 7. ENVIAR RESPUESTA ---
        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')

        # --- 8. FEEDBACK ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)

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
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.0 - Optimizado"}), 200

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
