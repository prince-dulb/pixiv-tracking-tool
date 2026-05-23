import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# PyInstaller 打包后 __file__ 不可用，用 sys._MEIPASS 或可执行文件目录
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# Pixiv auth
PIXIV_USERNAME = os.getenv("PIXIV_USERNAME", "")
PIXIV_PASSWORD = os.getenv("PIXIV_PASSWORD", "")
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN", "")

# Paths
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")

def _resolve_images_dir():
    v = os.getenv("IMAGES_DIR", "images")
    p = Path(v)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p

IMAGES_DIR = _resolve_images_dir()
DATABASE_URL = f"sqlite:///{DATA_DIR / 'pixiv_tracker.db'}"


def set_images_dir(new_path: str):
    """修改图片存储路径并持久化到 .env。"""
    import re
    env_file = PROJECT_ROOT / ".env"
    content = env_file.read_text() if env_file.exists() else ""
    if "IMAGES_DIR=" in content:
        content = re.sub(r'IMAGES_DIR=.*', f'IMAGES_DIR={new_path}', content)
    else:
        content += f'\nIMAGES_DIR={new_path}\n'
    env_file.write_text(content)
    os.environ["IMAGES_DIR"] = new_path

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Scheduler
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", "6"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "0")) or None

# Download
DOWNLOAD_WORKERS = int(os.getenv("DOWNLOAD_WORKERS", "3"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))
