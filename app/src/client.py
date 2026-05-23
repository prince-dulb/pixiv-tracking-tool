import json
import requests
from pathlib import Path

from . import config as _cfg
from .auth import CLIENT_ID, CLIENT_SECRET, HASH_SECRET


def _token_file():
    return _cfg.DATA_DIR / "pixiv_token.json"

API_HOST = "https://app-api.pixiv.net"


def _get_auth_header():
    """获取当前有效的 access_token 用于 API 请求。"""
    if not _token_file().exists():
        return {}

    saved = json.loads(_token_file().read_text())
    return {"Authorization": f"Bearer {saved['access_token']}"}


class PixivClient:
    def __init__(self):
        pass

    def _get(self, endpoint, params=None):
        headers = _get_auth_header()
        headers["Accept-Language"] = "zh-cn"
        headers["App-OS"] = "ios"
        headers["App-OS-Version"] = "16.7.2"
        headers["App-Version"] = "7.19.1"
        headers["User-Agent"] = "PixivIOSApp/7.19.1 (iOS 16.7.2; iPhone14,2)"

        r = requests.get(
            f"{API_HOST}{endpoint}",
            headers=headers,
            params=params or {},
            timeout=30,
        )
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")
        return data

    def search_artist(self, keyword):
        """搜索画师。"""
        result = self._get("/v1/search/user", {"word": keyword, "filter": "for_ios"})
        users = result.get("user_previews", [])
        return [
            {
                "user_id": str(u["user"]["id"]),
                "name": u["user"]["name"],
                "account": u["user"]["account"],
                "avatar_url": u["user"]["profile_image_urls"]["medium"],
            }
            for u in users
        ]

    def get_artist_detail(self, user_id):
        """获取画师详细信息。"""
        result = self._get("/v1/user/detail", {"user_id": user_id})
        user = result["user"]
        return {
            "user_id": str(user["id"]),
            "name": user["name"],
            "account": user["account"],
            "avatar_url": user["profile_image_urls"]["medium"],
            "total_illusts": user.get("total_illusts", 0),
        }

    def get_all_artist_illusts(self, user_id):
        """迭代获取画师的全部作品（插画 + 漫画）。"""
        for work_type in ("illust", "manga"):
            params = {"user_id": user_id, "type": work_type}
            url = "/v1/user/illusts"

            while True:
                data = self._get(url, params)
                for illust in data.get("illusts", []):
                    yield self._parse_illust(illust)

                next_url = data.get("next_url")
                if not next_url:
                    break
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(next_url).query)
                params = {k: v[0] for k, v in qs.items()}

    def get_illust_detail(self, illust_id):
        """获取单个作品详情。"""
        data = self._get("/v1/illust/detail", {"illust_id": illust_id})
        return self._parse_illust(data["illust"])

    @staticmethod
    def _parse_illust(illust):
        tags = [t["name"] for t in illust.get("tags", [])]

        if illust.get("meta_pages"):
            urls = [
                {
                    "thumb": p["image_urls"].get("square_medium"),
                    "medium": p["image_urls"].get("medium"),
                    "original": p["image_urls"].get("original"),
                }
                for p in illust["meta_pages"]
            ]
        else:
            urls = [
                {
                    "thumb": illust["image_urls"].get("square_medium"),
                    "medium": illust["image_urls"].get("medium"),
                    "original": illust.get("meta_single_page", {}).get("original_image_url")
                    or illust["image_urls"].get("large"),
                }
            ]

        return {
            "illust_id": str(illust["id"]),
            "title": illust["title"],
            "type": illust.get("type", "illust"),
            "page_count": illust.get("page_count", 1),
            "tags": tags,
            "bookmark_count": illust.get("total_bookmarks", 0),
            "view_count": illust.get("total_view", 0),
            "posted_at": illust.get("create_date"),
            "urls": urls,
        }
