from apscheduler.schedulers.background import BackgroundScheduler

from .config import CHECK_INTERVAL_HOURS, CHECK_INTERVAL_MINUTES
from .models import Session

_scheduler: BackgroundScheduler = None


def check_and_download(tracker):
    """定时任务：检查更新并下载新作品。"""
    try:
        results = tracker.check_updates()
        if any(results.values()):
            session = Session()
            tracker.downloader.download_pending(session)
            session.close()
    except Exception:
        pass  # 定时任务静默处理错误，避免影响主进程


def start_scheduler(tracker):
    global _scheduler
    _scheduler = BackgroundScheduler(daemon=True)

    interval_kwargs = {}
    if CHECK_INTERVAL_HOURS:
        interval_kwargs["hours"] = CHECK_INTERVAL_HOURS
    if CHECK_INTERVAL_MINUTES:
        interval_kwargs["minutes"] = CHECK_INTERVAL_MINUTES

    _scheduler.add_job(
        check_and_download,
        "interval",
        args=[tracker],
        id="check_updates",
        **interval_kwargs,
    )
    _scheduler.start()


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
