import os
import logging
import numpy as np
from typing import List

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
    import psycopg2
    return psycopg2.connect(os.environ.get("DATABASE_URL"))

def embed(texto: str) -> List[float]:
    if not texto or len(texto) < 2:
        return [0.0] * 384
    return get_model().encode(texto, normalize_embeddings=True).tolist()

# ... (resto de las funciones guardar_mensaje, buscar_contexto, etc.)
# Asegúrate de que todas usen get_model() y get_connection()
