import os
import re
from typing import List, Dict, Optional

# Ruta al archivo de conocimiento crítico
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'critical_knowledge.txt')

class KnowledgeLoader:
    """
    Carga y gestiona el conocimiento crítico desde un archivo de texto.
    """
    def __init__(self):
        self.raw_text = ""
        self.concepts = {}
        self.authors = {}
        self._cargar_conocimiento()

    def _cargar_conocimiento(self):
        """Carga el archivo de conocimiento en memoria."""
        try:
            if os.path.exists(KNOWLEDGE_PATH):
                with open(KNOWLEDGE_PATH, 'r', encoding='utf-8') as f:
                    self.raw_text = f.read()
                self._parsear_conocimiento()
            else:
                print(f"⚠️ Archivo de conocimiento no encontrado en: {KNOWLEDGE_PATH}")
                self.raw_text = "No se encontró el archivo de conocimiento."
        except Exception as e:
            print(f"❌ Error cargando conocimiento: {e}")
            self.raw_text = f"Error: {e}"

    def _parsear_conocimiento(self):
        """Convierte el texto en estructuras de datos."""
        # Dividir por secciones (entre corchetes)
        secciones = re.split(r'\[([^\]]+)\]', self.raw_text)
        
        # El primer elemento siempre está vacío (por el split)
        for i in range(1, len(secciones), 2):
            titulo = secciones[i].strip()
            contenido = secciones[i+1].strip()
            
            # Guardar como conceptos o autores según el título
            if "PENSADORES" in titulo.upper() or "AUTORES" in titulo.upper():
                # Cada línea es un autor: "Nombre: descripción"
                lineas = contenido.split('\n')
                for linea in lineas:
                    if ':' in linea:
                        autor, desc = linea.split(':', 1)
                        self.authors[autor.strip()] = desc.strip()
            else:
                # Es una sección de conceptos
                lineas = contenido.split('\n')
                for linea in lineas:
                    if ':' in linea:
                        concepto, desc = linea.split(':', 1)
                        self.concepts[concepto.strip()] = desc.strip()

    def buscar_conceptos(self, consulta: str) -> List[str]:
        """Busca conceptos relevantes en el conocimiento."""
        consulta_lower = consulta.lower()
        resultados = []
        
        # Buscar en conceptos
        for concepto, desc in self.concepts.items():
            if concepto.lower() in consulta_lower:
                resultados.append(f"{concepto}: {desc}")
        
        # Buscar en autores
        for autor, desc in self.authors.items():
            if autor.lower() in consulta_lower:
                resultados.append(f"{autor}: {desc}")
        
        return resultados

    def obtener_contexto_critico(self, consulta: str) -> str:
        """
        Devuelve un contexto enriquecido con el conocimiento crítico.
        """
        resultados = self.buscar_conceptos(consulta)
        if not resultados:
            # Si no hay coincidencias directas, devolver algunos conceptos clave por defecto
            conceptos_clave = ["Neoliberalismo", "Hegemonía cultural", "Guerra híbrida", "Autodeterminación"]
            for c in conceptos_clave:
                if c in self.concepts:
                    resultados.append(f"{c}: {self.concepts[c]}")
        
        if resultados:
            return "🔍 *Conocimiento crítico relevante:*\n" + "\n".join(resultados)
        else:
            return ""

"Agrega cargador de conocimiento crítico"

# Instancia global
knowledge = KnowledgeLoader()
