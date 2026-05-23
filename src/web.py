from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import HOST, PORT, PROJECT_ROOT
from .models import init_db
from .auth import auth
from .client import PixivClient
from .tracker import Tracker
from .scheduler import start_scheduler, stop_scheduler

templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src" / "templates"))

# 全局实例，在 startup 时初始化
pixiv_client: PixivClient = None
tracker: Tracker = None


def get_tracker():
    return tracker


def get_client():
    return pixiv_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pixiv_client, tracker

    init_db()

    try:
        api = auth()
        pixiv_client = PixivClient(api)
        tracker = Tracker(pixiv_client)
        start_scheduler(tracker)
    except Exception as e:
        print(f"[warn] Pixiv 未登录: {e}")
        print("[warn] Web 界面可用，但追踪/下载功能需登录后使用")
        pixiv_client = None
        tracker = None

    from .routes import artists, works, settings
    app.include_router(artists.router)
    app.include_router(works.router)
    app.include_router(settings.router)

    # 添加全局变量到模板
    templates.env.globals["pixiv_logged_in"] = pixiv_client is not None

    yield

    stop_scheduler()


app = FastAPI(title="Pixiv Tracking Tool", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")

# 挂载图片目录用于浏览器访问
app.mount("/images", StaticFiles(directory=str(PROJECT_ROOT / "images")), name="images")


def main():
    import uvicorn
    uvicorn.run("src.web:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    main()
