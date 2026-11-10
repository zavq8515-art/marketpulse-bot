import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Windows/macOS tizim sertifikat omboridan foydalanish (antivirus/proksi bo'lsa SSL xatolarini oldini oladi)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@MarketPulseZK").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

CHECK_INTERVAL_MIN = _int("CHECK_INTERVAL_MIN", 10)
MAX_POSTS_PER_DAY = _int("MAX_POSTS_PER_DAY", 20)
MAX_POSTS_PER_RUN = _int("MAX_POSTS_PER_RUN", 2)
MIN_GAP_MIN = _int("MIN_GAP_MIN", 15)
MIN_IMPORTANCE = _int("MIN_IMPORTANCE", 7)
MAX_NEWS_AGE_HOURS = _int("MAX_NEWS_AGE_HOURS", 6)
QUIET_HOURS = os.getenv("QUIET_HOURS", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "true").strip().lower() in ("1", "true", "yes")

TASHKENT = ZoneInfo("Asia/Tashkent")
NEW_YORK = ZoneInfo("America/New_York")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / ("marketpulse_dryrun.db" if DRY_RUN else "marketpulse.db")
PREVIEW_DIR = DATA_DIR / "preview"
ASSETS_DIR = BASE_DIR / "assets"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
