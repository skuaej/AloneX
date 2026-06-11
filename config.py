import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------
# Core Bot Variables
# ---------------------------------------------------------
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# ---------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://...")

# ---------------------------------------------------------
# Dual-Channel Caching System Configuration
# ---------------------------------------------------------
# Dedicated Audio Cache Channel
try:
    AUDIO_CACHE_CHANNEL = int(os.getenv("AUDIO_CACHE_CHANNEL", "-1004068406600"))
except ValueError:
    AUDIO_CACHE_CHANNEL = None

# Dedicated Video Cache Channel
try:
    VIDEO_CACHE_CHANNEL = int(os.getenv("VIDEO_CACHE_CHANNEL", "-1003765204368"))
except ValueError:
    VIDEO_CACHE_CHANNEL = None

# ---------------------------------------------------------
# UI / Cosmetics
# ---------------------------------------------------------
DEFAULT_THUMB = os.getenv("DEFAULT_THUMB", "https://telegra.ph/file/default.jpg")
