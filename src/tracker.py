import json
import os
import io
import re
import zipfile
from datetime import datetime, timezone
from PIL import Image
from sqlalchemy import and_

import gallery_dl.config as gdl_config
import gallery_dl.job as gdl_job

from .client import PixivClient
from .config import IMAGES_DIR, DATA_DIR
from .models import Session, TrackedArtist, Illustration


def _parse_iso_date(s):
    """将 Pixiv API 返回的 ISO 8601 日期字符串转为 datetime。"""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # 处理 Python 3.11 之前不支持的时区格式
        s = s.replace("Z", "+00:00")
        if s.endswith("+00:00"):
            s = s[:-6]
        return datetime.fromisoformat(s)


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
        self._convert_ugoira_zips(session, artist)

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
            self._update_file_paths(session, artist)
            self._convert_ugoira_zips(session, artist)
            session.commit()
            missing = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id)
                .filter(Illustration.file_paths == None).count()
            )
            if new_count > 0 or missing > 0:
                self._download_artist(artist.pixiv_user_id, clear_archive=(missing > 0))
                self._update_file_paths(session, artist)
                self._convert_ugoira_zips(session, artist)
            results[artist.name] = new_count
            artist.last_checked_at = datetime.utcnow()

        session.commit()
        session.close()
        return results

    def download_pending(self):
        """下载所有未下载的文件缺失的作品。"""
        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()
        for artist in artists:
            self._update_file_paths(session, artist)
            self._convert_ugoira_zips(session, artist)
            session.commit()
            missing = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id)
                .filter(Illustration.file_paths == None).count()
            )
            if missing > 0:
                self._download_artist(artist.pixiv_user_id, clear_archive=True)
                self._update_file_paths(session, artist)
                self._convert_ugoira_zips(session, artist)
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
        posted_at = illust_data.get("posted_at")
        if posted_at and isinstance(posted_at, str):
            posted_at = _parse_iso_date(posted_at)

        illust = Illustration(
            pixiv_illust_id=illust_data["illust_id"],
            artist_id=artist.id,
            title=illust_data["title"],
            type=illust_data["type"],
            page_count=illust_data["page_count"],
            tags=json.dumps(illust_data["tags"], ensure_ascii=False),
            bookmark_count=illust_data["bookmark_count"],
            view_count=illust_data["view_count"],
            posted_at=posted_at,
        )
        session.add(illust)
        session.commit()
        return illust

    def _download_artist(self, user_id, clear_archive=False):
        """用 gallery-dl 下载画师的全部作品（auto-dedup）。"""
        from .auth import configure_gallery_dl, _load_token
        saved = _load_token()
        if saved.get("refresh_token"):
            configure_gallery_dl(saved["refresh_token"])

        # 如果文件被删了需要重新下载，先清除 archive 让 gallery-dl 不跳过
        if clear_archive:
            archive = DATA_DIR / "gallery_dl_archive.db"
            if archive.exists():
                archive.unlink()

        url = f"https://www.pixiv.net/users/{user_id}"
        try:
            job = gdl_job.DownloadJob(url)
            job.run()
        except Exception as e:
            print(f"  [!] 下载出错 ({user_id}): {e}")

    def _convert_ugoira_zips(self, session, artist):
        """将画师目录下已下载的 ugoira ZIP 转换为 GIF。"""
        import zipfile
        from PIL import Image
        artist_dir = IMAGES_DIR / artist.pixiv_user_id
        if not artist_dir.exists():
            return

        ugoira_illusts = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id, type='ugoira')
            .all()
        )

        for illust in ugoira_illusts:
            zip_path = artist_dir / f"{illust.pixiv_illust_id}_ugoira.zip"
            gif_path = artist_dir / f"{illust.pixiv_illust_id}.gif"
            if not zip_path.exists() or gif_path.exists():
                continue

            try:
                # 获取帧延迟信息
                metadata = self.client.get_illust_detail(illust.pixiv_illust_id)
                frames_data = []
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for name in sorted(zf.namelist()):
                        with zf.open(name) as f:
                            img = Image.open(io.BytesIO(f.read()))
                            frames_data.append(img.convert('RGBA'))

                if not frames_data:
                    continue

                # 从 Pixiv API 获取帧延迟
                delays = []
                try:
                    data = self.client._get(
                        '/v1/ugoira/metadata',
                        {'illust_id': illust.pixiv_illust_id}
                    )
                    frames = data.get('ugoira_metadata', {}).get('frames', [])
                    delays = [f.get('delay', 100) for f in frames]
                except Exception:
                    pass

                if frames_data:
                    kwargs = {
                        'save_all': True,
                        'append_images': frames_data[1:],
                        'loop': 0,
                        'optimize': True,
                        'disposal': 2,
                    }
                    if delays:
                        kwargs['duration'] = delays
                    frames_data[0].save(gif_path, **kwargs)

                # 更新文件路径指向 GIF
                web_prefix = f"/images/{artist.pixiv_user_id}"
                illust.file_paths = f"{web_prefix}/{gif_path.name}"
                zip_path.unlink()  # 删除原始 ZIP

            except Exception as e:
                print(f"  [!] ugoira 转换失败 {illust.title}: {e}")

    def _update_file_paths(self, session, artist):
        """扫描下载目录，检查并更新所有作品的本地文件路径。缺失的标记为待下载。"""
        artist_dir = IMAGES_DIR / artist.pixiv_user_id
        web_prefix = f"/images/{artist.pixiv_user_id}"

        all_illusts = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id)
            .all()
        )

        for illust in all_illusts:
            paths = []
            if artist_dir.exists():
                for f in sorted(artist_dir.iterdir()):
                    if f.name.startswith(f"{illust.pixiv_illust_id}_p"):
                        paths.append(f"{web_prefix}/{f.name}")
                    elif f.name.startswith(f"{illust.pixiv_illust_id}."):
                        paths.append(f"{web_prefix}/{f.name}")
            illust.file_paths = ",".join(paths) if paths else None
