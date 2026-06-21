from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import logging
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from core.memory import guardar_mensaje, buscar_contexto, buscar_resumenes, guardar_resumen
from core.classifier import clasificador
from core.orchestrator import orquestar
from core.strategist import estratega
from core.personality import obtener_prompt
from utils.web import obtener_tasa, buscar_noticias, buscar_en_web
from utils.media import generar_imagen, generar_audio, transcribir_audio

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
        from core.memory import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mensajes;")
            cur.execute("DELETE FROM resumenes;")
            conn.commit()
        bot.send_message(m.chat.id, "✅ Base de datos limpiada.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Error: {e}")

@bot.message_handler(func=lambda m: True)
def handle_message(m):
    chat_id = m.chat.id
    texto = m.text or ""
    if not texto or len(texto) < 2:
        return
    
    logger.info(f"Mensaje de {chat_id}: {texto[:50]}...")
    
    try:
        # --- 1. SALUDOS (sin IA) ---
        if texto.lower() in ["hola", "buenas", "hey", "saludos", "epa"]:
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
        
        # --- 4. MODO ANÁLISIS ---
        if chat_id in modo_analisis and modo_analisis[chat_id]:
            modo_analisis[chat_id] = False
            tema = texto
            bot.send_message(chat_id, f"📊 Analizando: {tema[:50]}...")
            # Buscar contexto web
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
        
        # --- 5. CLASIFICAR ---
        categoria = clasificador.clasificar(texto)
        logger.info(f"Clasificado como: {categoria}")
        
        # --- 6. BUSCAR CONTEXTO (memoria vectorial) ---
        from core.memory import get_connection
        conn = get_connection()
        historial = buscar_contexto(chat_id, texto, conn)
        resumenes = buscar_resumenes(chat_id, texto, conn)
        conn.close()
        
        contexto = historial + resumenes
        
        # --- 7. OBTENER PERFIL ---
        perfil = {}  # Simplificado, se puede expandir
        
        # --- 8. ORQUESTAR ---
        bot.send_message(chat_id, "⏳ Pensando...")
        respuesta = orquestar(texto, categoria, contexto, perfil)
        
        # --- 9. ENVIAR RESPUESTA ---
        sent_msg = bot.send_message(chat_id, respuesta, parse_mode='Markdown')
        
        # --- 10. FEEDBACK ---
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("👍", callback_data=f"fb_{sent_msg.message_id}_1"),
            InlineKeyboardButton("👎", callback_data=f"fb_{sent_msg.message_id}_-1")
        )
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)
        
        # --- 11. GUARDAR EN MEMORIA (async) ---
        def guardar():
            conn = get_connection()
            guardar_mensaje(chat_id, "usuario", texto, conn)
            guardar_mensaje(chat_id, "asistente", respuesta, conn)
            conn.close()
        threading.Thread(target=guardar).start()
        
        # --- 12. APRENDER PATRONES ---
        estratega.aprender(chat_id, texto, respuesta)
        
        # --- 13. SUGERENCIA ---
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
        # Actualizar clasificador con feedback
        # (se puede expandir para guardar feedback en DB)
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
    return jsonify({"status": "ok", "bot": "Guaribe Beta 2.0 - IA sin límites, costo $0"}), 200

if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe Beta 2.0...")
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    app.run(host='0.0.0.0', port=port)
