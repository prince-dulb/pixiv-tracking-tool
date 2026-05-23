from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse

from ..models import Session, TrackedArtist, Illustration
from ..web import templates, get_tracker

router = APIRouter(tags=["works"])

TYPE_LABELS = {"illust": "插画", "manga": "漫画", "ugoira": "动图"}


@router.get("/")
async def index(request: Request, artist_id: int = Query(None), type: str = Query(None)):
    session = Session()
    query = session.query(Illustration).order_by(Illustration.posted_at.desc())

    if artist_id:
        query = query.filter_by(artist_id=artist_id)
        artist = session.query(TrackedArtist).get(artist_id)
    else:
        artist = None

    if type and type in TYPE_LABELS:
        query = query.filter_by(type=type)

    illustrations = query.limit(200).all()

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
         "artists_map": artists_map, "current_artist": artist,
         "current_type": type, "type_labels": TYPE_LABELS},
    )


@router.get("/illust/{illust_id}")
async def illust_detail(request: Request, illust_id: int):
    session = Session()
    illust = session.query(Illustration).get(illust_id)
    if not illust:
        session.close()
        return templates.TemplateResponse(request, "error.html", {"message": "作品不存在"})

    artist = session.query(TrackedArtist).get(illust.artist_id)

    # 解析文件路径和标签
    import json
    paths = illust.file_paths.split(",") if illust.file_paths else []
    page_count = len(paths) or illust.page_count
    try:
        tags = json.loads(illust.tags) if illust.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    session.close()

    return templates.TemplateResponse(
        request, "illust_detail.html",
        {"illust": illust, "artist": artist, "paths": paths,
         "page_count": page_count, "tags": tags, "type_labels": TYPE_LABELS},
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
        {"artist": artist, "illustrations": illustrations, "type_labels": TYPE_LABELS},
    )


@router.post("/refresh")
async def refresh_all():
    tracker = get_tracker()
    if tracker:
        tracker.check_updates()
        tracker.download_pending()
    return RedirectResponse("/", status_code=303)
