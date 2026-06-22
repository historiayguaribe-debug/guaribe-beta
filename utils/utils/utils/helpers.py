import re

def sanitizar_texto(texto: str) -> str:
    """Limpia caracteres especiales y espacios extra."""
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\w\s.,!?¿¡-]', '', texto)
    return texto.strip()
