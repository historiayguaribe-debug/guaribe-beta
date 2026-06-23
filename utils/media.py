import requests
from io import BytesIO
from PIL import Image
from gtts import gTTS
import os

def generar_imagen(prompt: str, tipo: str = "general") -> BytesIO:
    try:
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
        tts = gTTS(text=texto[:500], lang='es', slow=False)
        audio_data = BytesIO()
        tts.write_to_fp(audio_data)
        audio_data.seek(0)
        return audio_data
    except:
        return None

def transcribir_audio(data: bytes, groq_client) -> str:
    if not groq_client:
        return None
    try:
        temp_path = "/tmp/audio.ogg"
        with open(temp_path, "wb") as f:
            f.write(data)
        with open(temp_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                file=(temp_path, f.read()),
                model="whisper-large-v3",
                response_format="text",
                language="es"
            )
        os.remove(temp_path)
        return transcription
    except:
        return None
