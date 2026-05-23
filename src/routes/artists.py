from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..models import Session, TrackedArtist
from ..web import get_tracker, get_client, templates

router = APIRouter(prefix="/artists", tags=["artists"])


@router.get("")
async def list_artists(request: Request):
    session = Session()
    artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
    session.close()
    return templates.TemplateResponse(request, "artists.html", {"request": request, "artists": artists})


@router.post("/add")
async def add_artist(request: Request, search: str = Form(...)):
    client = get_client()
    tracker = get_tracker()

    if not client or not tracker:
        session = Session()
        artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
        session.close()
        return templates.TemplateResponse(
            request, "artists.html", {"artists": artists, "error": "未登录 Pixiv，无法添加画师"}
        )

    if search.isdigit():
        user_id = search
    else:
        results = client.search_artist(search)
        if not results:
            session = Session()
            artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
            session.close()
            return templates.TemplateResponse(
                request, "artists.html", {"artists": artists, "error": f"未找到画师: {search}"}
            )
        user_id = results[0]["user_id"]

    artist, created = tracker.add_artist(user_id)
    if not created:
        session = Session()
        artists = session.query(TrackedArtist).order_by(TrackedArtist.added_at.desc()).all()
        session.close()
        return templates.TemplateResponse(
            request, "artists.html", {"artists": artists, "error": f"画师 {artist.name} 已在特别关注列表中"}
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
