from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse

from ..web import get_tracker, templates
from ..models import Session, TrackedArtist, Illustration
from ..config import set_data_root, DATA_ROOT as _CFG_DATA_ROOT

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_context():
    from ..config import CHECK_INTERVAL_HOURS, CHECK_INTERVAL_MINUTES, PORT, DATA_ROOT
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
    import threading
    tracker = get_tracker()
    if tracker:
        threading.Thread(target=_run_check_all, args=(tracker,), daemon=True).start()
    return RedirectResponse("/settings", status_code=303)


def _run_check_all(tracker):
    try:
        tracker.check_updates()
        tracker.download_pending()
    except Exception:
        pass


@router.post("/download-pending")
async def download_pending():
    import threading
    tracker = get_tracker()
    if tracker:
        threading.Thread(target=_run_download_all, args=(tracker,), daemon=True).start()
    return RedirectResponse("/settings", status_code=303)


def _run_download_all(tracker):
    try:
        tracker.download_pending()
    except Exception:
        pass


@router.post("/change-path")
async def change_path(request: Request, new_path: str = Form(...)):
    new_path = new_path.strip()
    if not new_path:
        return RedirectResponse("/settings", status_code=303)

    try:
        set_data_root(new_path)
    except Exception as e:
        return JSONResponse({"error": f"迁移失败: {e}"})

    return JSONResponse({"ok": True})


@router.post("/browse-path")
async def browse_path():
    """弹出原生文件夹选择对话框，返回所选路径。"""
    import asyncio
    import tkinter as tk
    from tkinter import filedialog

    result = {"path": None}

    def _open_dialog():
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(
            parent=root,
            initialdir=str(_CFG_DATA_ROOT),
            title="选择数据存储目录",
        )
        root.destroy()
        result["path"] = path

    await asyncio.to_thread(_open_dialog)
    return JSONResponse(result)
