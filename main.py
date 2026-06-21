from gevent import monkey
monkey.patch_all()

import os
import time
import telebot
import requests
import logging
import psycopg2
import PyPDF2
import docx
import base64
import json
import re
import datetime
import hashlib
import threading
from flask import Flask, request, jsonify
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
from psycopg2.extras import DictCursor
from io import BytesIO
from PIL import Image
from groq import Groq
from gtts import gTTS

# ==================== CONFIGURACIÓN ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")   # Su chat_id
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")     # Clave secreta

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ... (todo el código existente, igual que antes, pero con las adiciones de limpieza)

# ==================== COMANDOS DE ADMINISTRACIÓN ====================
@bot.message_handler(commands=['admin_clean'])
def cmd_admin_clean(m):
    if str(m.chat.id) != ADMIN_CHAT_ID:
        bot.reply_to(m, "⛔ No autorizado.")
        return
    bot.reply_to(m, "🧹 Limpiando base de datos...")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conocimiento;")
                cur.execute("DELETE FROM conversaciones WHERE LENGTH(mensaje) < 3 OR mensaje IN ('Hola', 'hola', '/star', 'Oye tiempo que no te escribia', 'Cómo estás pana', 'como estas', 'buenas', 'hey', 'epa', 'epale');")
                conn.commit()
                bot.reply_to(m, "✅ Base de datos limpiada:\n- conocimiento: eliminado\n- conversaciones: ruido eliminado")
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")

# ==================== ENDPOINTS FLASK ====================
@app.route('/admin/clean', methods=['GET'])
def admin_clean():
    secret = request.args.get('secret')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "No autorizado"}), 403
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conocimiento;")
                cur.execute("DELETE FROM conversaciones WHERE LENGTH(mensaje) < 3 OR mensaje IN ('Hola', 'hola', '/star', 'Oye tiempo que no te escribia', 'Cómo estás pana', 'como estas', 'buenas', 'hey', 'epa', 'epale');")
                conn.commit()
                return jsonify({"status": "ok", "message": "Base de datos limpiada"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ... (resto del código igual)
