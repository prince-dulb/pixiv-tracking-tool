from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..web import get_tracker, templates
from ..downloader import Downloader
from ..models import Session

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def settings_page(request: Request):
    session = Session()
    from ..models import TrackedArtist, Illustration

    artist_count = session.query(TrackedArtist).count()
    illust_count = session.query(Illustration).count()
    downloaded = session.query(Illustration).filter(Illustration.file_paths != None).count()  # noqa: E711
    session.close()

    from ..config import CHECK_INTERVAL_HOURS, CHECK_INTERVAL_MINUTES, PORT

    return templates.TemplateResponse(
        request, "settings.html",
        {"artist_count": artist_count, "illust_count": illust_count,
         "downloaded": downloaded, "check_interval_hours": CHECK_INTERVAL_HOURS,
         "check_interval_minutes": CHECK_INTERVAL_MINUTES, "port": PORT},
    )


@router.post("/check-now")
async def check_now():
    tracker = get_tracker()
    if tracker:
        tracker.check_updates()
        tracker.downloader.download_pending(Session())
    return RedirectResponse("/settings", status_code=303)


@router.post("/download-pending")
async def download_pending():
    tracker = get_tracker()
    if tracker:
        tracker.downloader.download_pending(Session())
    return RedirectResponse("/settings", status_code=303)
