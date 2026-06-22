from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== IMPORTACIONES (con fallback) ====================
try:
    from core.memory import guardar_mensaje, buscar_contexto, buscar_resumenes, get_connection
    from core.classifier import clasificador
    from core.strategist import estratega
    from utils.web import obtener_tasa, buscar_noticias, buscar_en_web
    from utils.media import generar_imagen, generar_audio, transcribir_audio
except ImportError as e:
    logging.error(f"Error importando módulos: {e}")
    # Fallback: definir funciones vacías para que no falle
    def guardar_mensaje(*args, **kwargs): pass
    def buscar_contexto(*args, **kwargs): return []
    def buscar_resumenes(*args, **kwargs): return []
    def get_connection(): return None
    class clasificador:
        @staticmethod
        def clasificar(texto): return "simple"
    class estratega:
        @staticmethod
        def aprender(*args): pass
        @staticmethod
        def sugerir(*args): return None
    def obtener_tasa(): return "💰 No disponible"
    def buscar_noticias(): return "📰 No disponible"
    def buscar_en_web(*args): return []
    def generar_imagen(*args): return None
    def generar_audio(*args): return None
    def transcribir_audio(*args): return None

# ==================== ORQUESTADOR SIMULADO ====================
def orquestar(consulta, categoria, contexto, perfil):
    """Simula una respuesta inteligente mientras desarrollamos el orquestador real."""
    if categoria == "saludo":
        return "¡Hola! Soy Guaribe. ¿En qué te ayudo hoy? 🤠"
    
    if categoria == "simple":
        return f"Pana, eso es sencillo. Según lo que sé, {consulta[:50]}... ¡pero dame un momento y te respondo mejor!"
    
    if categoria == "noticias":
        return buscar_noticias()
    
    if categoria == "imagen":
        return "🎨 Para imágenes, solo dime 'genera una imagen de...'"
    
    if categoria == "creativa":
        return "📝 *Poema improvisado:*\n\nEn el llano donde el sol se esconde,\nGuaribe responde, sin que nadie lo esconda.\n\n(Soy Guaribe, tu asistente llanero. ¡Seguimos!)"
    
    # Respuesta genérica
    return f"📌 *Análisis rápido:*\n\n{consulta[:200]}...\n\nSoy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CONFIGURACIÓN ====================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

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

@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.send_message(m.chat.id, "⛔ No autorizado.")
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

@bot.message_handler(commands=['status'])
def cmd_status(m):
    chat_id = m.chat.id
    if str(chat_id) != ADMIN_CHAT_ID:
        bot.send_message(chat_id, "⛔ Este comando es solo para administradores.")
        return
    
    bot.send_message(chat_id, "🔍 Verificando estructura del bot...")
    mensaje = "📁 *ESTRUCTURA DE GUARIBE BETA*\n\n"
    
    archivos_requeridos = [
        ("main.py", "✅"),
        ("core/memory.py", "✅"),
        ("core/classifier.py", "✅"),
        ("core/personality.py", "✅"),
        ("core/strategist.py", "✅"),
        ("utils/__init__.py", "✅"),
        ("utils/web.py", "✅"),
        ("utils/media.py", "✅"),
        ("requirements.txt", "✅"),
    ]
    
    mensaje += "*Archivos y carpetas:*\n"
    todos_ok = True
    for archivo, icono in archivos_requeridos:
        existe = os.path.exists(archivo)
        if existe:
            mensaje += f"  ✅ {archivo}\n"
        else:
            mensaje += f"  ❌ {archivo} (no encontrado)\n"
            todos_ok = False
    
    if todos_ok:
        mensaje += "\n✅ *Estructura completa.*\n"
    else:
        mensaje += "\n⚠️ *Faltan archivos. Revisa el deploy.*\n"
    
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mensajes;")
            count_mensajes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM resumenes;")
            count_resumenes = cur.fetchone()[0]
        conn.close()
        mensaje += f"\n💾 *Base de datos:* ✅ Conectada\n"
        mensaje += f"   - Mensajes guardados: {count_mensajes}\n"
        mensaje += f"   - Resúmenes guardados: {count_resumenes}\n"
    except Exception as e:
        mensaje += f"\n💾 *Base de datos:* ❌ Error: {str(e)[:50]}\n"
    
    deepseek_token = os.environ.get("DEEPSEEK_TOKEN")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    mensaje += "\n🔑 *APIs:*\n"
    if deepseek_token:
        mensaje += f"   ✅ DeepSeek: configurada (token: ...{deepseek_token[-4:]})\n"
    else:
        mensaje += "   ❌ DeepSeek: no configurada\n"
    
    if groq_key:
        mensaje += f"   ✅ Groq: configurada (clave: ...{groq_key[-4:]})\n"
    else:
        mensaje += "   ❌ Groq: no configurada\n"
    
    mensaje += "\n📦 *Versión:* Guaribe Beta 2.1 (con orquestador simulado)"
    bot.send_message(chat_id, mensaje, parse_mode='Markdown')

# ==================== HANDLER PRINCIPAL ====================
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
        
        # --- IMÁGENES ---
        if "genera" in texto.lower() and ("imagen" in texto.lower() or "dibujo" in texto.lower()):
            bot.send_message(chat_id, "🎨 Generando imagen...")
            img = generar_imagen(texto)
            if img:
                bot.send_photo(chat_id, img, caption=f"🎨 *{texto[:50]}...*", parse_mode='Markdown')
            else:
                bot.send_message(chat_id, "❌ No pude generar la imagen.")
            return
        
        # --- MODO ANÁLISIS ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            tema = texto
            bot.send_message(chat_id, f"📊 Analizando: {tema[:50]}...")
            contexto_web = buscar_en_web(tema, 3)
            contexto_texto = "\n".join(contexto_web) if contexto_web else ""
            respuesta = orquestar(
                consulta=tema,
                categoria="compleja",
                contexto=[contexto_texto] if contexto_texto else [],
                perfil={}
            )
            bot.send_message(chat_id, respuesta, parse_mode='Markdown')
            return
        
        # --- BOTONES ---
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
            bot.send_message(chat_id, "🎙️ Envíame un mensaje de voz y te responderé.")
            return
        
        # --- CLASIFICAR Y RESPONDER ---
        categoria = clasificador.clasificar(texto)
        logger.info(f"Clasificado como: {categoria}")
        
        # --- BUSCAR CONTEXTO ---
        try:
            conn = get_connection()
            if conn:
                historial = buscar_contexto(chat_id, texto, conn)
                resumenes = buscar_resumenes(chat_id, texto, conn)
                conn.close()
                contexto = historial + resumenes
            else:
                contexto = []
        except:
            contexto = []
        
        # --- ORQUESTAR ---
        bot.send_message(chat_id, "⏳ Pensando...")
        respuesta = orquestar(texto, categoria, contexto, {})
        
        # --- ENVIAR RESPUESTA ---
        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')
        
        # --- FEEDBACK ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)
        
        # --- GUARDAR EN MEMORIA (async) ---
        def guardar():
            try:
                conn = get_connection()
                if conn:
                    guardar_mensaje(chat_id, "usuario", texto, conn)
                    guardar_mensaje(chat_id, "asistente", respuesta, conn)
                    conn.close()
            except:
                pass
        threading.Thread(target=guardar).start()
        
        # --- APRENDER PATRONES ---
        estratega.aprender(chat_id, texto, respuesta)
        
        # --- SUGERENCIA ---
        sugerencia = estratega.sugerir(chat_id, texto)
        if sugerencia:
            time.sleep(1)
            bot.send_message(chat_id, f"💡 {sugerencia}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.send_message(chat_id, "Pana, hubo un error. Intenta de nuevo. 🙏")

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
        logger.error(f"Webhook error: {e}")
        return 'ok', 200

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.1 - con orquestador simulado"}), 200

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

# ==================== CONFIGURACIÓN DEL WEBHOOK EN PRODUCCIÓN ====================
# Esto se ejecuta cuando gunicorn inicia (porque no está dentro de if __name__)
if not os.environ.get("WEBHOOK_SET"):
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url="https://guaribe-beta.onrender.com/webhook")
        os.environ["WEBHOOK_SET"] = "true"
        logger.info("✅ Webhook configurado automáticamente en producción")
    except Exception as e:
        logger.error(f"Error configurando webhook: {e}")

# ==================== EJECUCIÓN LOCAL ====================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe Beta 2.1 en modo desarrollo...")
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port)
