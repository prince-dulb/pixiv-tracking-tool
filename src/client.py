import time
from pixivpy3 import AppPixivAPI

from .config import REQUEST_DELAY


class PixivClient:
    def __init__(self, api: AppPixivAPI):
        self.api = api

    def _delay(self):
        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)

    def search_artist(self, keyword):
        """搜索画师，返回用户列表。"""
        self._delay()
        result = self.api.search_user(keyword)
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
        self._delay()
        result = self.api.user_detail(user_id)
        user = result["user"]
        return {
            "user_id": str(user["id"]),
            "name": user["name"],
            "account": user["account"],
            "avatar_url": user["profile_image_urls"]["medium"],
            "total_illusts": user.get("total_illusts", 0),
        }

    def get_artist_illusts(self, user_id, offset=None):
        """获取画师的单页作品列表。"""
        self._delay()
        result = self.api.user_illusts(user_id, type="illust", offset=offset)
        if "error" in result:
            raise RuntimeError(f"API error: {result['error']}")
        return result.get("illusts", []), result.get("next_url")

    def get_all_artist_illusts(self, user_id):
        """迭代获取画师的全部作品。"""
        offset = None
        while True:
            illusts, next_url = self.get_artist_illusts(user_id, offset)
            for illust in illusts:
                yield self._parse_illust(illust)
            if not next_url:
                break
            # 从 next_url 提取 offset 参数
            offset = self._extract_offset(next_url)

    def get_illust_detail(self, illust_id):
        """获取单个作品详情。"""
        self._delay()
        result = self.api.illust_detail(illust_id)
        if "error" in result:
            raise RuntimeError(f"API error: {result['error']}")
        return self._parse_illust(result["illust"])

    def download(self, url, path, name=None):
        """下载图片到指定目录，返回下载后的本地路径。"""
        import os
        os.makedirs(path, exist_ok=True)
        self.api.download(url, path=path, name=name)

    @staticmethod
    def _parse_illust(illust):
        return {
            "illust_id": str(illust["id"]),
            "title": illust["title"],
            "type": illust.get("type", "illust"),
            "page_count": illust.get("page_count", 1),
            "tags": [t["name"] for t in illust.get("tags", [])],
            "bookmark_count": illust.get("total_bookmarks", 0),
            "view_count": illust.get("total_view", 0),
            "posted_at": illust.get("create_date"),
            "urls": [
                {
                    "thumb": p["image_urls"].get("square_medium"),
                    "medium": p["image_urls"].get("medium"),
                    "original": p["image_urls"].get("original"),
                }
                for p in illust.get("meta_pages", [])
            ]
            or [
                {
                    "thumb": illust["image_urls"].get("square_medium"),
                    "medium": illust["image_urls"].get("medium"),
                    "original": illust.get("meta_single_page", {}).get("original_image_url")
                    or illust["image_urls"].get("large"),
                }
            ],
        }

    @staticmethod
    def _extract_offset(next_url):
        """从 next_url 中提取 offset 参数值。"""
        if not next_url:
            return None
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(next_url).query)
        offsets = qs.get("offset", [])
        return int(offsets[0]) if offsets else None
