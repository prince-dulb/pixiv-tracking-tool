import json
import hashlib
import secrets
import base64
import webbrowser
from pathlib import Path
from pixivpy3 import AppPixivAPI

from .config import PIXIV_USERNAME, PIXIV_PASSWORD, PIXIV_REFRESH_TOKEN, DATA_DIR

TOKEN_FILE = DATA_DIR / "pixiv_token.json"


def _save_token(api):
    TOKEN_FILE.write_text(json.dumps({
        "access_token": api.access_token,
        "refresh_token": api.refresh_token,
    }))


def _load_token():
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return {}


def _try_refresh_token(api):
    """尝试用本地保存的或 .env 中的 refresh_token 恢复会话。"""
    saved = _load_token()
    refresh_token = saved.get("refresh_token") or PIXIV_REFRESH_TOKEN

    if not refresh_token:
        return False

    try:
        api.auth(refresh_token=refresh_token)
        _save_token(api)
        return True
    except Exception:
        return False


def _oauth_pkce(api):
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
    print("3. 登录成功后浏览器会跳转到一个空白页(pixiv://...)，")
    print("   复制地址栏中的完整 URL\n")

    # 尝试自动打开浏览器
    try:
        webbrowser.open(login_url)
        print("  (已尝试自动打开浏览器)\n")
    except Exception:
        pass

    callback_url = input("  >> 粘贴跳转后的 URL: ").strip()

    # 从回调 URL 中提取 code
    code = _extract_code(callback_url)
    if not code:
        print("\n✗ 未能从 URL 中提取授权码。\n")
        return None

    # 用 code 换取 token
    try:
        api.auth(
            refresh_token=code,
            headers={
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
    except Exception:
        # pixivpy 的 auth() 不支持 authorization_code grant，需要手动请求
        return _token_exchange(code, code_verifier, api)

    _save_token(api)
    print("\n✓ 登录成功！\n")
    return api


def _token_exchange(code, code_verifier, api):
    """手动完成 authorization_code → token 交换。"""
    import requests
    from datetime import datetime
    from requests.structures import CaseInsensitiveDict

    local_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    headers = CaseInsensitiveDict({
        "x-client-time": local_time,
        "x-client-hash": hashlib.md5(
            (local_time + api.hash_secret).encode("utf-8")
        ).hexdigest(),
        "app-os": "ios",
        "app-os-version": "14.6",
        "user-agent": "PixivIOSApp/7.13.3 (iOS 14.6; iPhone13,2)",
    })

    data = {
        "client_id": api.client_id,
        "client_secret": api.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "get_secure_url": "1",
    }

    r = requests.post("https://oauth.secure.pixiv.net/auth/token", headers=headers, data=data)
    if r.status_code != 200:
        print(f"\n✗ Token 交换失败: HTTP {r.status_code}")
        print(f"  {r.text}\n")
        return None

    resp = r.json()
    api.access_token = resp["access_token"]
    api.refresh_token = resp["refresh_token"]
    if "user" in resp:
        api.user_id = str(resp["user"]["id"])

    _save_token(api)
    print("\n✓ 登录成功！\n")
    return api


def _extract_code(url_string):
    """从回调 URL 中提取 authorization code。"""
    from urllib.parse import urlparse, parse_qs

    if "code=" not in url_string:
        # 也许是直接粘贴的 code
        return url_string

    parsed = urlparse(url_string.strip())
    params = parse_qs(parsed.query)
    codes = params.get("code", [])
    return codes[0] if codes else None


def _password_login(api):
    """旧版账号密码登录（Pixiv 已禁用此方式，保留作为兜底）。"""
    api.login(PIXIV_USERNAME, PIXIV_PASSWORD)
    _save_token(api)
    return api


def auth():
    """认证入口：refresh_token → OAuth PKCE → password 依次尝试。"""
    api = AppPixivAPI()

    # 1. 尝试 refresh_token 恢复
    if _try_refresh_token(api):
        return api

    # 2. 尝试 OAuth PKCE 流程
    if _oauth_pkce(api):
        return api

    # 3. 兜底：账号密码登录
    if PIXIV_USERNAME and PIXIV_PASSWORD:
        print("\n尝试密码登录（可能失败）...")
        try:
            return _password_login(api)
        except Exception as e:
            print(f"\n密码登录也失败了: {e}")

    raise RuntimeError(
        "Pixiv 登录失败。请通过浏览器 OAuth 流程授权。"
    )
