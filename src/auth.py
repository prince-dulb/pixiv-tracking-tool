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
1. 浏览器会打开 Pixiv 登录页面（如未自动打开，复制上面的链接）

2. 在登录页面按 F12，点击顶部 "Network"（网络）标签页
   在 Network 标签页顶部的过滤框里输入: callback
   （这样只会显示 callback 相关的请求，方便查找）

3. 正常登录你的 Pixiv 账号

4. 登录成功后，Network 标签页里会出现一条 "callback?state=..."
   的请求。点击它，右侧会显示该请求的详情。

5. 在右侧找到 "Query String Parameters"（查询字符串参数），
   复制 code 那一行的值（一长串字符，不是 code_challenge）
""")

    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    user_input = input("  >> 粘贴 code: ").strip()

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
        print("  你需要从 Network 标签页的 callback 请求中获取 code：")
        print("  1. 在 Network 过滤框输入 callback 缩小范围")
        print("  2. 找到 callback?state=... 这条请求")
        print("  3. 点击后在右侧 Query String Parameters 里复制 code 的值\n")
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
