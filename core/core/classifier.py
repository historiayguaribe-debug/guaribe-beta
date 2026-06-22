import pickle
import os
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
import numpy as np
from typing import Tuple

MODEL_PATH = "data/classifier.pkl"

# Dataset de entrenamiento (mínimo, se expandirá con feedback)
EJEMPLOS_INICIALES = [
    ("Hola", "saludo"),
    ("Buenos días", "saludo"),
    ("¿Cómo estás?", "saludo"),
    ("Tasa BCV", "simple"),
    ("Cuánto está el dólar", "simple"),
    ("2+2", "simple"),
    ("Analiza la guerra híbrida", "compleja"),
    ("¿Qué opinas de Maduro?", "compleja"),
    ("Dame un poema", "creativa"),
    ("Escribe un manifiesto", "creativa"),
    ("Noticias de hoy", "noticias"),
    ("¿Qué pasó en Venezuela?", "noticias"),
    ("Quién es María Corina Machado", "pregunta_persona"),
    ("Genera una imagen de un paisaje", "imagen"),
    ("Subo un PDF", "archivo"),
]

class Clasificador:
    def __init__(self):
        self.vectorizer = None
        self.clf = None
        self.ejemplos = EJEMPLOS_INICIALES.copy()
        self.contador = 0
        self.cargar_o_entrenar()
    
    def cargar_o_entrenar(self):
        """Carga el modelo si existe, o lo entrena desde cero."""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, 'rb') as f:
                    self.vectorizer, self.clf = pickle.load(f)
                return
            except:
                pass
        self.entrenar()
    
    def entrenar(self):
        """Entrena el modelo con los ejemplos actuales."""
        textos = [ej[0] for ej in self.ejemplos]
        etiquetas = [ej[1] for ej in self.ejemplos]
        self.vectorizer = TfidfVectorizer(max_features=1000)
        X = self.vectorizer.fit_transform(textos)
        self.clf = RandomForestClassifier(n_estimators=50, random_state=42)
        self.clf.fit(X, etiquetas)
        self.guardar()
    
    def guardar(self):
        """Guarda el modelo en disco."""
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump((self.vectorizer, self.clf), f)
    
    def clasificar(self, texto: str) -> str:
        """Clasifica el mensaje en una categoría."""
        if not texto or len(texto) < 2:
            return "simple"
        # Normalizar texto
        texto = texto.lower().strip()
        # Si contiene saludos comunes, clasificar como saludo
        if any(p in texto for p in ["hola", "buen", "saludos", "que tal", "como estas"]):
            return "saludo"
        try:
            X = self.vectorizer.transform([texto])
            return self.clf.predict(X)[0]
        except:
            # Fallback: reglas simples si el modelo falla
            if "tasa" in texto or "dólar" in texto or "bcv" in texto:
                return "simple"
            if "noticias" in texto or "qué pasó" in texto:
                return "noticias"
            if "imagen" in texto or "genera" in texto:
                return "imagen"
            if "poema" in texto or "manifiesto" in texto:
                return "creativa"
            if "quién es" in texto or "quien es" in texto:
                return "pregunta_persona"
            if len(texto) > 50:
                return "compleja"
            return "simple"
    
    def actualizar(self, texto: str, categoria: str, feedback: int):
        """Actualiza el modelo con feedback del usuario (👍/👎)."""
        # Solo si el feedback es positivo y el texto es relevante
        if feedback == 1 and len(texto) > 10:
            self.ejemplos.append((texto, categoria))
            self.contador += 1
            # Reentrenar cada 20 nuevos ejemplos
            if self.contador >= 20:
                self.entrenar()
                self.contador = 0

# Instancia global
clasificador = Clasificador()
