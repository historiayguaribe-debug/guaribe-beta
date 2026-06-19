# ================== CONEXIÓN A BASE DE DATOS (SIN POOL) ==================

def get_connection():
    """Obtiene una conexión efímera bajo demanda. Se cierra automáticamente al salir del 'with'."""
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        conn.autocommit = False  # Controlamos los commits manualmente
        return conn
    except Exception as e:
        logger.error(f"❌ Error crítico conectando a DB: {e}")
        raise

# ================== FUNCIONES DE BASE DE DATOS (REFACTORIZADAS) ==================

def init_db():
    """Inicializa tablas usando el nuevo patrón 'with'."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
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
                        preferencia_audio BOOLEAN DEFAULT FALSE,
                        ultima_interaccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS memoria_larga (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        resumen TEXT NOT NULL,
                        temas TEXT[],
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS notas (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        texto TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recordatorios (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        texto TEXT NOT NULL,
                        fecha_hora TIMESTAMP NOT NULL,
                        enviado BOOLEAN DEFAULT FALSE,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS feedback (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        respuesta TEXT NOT NULL,
                        puntuacion INTEGER CHECK (puntuacion IN (1, -1)),
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_chat_ts ON conversaciones (chat_id, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_memoria_larga_chat_ts ON memoria_larga (chat_id, timestamp);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_chat ON conocimiento (chat_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_chat ON feedback (chat_id);")
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_conocimiento_contenido_trgm ON conocimiento USING gin (contenido gin_trgm_ops);")
                conn.commit()
                logger.info("✅ Base de datos inicializada con todas las tablas e índices")
    except Exception as e:
        logger.error(f"❌ Error en init_db: {e}")
        raise


def guardar_perfil(chat_id, nombre=None, estilo=None, intereses=None, estado_animo=None, preferencia_audio=None):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO perfiles (chat_id, nombre, estilo, intereses, estado_animo, preferencia_audio)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET
                        nombre = COALESCE(EXCLUDED.nombre, perfiles.nombre),
                        estilo = COALESCE(EXCLUDED.estilo, perfiles.estilo),
                        intereses = COALESCE(EXCLUDED.intereses, perfiles.intereses),
                        estado_animo = COALESCE(EXCLUDED.estado_animo, perfiles.estado_animo),
                        preferencia_audio = COALESCE(EXCLUDED.preferencia_audio, perfiles.preferencia_audio),
                        ultima_interaccion = CURRENT_TIMESTAMP
                """, (chat_id, nombre, estilo, intereses, estado_animo, preferencia_audio))
                conn.commit()
    except Exception as e:
        logger.error(f"❌ Error guardar_perfil: {e}")


def obtener_perfil(chat_id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT * FROM perfiles WHERE chat_id = %s", (chat_id,))
                perfil = cursor.fetchone()
                return perfil if perfil else {'chat_id': chat_id, 'estilo': 'conversacional', 'preferencia_audio': False}
    except Exception as e:
        logger.error(f"❌ Error obtener_perfil: {e}")
        return {'chat_id': chat_id, 'estilo': 'conversacional', 'preferencia_audio': False}


def guardar_mensaje(chat_id, rol, mensaje):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conversaciones (chat_id, rol, mensaje) VALUES (%s, %s, %s)",
                    (chat_id, rol, mensaje)
                )
                conn.commit()
    except Exception as e:
        logger.error(f"❌ Error guardar_mensaje: {e}")


def obtener_historia(chat_id, limite=10):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT rol, mensaje FROM conversaciones 
                    WHERE chat_id = %s 
                    ORDER BY timestamp DESC 
                    LIMIT %s
                """, (chat_id, limite))
                filas = cursor.fetchall()
                return [{"role": f["rol"], "content": f["mensaje"]} for f in reversed(filas)]
    except Exception as e:
        logger.error(f"❌ Error obtener_historia: {e}")
        return []


def guardar_conocimiento(chat_id, nombre, contenido):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO conocimiento (chat_id, nombre_archivo, contenido) VALUES (%s, %s, %s)",
                    (chat_id, nombre, contenido[:50000])
                )
                conn.commit()
    except Exception as e:
        logger.error(f"❌ Error guardar_conocimiento: {e}")


def buscar_conocimiento(chat_id, consulta):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT nombre_archivo, contenido 
                    FROM conocimiento 
                    WHERE chat_id = %s 
                    ORDER BY similarity(contenido, %s) DESC 
                    LIMIT 3
                """, (chat_id, consulta))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ Error buscar_conocimiento: {e}")
        return []


def guardar_nota(chat_id, texto):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO notas (chat_id, texto) VALUES (%s, %s)", (chat_id, texto))
                conn.commit()
                return "✅ Nota guardada."
    except Exception as e:
        logger.error(f"❌ Error guardar_nota: {e}")
        return "❌ Error guardando nota."


def obtener_notas(chat_id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("SELECT texto, timestamp FROM notas WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 10", (chat_id,))
                notas = cursor.fetchall()
                if not notas:
                    return "📝 No tienes notas guardadas."
                return "📝 Tus últimas notas:\n" + "\n".join([f"- {n['texto']} ({n['timestamp'].strftime('%d/%m/%Y %H:%M')})" for n in notas])
    except Exception as e:
        logger.error(f"❌ Error obtener_notas: {e}")
        return "❌ Error obteniendo notas."


def guardar_recordatorio(chat_id, texto, fecha_hora):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO recordatorios (chat_id, texto, fecha_hora) VALUES (%s, %s, %s)",
                    (chat_id, texto, fecha_hora)
                )
                conn.commit()
                return f"✅ Recordatorio guardado para {fecha_hora.strftime('%d/%m/%Y %H:%M')}."
    except Exception as e:
        logger.error(f"❌ Error guardar_recordatorio: {e}")
        return "❌ Error guardando recordatorio."


def revisar_recordatorios():
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                ahora = datetime.datetime.now()
                cursor.execute(
                    "SELECT id, chat_id, texto, fecha_hora FROM recordatorios WHERE enviado = FALSE AND fecha_hora <= %s",
                    (ahora,)
                )
                pendientes = cursor.fetchall()
                for r in pendientes:
                    try:
                        bot.send_message(r['chat_id'], f"⏰ *Recordatorio:* {r['texto']}\n\n(Programado para {r['fecha_hora'].strftime('%d/%m/%Y %H:%M')})", parse_mode='Markdown')
                        cursor.execute("UPDATE recordatorios SET enviado = TRUE WHERE id = %s", (r['id'],))
                        conn.commit()
                    except Exception as e:
                        logger.error(f"❌ Error enviando recordatorio {r['id']}: {e}")
                return f"✅ Revisados {len(pendientes)} recordatorios."
    except Exception as e:
        logger.error(f"❌ Error revisar_recordatorios: {e}")
        return "❌ Error revisando recordatorios."


def guardar_feedback(chat_id, respuesta, puntuacion):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO feedback (chat_id, respuesta, puntuacion) VALUES (%s, %s, %s)",
                    (chat_id, respuesta, puntuacion)
                )
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"❌ Error guardar_feedback: {e}")
        return False


def obtener_feedback_relevante(chat_id):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT respuesta, puntuacion FROM feedback WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 20",
                    (chat_id,)
                )
                datos = cursor.fetchall()
                negativos = [d['respuesta'] for d in datos if d['puntuacion'] == -1]
                if negativos:
                    return "El usuario ha dado feedback negativo a respuestas similares en el pasado. Evita repetir esos enfoques."
                return ""
    except Exception as e:
        logger.error(f"❌ Error obtener_feedback_relevante: {e}")
        return ""


def necesita_compresion(chat_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT MAX(timestamp) FROM memoria_larga WHERE chat_id = %s", (chat_id,))
                ultima = cursor.fetchone()[0]
                if ultima:
                    cursor.execute("SELECT COUNT(*) FROM conversaciones WHERE chat_id = %s AND timestamp > %s", (chat_id, ultima))
                    count = cursor.fetchone()[0]
                    return count > 15
                else:
                    cursor.execute("SELECT COUNT(*) FROM conversaciones WHERE chat_id = %s", (chat_id,))
                    count = cursor.fetchone()[0]
                    return count > 15
    except Exception as e:
        logger.error(f"❌ Error necesita_compresion: {e}")
        return False


def comprimir_conversacion(chat_id):
    if not necesita_compresion(chat_id):
        return None
    historia = obtener_historia(chat_id, limite=15)
    if len(historia) < 4:
        return None
    texto_historia = "\n".join([f"{h['role']}: {h['content']}" for h in historia])
    prompt_compresor = f"""
    Eres el archivista de Guaribe. Resume la siguiente conversación en una cápsula de memoria.
    Extrae los temas principales (máximo 3), el tono emocional, y los datos relevantes del usuario.
    Conversación:
    {texto_historia}
    Responde ÚNICAMENTE en formato JSON sin markdown:
    {{"resumen": "texto conciso de 100 palabras máximo", "temas": ["tema1", "tema2", "tema3"]}}
    """
    try:
        respuesta = orquestador._consultar_deepseek([{"role": "user", "content": prompt_compresor}])
        json_str = re.sub(r'```json|```', '', respuesta).strip()
        datos = json.loads(json_str)
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memoria_larga (chat_id, resumen, temas) VALUES (%s, %s, %s)",
                    (chat_id, datos['resumen'], datos['temas'])
                )
                conn.commit()
                logger.info(f"🧠 Memoria comprimida para {chat_id}: {datos['temas']}")
        return datos
    except Exception as e:
        logger.error(f"❌ Error comprimiendo memoria: {e}")
        return None


def recuperar_memorias_relevantes(chat_id, consulta):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    "SELECT resumen, temas FROM memoria_larga WHERE chat_id = %s ORDER BY timestamp DESC LIMIT 20",
                    (chat_id,)
                )
                registros = cursor.fetchall()
                if not registros:
                    return []
                texto_memorias = "\n".join([f"- {r['resumen']} (Temas: {', '.join(r['temas'])})" for r in registros])
                prompt_selector = f"""
                Dada la consulta del usuario: "{consulta}"
                Estas son las memorias del usuario:
                {texto_memorias}
                Devuelve ÚNICAMENTE los IDs (números de línea) de las memorias que SON RELEVANTES para esta consulta.
                Si ninguna es relevante, devuelve "NINGUNA".
                Formato de respuesta: "1, 3, 5"
                """
                respuesta = orquestador._consultar_deepseek([{"role": "user", "content": prompt_selector}])
                if "NINGUNA" in respuesta:
                    return []
                indices = [int(x.strip()) for x in respuesta.split(',') if x.strip().isdigit()]
                relevantes = [registros[i-1] for i in indices if 0 < i <= len(registros)]
                return [r['resumen'] for r in relevantes]
    except Exception as e:
        logger.error(f"❌ Error recuperar_memorias: {e}")
        return []
