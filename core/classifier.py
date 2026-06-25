import pickle
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier

MODEL_PATH = "data/classifier.pkl"

EJEMPLOS_INICIALES = [
    # Saludos
    ("Hola", "saludo"),
    ("Buenos días", "saludo"),
    ("¿Cómo estás?", "saludo"),
    
    # Simples
    ("Tasa BCV", "simple"),
    ("Cuánto está el dólar", "simple"),
    ("2+2", "simple"),
    ("Cuánto es 15+27", "simple"),
    
    # Complejas (política, economía)
    ("Analiza la guerra híbrida", "compleja"),
    ("¿Qué opinas de Maduro?", "compleja"),
    ("Explica el bloqueo económico a Venezuela", "compleja"),
    
    # Creativas
    ("Dame un poema", "creativa"),
    ("Escribe un manifiesto", "creativa"),
    
    # Noticias
    ("Noticias de hoy", "noticias"),
    ("¿Qué pasó en Venezuela?", "noticias"),
    
    # Preguntas sobre personas
    ("Quién es María Corina Machado", "pregunta_persona"),
    ("Quién es el presidente de Venezuela", "pregunta_persona"),
    
    # Imagen
    ("Genera una imagen de un paisaje", "imagen"),
    
    # Archivo
    ("Subo un PDF", "archivo"),
    
    # === NUEVOS EJEMPLOS CULTURALES ===
    ("Cuéntame algo sobre el llano venezolano", "cultural"),
    ("Qué es la cultura venezolana", "cultural"),
    ("Historia de Venezuela", "cultural"),
    ("Tradiciones venezolanas", "cultural"),
    ("Cómo se hace una arepa", "cultural"),
    ("Qué es el joropo", "cultural"),
    ("Quién fue Simón Bolívar", "cultural"),
    ("Qué es el folklore venezolano", "cultural"),
    ("Dónde queda el llano", "cultural"),
    ("Costumbres de los llaneros", "cultural"),
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
        textos = [ej[0] for ej in self.ejemplos]
        etiquetas = [ej[1] for ej in self.ejemplos]
        self.vectorizer = TfidfVectorizer(max_features=1000)
        X = self.vectorizer.fit_transform(textos)
        self.clf = RandomForestClassifier(n_estimators=50, random_state=42)
        self.clf.fit(X, etiquetas)
        self.guardar()
    
    def guardar(self):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, 'wb') as f:
            pickle.dump((self.vectorizer, self.clf), f)
    
    def clasificar(self, texto: str) -> str:
        if not texto or len(texto) < 2:
            return "simple"
        texto = texto.lower().strip()
        # Reglas rápidas para saludos y culturales (por si el modelo falla)
        if any(p in texto for p in ["hola", "buen", "saludos", "que tal"]):
            return "saludo"
        # Detectar palabras clave culturales como respaldo
        if any(p in texto for p in ["llano", "cultura", "historia", "tradición", "venezolano", "costumbre"]):
            return "cultural"
        try:
            X = self.vectorizer.transform([texto])
            return self.clf.predict(X)[0]
        except:
            # Fallback por reglas
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
        if feedback == 1 and len(texto) > 10:
            self.ejemplos.append((texto, categoria))
            self.contador += 1
            if self.contador >= 20:
                self.entrenar()
                self.contador = 0

clasificador = Clasificador()
