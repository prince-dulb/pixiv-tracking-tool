import json
import hashlib
import secrets
import base64
import webbrowser
import requests
from pathlib import Path
from datetime import datetime
from requests.structures import CaseInsensitiveDict

import gallery_dl.config as gdl_config

from .config import PIXIV_REFRESH_TOKEN, DATA_DIR

TOKEN_FILE = DATA_DIR / "pixiv_token.json"

# gallery-dl 内置的 Pixiv 客户端凭证
CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"


def _save_token(access_token, refresh_token):
    TOKEN_FILE.write_text(json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
    }))


def _load_token():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def _try_refresh_token():
    """尝试用本地保存的或 .env 中的 refresh_token 恢复会话。"""
    saved = _load_token()
    refresh_token = saved.get("refresh_token") or PIXIV_REFRESH_TOKEN

    if not refresh_token:
        return None

    try:
        # 用 refresh_token 获取新的 access_token
        local_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        headers = CaseInsensitiveDict({
            "x-client-time": local_time,
            "x-client-hash": hashlib.md5(
                (local_time + HASH_SECRET).encode("utf-8")
            ).hexdigest(),
            "app-os": "ios",
            "app-os-version": "14.6",
            "user-agent": "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)",
        })

        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "get_secure_url": "1",
        }

        r = requests.post(
            "https://oauth.secure.pixiv.net/auth/token",
            headers=headers, data=data, timeout=30,
        )

        if r.status_code != 200:
            return None

        resp = r.json()
        access_token = resp["access_token"]
        new_refresh_token = resp.get("refresh_token", refresh_token)
        _save_token(access_token, new_refresh_token)
        return new_refresh_token

    except Exception:
        return None


def _oauth_pkce():
    """通过浏览器 OAuth PKCE 流程获取 refresh_token。"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    login_url = (
        "https://app-api.pixiv.net/web/v1/login"
        f"?code_challenge={code_challenge}"
        "&code_challenge_method=S256"
        "&client=pixiv-android"
    )

    print("\n" + "=" * 55)
    print("  Pixiv 需要浏览器授权登录")
    print("=" * 55)
    print(f"\n1. 在浏览器中打开以下链接：\n\n  {login_url}\n")
    print("2. 登录你的 Pixiv 账号")
    print("3. 登录成功后浏览器会跳转到一个以 pixiv:// 开头的空白页")
    print("   -> 点击浏览器地址栏，复制完整的 URL")
    print("   -> 格式类似: pixiv://account/authorize?code=...&state=...\n")

    try:
        webbrowser.open(login_url)
        print("  (已尝试自动打开浏览器)\n")
    except Exception:
        pass

    callback_url = input("  >> 粘贴 pixiv:// 开头的 URL: ").strip()

    code = _extract_code(callback_url)
    if not code:
        print("\n[X] 未能从 URL 中提取授权码。\n")
        return None

    local_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    headers = CaseInsensitiveDict({
        "x-client-time": local_time,
        "x-client-hash": hashlib.md5(
            (local_time + HASH_SECRET).encode("utf-8")
        ).hexdigest(),
        "app-os": "ios",
        "app-os-version": "14.6",
        "user-agent": "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)",
    })

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "get_secure_url": "1",
    }

    r = requests.post(
        "https://oauth.secure.pixiv.net/auth/token",
        headers=headers, data=data, timeout=30,
    )

    if r.status_code != 200:
        print(f"\n[X] Token 交换失败: HTTP {r.status_code}")
        print(f"  {r.text}\n")
        return None

    resp = r.json()
    _save_token(resp["access_token"], resp["refresh_token"])
    print("\n[OK] 登录成功！\n")
    return resp["refresh_token"]


def _extract_code(url_string):
    """从回调 URL 中提取 authorization code。"""
    from urllib.parse import urlparse, parse_qs

    if not url_string:
        return None

    url_string = url_string.strip()

    # 用户可能粘贴了重定向过程中的中间 URL，提示他们找最终的跳转 URL
    if "accounts.pixiv.net" in url_string:
        print("\n  [!] 你粘贴的是登录过程中的中间跳转 URL，不是最终的回调地址。")
        print("  登录成功后浏览器会跳转到一个以 pixiv:// 开头的空白页。")
        print("  请复制那个页面的完整地址。\n")
        return None

    # 尝试从 URL query 参数中提取
    parsed = urlparse(url_string)
    params = parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if code:
        return code

    # pixiv:// 回调 URL：scheme 可能被解析为 hostname
    # 格式: pixiv://account/authorize?code=xxx&state=xxx
    if parsed.scheme == "pixiv":
        print("\n  [!] 未能从 pixiv:// URL 中提取到 code 参数。")
        print("  请确认复制的是完整 URL，例如：")
        print("  pixiv://account/authorize?code=SECRET&state=...\n")
        return None

    return None


def configure_gallery_dl(refresh_token):
    """将 refresh_token 配置到 gallery-dl 全局设置。"""
    project_root = Path(__file__).parent.parent
    gdl_config.set((), 'extractor', {
        'pixiv': {
            'refresh-token': refresh_token,
            'directory': ['images', '{user[id]}'],
            'archive': str(DATA_DIR / 'gallery_dl_archive.db'),
        }
    })
    gdl_config.set((), 'base-directory', str(project_root))
    gdl_config.set((), 'output', {
        'mode': 'auto',
        'skip': 'true',  # 跳过已存在的文件
        'progress': 'false',
    })


def auth():
    """认证入口：refresh_token → OAuth PKCE 依次尝试。"""
    # 1. 尝试 refresh_token 恢复
    token = _try_refresh_token()
    if token:
        configure_gallery_dl(token)
        return

    # 2. 尝试 OAuth PKCE 流程
    token = _oauth_pkce()
    if token:
        configure_gallery_dl(token)
        return

    raise RuntimeError("Pixiv 登录失败。请通过浏览器 OAuth 流程授权。")
