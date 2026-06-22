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


@app.get("/api/progress")
async def api_progress():
    from . import progress
    from fastapi.responses import JSONResponse
    return JSONResponse(progress.get_state())


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


@app.post("/api/sync-bookmarks")
async def api_sync_bookmarks():
    """一次性全量同步所有活跃画师作品的收藏状态。在后台线程运行。"""
    from fastapi.responses import JSONResponse
    import threading
    global tracker
    if not tracker:
        return JSONResponse({"ok": False, "error": "未登录 Pixiv"}, status_code=503)
    threading.Thread(target=tracker.sync_all_bookmarks, daemon=True).start()
    return JSONResponse({"ok": True})


# 动态服务图片文件（支持自定义路径）
@app.get("/images/{path:path}")
async def serve_image(path: str):
    file_path = _cfg.IMAGES_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    from starlette.responses import Response
    return Response(status_code=404)


def _print_startup_urls():
    """启动后打印本机可访问链接。"""
    import socket
    print(f"\n  Pixiv Tracking Tool 已启动")
    print(f"  本地访问: http://localhost:{PORT}")

    # 局域网 IPv4
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        lan_ip = s.getsockname()[0]
        s.close()
        print(f"  局域网访问: http://{lan_ip}:{PORT}")
    except Exception:
        pass

    # IPv6 地址（过滤回环和链路本地）
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET6)
        seen = set()
        for addr in addrs:
            ip = addr[4][0]
            # 跳过回环、链路本地、以及去掉 % 作用域 ID 后的重复项
            if ip.startswith('::1') or ip.startswith('fe80'):
                continue
            ip_clean = ip.split('%')[0]
            if ip_clean not in seen:
                seen.add(ip_clean)
                print(f"  IPv6 外网访问: http://[{ip_clean}]:{PORT}")
    except Exception:
        pass

    print()


def main():
    import uvicorn
    import sys
    import threading
    import socket as _socket

    def _after_start():
        import time
        time.sleep(1.5)
        _print_startup_urls()

    threading.Thread(target=_after_start, daemon=True).start()

    reload = not getattr(sys, 'frozen', False)

    if reload:
        # Dev 模式：reload 不支持自定义 socket，单栈启动
        uvicorn.run("src.web:app", host=HOST, port=PORT, reload=True)
        return

    # 生产/打包模式：创建 IPv4 + IPv6 双 socket 实现双栈监听
    config = uvicorn.Config(app, host=None, port=PORT, loop="asyncio")
    server = uvicorn.Server(config)

    socks = []
    try:
        s_v6 = _socket.socket(_socket.AF_INET6, _socket.SOCK_STREAM)
        s_v6.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_V6ONLY, 1)
        s_v6.bind(('::', PORT))
        s_v6.listen(2048)
        socks.append(s_v6)
    except Exception as e:
        print(f"  [warn] IPv6 绑定失败: {e}")

    try:
        s_v4 = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s_v4.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        s_v4.bind(('0.0.0.0', PORT))
        s_v4.listen(2048)
        socks.append(s_v4)
    except Exception as e:
        print(f"  [warn] IPv4 绑定失败: {e}")

    if not socks:
        print("  [ERROR] 无法绑定任何地址，退出")
        return

    server.run(sockets=socks)


if __name__ == "__main__":
    main()
