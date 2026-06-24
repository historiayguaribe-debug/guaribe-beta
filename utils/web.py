import re
from datetime import datetime

def obtener_tasa():
    try:
        import requests
        r = requests.get("https://ve.dolarapi.com/v1/dolares", timeout=10)
        # ... resto del código
    except:
        return "💰 Error al consultar la tasa."

# ... (buscar_noticias y buscar_en_web con imports internos)
