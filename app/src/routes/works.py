import threading
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import RedirectResponse

from ..models import Session, TrackedArtist, Illustration
from ..web import templates, get_tracker

router = APIRouter(tags=["works"])

TYPE_LABELS = {"illust": "插画", "manga": "漫画", "ugoira": "动图"}


def _ids_str(ids_set):
    return ",".join(str(x) for x in sorted(ids_set))


@router.get("/")
async def index(request: Request, artist_ids: str = Query(None), type: str = Query(None)):
    session = Session()
    all_artists = session.query(TrackedArtist).filter_by(is_active=True).order_by(TrackedArtist.name).all()
    all_artist_ids = {a.id for a in all_artists}

    selected_ids = None  # None = 全选
    if artist_ids:
        try:
            selected_ids = {int(x.strip()) for x in artist_ids.split(",") if x.strip()}
        except (ValueError, TypeError):
            pass

    query = session.query(Illustration).order_by(Illustration.posted_at.desc())

    if selected_ids is not None:
        query = query.filter(Illustration.artist_id.in_(selected_ids))

    if type and type in TYPE_LABELS:
        query = query.filter_by(type=type)

    illustrations = query.limit(200).all()

    illust_artist_ids = {i.artist_id for i in illustrations}
    artists_map = {}
    if illust_artist_ids:
        artists_list = session.query(TrackedArtist).filter(TrackedArtist.id.in_(illust_artist_ids)).all()
        artists_map = {a.id: a for a in artists_list}

    session.close()

    # 画师 toggle URL（全选默认逻辑）
    def _index_url(artist_param=None, type_param=None):
        parts = []
        if artist_param:
            parts.append(artist_param)
        t = type_param if type_param is not None else type
        if t:
            parts.append(f"type={t}")
        if not parts:
            return "/"
        return "/?" + "&".join(parts)

    toggle_urls = {}
    if selected_ids is None:
        for a in all_artists:
            others = all_artist_ids - {a.id}
            toggle_urls[a.id] = _index_url(f"artist_ids={_ids_str(others)}")
    else:
        for a in all_artists:
            new_set = selected_ids.copy()
            if a.id in new_set:
                new_set.discard(a.id)
            else:
                new_set.add(a.id)
            toggle_urls[a.id] = _index_url(
                f"artist_ids={_ids_str(new_set)}" if new_set else None)

    if selected_ids is None:
        invert_url = _index_url()
    else:
        inverted = all_artist_ids - selected_ids
        invert_url = _index_url(f"artist_ids={_ids_str(inverted)}" if inverted else "artist_ids=")

    all_url = _index_url()

    type_urls = {}
    for t in TYPE_LABELS:
        if t == type:
            type_urls[t] = _index_url(
                f"artist_ids={_ids_str(selected_ids)}" if selected_ids is not None else None)
        else:
            type_urls[t] = _index_url(
                f"artist_ids={_ids_str(selected_ids)}" if selected_ids is not None else None, t)

    return templates.TemplateResponse(
        request, "index.html",
        {"illustrations": illustrations, "artists": all_artists,
         "artists_map": artists_map, "selected_artist_ids": selected_ids,
         "all_artist_ids": all_artist_ids,
         "toggle_urls": toggle_urls, "type_urls": type_urls,
         "invert_url": invert_url, "all_url": all_url,
         "current_type": type, "type_labels": TYPE_LABELS},
    )


@router.get("/illust/{illust_id}")
async def illust_detail(request: Request, illust_id: int,
                         artist_ids: str = Query(None), artist_id: int = Query(None),
                         type: str = Query(None)):
    session = Session()
    illust = session.query(Illustration).get(illust_id)
    if not illust:
        session.close()
        return templates.TemplateResponse(request, "error.html", {"message": "作品不存在"})

    artist = session.query(TrackedArtist).get(illust.artist_id)

    import json
    paths = illust.file_paths.split(",") if illust.file_paths else []
    page_count = len(paths) or illust.page_count
    try:
        tags = json.loads(illust.tags) if illust.tags else []
    except (json.JSONDecodeError, TypeError):
        tags = []

    # 根据上下文构建查询，找到前/后作品（带 posted_at 用于插入点查找）
    base_query = session.query(Illustration.id, Illustration.posted_at)\
        .order_by(Illustration.posted_at.desc())
    if artist_id:
        base_query = base_query.filter_by(artist_id=artist_id)
    elif artist_ids:
        try:
            ids = {int(x.strip()) for x in artist_ids.split(",") if x.strip()}
            if ids:
                base_query = base_query.filter(Illustration.artist_id.in_(ids))
        except (ValueError, TypeError):
            pass
    if type and type in TYPE_LABELS:
        base_query = base_query.filter_by(type=type)

    all_rows = base_query.all()
    all_ids = [row[0] for row in all_rows]
    try:
        current_idx = all_ids.index(illust.id)
    except ValueError:
        # 当前图不在筛选范围，找它应插入的位置作为导航锚点
        current_idx = 0
        for i, (rid, rdate) in enumerate(all_rows):
            if illust.posted_at and rdate and rdate <= illust.posted_at:
                current_idx = i
                break
            current_idx = i + 1

    prev_id = all_ids[current_idx - 1] if current_idx > 0 and current_idx <= len(all_ids) else None
    next_id = all_ids[current_idx] if current_idx < len(all_ids) else None

    # 构建导航链接的查询参数
    params = []
    if artist_ids:
        params.append(f"artist_ids={artist_ids}")
    if artist_id:
        params.append(f"artist_id={artist_id}")
    if type:
        params.append(f"type={type}")
    nav_query = "?" + "&".join(params) if params else ""

    if artist_id:
        back_url = f"/artist/{artist_id}"
    else:
        back_url = "/" + nav_query

    # 为详情页筛选栏准备数据
    all_artists = session.query(TrackedArtist).filter_by(is_active=True).order_by(TrackedArtist.name).all()
    all_artist_ids = {a.id for a in all_artists}
    selected_ids = None  # None = 全选（默认）
    if artist_id:
        selected_ids = {artist_id}
    elif artist_ids:
        try:
            selected_ids = {int(x.strip()) for x in artist_ids.split(",") if x.strip()}
        except (ValueError, TypeError):
            pass

    # 构建详情页筛选 URL（都指向当前插图，不跳走）
    def _make_url(artist_param=None, type_param=None):
        parts = []
        if artist_param:
            parts.append(artist_param)
        if type_param:
            parts.append(f"type={type_param}")
        else:
            # 保留当前 type，除非显式传 None
            pass
        if not parts:
            return f"/illust/{illust_id}"
        return f"/illust/{illust_id}?{'&'.join(parts)}"

    def _artist_param(id_set):
        if id_set is None:
            return None  # 全选（不传参数）
        if artist_id:
            return f"artist_ids={_ids_str(id_set)}"
        return f"artist_ids={_ids_str(id_set)}" if id_set else "artist_ids="

    # 画师 toggle URL
    detail_toggle_urls = {}
    if selected_ids is None:
        for a in all_artists:
            others = all_artist_ids - {a.id}
            detail_toggle_urls[a.id] = _make_url(_artist_param(others), type)
    else:
        for a in all_artists:
            new_set = selected_ids.copy()
            if a.id in new_set:
                new_set.discard(a.id)
            else:
                new_set.add(a.id)
            detail_toggle_urls[a.id] = _make_url(_artist_param(new_set), type)

    # 反选 URL
    if selected_ids is None:
        invert_url = _make_url(None, type)
    else:
        inverted = all_artist_ids - selected_ids
        invert_url = _make_url(_artist_param(inverted), type)

    # "全部" URL（清除画师筛选，保留类型）
    all_url = _make_url(None, type)

    # 类型 URL（保留画师筛选）
    detail_type_urls = {}
    for t in TYPE_LABELS:
        if t == type:
            detail_type_urls[t] = _make_url(_artist_param(selected_ids), None)
        else:
            detail_type_urls[t] = _make_url(_artist_param(selected_ids), t)

    session.close()

    return templates.TemplateResponse(
        request, "illust_detail.html",
        {"illust": illust, "artist": artist, "paths": paths,
         "page_count": page_count, "tags": tags, "type_labels": TYPE_LABELS,
         "prev_id": prev_id, "next_id": next_id, "nav_query": nav_query,
         "current_idx": current_idx + 1, "total_count": len(all_ids),
         "back_url": back_url,
         "all_artists": all_artists, "all_artist_ids": all_artist_ids,
         "selected_artist_ids": selected_ids,
         "detail_toggle_urls": detail_toggle_urls, "detail_type_urls": detail_type_urls,
         "invert_url": invert_url, "all_url": all_url,
         "current_type": type},
    )


@router.get("/artist/{artist_id}")
async def artist_works(request: Request, artist_id: int, type: str = Query(None)):
    session = Session()
    artist = session.query(TrackedArtist).get(artist_id)
    if not artist:
        session.close()
        return templates.TemplateResponse(request, "error.html", {"message": "画师不存在"})

    query = (
        session.query(Illustration)
        .filter_by(artist_id=artist_id)
        .order_by(Illustration.posted_at.desc())
    )
    if type and type in TYPE_LABELS:
        query = query.filter_by(type=type)

    illustrations = query.limit(200).all()
    session.close()

    return templates.TemplateResponse(
        request, "artist_works.html",
        {"artist": artist, "illustrations": illustrations,
         "type_labels": TYPE_LABELS, "current_type": type},
    )


@router.post("/refresh")
async def refresh_all(artist_ids: str = Form(None), type: str = Form(None)):
    tracker = get_tracker()
    if tracker:
        threading.Thread(target=_do_refresh_all, args=(tracker,), daemon=True).start()
    params = []
    if artist_ids:
        params.append(f"artist_ids={artist_ids}")
    if type:
        params.append(f"type={type}")
    url = "/?" + "&".join(params) if params else "/"
    return RedirectResponse(url, status_code=303)


def _do_refresh_all(tracker):
    tracker.check_updates()
    tracker.download_pending()
