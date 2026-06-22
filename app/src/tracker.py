import collections
import json
import os
import io
import re
import shutil
import zipfile
from datetime import datetime, timezone
from PIL import Image
from sqlalchemy import and_

import gallery_dl.config as gdl_config
import gallery_dl.job as gdl_job

from .client import PixivClient
from . import config as _cfg
from . import progress
from .models import Session, TrackedArtist, Illustration, IllustrationTag


def _artist_dir_name(artist):
    """画师对应的文件目录名：{name} {user_id}（Windows 非法字符替换为 _）"""
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', artist.name)
    return f"{safe_name} {artist.pixiv_user_id}"


def _natsort_key(f):
    """自然排序：将文件名中的数字段转为 int，确保 _p10 排在 _p2 之后。"""
    parts = re.split(r'(\d+)', f.name)
    key = []
    for p in parts:
        key.append(int(p) if p.isdigit() else p.lower())
    return key


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
        """添加一个特别关注画师（只创建记录，不拉取作品）。
        返回 (ArtistLike, is_new)。ArtistLike 有 .id 和 .name 属性。"""
        session = Session()

        existing = session.query(TrackedArtist).filter_by(pixiv_user_id=user_id).first()
        if existing:
            eid, ename = existing.id, existing.name
            session.close()
            return type("_ArtistRef", (), {"id": eid, "name": ename})(), False

        info = self.client.get_artist_detail(user_id)
        artist = TrackedArtist(
            pixiv_user_id=info["user_id"],
            name=info["name"],
            pixiv_account=info["account"],
            avatar_url=info["avatar_url"],
        )
        session.add(artist)
        session.commit()
        aid, aname = artist.id, artist.name
        session.close()
        return type("_ArtistRef", (), {"id": aid, "name": aname})(), True

    def fetch_artist(self, artist_id):
        """后台拉取画师的全部作品并下载（用于添加画师后的异步任务）。"""
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if not artist:
            session.close()
            return

        task_id = progress.begin_task(artist.name)
        progress.begin_phase(task_id, "checking")
        progress.set_detail(task_id, f"正在获取 {artist.name} 的全部作品...")
        progress.set_artist_progress(task_id, 1, 1)

        try:
            count = self._fetch_all_illusts(session, artist)
            progress.add_found(task_id, count)
        except Exception as e:
            progress.add_error(task_id, f"{artist.name}: {e}")
            progress.finish_task(task_id)
            session.close()
            return

        self._update_file_paths(session, artist)
        self._convert_ugoira_zips(session, artist)
        session.commit()

        pending = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id)
            .filter(Illustration.file_paths == None)
            .all()
        )
        total_pending = len(pending)

        if total_pending > 0:
            needs_clear = total_pending > count

            if needs_clear:
                all_illusts = (
                    session.query(Illustration)
                    .filter_by(artist_id=artist.id).all()
                )
                files_total = sum(i.page_count for i in all_illusts)
            else:
                files_total = sum(i.page_count for i in pending)

            progress.begin_phase(task_id, "downloading")
            progress.set_files_total(task_id, files_total)
            progress.set_dl_artist_progress(task_id, 1, 1)
            progress.set_detail(task_id, f"正在下载 {artist.name} 的作品...")

            try:
                self._download_artist(
                    artist.pixiv_user_id,
                    artist_dir=str(_cfg.IMAGES_DIR / _artist_dir_name(artist)),
                    task_id=task_id,
                    clear_archive=needs_clear,
                )
            except Exception as e:
                progress.add_error(task_id, f"下载 {artist.name}: {e}")

            self._update_file_paths(session, artist)
            self._convert_ugoira_zips(session, artist)
            session.commit()

        progress.finish_task(task_id)
        session.close()

    def remove_artist(self, artist_id):
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if artist:
            session.delete(artist)
            session.commit()
        session.close()

    def delete_illust_files(self, illust):
        """删除单件作品的全部本地图片文件。"""
        if not illust.file_paths:
            return
        for web_path in illust.file_paths.split(","):
            web_path = web_path.strip()
            if not web_path:
                continue
            # "/images/DirName/file.jpg" → 文件系统路径
            relative = web_path.replace("/images/", "", 1)
            fs_path = _cfg.IMAGES_DIR / relative
            try:
                if fs_path.exists():
                    fs_path.unlink()
            except OSError as e:
                print(f"  [!] 删除文件失败 {fs_path}: {e}")

    def permanently_delete_illust(self, illust_id):
        """永久删除作品：删本地文件 + 删数据库记录。"""
        session = Session()
        illust = session.query(Illustration).get(illust_id)
        if illust:
            self.delete_illust_files(illust)
            session.delete(illust)
            session.commit()
        session.close()

    def sync_all_bookmarks(self):
        """全量同步所有活跃画师作品的 is_bookmarked 状态。
        在后台线程中调用；通过 progress 模块报告进度。"""
        from . import progress

        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()

        task_id = progress.begin_task("同步收藏状态")
        progress.begin_phase(task_id, "checking")
        progress.set_artist_progress(task_id, 0, len(artists))
        progress.set_detail(task_id, "正在同步收藏状态...")

        total_updated = 0
        for i, artist in enumerate(artists):
            progress.set_artist(task_id, artist.name)
            progress.set_artist_progress(task_id, i + 1, len(artists))
            try:
                for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
                    illust = session.query(Illustration).filter_by(
                        pixiv_illust_id=illust_data["illust_id"]
                    ).first()
                    if illust:
                        api_bookmarked = illust_data.get("is_bookmarked", False)
                        if illust.is_bookmarked != api_bookmarked:
                            illust.is_bookmarked = api_bookmarked
                            total_updated += 1
                session.commit()
            except Exception as e:
                progress.add_error(task_id, f"{artist.name}: {e}")

        session.close()
        progress.set_detail(task_id, f"同步完成，更新 {total_updated} 件作品")
        progress.finish_task(task_id)
        return total_updated

    def remove_artist_keep_files(self, artist_id):
        """移除画师：删数据库记录，保留已下载文件。"""
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if artist:
            session.delete(artist)  # cascade 删除所有 Illustration 记录
            session.commit()
        session.close()

    def remove_artist_and_files(self, artist_id):
        """移除画师：删数据库记录 + 删除整个画师下载目录。"""
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if not artist:
            session.close()
            return
        dir_name = _artist_dir_name(artist)
        session.delete(artist)  # 先删 DB（cascade），文件删除失败不影响 DB 清理
        session.commit()
        session.close()
        # DB 提交成功后再删文件
        folder = _cfg.IMAGES_DIR / dir_name
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)

    def check_updates(self):
        """检查所有活跃画师的新作品——先全部检查，再统一下载。"""
        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()
        results = {}

        task_id = progress.begin_task()
        progress.begin_phase(task_id, "checking")
        progress.set_artist_progress(task_id, 0, len(artists))
        progress.set_detail(task_id, "正在检查画师更新...")

        # ═══ Phase 1: 检查所有画师，记录需要下载的画师 ═══
        to_download = []

        for i, artist in enumerate(artists):
            progress.set_artist(task_id, artist.name)
            progress.set_artist_progress(task_id, i + 1, len(artists))

            try:
                new_count = self._fetch_new_illusts(session, artist)
                progress.add_found(task_id, new_count)
            except Exception as e:
                progress.add_error(task_id, f"{artist.name}: {e}")
                new_count = 0

            self._update_file_paths(session, artist)
            self._convert_ugoira_zips(session, artist)
            session.commit()

            results[artist.name] = new_count
            artist.last_checked_at = datetime.utcnow()

            pending = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id)
                .filter(Illustration.file_paths == None)
                .all()
            )
            if pending:
                to_download.append((artist, pending, new_count))

        session.commit()

        # ═══ Phase 2: 统一下载，逐文件更新进度 ═══
        total_files = 0
        download_plan = []
        for artist, pending, new_count in to_download:
            needs_clear = len(pending) > new_count
            if needs_clear:
                all_illusts = (
                    session.query(Illustration)
                    .filter_by(artist_id=artist.id).all()
                )
                artist_files = sum(i.page_count for i in all_illusts)
            else:
                artist_files = sum(i.page_count for i in pending)
            total_files += artist_files
            download_plan.append((artist, needs_clear))

        if total_files > 0:
            progress.begin_phase(task_id, "downloading")
            progress.set_files_total(task_id, total_files)
            progress.set_dl_artist_progress(task_id, 0, len(download_plan))

            for i, (artist, needs_clear) in enumerate(download_plan):
                progress.set_artist(task_id, artist.name)
                progress.set_dl_artist_progress(task_id, i + 1, len(download_plan))
                progress.set_detail(task_id, f"正在下载 {artist.name} 的作品...")

                try:
                    self._download_artist(
                        artist.pixiv_user_id,
                        artist_dir=str(_cfg.IMAGES_DIR / _artist_dir_name(artist)),
                        task_id=task_id,
                        clear_archive=needs_clear,
                    )
                except Exception as e:
                    progress.add_error(task_id, f"下载 {artist.name}: {e}")

                self._update_file_paths(session, artist)
                self._convert_ugoira_zips(session, artist)
                session.commit()

        session.close()
        progress.finish_task(task_id)
        return results

    def download_pending(self):
        """下载所有缺失文件的作品。先扫描全部画师，再统一下载。"""
        session = Session()
        artists = session.query(TrackedArtist).filter_by(is_active=True).all()

        task_id = progress.begin_task()
        progress.begin_phase(task_id, "checking")
        progress.set_artist_progress(task_id, 0, len(artists))
        progress.set_detail(task_id, "正在扫描缺失文件...")

        # ═══ Phase 1: 扫描所有画师，收集待下载清单 ═══
        to_download = []

        for i, artist in enumerate(artists):
            progress.set_artist(task_id, artist.name)
            progress.set_artist_progress(task_id, i + 1, len(artists))

            self._update_file_paths(session, artist)
            self._convert_ugoira_zips(session, artist)
            session.commit()

            pending = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id)
                .filter(Illustration.file_paths == None)
                .all()
            )
            if pending:
                to_download.append((artist, pending))

        # ═══ Phase 2: 统一下载，逐文件更新进度 ═══
        total_files = 0
        for artist, _ in to_download:
            all_illusts = (
                session.query(Illustration)
                .filter_by(artist_id=artist.id).all()
            )
            total_files += sum(i.page_count for i in all_illusts)

        if total_files > 0:
            progress.begin_phase(task_id, "downloading")
            progress.set_files_total(task_id, total_files)
            progress.set_dl_artist_progress(task_id, 0, len(to_download))

            for i, (artist, _) in enumerate(to_download):
                progress.set_artist(task_id, artist.name)
                progress.set_dl_artist_progress(task_id, i + 1, len(to_download))
                progress.set_detail(task_id, f"正在下载 {artist.name} 的作品...")

                try:
                    self._download_artist(
                        artist.pixiv_user_id,
                        artist_dir=str(_cfg.IMAGES_DIR / _artist_dir_name(artist)),
                        task_id=task_id,
                        clear_archive=True,
                    )
                except Exception as e:
                    progress.add_error(task_id, f"下载 {artist.name}: {e}")

                self._update_file_paths(session, artist)
                self._convert_ugoira_zips(session, artist)
                session.commit()

        session.close()
        progress.finish_task(task_id)

    def _fetch_all_illusts(self, session, artist):
        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            self._save_illust(session, artist, illust_data)
            count += 1
        return count

    def _fetch_new_illusts(self, session, artist):
        """检查并保存画师的新作品。全量拉取后比对，不依赖 API 返回顺序。"""
        existing_ids = {
            row[0]
            for row in session.query(Illustration.pixiv_illust_id)
            .filter_by(artist_id=artist.id)
            .all()
        }

        count = 0
        for illust_data in self.client.get_all_artist_illusts(artist.pixiv_user_id):
            if illust_data["illust_id"] not in existing_ids:
                self._save_illust(session, artist, illust_data)
                count += 1
            else:
                # 已有作品：同步收藏状态（数据已在手，零额外 API 调用）
                illust = session.query(Illustration).filter_by(
                    pixiv_illust_id=illust_data["illust_id"]
                ).first()
                if illust:
                    api_bookmarked = illust_data.get("is_bookmarked", False)
                    if illust.is_bookmarked != api_bookmarked:
                        illust.is_bookmarked = api_bookmarked
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
            is_bookmarked=illust_data.get("is_bookmarked", False),
        )
        session.add(illust)
        session.commit()

        # 写入 illustration_tag 表
        for tag in illust_data["tags"]:
            session.execute(
                IllustrationTag.__table__.insert().values(
                    illustration_id=illust.id, tag=tag
                ).prefix_with("OR IGNORE")
            )
        session.commit()

        return illust

    def _download_artist(self, user_id, artist_dir=None, task_id=None, clear_archive=False):
        """用 gallery-dl 下载画师的全部作品（auto-dedup）。
        若提供 artist_dir+task_id，会每秒轮询该目录新增文件数来更新下载进度。"""
        from .auth import configure_gallery_dl, _load_token
        import threading
        import time
        from pathlib import Path

        saved = _load_token()
        if saved.get("refresh_token"):
            configure_gallery_dl(saved["refresh_token"])

        if clear_archive:
            archive = _cfg.DATA_DIR / "gallery_dl_archive.db"
            if archive.exists():
                archive.unlink()

        url = f"https://www.pixiv.net/users/{user_id}"

        if artist_dir and task_id:
            artist_dir = Path(artist_dir)
            artist_dir.mkdir(parents=True, exist_ok=True)
            before = {f.name for f in artist_dir.iterdir() if not f.name.endswith(".part")}
            last_count = [0]
            done = threading.Event()

            def _dl():
                try:
                    job = gdl_job.DownloadJob(url)
                    job.run()
                except Exception as e:
                    print(f"  [!] 下载出错 ({user_id}): {e}")
                finally:
                    done.set()

            t = threading.Thread(target=_dl, daemon=True)
            t.start()

            while not done.wait(0.5):
                if artist_dir.exists():
                    current = {f.name for f in artist_dir.iterdir() if not f.name.endswith(".part")}
                    new = len(current - before)
                    if new > last_count[0]:
                        progress.add_files_done(task_id, new - last_count[0])
                        last_count[0] = new

            t.join()

            if artist_dir.exists():
                current = {f.name for f in artist_dir.iterdir() if not f.name.endswith(".part")}
                new = len(current - before)
                if new > last_count[0]:
                    progress.add_files_done(task_id, new - last_count[0])
        else:
            try:
                job = gdl_job.DownloadJob(url)
                job.run()
            except Exception as e:
                print(f"  [!] 下载出错 ({user_id}): {e}")

    def _convert_ugoira_zips(self, session, artist):
        """将画师目录下已下载的 ugoira ZIP 转换为 GIF。"""
        import zipfile
        from PIL import Image
        dir_name = _artist_dir_name(artist)
        artist_dir = _cfg.IMAGES_DIR / dir_name
        if not artist_dir.exists():
            return

        ugoira_illusts = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id, type='ugoira')
            .all()
        )

        for illust in ugoira_illusts:
            # gallery-dl 下载的 ugoira 格式：{id}_p0.zip
            zip_path = artist_dir / f"{illust.pixiv_illust_id}_p0.zip"
            if not zip_path.exists():
                # 也尝试旧格式
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
                web_prefix = f"/images/{dir_name}"
                illust.file_paths = f"{web_prefix}/{gif_path.name}"
                zip_path.unlink()  # 删除原始 ZIP

            except Exception as e:
                print(f"  [!] ugoira 转换失败 {illust.title}: {e}")

    def _update_file_paths(self, session, artist):
        """扫描下载目录，检查并更新所有作品的本地文件路径。缺失的标记为待下载。"""
        dir_name = _artist_dir_name(artist)
        artist_dir = _cfg.IMAGES_DIR / dir_name
        web_prefix = f"/images/{dir_name}"

        all_illusts = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id)
            .all()
        )

        for illust in all_illusts:
            paths = []
            if artist_dir.exists():
                for f in sorted(artist_dir.iterdir(), key=_natsort_key):
                    name = f.name
                    # 匹配：{id}_p0.png, {id}.gif, {id}.jpg 等
                    if name.startswith(f"{illust.pixiv_illust_id}_p") \
                       or name.startswith(f"{illust.pixiv_illust_id}.") \
                       or name.startswith(f"{illust.pixiv_illust_id}_"):
                        if name.endswith('.part'):
                            continue  # 跳过未完成的下载
                        paths.append(f"{web_prefix}/{name}")
            illust.file_paths = ",".join(paths) if paths else None
