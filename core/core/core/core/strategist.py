import re
from collections import defaultdict
from datetime import datetime

class Estratega:
    def __init__(self):
        self.patrones = defaultdict(lambda: defaultdict(int))
        self.ultimas_preguntas = {}
    
    def aprender(self, chat_id: int, pregunta: str, respuesta: str):
        """Aprende patrones de conversación."""
        # Guardar última pregunta
        self.ultimas_preguntas[chat_id] = pregunta
        
        # Extraer palabras clave
        palabras = re.findall(r'\b\w+\b', pregunta.lower())
        for p in palabras:
            if len(p) > 3:
                self.patrones[chat_id][p] += 1
    
    def sugerir(self, chat_id: int, consulta_actual: str) -> str:
        """Sugiere una pregunta relacionada."""
        if chat_id not in self.patrones:
            return None
        
        # Palabras clave de la consulta actual
        palabras = re.findall(r'\b\w+\b', consulta_actual.lower())
        # Buscar patrones relacionados
        for p in palabras:
            if p in self.patrones[chat_id]:
                if self.patrones[chat_id][p] > 2:
                    return f"¿Quieres saber más sobre {p}?"
        return None

estratega = Estratega()
