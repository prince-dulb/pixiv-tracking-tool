import json
from datetime import datetime
from sqlalchemy import and_

from .client import PixivClient
from .downloader import Downloader
from .models import Session, TrackedArtist, Illustration


class Tracker:
    def __init__(self, client: PixivClient):
        self.client = client
        self.downloader = Downloader(client)

    def add_artist(self, user_id):
        """添加一个特别关注画师，并拉取其全部已有作品。"""
        session = Session()

        existing = session.query(TrackedArtist).filter_by(pixiv_user_id=user_id).first()
        if existing:
            session.close()
            return existing, False  # 已存在，不重复添加

        info = self.client.get_artist_detail(user_id)
        artist = TrackedArtist(
            pixiv_user_id=info["user_id"],
            name=info["name"],
            pixiv_account=info["account"],
            avatar_url=info["avatar_url"],
        )
        session.add(artist)
        session.commit()

        self._fetch_all_illusts(session, artist)

        session.close()
        return artist, True

    def remove_artist(self, artist_id):
        """移除特别关注画师及其所有作品记录。"""
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if artist:
            session.delete(artist)
            session.commit()
        session.close()

    def check_updates(self):
        """检查所有活跃画师的新作品。"""
        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()
        results = {}

        for artist in artists:
            new_count = self._fetch_new_illusts(session, artist)
            results[artist.name] = new_count
            artist.last_checked_at = datetime.utcnow()

        session.commit()
        session.close()
        return results

    def _fetch_all_illusts(self, session, artist):
        """拉取画师全部已有作品并入库。"""
        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            self._save_illust(session, artist, illust_data)
            count += 1
        return count

    def _fetch_new_illusts(self, session, artist):
        """只拉取画师的新作品（数据库中没有的）。"""
        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            exists = (
                session.query(Illustration)
                .filter_by(pixiv_illust_id=illust_data["illust_id"])
                .first()
            )
            if exists:
                # 假设作品按时间倒序返回，遇到已存在就停止
                break
            self._save_illust(session, artist, illust_data)
            count += 1
        return count

    def _save_illust(self, session, artist, illust_data):
        illust = Illustration(
            pixiv_illust_id=illust_data["illust_id"],
            artist_id=artist.id,
            title=illust_data["title"],
            type=illust_data["type"],
            page_count=illust_data["page_count"],
            tags=json.dumps(illust_data["tags"], ensure_ascii=False),
            bookmark_count=illust_data["bookmark_count"],
            view_count=illust_data["view_count"],
            posted_at=illust_data["posted_at"],
        )
        session.add(illust)
        session.commit()
        return illust
