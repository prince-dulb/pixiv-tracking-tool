import os
import io
import zipfile
from PIL import Image

from .config import IMAGES_DIR


class Downloader:
    def __init__(self, client):
        self.client = client

    def download_illust(self, illust, pixiv_user_id):
        """下载一个作品的所有页面，返回本地文件路径列表。"""
        artist_dir = IMAGES_DIR / pixiv_user_id
        artist_dir.mkdir(parents=True, exist_ok=True)

        if illust.type == "ugoira":
            return self._download_ugoira(illust, artist_dir)

        paths = []
        urls = self._get_urls(illust.pixiv_illust_id)

        for i, url_info in enumerate(urls):
            url = url_info["original"]
            ext = self._get_ext(url)
            name = f"{illust.pixiv_illust_id}_p{i}"
            self.client.download(url, path=str(artist_dir), name=name)
            paths.append(str(artist_dir / f"{name}{ext}"))

        return paths

    def download_pending(self, session):
        """下载所有未下载的作品（file_paths 为空的）。"""
        from .models import Illustration

        pending = session.query(Illustration).filter(Illustration.file_paths == None).all()  # noqa: E711
        count = 0
        for illust in pending:
            try:
                paths = self.download_illust(illust, illust.artist.pixiv_user_id)
                illust.file_paths = ",".join(paths)
                count += 1
            except Exception:
                continue
        session.commit()
        return count

    def _download_ugoira(self, illust, artist_dir):
        """下载 ugoira 并转换为 GIF。"""
        # 获取 ugoira 元数据
        metadata = self.client.api.ugoira_metadata(illust.pixiv_illust_id)
        if "error" in metadata:
            raise RuntimeError(f"Ugoira metadata error: {metadata['error']}")

        # 下载原始 zip 文件
        original_url = metadata["ugoira_metadata"]["zip_urls"]["medium"]
        zip_path = artist_dir / f"{illust.pixiv_illust_id}_ugoira.zip"
        gif_path = artist_dir / f"{illust.pixiv_illust_id}.gif"

        self.client.download(original_url, path=str(artist_dir), name=f"{illust.pixiv_illust_id}_ugoira")

        # 解压帧并合成 GIF
        frames = []
        delays = [f["delay"] for f in metadata["ugoira_metadata"]["frames"]]

        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in sorted(zf.namelist()):
                with zf.open(name) as f:
                    img = Image.open(io.BytesIO(f.read()))
                    frames.append(img.convert("RGBA"))

        if frames:
            frames[0].save(
                gif_path,
                save_all=True,
                append_images=frames[1:],
                duration=delays,
                loop=0,
                optimize=True,
                disposal=2,
            )

        # 删除临时 zip
        os.remove(zip_path)
        return [str(gif_path)]

    def _get_urls(self, illust_id):
        """从 API 获取作品 URL 信息。"""
        illust_data = self.client.get_illust_detail(illust_id)
        return illust_data["urls"]

    @staticmethod
    def _get_ext(url):
        """从 URL 提取文件扩展名。"""
        from urllib.parse import urlparse

        path = urlparse(url).path
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            if path.lower().endswith(ext):
                return ext
        return ".jpg"
