import json
from pathlib import Path
from pixivpy3 import AppPixivAPI

from .config import PIXIV_USERNAME, PIXIV_PASSWORD, PIXIV_REFRESH_TOKEN, DATA_DIR

TOKEN_FILE = DATA_DIR / "pixiv_token.json"


def login():
    """首次登录或 token 失效时用账号密码登录，返回 API 实例和 token。"""
    api = AppPixivAPI()
    api.login(PIXIV_USERNAME, PIXIV_PASSWORD)
    token = {
        "access_token": api.access_token,
        "refresh_token": api.refresh_token,
    }
    TOKEN_FILE.write_text(json.dumps(token))
    return api


def auth():
    """优先用 refresh_token 恢复会话，失败则用账号密码重新登录。"""
    api = AppPixivAPI()

    # 先尝试从文件加载 token
    if TOKEN_FILE.exists():
        saved = json.loads(TOKEN_FILE.read_text())
        refresh_token = saved.get("refresh_token", "")
    else:
        refresh_token = PIXIV_REFRESH_TOKEN

    if refresh_token:
        try:
            api.auth(refresh_token=refresh_token)
            # 更新本地的 token
            token = {
                "access_token": api.access_token,
                "refresh_token": api.refresh_token,
            }
            TOKEN_FILE.write_text(json.dumps(token))
            return api
        except Exception:
            pass

    # refresh token 不可用，用账号密码登录
    if not PIXIV_USERNAME or not PIXIV_PASSWORD:
        raise RuntimeError(
            "Pixiv 未登录。请设置 PIXIV_USERNAME 和 PIXIV_PASSWORD 环境变量，"
            "或将 PIXIV_REFRESH_TOKEN 写入 .env 或 data/pixiv_token.json"
        )

    return login()
