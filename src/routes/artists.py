from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse

from ..models import Session, TrackedArtist, Illustration
from ..web import get_tracker, get_client, templates

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
    client = get_client()
    tracker = get_tracker()

    if not client or not tracker:
        session = Session()
        artists, counts = _artists_context(session)
        session.close()
        return templates.TemplateResponse(
            request, "artists.html",
            {"artists": artists, "artist_counts": counts, "results": [], "error": "未登录 Pixiv，无法添加画师"}
        )

    artist, created = tracker.add_artist(user_id)
    session = Session()
    artists, counts = _artists_context(session)
    session.close()

    if not created:
        return templates.TemplateResponse(
            request, "artists.html",
            {"artists": artists, "artist_counts": counts, "results": [], "error": f"画师 {artist.name} 已在特别关注列表中"}
        )

    return RedirectResponse("/artists", status_code=303)


@router.post("/{artist_id}/remove")
async def remove_artist(artist_id: int):
    tracker = get_tracker()
    if tracker:
        tracker.remove_artist(artist_id)
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
        session = Session()
        artist = session.query(TrackedArtist).get(artist_id)
        if artist:
            from ..models import Illustration
            # 清除旧作品的文件路径，强制重新检查
            for i in session.query(Illustration).filter_by(artist_id=artist.id).all():
                i.file_paths = None
            session.commit()
            tracker._download_artist(artist.pixiv_user_id)
            tracker._update_file_paths(session, artist)
            session.commit()
        session.close()
    return RedirectResponse("/artists", status_code=303)
