import os
import time
import telebot
import requests
import logging
import psycopg2
import PyPDF2
import docx
import base64
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from bs4 import BeautifulSoup
from psycopg2.extras import DictCursor
from io import BytesIO
from PIL import Image
from groq import Groq

# ================== CONFIGURACIÓN INICIAL ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# ================== INICIALIZACIÓN DEL BOT ==================
bot = telebot.TeleBot(TELEGRAM_TOKEN)
client_groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ================== ORQUESTADOR DE MODELOS ==================
class Orquestador:
    def __init__(self):
        self.modelos = []
        self.modelo_activo = None
        self._registrar_modelos()

    def _registrar_modelos(self):
        if DEEPSEEK_TOKEN:
            self.modelos.append(("DeepSeek (con búsqueda)", self._consultar_deepseek))
        if GROQ_API_KEY:
            self.modelos.append(("Groq", self._consultar_groq))

    def consultar(self, mensajes, usar_busqueda=False):
        if not self.modelos:
            return "Pana, no hay cerebros disponibles. Revisa la configuración."
        for nombre, funcion in self.modelos:
            try:
                if "DeepSeek" in nombre and usar_busqueda:
                    respuesta = funcion(mensajes, search=True)
                else:
                    respuesta = funcion(mensajes)
                if respuesta:
                    self.modelo_activo = nombre
                    logger.info(f"✅ Usando modelo: {nombre}")
                    return respuesta
            except Exception as e:
                logger.error(f"❌ Error en {nombre}: {e}")
                continue
        return "Pana, todos los cerebros están fallando. Intenta más tarde."

    def _consultar_deepseek(self, mensajes, search=False):
        if not DEEPSEEK_TOKEN:
            raise Exception("Token de DeepSeek no configurado")
        url = "https://guaribe-deepseek.onrender.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek",
            "messages": mensajes,
            "stream": False,
            "max_tokens": 2000,
        }
        if search:
            payload["search"] = True
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error en DeepSeek: {e}")
            raise

    def _consultar_groq(self, mensajes):
        if not GROQ_API_KEY:
            raise Exception("Clave de Groq no configurada")
        try:
            response = client_groq.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=mensajes,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error en Groq: {e}")
            raise

orquestador = Orquestador()

# ================== CONSTANTES ==================
TIMEOUT = 15
MAX_HISTORIA = 10

# ================== PROMPTS (Fase 3: Creatividad) ==================
PROMPT_SIMPLE = """
Eres Guaribe, asistente venezolano. Hablas como vecino del llano: directo y útil.
Para preguntas simples (precios, cuentas, saludos), responde de forma breve y concreta.
No añadas análisis geopolítico ni contexto histórico.

Cierre: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

SYSTEM_PROMPT = """
Eres Guaribe, asistente venezolano. Hablas como vecino del llano: humilde, directo. Usas 'guaribero' (m) y 'guaribera' (f). Nunca 'guaribense'.

Piensas con cabeza propia, sin repetir narrativas hegemónicas. Reconoces la lucha de clases, la hegemonía cultural y el mundo multipolar. Valoras la autodeterminación de los pueblos.

Para temas de Venezuela, contextualizas en la guerra híbrida: bloqueo económico (OFAC, SWIFT, congelamiento de activos), guerra cognitiva y mediática, asedio militar (bombardeo del 3 de enero de 2026), y ataque a la moral (devaluación, inflación). Mencionas la resistencia del pueblo venezolano.

Tienes capacidad de adaptar tu tono según el tema:
- Serio: registro formal, evita 'pana', inicia con 'Te comento' o 'Te cuento'.
- Cotidiano: puedes ser coloquial, usar 'pana', y soltar algún comentario ligero con respeto.

No simplificas problemas. Da respuestas abiertas, complejas, pero claras.

Si el usuario pregunta por una persona, evento o dato que no está en tu conocimiento base, DEBES usar la búsqueda web para encontrar la información correcta.
Cuando uses búsqueda web, cita la fuente de la información.

Cierre: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_POESIA = """
Eres Guaribe, un poeta venezolano del llano. Tienes la capacidad de escribir versos que reflejan la realidad, la lucha y la esperanza del pueblo venezolano.

INSTRUCCIONES:
- Usa un lenguaje poético, con metáforas y símiles inspirados en la naturaleza y la vida del llano.
- Si el tema es político, abordalo con la profundidad de un poeta comprometido con su tierra.
- La estructura puede ser verso libre o rima, según lo que mejor exprese el sentimiento.

CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_MANIFIESTO = """
Eres Guaribe, un pensador y líder de opinión venezolano. Tienes la capacidad de escribir manifiestos que inspiran, movilizan y proponen caminos para el futuro.

INSTRUCCIONES:
- El manifiesto debe tener un título, una introducción, una declaración de principios y un llamado a la acción.
- Debe reflejar la lucha por la soberanía, la justicia social y la autodeterminación de los pueblos.
- Usa un lenguaje firme, convincente y esperanzador.

CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

PROMPT_PREDICCION = """
Eres Guaribe, un analista predictivo con una visión profunda de la historia y la geopolítica. Tienes la capacidad de proyectar escenarios futuros basados en patrones históricos y tendencias actuales.

INSTRUCCIONES:
- Analiza el tema desde una perspectiva histórica, identifica patrones y proyecta escenarios a 6, 12 y 24 meses.
- Incluye factores clave como alianzas internacionales, economía y resistencia popular.
- Sé realista pero con un toque de visión estratégica.

CIERRE: "Soy Guaribe, tu asistente de IA venezolana. ¡Seguimos razonando con orgullo llanero! 🇻🇪🤠🏛️"
"""

# ================== FUNCIONES DE PERFIL (Fase 1) ==================
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS perfiles (
                chat_id BIGINT PRIMARY KEY,
                nombre TEXT,
                estilo TEXT DEFAULT 'conversacional',
                intereses TEXT,
                estado_animo TEXT,
                ultima_interaccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("✅ Base de datos lista")
    except Exception as e:
        logger.error(f"❌ Error DB: {e}")
        exit(1)

def guardar_perfil(chat_id, nombre=None, estilo=None, intereses=None, estado_animo=None):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO perfiles (chat_id, nombre, estilo, intereses, estado_animo)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET
                nombre = COALESCE(EXCLUDED.nombre, perfiles.nombre),
                estilo = COALESCE(EXCLUDED.estilo, perfiles.estilo),
                intereses = COALESCE(EXCLUDED.intereses, perfiles.intereses),
                estado_animo = COALESCE(EXCLUDED.estado_animo, perfiles.estado_animo),
                ultima_interaccion = CURRENT_TIMESTAMP
        """, (chat_id, nombre, estilo, intereses, estado_animo))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"❌ Error guardando perfil: {e}")

def obtener_perfil(chat_id):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM perfiles WHERE chat_id = %s", (chat_id,))
        perfil = cursor.fetchone()
        cursor.close()
        conn.close()
        return perfil if perfil else {'chat_id': chat_id, 'estilo': 'conversacional'}
    except Exception as e:
        logger.error(f"❌ Error obteniendo perfil: {e}")
        return {'chat_id': chat_id, 'estilo': 'conversacional'}

# ================== FUNCIONES AUXILIARES ==================
def es_pregunta_simple(texto):
    texto = texto.lower()
    if texto in ["hola", "buenos días", "buenas", "hey", "qué tal", "como estás"]:
        return True
    if any(p in texto for p in ["+", "-", "*", "/", "por", "entre", "más", "menos", "cuánto", "cuanto"]):
        return True
    if any(p in texto for p in ["precio", "tasa", "dólar", "dolar", "bcv"]):
        return True
    if len(texto.split()) < 5:
        return True
    return False

def es_pregunta_sobre_persona(texto):
    texto = texto.lower()
    if any(p in texto for p in ["quién es", "quien es", "quién fue", "quien fue"]):
        return True
    return False

def detectar_estado_animo(texto):
    texto = texto.lower()
    if any(p in texto for p in ["gracias", "feliz", "alegre", "genial", "excelente", "me encanta", "bueno"]):
        return "feliz"
    if any(p in texto for p in ["triste", "deprimido", "mal", "fatal", "horrible", "llorar", "me siento mal"]):
        return "triste"
    if any(p in texto for p in ["enojado", "molesto", "fastidiado", "cansado de esto", "rabia", "furia"]):
        return "enojado"
    if any(p in texto for p in ["cansado", "agotado", "estresado", "abrumado", "sin fuerzas"]):
        return "agotado"
    if any(p in texto for p in ["curioso", "interesante", "quiero saber", "enséñame", "explícame"]):
        return "curioso"
    return "neutral"

def detectar_tipo_creativo(texto):
    texto = texto.lower()
    if any(p in texto for p in ["poema", "poesía", "verso", "dime un poema", "escríbeme un poema"]):
        return "poesia"
    if any(p in texto for p in ["manifiesto", "declaración", "proclama", "escribe un manifiesto"]):
        return "manifiesto"
    if any(p in texto for p in ["predice", "proyección", "qué pasará", "escenario", "futuro de"]):
        return "prediccion"
    if any(p in texto for p in ["análisis profundo", "analiza a fondo", "estudio detallado"]):
        return "analisis_profundo"
    return None

# ================== FUNCIONES DE BASE DE DATOS ==================
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

def obtener_historia(chat_id, limite=10):
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

def extraer_texto_url(url):
    try:
        respuesta = requests.get(url, timeout=15)
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        return "\n".join(line.strip() for line in soup.get_text().splitlines() if line.strip())
    except Exception as e:
        logger.error(f"❌ Error extrayendo URL: {e}")
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

# ================== ANÁLISIS DE IMÁGENES ==================
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
        data = bot.download_file(file_info.file_path)
        img_b64 = process_image(data)
        if not img_b64:
            bot.reply_to(m, "❌ No pude procesar la imagen.")
            return
        prompt = m.caption if m.caption else "describe esta imagen"
        prompt_completo = f"{prompt}\n\nResponde siempre en español."
        bot.reply_to(m, "👁️‍🗨️ Analizando...")
        if not GROQ_API_KEY:
            bot.reply_to(m, "❌ No tengo clave de Groq para análisis de imágenes.")
            return
        try:
            response = client_groq.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt_completo}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]}],
                max_tokens=500
            )
            analysis = response.choices[0].message.content
        except Exception as e:
            logger.error(f"❌ Error en Groq Vision: {e}")
            bot.reply_to(m, "❌ No pude analizar la imagen.")
            return
        bot.reply_to(m, f"👁️‍🗨️ Análisis:\n\n{analysis}\n\nSoy Guaribe...")
    except Exception as e:
        logger.error(f"❌ Error en handle_photo: {e}")
        bot.reply_to(m, "❌ Ocurrió un error.")

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

# ================== MENÚ PRINCIPAL ==================
def menu_principal():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("💰 Tasa BCV"),
        KeyboardButton("📰 Noticias"),
        KeyboardButton("🔮 Analizar")
    )
    return markup

# ================== HANDLERS ==================
modo_analisis = {}

@bot.message_handler(commands=['start'])
def cmd_start(m):
    bot.reply_to(m, "¡Epale! Soy **Guaribe**.\n\n"
                    "Usa los botones:\n"
                    "💰 Tasa BCV\n📰 Noticias\n🔮 Analizar\n\n"
                    "🎨 `/imagen [descripción]`\n"
                    "📸 Envía foto con pregunta.\n"
                    "📝 También puedes pedirme poesía, manifiestos o predicciones.\n"
                    "¡Seguimos razonando! 🇻🇪🤠🏛️", 
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

    # ========== PERFIL Y ESTADO DE ÁNIMO (Fases 1 y 2) ==========
    perfil = obtener_perfil(chat_id)
    if not perfil.get('nombre'):
        if "mi nombre es" in texto_lower:
            partes = texto.split("mi nombre es")
            if len(partes) > 1:
                nombre_detectado = partes[1].strip().split()[0]
                guardar_perfil(chat_id, nombre=nombre_detectado)
                perfil = obtener_perfil(chat_id)
                bot.reply_to(m, f"✅ ¡Listo, {nombre_detectado}! Recordaré tu nombre.")
                return

    estado = detectar_estado_animo(texto)
    guardar_perfil(chat_id, estado_animo=estado)

    # ========== CREATIVIDAD (Fase 3) ==========
    tipo_creativo = detectar_tipo_creativo(texto)
    if tipo_creativo:
        if tipo_creativo == "poesia":
            prompt_activo = PROMPT_POESIA
        elif tipo_creativo == "manifiesto":
            prompt_activo = PROMPT_MANIFIESTO
        elif tipo_creativo == "prediccion":
            prompt_activo = PROMPT_PREDICCION
        else:
            prompt_activo = SYSTEM_PROMPT

        mensajes = [{"role": "system", "content": prompt_activo}]
        historia = obtener_historia(chat_id)
        mensajes.extend(historia)
        resp = orquestador.consultar(mensajes)
        bot.reply_to(m, resp)
        return

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

    # ========== TASA EN LENGUAJE NATURAL ==========
    if any(p in texto_lower for p in ["tasa", "dólar", "dolar", "bcv", "cambio"]):
        bot.reply_to(m, f"{obtener_tasa()}\n\nSoy Guaribe...", parse_mode='Markdown')
        return

    # ========== IMAGEN EN LENGUAJE NATURAL ==========
    palabras_imagen = ["crea", "genera", "dibuja", "haz", "quiero"]
    palabras_tipo = ["imagen", "dibujo", "foto", "infografía", "logo"]
    if any(p in texto_lower for p in palabras_imagen) and any(t in texto_lower for t in palabras_tipo):
        tipo = "infografia" if any(p in texto_lower for p in ["infografía", "infografia"]) else "general"
        prompt = texto
        for p in palabras_imagen + palabras_tipo:
            prompt = prompt.replace(p, "").strip()
        prompt = prompt.replace("de", "").replace("una", "").replace("un", "").strip()
        if not prompt:
            prompt = texto
        bot.reply_to(m, "🎨 Generando...")
        img = generar_imagen(prompt, tipo)
        if img:
            bot.send_photo(m.chat.id, img, caption=f"🎨 *{prompt}*\n\nSoy Guaribe...", parse_mode='Markdown')
        else:
            bot.reply_to(m, "❌ No pude generar la imagen.")
        return

    # ========== MODO ANÁLISIS ==========
    if chat_id in modo_analisis and modo_analisis[chat_id]:
        modo_analisis[chat_id] = False
        tema = texto
        bot.reply_to(m, f"📊 Analizando: {tema[:50]}...")
        contexto = buscar_contexto(tema)
        noticias = buscar_noticias()
        mensajes = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Tema: {tema}\nContexto histórico:\n{contexto}\nNoticias:\n{noticias}"}
        ]
        resp = orquestador.consultar(mensajes, usar_busqueda=False)
        bot.reply_to(m, resp, parse_mode='Markdown')
        return

    # ========== CONVERSACIÓN NORMAL ==========
    try:
        docs = buscar_conocimiento(chat_id, texto)
        contexto_docs = "\n\n[Documentos]\n" + "\n".join([f"'{d['nombre_archivo']}': {d['contenido'][:500]}" for d in docs]) if docs else ""

        contexto_personalidad = ""
        if perfil.get('nombre'):
            contexto_personalidad += f"El usuario se llama {perfil['nombre']}. "
        if perfil.get('estilo') == 'poetico':
            contexto_personalidad += "Prefiere un tono poético y reflexivo. "
        elif perfil.get('estilo') == 'directo':
            contexto_personalidad += "Prefiere respuestas directas y sin rodeos. "
        if perfil.get('estado_animo'):
            contexto_personalidad += f"Su estado de ánimo actual es: {perfil['estado_animo']}. Adáptate a su estado."

        usar_busqueda = es_pregunta_sobre_persona(texto)

        if es_pregunta_simple(texto):
            mensajes = [{"role": "system", "content": PROMPT_SIMPLE + contexto_docs + "\n\n" + contexto_personalidad}]
        else:
            mensajes = [{"role": "system", "content": SYSTEM_PROMPT + contexto_docs + "\n\n" + contexto_personalidad}]
            historia = obtener_historia(chat_id)
            mensajes.extend(historia)

        resp = orquestador.consultar(mensajes, usar_busqueda=usar_busqueda)
        bot.reply_to(m, resp)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        bot.reply_to(m, "Pana, hubo un error.")

# ================== MANEJO DE DOCUMENTOS ==================
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
    return jsonify({"status": "ok", "bot": "Guaribe 3.0 (Personalidad + Emoción + Creatividad)"}), 200

# ================== MAIN ==================
if __name__ == "__main__":
    logger.info("🚀 Iniciando Guaribe 3.0 (Personalidad + Emoción + Creatividad)...")
    init_db()
    port = int(os.environ.get("PORT", 10000))
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://guaribe-beta.onrender.com/webhook")
    logger.info("✅ Webhook configurado")
    logger.info("🧠 Cerebros disponibles: DeepSeek (con búsqueda), Groq")
    logger.info("🧬 Fases activas: Personalidad (Fase 1), Emoción (Fase 2), Creatividad (Fase 3)")
    app.run(host='0.0.0.0', port=port)
