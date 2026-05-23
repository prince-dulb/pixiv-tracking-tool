import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# PyInstaller 打包后资源在 _MEIPASS 临时目录，数据在可执行文件目录
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)  # 静态资源临时解压目录
    PROJECT_ROOT = Path(sys.executable).parent  # 用户数据目录（data/, images/, .env）
else:
    BUNDLE_DIR = None
    PROJECT_ROOT = Path(__file__).parent.parent


def resource_path(relative_path):
    """获取资源文件路径，兼容 PyInstaller 打包。"""
    if BUNDLE_DIR:
        return str(BUNDLE_DIR / relative_path)
    return str(PROJECT_ROOT / relative_path)

env_file = PROJECT_ROOT / ".env"
if not env_file.exists():
    env_file.write_text("""\
# Pixiv Tracking Tool configuration
# First run will guide you through browser OAuth login

HOST=0.0.0.0
PORT=8000
# IMAGES_DIR=images
CHECK_INTERVAL_HOURS=6
""", encoding='utf-8')
load_dotenv(env_file, encoding='utf-8')

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
    content = env_file.read_text(encoding='utf-8') if env_file.exists() else ""
    if "IMAGES_DIR=" in content:
        content = re.sub(r'IMAGES_DIR=.*', f'IMAGES_DIR={new_path}', content)
    else:
        content += f'\nIMAGES_DIR={new_path}\n'
    env_file.write_text(content, encoding='utf-8')
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
