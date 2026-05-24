"""线程安全的进度追踪模块。支持多任务并发——每个任务有独立 ID，API 返回聚合进度。"""
import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class _Task:
    task_id: str
    phase: str = "checking"
    current_artist: str = ""
    current_detail: str = ""
    artists_checked: int = 0
    total_artists: int = 0
    new_works_found: int = 0
    files_total: int = 0
    files_done: int = 0
    dl_artist_index: int = 0
    dl_artist_total: int = 0
    errors: list = field(default_factory=list)


_tasks: dict[str, _Task] = {}
_lock = threading.Lock()


def begin_task(artist_name=""):
    """开始一个新任务，返回 task_id。"""
    task_id = uuid.uuid4().hex[:8]
    with _lock:
        _tasks[task_id] = _Task(task_id=task_id, current_artist=artist_name)
    return task_id


def begin_phase(task_id, phase):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].phase = phase


def set_artist(task_id, name):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].current_artist = name


def set_detail(task_id, msg):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].current_detail = msg


def set_artist_progress(task_id, checked, total):
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.artists_checked = checked
            t.total_artists = total


def add_found(task_id, n):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].new_works_found += n


def set_files_total(task_id, n):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].files_total = n


def add_files_done(task_id, n):
    with _lock:
        if task_id in _tasks:
            _tasks[task_id].files_done += n


def set_dl_artist_progress(task_id, index, total):
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.dl_artist_index = index
            t.dl_artist_total = total


def add_error(task_id, msg):
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.errors.append(msg)
            if len(t.errors) > 20:
                t.errors = t.errors[-20:]


def finish_task(task_id):
    with _lock:
        _tasks.pop(task_id, None)


def get_state():
    with _lock:
        if not _tasks:
            return _empty_state()

        tasks = list(_tasks.values())
        downloading = [t for t in tasks if t.phase == "downloading"]
        checking = [t for t in tasks if t.phase == "checking"]
        all_phases = {t.phase for t in tasks}

        # 阶段优先级：downloading > checking
        if "downloading" in all_phases:
            phase = "downloading"
        elif "checking" in all_phases:
            phase = "checking"
        else:
            phase = "idle"

        # 取最近更新的任务的详情
        last = tasks[-1]

        # 文件进度只统计下载阶段的任务
        dl_files_total = sum(t.files_total for t in downloading)
        dl_files_done = sum(t.files_done for t in downloading)
        dl_artist_idx = sum(t.dl_artist_index for t in downloading)
        dl_artist_tot = sum(t.dl_artist_total for t in downloading)

        # 画师进度只统计检查阶段的任务
        chk_checked = sum(t.artists_checked for t in checking)
        chk_total = sum(t.total_artists for t in checking)

        return {
            "active": True,
            "phase": phase,
            "current_artist": last.current_artist,
            "current_detail": last.current_detail,
            "artists_checked": chk_checked,
            "total_artists": chk_total,
            "new_works_found": sum(t.new_works_found for t in tasks),
            "files_total": dl_files_total,
            "files_done": dl_files_done,
            "dl_artist_index": dl_artist_idx,
            "dl_artist_total": dl_artist_tot,
            "errors": [e for t in tasks for e in t.errors],
            "task_count": len(tasks),
        }


def _empty_state():
    return {
        "active": False,
        "phase": "idle",
        "current_artist": "",
        "current_detail": "",
        "artists_checked": 0,
        "total_artists": 0,
        "new_works_found": 0,
        "files_total": 0,
        "files_done": 0,
        "dl_artist_index": 0,
        "dl_artist_total": 0,
        "errors": [],
        "task_count": 0,
    }
