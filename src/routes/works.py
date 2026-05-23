from fastapi import APIRouter, Request, Query

from ..models import Session, TrackedArtist, Illustration
from ..web import templates

router = APIRouter(tags=["works"])


@router.get("/")
async def index(request: Request, artist_id: int = Query(None)):
    session = Session()
    query = session.query(Illustration).order_by(Illustration.posted_at.desc())

    if artist_id:
        query = query.filter_by(artist_id=artist_id)
        artist = session.query(TrackedArtist).get(artist_id)
    else:
        artist = None

    illustrations = query.limit(200).all()

    # 预加载画师信息
    artist_ids = {i.artist_id for i in illustrations}
    artists_map = {}
    if artist_ids:
        artists_list = session.query(TrackedArtist).filter(TrackedArtist.id.in_(artist_ids)).all()
        artists_map = {a.id: a for a in artists_list}

    all_artists = session.query(TrackedArtist).filter_by(is_active=True).order_by(TrackedArtist.name).all()
    session.close()

    return templates.TemplateResponse(
        request, "index.html",
        {"illustrations": illustrations, "artists": all_artists,
         "artists_map": artists_map, "current_artist": artist},
    )


@router.get("/artist/{artist_id}")
async def artist_works(request: Request, artist_id: int):
    session = Session()
    artist = session.query(TrackedArtist).get(artist_id)
    if not artist:
        session.close()
        return templates.TemplateResponse(request, "error.html", {"message": "画师不存在"})

    illustrations = (
        session.query(Illustration)
        .filter_by(artist_id=artist_id)
        .order_by(Illustration.posted_at.desc())
        .limit(200)
        .all()
    )
    session.close()

    return templates.TemplateResponse(
        request, "artist_works.html",
        {"artist": artist, "illustrations": illustrations},
    )
