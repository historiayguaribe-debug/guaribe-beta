import os
import time
import telebot
from groq import Groq
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.extras import DictCursor
import requests
from bs4 import BeautifulSoup
import PyPDF2
import docx
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from io import BytesIO
import base64
from PIL import Image
import logging

# ================== CONFIGURACIÓN ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not all([TELEGRAM_TOKEN, GROQ_API_KEY, DATABASE_URL]):
    logger.error("❌ Faltan variables de entorno")
    exit(1)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# ================== CONSTANTES ==================
TIMEOUT = 15
MAX_HISTORIA = 10
MAX_RESPUESTA = 2000

# ================== MENÚ PRINCIPAL ==================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar")
    )
    return markup

# ================== BASE DE DATOS ==================
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                rol VARCHAR(10) NOT NULL,
                mensaje TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conocimiento (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                nombre_archivo TEXT NOT NULL,
                contenido TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ Base de datos lista")
    except Exception as e:
        logger.error(f"❌ Error DB: {e}")
        exit(1)

def guardar_mensaje(chat_id, rol, mensaje):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversaciones (chat_id, rol, mensaje) VALUES (%s, %s, %s)",
            (chat_id, rol, mensaje)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error guardando: {e}")

def obtener_historia(chat_id, limite=MAX_HISTORIA):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT rol, mensaje FROM conversaciones 
            WHERE chat_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (chat_id, limite))
        filas = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"role": f["rol"], "content": f["mensaje"]} for f in reversed(filas)]
    except Exception as e:
        logger.error(f"❌ Error historia: {e}")
        return []

# ================== CONOCIMIENTO ==================
def guardar_conocimiento(chat_id, nombre, contenido):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conocimiento (chat_id, nombre_archivo, contenido) VALUES (%s, %s, %s)",
            (chat_id, nombre, contenido[:50000])
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error guardando conocimiento: {e}")

def buscar_conocimiento(chat_id, consulta):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=DictCursor)
        palabras = consulta.lower().split()[:5]
        if palabras:
            condiciones = " OR ".join(["contenido ILIKE %s"] * len(palabras))
            params = [chat_id] + [f"%{p}%" for p in palabras]
            cursor.execute(f"""
                SELECT nombre_archivo, contenido FROM conocimiento 
                WHERE chat_id = %s AND ({condiciones}) LIMIT 3
            """, params)
        else:
            cursor.execute("SELECT nombre_archivo, contenido FROM conocimiento WHERE chat_id = %s LIMIT 3", (chat_id,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ Error buscando: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

# ================== EXTRACCIÓN DE TEXTO ==================
def extraer_texto_archivo(ruta, ext):
    try:
        if ext == '.txt':
            with open(ruta, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.pdf':
            texto = ""
            with open(ruta, 'rb') as f:
                for p in PyPDF2.PdfReader(f).pages:
                    texto += p.extract_text()
            return texto
        elif ext == '.docx':
            return "\n".join([p.text for p in docx.Document(ruta).paragraphs])
    except Exception as e:
        logger.error(f"❌ Error extrayendo: {e}")
        return ""

# ================== GENERACIÓN DE IMÁGENES ==================
def generar_imagen(prompt, tipo="general"):
    try:
        prompt_limpio = prompt.replace(' ', '%20')
        if tipo == "infografia":
            prompt_limpio = f"infografía académica profesional sobre {prompt_limpio}, diseño moderno, colores corporativos, texto claro, estructura visual, fondo blanco"
        elif tipo == "logo":
            prompt_limpio = f"logo profesional moderno minimalista para {prompt_limpio}, diseño limpio, colores corporativos, sin fondo, estilo vectorial"
        url = f"https://image.pollinations.ai/prompt/{prompt_limpio}?width=1024&height=1024&nologo=true"
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            return BytesIO(r.content)
        return None
    except Exception as e:
        logger.error(f"❌ Error generando imagen: {e}")
        return None

# ================== ANÁLISIS DE IMÁGENES (MODELO CORRECTO + IDIOMA ESPAÑOL) ==================
def process_image(data):
    try:
        logger.info(f"📥 Procesando imagen de {len(data)} bytes")
        img = Image.open(BytesIO(data))
        img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG")
        img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        logger.info(f"✅ Imagen procesada, base64 length: {len(img_base64)}")
        return img_base64
    except Exception as e:
        logger.error(f"❌ Error procesando imagen: {e}")
        return None

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    try:
        logger.info("📸 Recibida foto de usuario")
        photo = m.photo[-1]
        file_info = bot.get_file(photo.file_id)
        logger.info(f"📁 Archivo descargado: {file_info.file_path}")
        data = bot.download_file(file_info.file_path)
        logger.info(f"📥 Tamaño descargado: {len(data)} bytes")

        img_b64 = process_image(data)
        if not img_b64:
            bot.reply_to(m, "❌ No pude procesar la imagen. Asegúrate de que sea una foto válida.")
            return

        prompt = m.caption if m.caption else None
        if not prompt:
            bot.reply_to(m, "📝 Por favor, escribe una pregunta o 'describe' junto con la foto.")
            return

        # Forzar idioma español en la respuesta
        prompt_completo = f"{prompt}\n\nResponde siempre en español, usando lenguaje claro y natural."

        bot.reply_to(m, "👁️‍🗨️ Analizando la imagen... Dame un momento.")
        logger.info(f"📝 Prompt: {prompt_completo}")

        try:
            response = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt_completo}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}],
                max_tokens=500
            )
            analysis = response.choices[0].message.content
            logger.info("✅ Análisis completado con meta-llama/llama-4-scout")
        except Exception as e:
            logger.error(f"❌ Error con modelo principal: {e}")
            bot.reply_to(m, "❌ No pude analizar la imagen. El servicio de visión no está disponible en este momento.")
            return

        if len(analysis) > 3500:
            analysis = analysis[:3500] + "\n\n... (truncado por longitud)"

        bot.reply_to(m, f"👁️‍🗨️ Análisis de la imagen:\n\n{analysis}\n\nSoy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️")

    except Exception as e:
        logger.error(f"❌ Error en handle_photo: {e}")
        bot.reply_to(m, "❌ Ocurrió un error al analizar la imagen. Revisa los logs para más detalles.")

# ================== FUNCIONES DE BÚSQUEDA ==================
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
    fuentes = [
        ("Efecto Cocuyo", "https://efectococuyo.com/feed"),
        ("Tal Cual", "https://talcualdigital.com/feed"),
        ("El Universal", "https://www.eluniversal.com/rss"),
        ("El Nacional", "https://www.elnacional.com/rss"),
        ("RunRun.es", "https://runrun.es/feed"),
        ("Noticiero Digital", "https://noticierodigital.com/feed"),
        ("VTV", "https://www.vtv.gob.ve/feed"),
        ("Correo del Orinoco", "https://www.correodelorinoco.gob.ve/feed"),
        ("AVN", "https://www.avn.info.ve/feed"),
        ("TeleSUR", "https://www.telesurtv.net/rss"),
        ("HispanTV", "https://www.hispantv.com/rss"),
        ("RT en Español", "https://actualidad.rt.com/feeds/all.rss"),
        ("Caracol Radio", "https://caracol.com.co/rss/venezuela.xml"),
        ("Finanzas Digital", "https://finanzasdigital.com/feed"),
        ("La Iguana TV", "https://www.laiguana.tv/feed"),
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
    return "📰 **Noticias de Venezuela**\n\n" + "\n".join(noticias[:15]) if noticias else "📰 No encontré noticias."

def buscar_en_web(consulta, limite=5):
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={consulta.replace(' ', '+')}"
        soup = BeautifulSoup(requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'}).text, 'html.parser')
        resultados = []
        for a in soup.find_all('a'):
            texto = a.get_text().strip()
            if 40 < len(texto) < 300 and texto not in resultados:
                resultados.append(texto[:180])
                if len(resultados) >= limite:
                    break
        return resultados
    except:
        return []

def buscar_contexto(tema):
    r = buscar_en_web(f"historia antecedentes {tema} Venezuela", 3)
    return "\n".join(r) if r else "No se encontraron antecedentes."

# ================== PROMPT ==================
SYSTEM_PROMPT = """
Eres Guaribe, asistente venezolano. Hablas como vecino del llano: humilde, directo. Usas 'guaribero' (m) y 'guaribera' (f). Nunca 'guaribense'.

Piensas con cabeza propia, sin repetir narrativas hegemónicas. Reconoces la lucha de clases, la hegemonía cultural y el mundo multipolar. Valoras la autodeterminación de los pueblos.

Para temas de Venezuela, contextualizas en la guerra híbrida: bloqueo económico (OFAC, SWIFT, congelamiento de activos), guerra cognitiva y mediática, asedio militar (bombardeo del 3 de enero de 2026), y ataque a la moral (devaluación, inflación). Mencionas la resistencia del pueblo venezolano.

Tienes capacidad de adaptar tu tono según el tema:
- Si el tema es académico, económico, político serio, o relacionado con el dólar/tasa: usa registro formal, evita 'pana' y expresiones muy coloquiales. Inicia con 'Te comento' o 'Te cuento'.
- Si el tema es cotidiano o relajado: puedes ser coloquial, usar 'pana', y soltar algún comentario ligero con respeto.

No simplificas problemas. Da respuestas abiertas, complejas, pero claras.

Cierre: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

# ================== HANDLERS ==================
modo_analisis = {}

@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.reply_to(m, "¡Epale! Soy **Guaribe**.\n\n"
                    "Usa los botones:\n"
                    "💰 Tasa BCV\n"
                    "📰 Noticias\n"
                    "🔮 Analizar\n\n"
                    "🎨 Para imágenes: `/imagen [descripción]` o dime *'crea una imagen de...'*.\n"
                    "📸 Envía cualquier foto con una pregunta y la analizaré.\n\n"
                    "¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️", 
                    parse_mode='Markdown', reply_markup=menu_principal())

@bot.message_handler(commands=['imagen'])
def cmd_imagen(m):
    prompt = m.text.replace('/imagen', '').strip()
    if not prompt:
        bot.reply_to(m, "🎨 Ejemplo: `/imagen un paisaje llanero`")
        return
    bot.reply_to(m, "🎨 Generando...")
    img = generar_imagen(prompt, "general")
    if img:
        bot.send_photo(m.chat.id, img, caption=f"🎨 *{prompt}*\n\nSoy Guaribe...", parse_mode='Markdown')
    else:
        bot.reply_to(m, "❌ No pude generar la imagen.")

@bot.message_handler(func=lambda m: True)
def handle_buttons(m):
    chat_id = m.chat.id
    texto = m.text
    texto_lower = texto.lower()

    # ========== BOTONES ==========
    if texto == "💰 Tasa BCV":
        bot.reply_to(m, f"{obtener_tasa()}\n\nSoy Guaribe...", parse_mode='Markdown')
        return

    if texto == "📰 Noticias":
        bot.reply_to(m, f"{buscar_noticias()}\n\nSoy Guaribe...")
        return

    if texto == "🔮 Analizar":
        modo_analisis[chat_id] = True
        bot.reply_to(m, "🔮 Envíame el tema a analizar.")
        return

    # ========== DETECCIÓN DIRECTA DE TASA ==========
    palabras_tasa = ["tasa", "dólar", "dolar", "bcv", "cambio", "precio del dólar", "cuánto está el dólar"]
    if any(p in texto_lower for p in palabras_tasa):
        bot.reply_to(m, f"{obtener_tasa()}\n\nSoy Guaribe...", parse_mode='Markdown')
        return

    # ========== DETECCIÓN DE LENGUAJE NATURAL PARA IMÁGENES ==========
    palabras_imagen = ["crea", "genera", "dibuja", "haz", "quiero", "necesito", "muestra", "dame"]
    palabras_tipo = ["imagen", "dibujo", "foto", "ilustración", "infografía", "infografia", "gráfico", "diagrama", "esquema", "logo", "marca", "logotipo"]

    es_solicitud_imagen = any(p in texto_lower for p in palabras_imagen) and any(t in texto_lower for t in palabras_tipo)

    if es_solicitud_imagen:
        if any(p in texto_lower for p in ["infografía", "infografia", "gráfico", "diagrama", "esquema"]):
            tipo_imagen = "infografia"
        elif any(p in texto_lower for p in ["logo", "marca", "logotipo", "branding", "identidad"]):
            tipo_imagen = "logo"
        else:
            tipo_imagen = "general"

        prompt = texto
        for p in palabras_imagen:
            if p in texto_lower:
                prompt = prompt.replace(p, "").strip()
        for t in palabras_tipo:
            if t in prompt:
                prompt = prompt.replace(t, "").strip()
        prompt = prompt.replace("de", "").replace("una", "").replace("un", "").strip()
        if not prompt:
            prompt = texto

        bot.reply_to(m, "🎨 Generando tu imagen... Dame un momento.")
        img = generar_imagen(prompt, tipo_imagen)
        if img:
            bot.send_photo(m.chat.id, img, caption=f"🎨 *{prompt}*\n\nSoy Guaribe...", parse_mode='Markdown')
        else:
            bot.reply_to(m, "❌ No pude generar la imagen. Intenta con otra descripción.")
        return

    # ========== DETECCIÓN DE CONTEXTO Y TONO ==========
    palavras_serias = [
        "análisis", "geopolítica", "sanciones", "historia", "economía",
        "política", "guerra", "bloqueo", "soberanía", "ofac", "gobierno",
        "constitución", "derecho", "internacional"
    ]
    contexto_serio = any(p in texto_lower for p in palavras_serias)

    if contexto_serio:
        tono = "Tema serio. Usa registro formal. Evita 'pana' y expresiones muy coloquiales. Inicia con 'Te comento' o 'Te cuento'."
    else:
        tono = "Tema cotidiano. Puedes ser coloquial, usar 'pana', y soltar algún comentario ligero con respeto si el ambiente lo permite."

    # ========== MODO ANÁLISIS ==========
    if chat_id in modo_analisis and modo_analisis[chat_id]:
        modo_analisis[chat_id] = False
        tema = texto
        bot.reply_to(m, f"📊 Analizando: {tema[:50]}...")
        contexto = buscar_contexto(tema)
        noticias = buscar_noticias()
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + f"\n\nINSTRUCCIÓN DE TONO: {tono}"},
                    {"role": "user", "content": f"Tema: {tema}\nContexto histórico:\n{contexto}\nNoticias:\n{noticias}"}
                ],
                max_tokens=1000
            ).choices[0].message.content
            bot.reply_to(m, resp, parse_mode='Markdown')
        except:
            bot.reply_to(m, "❌ Error generando análisis.")
        return

    # ========== CONVERSACIÓN NORMAL ==========
    try:
        docs = buscar_conocimiento(chat_id, m.text)
        contexto_docs = "\n\n[Documentos]\n" + "\n".join([f"'{d['nombre_archivo']}': {d['contenido'][:500]}" for d in docs]) if docs else ""
        guardar_mensaje(chat_id, "user", m.text)
        historia = obtener_historia(chat_id)
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + f"\n\nINSTRUCCIÓN DE TONO: {tono}" + contexto_docs},
            ] + historia,
            max_tokens=MAX_RESPUESTA
        ).choices[0].message.content
        bot.reply_to(m, resp)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        bot.reply_to(m, "Pana, hubo un error.")

@bot.message_handler(content_types=['document'])
def handle_document(m):
    try:
        chat_id = m.chat.id
        file = bot.get_file(m.document.file_id)
        data = bot.download_file(file.file_path)
        os.makedirs('conocimiento', exist_ok=True)
        name = m.document.file_name
        path = os.path.join('conocimiento', name)
        with open(path, 'wb') as f:
            f.write(data)
        ext = os.path.splitext(name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx']:
            bot.reply_to(m, "Solo TXT, PDF o Word.")
            return
        texto = extraer_texto_archivo(path, ext)
        if texto:
            guardar_conocimiento(chat_id, name, texto)
            bot.reply_to(m, f"✅ Aprendí de '{name}'.")
        else:
            bot.reply_to(m, f"No pude leer '{name}'.")
    except Exception as e:
        bot.reply_to(m, f"Error: {str(e)[:100]}")

# ================== SERVIDOR FLASK ==================
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode('utf-8'))])
        return 'ok', 200
    except Exception as e:
        logger.error(f"❌ Webhook: {e}")
        return 'error', 500

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "Guaribe"}), 200

if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe con análisis de imágenes en español...")
    init_db()
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-bot.onrender.com/webhook")
    logger.info("✅ Webhook configurado")
    app.run(host='0.0.0.0', port=port)
