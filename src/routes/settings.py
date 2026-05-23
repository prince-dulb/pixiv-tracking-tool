from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..web import get_tracker, templates
from ..models import Session, TrackedArtist, Illustration
from ..config import DATA_ROOT, set_data_root

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_context():
    from ..config import CHECK_INTERVAL_HOURS, CHECK_INTERVAL_MINUTES, PORT
    session = Session()
    artist_count = session.query(TrackedArtist).count()
    illust_count = session.query(Illustration).count()
    downloaded = session.query(Illustration).filter(Illustration.file_paths != None).count()  # noqa: E711
    session.close()
    return {
        "artist_count": artist_count,
        "illust_count": illust_count,
        "downloaded": downloaded,
        "check_interval_hours": CHECK_INTERVAL_HOURS,
        "check_interval_minutes": CHECK_INTERVAL_MINUTES,
        "port": PORT,
        "data_root": str(DATA_ROOT),
    }


@router.get("")
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", _settings_context())


@router.post("/check-now")
async def check_now():
    tracker = get_tracker()
    if tracker:
        tracker.check_updates()
        tracker.download_pending()
    return RedirectResponse("/settings", status_code=303)


@router.post("/download-pending")
async def download_pending():
    tracker = get_tracker()
    if tracker:
        tracker.download_pending()
    return RedirectResponse("/settings", status_code=303)


@router.post("/change-path")
async def change_path(request: Request, new_path: str = Form(...)):
    new_path = new_path.strip()
    if not new_path:
        return RedirectResponse("/settings", status_code=303)

    try:
        set_data_root(new_path)
    except Exception as e:
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context() | {"error": f"迁移失败: {e}"}
        )

    return RedirectResponse("/settings", status_code=303)
