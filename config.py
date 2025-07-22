# config.py
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TOKEN = os.getenv("TOKEN")
ADMIN = os.getenv("ADMIN")
ALLOWED_CHANNELS = os.getenv("ALLOWED_CH")
