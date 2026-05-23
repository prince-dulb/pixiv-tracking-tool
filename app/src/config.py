import os
import sys
import shutil
from pathlib import Path
from dotenv import load_dotenv

# PyInstaller 打包后资源在 _MEIPASS 临时目录，数据在可执行文件目录
if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    PROJECT_ROOT = Path(sys.executable).parent
    APP_DIR = BUNDLE_DIR  # 打包后所有资源在 _MEIPASS
else:
    BUNDLE_DIR = None
    PROJECT_ROOT = Path(__file__).parent.parent.parent  # 仓库根目录
    APP_DIR = Path(__file__).parent.parent  # app/ 目录


def resource_path(relative_path):
    """获取资源文件路径，兼容 PyInstaller 打包。"""
    if BUNDLE_DIR:
        return str(BUNDLE_DIR / relative_path)
    return str(APP_DIR / relative_path)


env_file = (PROJECT_ROOT if getattr(sys, 'frozen', False) else APP_DIR) / ".env"
if not env_file.exists():
    env_file.write_text("""\
# Pixiv Tracking Tool configuration
# First run will guide you through browser OAuth login

HOST=0.0.0.0
PORT=8000
# DATA_ROOT=.
CHECK_INTERVAL_HOURS=6
""", encoding='utf-8')

load_dotenv(env_file, encoding='utf-8')


def _resolve_data_root():
    v = os.getenv("DATA_ROOT", "").strip()
    if v:
        p = Path(v)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p
    if getattr(sys, 'frozen', False):
        return PROJECT_ROOT
    return APP_DIR


def _migrate_to_data_root():
    """首次用新代码启动时：若 .env 有旧的 IMAGES_DIR 但无 DATA_ROOT，自动迁移。"""
    content = env_file.read_text(encoding='utf-8')
    if 'DATA_ROOT=' in content:
        return

    old_images = os.getenv("IMAGES_DIR", "").strip()
    old_data = os.getenv("DATA_DIR", "data").strip()

    # 解析旧路径
    old_images_path = Path(old_images) if old_images else PROJECT_ROOT / "images"
    if not old_images_path.is_absolute():
        old_images_path = PROJECT_ROOT / old_images_path

    old_data_path = Path(old_data)
    if not old_data_path.is_absolute():
        old_data_path = PROJECT_ROOT / old_data_path

    # 目标路径
    _default_root = PROJECT_ROOT if getattr(sys, 'frozen', False) else APP_DIR
    new_images = _default_root / "images"
    new_data = _default_root / "data"

    new_images.mkdir(parents=True, exist_ok=True)
    new_data.mkdir(parents=True, exist_ok=True)

    # 迁移 images：从旧位置移动到 PROJECT_ROOT/images/
    if old_images_path.resolve() != new_images.resolve() and old_images_path.exists():
        for child in old_images_path.iterdir():
            dest = new_images / child.name
            if not dest.exists():
                shutil.move(str(child), str(dest))

    # 迁移 data：从旧位置复制到 PROJECT_ROOT/data/
    if old_data_path.resolve() != new_data.resolve() and old_data_path.exists():
        for child in old_data_path.iterdir():
            dest = new_data / child.name
            if not dest.exists():
                if child.is_dir():
                    shutil.copytree(str(child), str(dest))
                else:
                    shutil.copy2(str(child), str(dest))

    # 更新 .env：添加 DATA_ROOT，清理旧配置项
    lines = content.split('\n')
    lines = [l for l in lines
             if not l.startswith('IMAGES_DIR=')
             and not l.startswith('DATA_DIR=')]
    content = '\n'.join(lines).rstrip('\n') + '\nDATA_ROOT=.\n'
    env_file.write_text(content, encoding='utf-8')

    # 重载环境变量
    os.environ["DATA_ROOT"] = "."
    os.environ.pop("IMAGES_DIR", None)
    os.environ.pop("DATA_DIR", None)


# 执行迁移（必须在 _resolve_data_root 之前）
_migrate_to_data_root()

DATA_ROOT = _resolve_data_root()
DATA_DIR = DATA_ROOT / "data"
IMAGES_DIR = DATA_ROOT / "images"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'pixiv_tracker.db'}"


def set_data_root(new_path):
    """修改数据根目录并持久化到 .env，同时迁移已有数据。"""
    new_path = new_path.strip()
    new_root = Path(new_path)
    if not new_root.is_absolute():
        new_root = PROJECT_ROOT / new_root

    old_root = DATA_ROOT

    # 相同路径无需迁移
    if new_root.resolve() == old_root.resolve():
        return

    # 创建新目录结构
    new_data = new_root / "data"
    new_images = new_root / "images"
    new_data.mkdir(parents=True, exist_ok=True)
    new_images.mkdir(parents=True, exist_ok=True)

    # 复制 data/ 到新位置
    if DATA_DIR.exists():
        for child in DATA_DIR.iterdir():
            dest = new_data / child.name
            if not dest.exists():
                if child.is_dir():
                    shutil.copytree(str(child), str(dest))
                else:
                    shutil.copy2(str(child), str(dest))

    # 移动 images/ 到新位置
    if IMAGES_DIR.exists():
        for child in IMAGES_DIR.iterdir():
            dest = new_images / child.name
            if not dest.exists():
                shutil.move(str(child), str(dest))

    # 持久化到 .env
    content = env_file.read_text(encoding='utf-8') if env_file.exists() else ""
    new_val = str(new_root.resolve())

    if 'DATA_ROOT=' in content:
        # 用字符串替换，避免 re.sub 在 Windows 路径上的转义问题
        lines = content.split('\n')
        lines = [f'DATA_ROOT={new_val}' if l.startswith('DATA_ROOT=') else l for l in lines]
        content = '\n'.join(lines)
    else:
        content += f'\nDATA_ROOT={new_val}\n'

    env_file.write_text(content, encoding='utf-8')
    os.environ["DATA_ROOT"] = new_val

    # 运行时更新模块级变量
    import src.config
    src.config.DATA_ROOT = new_root
    src.config.DATA_DIR = new_data
    src.config.IMAGES_DIR = new_images
    src.config.DATABASE_URL = f"sqlite:///{new_data / 'pixiv_tracker.db'}"


# Pixiv auth
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN", "")

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Scheduler
CHECK_INTERVAL_HOURS = int(os.getenv("CHECK_INTERVAL_HOURS", "6"))
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "0")) or None

# Download
DOWNLOAD_WORKERS = int(os.getenv("DOWNLOAD_WORKERS", "3"))
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.0"))
