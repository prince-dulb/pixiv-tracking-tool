import shutil
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..web import get_tracker, templates
from ..models import Session, TrackedArtist, Illustration
from ..config import IMAGES_DIR, PROJECT_ROOT, set_images_dir

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
        "images_dir": str(IMAGES_DIR),
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

    if new_path.startswith(('\\', '/')) or ':' in new_path:
        new_dir = __import__('pathlib').Path(new_path)
    else:
        new_dir = PROJECT_ROOT / new_path

    try:
        new_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context() | {"error": f"无法创建目录: {new_path}"}
        )

    old_dir = IMAGES_DIR

    # 迁移已有文件
    if old_dir.exists() and str(old_dir.resolve()) != str(new_dir.resolve()):
        for child in old_dir.iterdir():
            if child.is_dir():
                dest = new_dir / child.name
                if not dest.exists():
                    shutil.move(str(child), str(dest))

    # 更新 DB 路径
    session = Session()
    old_web = f"/images/{old_dir.name}"
    new_web = f"/images/{new_dir.name}"
    for i in session.query(Illustration).filter(Illustration.file_paths != None):
        if i.file_paths and old_web in i.file_paths:
            i.file_paths = i.file_paths.replace(old_web, new_web)
    session.commit()
    session.close()

    set_images_dir(str(new_dir))
    return RedirectResponse("/settings", status_code=303)
