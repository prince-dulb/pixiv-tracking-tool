import json
import os
import re
from datetime import datetime
from sqlalchemy import and_

import gallery_dl.config as gdl_config
import gallery_dl.job as gdl_job

from .client import PixivClient
from .config import IMAGES_DIR, DATA_DIR
from .models import Session, TrackedArtist, Illustration


class Tracker:
    def __init__(self):
        self.client = PixivClient()

    def add_artist(self, user_id):
        """添加一个特别关注画师，并拉取其全部已有作品。"""
        session = Session()

        existing = session.query(TrackedArtist).filter_by(pixiv_user_id=user_id).first()
        if existing:
            session.close()
            return existing, False

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
        self._download_artist(artist.pixiv_user_id)
        self._update_file_paths(session, artist)

        session.close()
        return artist, True

    def remove_artist(self, artist_id):
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
            if new_count > 0:
                self._download_artist(artist.pixiv_user_id)
                self._update_file_paths(session, artist)
            results[artist.name] = new_count
            artist.last_checked_at = datetime.utcnow()

        session.commit()
        session.close()
        return results

    def download_pending(self):
        """下载所有未下载的作品。"""
        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()
        for artist in artists:
            pending = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id)
                .filter(Illustration.file_paths == None)  # noqa: E711
                .count()
            )
            if pending > 0:
                self._download_artist(artist.pixiv_user_id)
                self._update_file_paths(session, artist)
        session.commit()
        session.close()

    def _fetch_all_illusts(self, session, artist):
        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            self._save_illust(session, artist, illust_data)
            count += 1
        return count

    def _fetch_new_illusts(self, session, artist):
        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            exists = (
                session.query(Illustration)
                .filter_by(pixiv_illust_id=illust_data["illust_id"])
                .first()
            )
            if exists:
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

    def _download_artist(self, user_id):
        """用 gallery-dl 下载画师的全部作品（auto-dedup）。"""
        url = f"https://www.pixiv.net/users/{user_id}"
        try:
            job = gdl_job.DownloadJob(url)
            job.run()
        except Exception:
            pass  # gallery-dl 内部处理大部分错误

    def _update_file_paths(self, session, artist):
        """扫描下载目录，为 DB 中没有 file_paths 的作品匹配本地文件。"""
        artist_dir = IMAGES_DIR / artist.pixiv_user_id
        if not artist_dir.exists():
            return

        pending = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id)
            .filter(Illustration.file_paths == None)  # noqa: E711
            .all()
        )

        for illust in pending:
            paths = []
            for f in sorted(artist_dir.iterdir()):
                if f.name.startswith(f"{illust.pixiv_illust_id}_p"):
                    paths.append(str(f))
                elif f.name.startswith(f"{illust.pixiv_illust_id}."):
                    paths.append(str(f))
            if paths:
                illust.file_paths = ",".join(paths)
