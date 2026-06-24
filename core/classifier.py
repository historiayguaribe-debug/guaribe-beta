import pickle
import os
import re

MODEL_PATH = "data/classifier.pkl"

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
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, 'rb') as f:
                    self.vectorizer, self.clf = pickle.load(f)
                return
            except:
                pass
        self.entrenar()

    def entrenar(self):
        # Importar sklearn solo cuando se entrena
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.ensemble import RandomForestClassifier
        textos = [ej[0] for ej in self.ejemplos]
        etiquetas = [ej[1] for ej in self.ejemplos]
        self.vectorizer = TfidfVectorizer(max_features=1000)
        X = self.vectorizer.fit_transform(textos)
        self.clf = RandomForestClassifier(n_estimators=50, random_state=42)
        self.clf.fit(X, etiquetas)
        self.guardar()

    # ... (resto de métodos guardar, clasificar, actualizar)
