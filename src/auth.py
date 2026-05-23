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

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
HASH_SECRET = "28c1fdd170a5204386cb1313c7077b34f83e4aaf4aa829ce78c231e05b0bae2c"

REDIRECT_URI = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"


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
    saved = _load_token()
    refresh_token = saved.get("refresh_token") or PIXIV_REFRESH_TOKEN

    if not refresh_token:
        return None

    try:
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

        r = requests.post(TOKEN_URL, headers=headers, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "get_secure_url": "1",
        }, timeout=30)

        if r.status_code != 200:
            return None

        resp = r.json()
        _save_token(resp["access_token"], resp.get("refresh_token", refresh_token))
        return resp["refresh_token"]

    except Exception:
        return None


def _oauth_pkce():
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
    print(f"""
1. 浏览器会打开 Pixiv 登录页面，正常登录你的 Pixiv 账号

2. 登录成功后，页面会快速跳转几次，最终停在一个空白页。
   现在打开浏览器的历史记录（Ctrl+H），搜索 "callback"

3. 历史记录中会有一条包含 "callback?state=..." 的网址，
   点击它，浏览器地址栏会显示类似：
   https://app-api.pixiv.net/.../callback?state=...&code=XXXXXXXX

4. 复制地址栏中这一整条 URL，粘贴到下方
""")

    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    user_input = input("  >> 粘贴 callback URL: ").strip()

    code = _extract_code(user_input)
    if not code:
        return None

    print(f"  code={code[:20]}...")

    # 用 code 换取 token
    headers = {
        "User-Agent": "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)",
    }
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "include_policy": "true",
        "redirect_uri": REDIRECT_URI,
        "get_secure_url": "1",
    }

    r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)

    if r.status_code != 200:
        resp_data = r.json()
        if resp_data.get("error") in ("invalid_request", "invalid_grant"):
            print("\n[X] code 已过期，请重新启动程序再试一次。\n")
        else:
            print(f"\n[X] Token 交换失败: HTTP {r.status_code}")
            print(f"  {r.text}\n")
        return None

    resp = r.json()
    if "error" in resp:
        print(f"\n[X] {resp}\n")
        return None

    _save_token(resp["access_token"], resp["refresh_token"])
    print("\n[OK] 登录成功！\n")
    return resp["refresh_token"]


def _extract_code(user_input):
    """从用户输入中提取 authorization code。

    用户可能粘贴：
    - 纯 code 字符串：直接返回
    - callback URL (code=xxx)：提取 code 参数
    - 中间跳转 URL（没有 code 参数）：报错并提示正确操作
    """
    from urllib.parse import urlparse, parse_qs

    if not user_input:
        return None

    user_input = user_input.strip()

    # 纯 code 字符串（不含 = 号，不以 http 开头）
    if "=" not in user_input and not user_input.startswith(("http", "pixiv")):
        return user_input

    # URL：尝试从 query 参数中提取 code
    parsed = urlparse(user_input)
    params = parse_qs(parsed.query)
    code = params.get("code", [None])[0]

    if code:
        return code

    # 没有 code 参数——分析用户错误粘贴了什么
    if "accounts.pixiv.net" in user_input or "code_challenge" in user_input:
        print("\n  [!] 这是登录跳转过程中的 URL，里面没有 code 参数。")
        print("  请按 Ctrl+H 打开浏览器历史记录，搜索 'callback'")
        print("  找到 callback?state=...&code=... 那条记录，复制整条 URL\n")
        return None

    # URL 里有 code= 但 parse_qs 没提取到（可能是嵌套 URL），兜底提取
    if "code=" in user_input:
        return user_input.rpartition("code=")[2].split("&")[0]

    print("\n  [!] 未找到 code 参数。请确认操作正确。\n")
    return None


def configure_gallery_dl(refresh_token):
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
        'skip': 'true',
        'progress': 'false',
    })


def auth():
    # 1. 尝试 refresh_token 恢复
    token = _try_refresh_token()
    if token:
        configure_gallery_dl(token)
        return

    # 2. OAuth PKCE 流程
    token = _oauth_pkce()
    if token:
        configure_gallery_dl(token)
        return

    raise RuntimeError("Pixiv 登录失败。请通过浏览器 OAuth 流程授权。")
