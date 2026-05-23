import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import HOST, PORT, PROJECT_ROOT, resource_path
from . import config as _cfg
from .models import init_db
from .auth import auth
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tracker

    init_db()

    try:
        # auth() 内部使用 Playwright sync API，必须在独立线程运行
        await asyncio.to_thread(auth)
        tracker = Tracker()
        start_scheduler(tracker)
    except Exception as e:
        print(f"[warn] Pixiv 未登录: {e}")
        print("[warn] Web 界面可用，但追踪/下载功能需登录后使用")
        tracker = None

    from .routes import artists, works, settings
    app.include_router(artists.router)
    app.include_router(works.router)
    app.include_router(settings.router)

    templates.env.globals["pixiv_logged_in"] = tracker is not None

    yield

    stop_scheduler()


from fastapi.responses import FileResponse

app = FastAPI(title="Pixiv Tracking Tool", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=resource_path("static")), name="static")


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
