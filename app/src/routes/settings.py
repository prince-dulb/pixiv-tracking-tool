from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse

from ..web import get_tracker, templates
from ..models import Session, TrackedArtist, Illustration
from ..config import set_data_root, set_port, DATA_ROOT as _CFG_DATA_ROOT

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_context():
    from ..config import CHECK_INTERVAL_HOURS, CHECK_INTERVAL_MINUTES, PORT, DATA_ROOT, \
        PAGE_SIZE, PAGINATION_MODE, MAX_VISIBLE_ITEMS
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
        "page_size": PAGE_SIZE,
        "pagination_mode": PAGINATION_MODE,
        "max_visible_items": MAX_VISIBLE_ITEMS,
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


@router.post("/validate-and-fix")
async def validate_and_fix():
    """校验并补全所有已有作品信息：caption、收藏状态、缺失文件。后台运行。"""
    import threading
    tracker = get_tracker()
    if tracker:
        threading.Thread(target=tracker.validate_and_fix_all, daemon=True).start()
    return RedirectResponse("/settings", status_code=303)


@router.post("/pagination")
async def update_pagination(page_size: int = Form(200), pagination_mode: str = Form("scroll"),
                            max_visible_items: int = Form(0)):
    """更新翻页设置并持久化到 .env。"""
    from .. import config as _cfg
    from ..config import env_file

    # 更新运行时配置
    _cfg.PAGE_SIZE = page_size
    _cfg.PAGINATION_MODE = pagination_mode
    _cfg.MAX_VISIBLE_ITEMS = max_visible_items

    # 持久化到 .env
    content = env_file.read_text(encoding='utf-8')
    lines = content.split('\n')
    new_lines = []
    updated = {"PAGE_SIZE": False, "PAGINATION_MODE": False, "MAX_VISIBLE_ITEMS": False}
    for line in lines:
        stripped = line.strip()
        for key in updated:
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={locals()[key.lower()]}")
                updated[key] = True
                break
        else:
            new_lines.append(line)
    for key, done in updated.items():
        if not done:
            new_lines.append(f"{key}={locals()[key.lower()]}")
    env_file.write_text('\n'.join(new_lines), encoding='utf-8')

    return RedirectResponse("/settings", status_code=303)


@router.post("/port")
async def update_port(port: int = Form(...)):
    """更新端口号，需要重启才能生效。"""
    try:
        set_port(port)
        return JSONResponse({"ok": True, "message": f"端口已改为 {port}，请手动重启程序使其生效。"})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


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
