import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Pixiv auth
PIXIV_USERNAME = os.getenv("PIXIV_USERNAME", "")
PIXIV_PASSWORD = os.getenv("PIXIV_PASSWORD", "")
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN", "")

# Paths
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
IMAGES_DIR = PROJECT_ROOT / os.getenv("IMAGES_DIR", "images")
DATABASE_URL = f"sqlite:///{DATA_DIR / 'pixiv_tracker.db'}"

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Scheduler
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", "6"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "0")) or None

# Download
DOWNLOAD_WORKERS = int(os.getenv("DOWNLOAD_WORKERS", "3"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))
