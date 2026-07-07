import threading
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse

from ..models import Session, TrackedArtist, Illustration
from .. import config as _cfg
from ..web import get_tracker, get_client, templates
from ..tracker import _sync_artist_name

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("")
async def list_artists(request: Request, search: str = Query(None)):
    session = Session()
    artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
    # 预计算作品数，避免模板中触发 lazy load
    artist_counts = {a.id: session.query(Illustration).filter_by(artist_id=a.id).count() for a in artists}

    results = []
    if search:
        client = get_client()
        if client:
            if search.strip().isdigit():
                # 按 Pixiv user_id 直接查找
                try:
                    info = client.get_artist_detail(search.strip())
                    results = [{
                        "user_id": info["user_id"],
                        "name": info["name"],
                        "account": info["account"],
                        "avatar_url": info["avatar_url"],
                    }]
                except Exception:
                    results = []
            else:
                results = client.search_artist(search)
        else:
            session.close()
            return templates.TemplateResponse(
                request, "artists.html",
                {"artists": artists, "artist_counts": artist_counts, "results": [], "error": "未登录 Pixiv，无法搜索"}
            )

    session.close()
    return templates.TemplateResponse(
        request, "artists.html",
        {"artists": artists, "artist_counts": artist_counts, "results": results, "search_term": search or ""}
    )


def _artists_context(session):
    artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
    counts = {a.id: session.query(Illustration).filter_by(artist_id=a.id).count() for a in artists}
    return artists, counts


@router.post("/add")
async def add_artist(request: Request, user_id: str = Form(...)):
    tracker = get_tracker()

    if not tracker:
        session = Session()
        artists, counts = _artists_context(session)
        session.close()
        return templates.TemplateResponse(
            request, "artists.html",
            {"artists": artists, "artist_counts": counts, "results": [], "error": "未登录 Pixiv，无法添加画师"}
        )

    artist, created = tracker.add_artist(user_id)
    if not created:
        session = Session()
        artists, counts = _artists_context(session)
        session.close()
        return templates.TemplateResponse(
            request, "artists.html",
            {"artists": artists, "artist_counts": counts, "results": [], "error": f"画师 {artist.name} 已在特别关注列表中"}
        )

    # 后台拉取作品和下载，不阻塞页面
    threading.Thread(target=tracker.fetch_artist, args=(artist.id,), daemon=True).start()

    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/remove")
async def remove_artist(artist_id: int):
    tracker = get_tracker()
    if tracker:
        tracker.remove_artist(artist_id)
    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/remove-keep-files")
async def remove_artist_keep_files(artist_id: int):
    tracker = get_tracker()
    if tracker:
        tracker.remove_artist_keep_files(artist_id)
    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/remove-and-files")
async def remove_artist_and_files(artist_id: int):
    tracker = get_tracker()
    if tracker:
        tracker.remove_artist_and_files(artist_id)
    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/toggle")
async def toggle_artist(artist_id: int):
    session = Session()
    artist = session.query(TrackedArtist).get(artist_id)
    if artist:
        artist.is_active = not artist.is_active
        session.commit()
    session.close()
    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/refresh")
async def refresh_artist(artist_id: int):
    tracker = get_tracker()
    if tracker:
        threading.Thread(target=_do_refresh_artist, args=(tracker, artist_id), daemon=True).start()
    return RedirectResponse("/artists", status_code=303)


def _do_refresh_artist(tracker, artist_id):
    from .. import progress

    session = Session()
    artist = session.query(TrackedArtist).get(artist_id)
    if not artist:
        session.close()
        return

    _sync_artist_name(artist, tracker.client, session)

    task_id = progress.begin_task(artist.name)

    progress.begin_phase(task_id, "checking")
    progress.set_artist_progress(task_id, 1, 1)
    progress.set_detail(task_id, "正在扫描本地文件...")

    tracker._update_file_paths(session, artist)
    tracker._convert_ugoira_zips(session, artist)
    session.commit()

    # 补拉该画师缺失的 caption
    from ..tracker import _caption_path
    no_caption = []
    for ill in artist.illustrations:
        if not _caption_path(artist, ill.pixiv_illust_id).exists():
            no_caption.append(ill)
    if no_caption:
        progress.begin_phase(task_id, "syncing")
        progress.set_files_total(task_id, len(no_caption))
        progress.set_detail(task_id, "正在补拉作品简介...")
        for i, ill in enumerate(no_caption):
            progress.add_files_done(task_id, 1)
            progress.set_artist(task_id, artist.name)
            try:
                tracker._fetch_and_save_caption(ill)
            except Exception as e:
                progress.add_error(task_id, f"caption {ill.pixiv_illust_id}: {e}")
    session.commit()

    pending = (
        session.query(Illustration)
        .filter_by(artist_id=artist.id)
        .filter(Illustration.file_paths.is_(None))
        .all()
    )

    if pending:
        all_illusts = (
            session.query(Illustration)
            .filter_by(artist_id=artist.id).all()
        )
        files_total = sum(i.page_count for i in all_illusts)

        progress.begin_phase(task_id, "downloading")
        progress.set_files_total(task_id, files_total)
        progress.set_dl_artist_progress(task_id, 1, 1)
        progress.set_detail(task_id, f"正在下载 {artist.name} 的作品...")

        safe_name = artist.name
        for ch in r'\/:*?"<>|':
            safe_name = safe_name.replace(ch, '_')
        artist_dir = str(_cfg.IMAGES_DIR / f"{safe_name} {artist.pixiv_user_id}")

        try:
            tracker._download_artist(
                artist.pixiv_user_id,
                artist_dir=artist_dir,
                task_id=task_id,
                clear_archive=True,
            )
        except Exception as e:
            progress.add_error(task_id, f"下载 {artist.name}: {e}")

        tracker._update_file_paths(session, artist)
        tracker._convert_ugoira_zips(session, artist)
        session.commit()

    progress.finish_task(task_id)
    session.close()
