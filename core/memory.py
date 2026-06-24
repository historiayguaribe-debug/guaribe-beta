import os
import psycopg2
from psycopg2.extras import DictCursor
import numpy as np
from typing import List
import logging

logger = logging.getLogger(__name__)

# === MODELO CON LAZY LOADING ===
modelo = None

def get_model():
    """Carga el modelo de embeddings solo cuando se necesita."""
    global modelo
    if modelo is None:
        from sentence_transformers import SentenceTransformer
        modelo = SentenceTransformer('paraphrase-MiniLM-L3-v2', device='cpu')
    return modelo

def get_connection():
    """Crea una conexión a la base de datos."""
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def embed(texto: str) -> List[float]:
    """Convierte un texto en un vector de 384 dimensiones."""
    if not texto or len(texto) < 2:
        return [0.0] * 384
    return get_model().encode(texto, normalize_embeddings=True).tolist()

def guardar_mensaje(chat_id: int, rol: str, mensaje: str, conn=None):
    """Guarda un mensaje con su embedding en la base de datos."""
    if not mensaje or len(mensaje) < 3:
        return
    embedding = embed(mensaje)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mensajes (chat_id, rol, mensaje, embedding)
                VALUES (%s, %s, %s, %s)
            """, (chat_id, rol, mensaje, embedding))
            # Mantener solo los últimos 20 mensajes por chat
            cur.execute("""
                DELETE FROM mensajes
                WHERE chat_id = %s AND id NOT IN (
                    SELECT id FROM mensajes
                    WHERE chat_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 20
                )
            """, (chat_id, chat_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error guardando mensaje: {e}")
        if conn:
            conn.rollback()
    finally:
        if close_conn and conn:
            conn.close()

def buscar_contexto(chat_id: int, consulta: str, conn=None, limite: int = 3) -> List[str]:
    """Busca los mensajes más relevantes por similitud coseno."""
    embedding = embed(consulta)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT mensaje FROM mensajes
                WHERE chat_id = %s
                ORDER BY embedding <-> %s
                LIMIT %s
            """, (chat_id, embedding, limite))
            return [row['mensaje'] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error buscando contexto: {e}")
        return []
    finally:
        if close_conn and conn:
            conn.close()

def guardar_resumen(chat_id: int, resumen: str, temas: List[str], conn=None):
    """Guarda un resumen con embedding en la base de datos."""
    if not resumen or len(resumen) < 20:
        return
    embedding = embed(resumen)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO resumenes (chat_id, resumen, temas, embedding)
                VALUES (%s, %s, %s, %s)
            """, (chat_id, resumen, temas, embedding))
            # Mantener solo los últimos 10 resúmenes por chat
            cur.execute("""
                DELETE FROM resumenes
                WHERE chat_id = %s AND id NOT IN (
                    SELECT id FROM resumenes
                    WHERE chat_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 10
                )
            """, (chat_id, chat_id))
            conn.commit()
    except Exception as e:
        logger.error(f"Error guardando resumen: {e}")
        if conn:
            conn.rollback()
    finally:
        if close_conn and conn:
            conn.close()

def buscar_resumenes(chat_id: int, consulta: str, conn=None, limite: int = 2) -> List[str]:
    """Busca resúmenes relevantes por similitud coseno."""
    embedding = embed(consulta)
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT resumen FROM resumenes
                WHERE chat_id = %s
                ORDER BY embedding <-> %s
                LIMIT %s
            """, (chat_id, embedding, limite))
            return [row['resumen'] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Error buscando resúmenes: {e}")
        return []
    finally:
        if close_conn and conn:
            conn.close()
