import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import HOST, PORT, PROJECT_ROOT, resource_path
from . import config as _cfg
from .models import init_db
from .auth import auth, get_pending_login_url, submit_oauth_code, validate_oauth_input
from .client import PixivClient
from .tracker import Tracker
from .scheduler import start_scheduler, stop_scheduler

templates = Jinja2Templates(directory=resource_path("src/templates"))

# 全局实例，在 startup 时初始化
tracker: Tracker = None


def get_tracker():
    return tracker


def get_client():
    return PixivClient() if tracker else None


async def _init_auth():
    """后台执行 Pixiv 认证，完成后更新全局状态。"""
    global tracker
    try:
        await asyncio.to_thread(auth)
        tracker = Tracker()
        start_scheduler(tracker)
        templates.env.globals["pixiv_logged_in"] = True
        print("[OK] Pixiv 登录成功，追踪功能已就绪")
    except Exception as e:
        print(f"[warn] Pixiv 未登录: {e}")
        print("[warn] Web 界面可用，但追踪/下载功能需登录后使用")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tracker

    init_db()

    from .routes import artists, works, settings
    app.include_router(artists.router)
    app.include_router(works.router)
    app.include_router(settings.router)

    templates.env.globals["pixiv_logged_in"] = False
    auth_task = asyncio.create_task(_init_auth())

    yield

    stop_scheduler()
    auth_task.cancel()


from fastapi.responses import FileResponse

app = FastAPI(title="Pixiv Tracking Tool", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")


@app.get("/api/status")
async def api_status():
    from fastapi.responses import JSONResponse
    login_url = get_pending_login_url()
    return JSONResponse({
        "logged_in": tracker is not None,
        "login_url": login_url,
    })


@app.post("/api/reload")
async def api_reload():
    """原地重载：重启数据库引擎和 tracker，用于数据目录迁移后。"""
    global tracker
    from fastapi.responses import JSONResponse

    stop_scheduler()
    if tracker:
        tracker = None

    from .models import reinit_db
    reinit_db()

    try:
        tracker = Tracker()
        start_scheduler(tracker)
        templates.env.globals["pixiv_logged_in"] = True
    except Exception as e:
        templates.env.globals["pixiv_logged_in"] = False
        return JSONResponse({"ok": False, "error": str(e)})

    return JSONResponse({"ok": True})


@app.post("/api/submit-code")
async def api_submit_code(data: dict):
    from fastapi.responses import JSONResponse
    code, error = validate_oauth_input(data.get("code", ""))
    if error:
        return JSONResponse({"ok": False, "error": error})
    submit_oauth_code(code)
    return JSONResponse({"ok": True})


# 动态服务图片文件（支持自定义路径）
@app.get("/images/{path:path}")
async def serve_image(path: str):
    file_path = _cfg.IMAGES_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    from starlette.responses import Response
    return Response(status_code=404)


def main():
    import uvicorn
    import sys
    # PyInstaller 打包后不能用 reload 模式
    reload = not getattr(sys, 'frozen', False)
    uvicorn.run("src.web:app" if not getattr(sys, 'frozen', False) else app,
                host=HOST, port=PORT, reload=reload)


if __name__ == "__main__":
    main()
