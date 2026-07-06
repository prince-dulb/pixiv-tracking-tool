# Bug 回报

> 审查日期：2026-07-07 | 审查范围：v0.1.0 全部改动 | 审查方式：对抗式审查

| # | 日期 | 严重等级 | 状态 | 描述 | 解决方案 |
|---|------|----------|------|------|----------|
| 1 | 2026-07-07 | 🔴 严重 | ✅ 已修复 | `validate_and_fix_all` 循环中 `illust.artist` 每次触发独立 SQL 查询（N+1），500 件作品 = 501 次查询 | upfront 构建 `{artist_id: artist_dir_name}` 字典，循环内查字典 |
| 2 | 2026-07-07 | 🔴 严重 | ✅ 已修复 | `validate_and_fix_all` 只统计缺失图片文件数量，不做修复；收藏状态同步未实现 | 缺失文件的作品清空 `file_paths`，后续 `download_pending` 可拾取重下；docstring 如实描述功能范围 |
| 3 | 2026-07-07 | 🟡 中等 | ✅ 已修复 | `_do_refresh_artist` 单个画师刷新时遍历全部已有作品补拉 caption，与 `_fetch_new_illusts` 策略不一致，大量作品时 API 调用膨胀 | 移除 per-artist refresh 中的 caption 补拉，统一走设置页「校验补全」按钮 |
| 4 | 2026-07-07 | 🟡 中等 | 待修复 | `progress.set_artist(task_id, illust.title)` 方法名是 artist 但传入的是作品标题，前端进度条标签显示错位 | 改为传入实际画师名 |
| 5 | 2026-07-07 | 🟡 中等 | 待修复 | `illust_detail.html` 中 `{{ caption_html \| safe }}` 不经过 HTML sanitize，理论上有 XSS 风险（实际数据来源 Pixiv API 已消毒，本地工具风险低） | 用 `bleach` 或 `html.escape` + 白名单标签做 sanitize |
| 6 | 2026-07-07 | 🟢 低 | 待修复 | `_fetch_and_save_caption(session, illust)` 方法签名接受 `session` 参数但函数体完全不碰它，只写文件 | 移除参数，或保留并加注释说明预留用途 |
| 7 | 2026-07-07 | 🟢 低 | 待修复 | `progress._tasks` dict 无过期机制，后台线程崩溃后 task 永远残留，前端持续显示陈旧进度条 | 加 TTL（如 30 分钟超时自动清理）或心跳机制 |
| 8 | 2026-07-07 | 🟢 低 | 待修复 | caption 文件路径 `_artist_dir_name + .caption.html` 拼接逻辑在 `works.py:472` 和 `tracker.py:587` 重复 | 提取为共用函数 `_caption_path(artist, illust_id)` |
