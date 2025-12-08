# config.py
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TOKEN = os.getenv("TOKEN")
ADMIN = os.getenv("ADMIN")
ALLOWED_CHANNELS_IMPORT = os.getenv("ALLOWED_CH")

ALLOWED_CHANNELS = [ch.strip() for ch in ALLOWED_CHANNELS_IMPORT.split(",") if ch.strip()]