import os
from io import BytesIO

def generar_imagen(prompt: str, tipo: str = "general") -> BytesIO:
    try:
        import requests
        from PIL import Image  # Import dentro de la función
        prompt_limpio = prompt.replace(' ', '%20')
        if tipo == "infografia":
            prompt_limpio = f"infografía profesional sobre {prompt_limpio}, diseño moderno"
        elif tipo == "logo":
            prompt_limpio = f"logo minimalista para {prompt_limpio}, sin fondo"
        url = f"https://image.pollinations.ai/prompt/{prompt_limpio}?width=1024&height=1024&nologo=true"
        r = requests.get(url, timeout=60)
        if r.status_code == 200 and r.content:
            return BytesIO(r.content)
        return None
    except:
        return None

def generar_audio(texto: str) -> BytesIO:
    try:
        from gtts import gTTS  # Import dentro de la función
        tts = gTTS(text=texto[:500], lang='es', slow=False)
        audio_data = BytesIO()
        tts.write_to_fp(audio_data)
        audio_data.seek(0)
        return audio_data
    except:
        return None

# ... (transcribir_audio sin cambios, ya es liviano)
