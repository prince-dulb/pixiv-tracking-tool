# Bug 回报 — v0.1.0 对抗式审查

> 审查日期：2026-07-07 | 审查范围：v0.1.0 全部改动文件

---

## 🔴 严重

### #1 — `validate_and_fix_all` N+1 懒加载查询

**文件**：`app/src/tracker.py:296`  
**现象**：循环中 `illust.artist` 每次触发独立 SQL 查询。500 件作品 → 501 次查询。  
**修复**：upfront 构建 `{artist_id: artist_dir_name}` 字典。  
**状态**：✅ 已修复

### #2 — `validate_and_fix_all` 功能不完整

**文件**：`app/src/tracker.py:309-320`  
**现象**：docstring 和 UI 都说"检查图片文件缺失，缺损则补上"，实际只统计数量不做修复。收藏状态同步也未实现。  
**修复**：缺失文件的作品清空 `file_paths`（使 `download_pending` 可拾取重下）；docstring 如实描述。  
**状态**：✅ 已修复

---

## 🟡 中等

### #3 — `_do_refresh_artist` 全量补拉 caption

**文件**：`app/src/routes/artists.py:144-157`  
**现象**：单个画师手动刷新时遍历全部已有作品补拉 caption，与 `_fetch_new_illusts` 修复策略不一致。若画师有 500 件作品且都无 caption，产生 500 次 detail API 调用。  
**修复**：移除 per-artist refresh 中的 caption 补拉逻辑，统一走设置页「校验补全」按钮。  
**状态**：✅ 已修复

### #4 — `progress.set_artist` 传入了作品标题

**文件**：`app/src/tracker.py:293`、`app/src/routes/artists.py:156`  
**现象**：
```python
progress.set_artist(task_id, illust.title or illust.pixiv_illust_id)
```
方法名是 `set_artist` 但传的是作品标题，前端进度条标签显示错位。  
**修复**：传入实际画师名。  
**状态**：待修复

### #5 — XSS：caption 用 `| safe` 直接渲染原始 HTML

**文件**：`app/src/templates/illust_detail.html:145`  
**现象**：`{{ caption_html | safe }}` 不经过任何消毒，若 Pixiv API 返回的 caption 含 `<script>` 等恶意标签会直接执行。  
**风险**：低（数据来源 Pixiv、本地工具），但防御性不足。  
**修复建议**：用 `bleach` 或 `html.escape` + 白名单标签做 sanitize。  
**状态**：待修复

---

## 🟢 低

### #6 — `_fetch_and_save_caption` 的 `session` 参数未使用

**文件**：`app/src/tracker.py:581`  
**现象**：方法签名接受 `session` 参数但函数体完全不碰它，只写文件不碰 DB。  
**修复建议**：移除参数或保留并注释用途。  
**状态**：待修复

### #7 — `progress._tasks` 无过期清理

**文件**：`app/src/progress.py:23-24`  
**现象**：后台线程崩溃时 `finish_task` 不调用，task 永远留在 dict 里，前端持续显示陈旧进度条。  
**修复建议**：加 TTL（如 30 分钟）或心跳过期机制。  
**状态**：待修复

### #8 — 详情页 caption 路径构建逻辑重复

**文件**：`app/src/routes/works.py:472-474`、`app/src/tracker.py:587-589`  
**现象**：两处重复相同的 `_artist_dir_name` + `.caption.html` 路径拼接逻辑。  
**修复建议**：提取为共用函数 `_caption_path(artist, illust_id)`。  
**状态**：待修复

---

## 修复摘要

| Bug # | 严重度 | 状态 |
|-------|--------|------|
| #1 N+1 查询 | 🔴 严重 | ✅ 已修复 |
| #2 功能不完整 | 🔴 严重 | ✅ 已修复 |
| #3 全量补拉 | 🟡 中等 | ✅ 已修复 |
| #4 set_artist 标题 | 🟡 中等 | 待修复 |
| #5 XSS caption | 🟡 中等 | 待修复 |
| #6 session 参数 | 🟢 低 | 待修复 |
| #7 progress 过期 | 🟢 低 | 待修复 |
| #8 路径重复 | 🟢 低 | 待修复 |
