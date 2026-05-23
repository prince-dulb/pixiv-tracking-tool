"""线程安全的进度追踪模块。Tracker 写入，/api/progress 读取。"""
import threading
from dataclasses import dataclass, field


@dataclass
class _State:
    phase: str = "idle"
    current_artist: str = ""
    current_detail: str = ""
    works_found: int = 0
    works_downloaded: int = 0
    total_artists: int = 0
    artist_index: int = 0
    errors: list = field(default_factory=list)
    active: bool = False


_state = _State()
_lock = threading.Lock()


def reset():
    with _lock:
        _state.phase = "idle"
        _state.current_artist = ""
        _state.current_detail = ""
        _state.works_found = 0
        _state.works_downloaded = 0
        _state.total_artists = 0
        _state.artist_index = 0
        _state.errors.clear()
        _state.active = True


def begin_phase(phase):
    with _lock:
        _state.phase = phase


def set_artist(name):
    with _lock:
        _state.current_artist = name


def set_detail(msg):
    with _lock:
        _state.current_detail = msg


def set_progress(index, total):
    with _lock:
        _state.artist_index = index
        _state.total_artists = total


def add_found(n):
    with _lock:
        _state.works_found += n


def add_downloaded(n):
    with _lock:
        _state.works_downloaded += n


def add_error(msg):
    with _lock:
        _state.errors.append(msg)
        if len(_state.errors) > 20:
            _state.errors = _state.errors[-20:]


def finish():
    with _lock:
        _state.phase = "idle"
        _state.active = False


def get_state():
    with _lock:
        return {
            "active": _state.active,
            "phase": _state.phase,
            "current_artist": _state.current_artist,
            "current_detail": _state.current_detail,
            "works_found": _state.works_found,
            "works_downloaded": _state.works_downloaded,
            "total_artists": _state.total_artists,
            "artist_index": _state.artist_index,
            "errors": list(_state.errors),
        }
