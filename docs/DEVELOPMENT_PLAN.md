# 开发计划书

> 上次更新：2026-06-16 | 当前版本：v0.0.6

---

## 一、版本路线总览

| 版本 | 主题 | 状态 |
|------|------|------|
| v0.0.4 | 进度条重构 + 多任务并发 + UI 完善 | ✅ 已发布 |
| v0.0.5 | API 节流 | ✅ 已发布 |
| v0.0.6 | 隐藏/删除 + 收藏 + 翻页 + 筛选栏重构 + 投稿期间 + Tag 筛选 | ✅ 已发布 |
| v0.0.7 | 自定义排序 + Tag 统计图表 + 备份还原 | 📋 待实现 |
| v0.0.8 | 应用内更新 + 待定 | 📋 待规划 |

---

## 二、已发布版本

### v0.0.4（2026-05-24）
画师搜索与特别关注、gallery-dl 全量下载、CSS Grid 画廊（画师/类型多选筛选+反选）、作品详情页（原图+前后导航+键盘+触屏）、定时检查、文件级下载进度条+多任务并发、画师管理（暂停/恢复/刷新）、设置页（统计+手动检查+数据目录迁移）、Ugoira→GIF、SQLite WAL、非阻塞添加画师。

### v0.0.5（2026-06-16）
Pixiv API 全局节流（~1 req/s 安全基线 + token 过期自动刷新 + rate limit 60s/120s/180s 退避）、gallery-dl 同步限速、文件系统安全画师名。

### v0.0.6（2026-06-16）

| 模块 | 内容 |
|------|------|
| 收藏/取消收藏 | 详情页/pv 右下角+卡片 hover 角标，AJAX 乐观更新+toast，全量同步入口，下载时自动内联同步，`restrict="public"` |
| 画廊翻页 | 默认无限滚动（IntersectionObserver+Fragment），可选页码翻页（`?page=N`+页码栏），600px预加载+1s冷却+图片感知+上限封顶，回到顶部按钮 |
| 筛选栏重构 | ☰浮动面板→4section手风琴（画师/类型/期间/显示），面板 AJAX 化（pushState 不刷新），筛选条件翻页间保持 |
| 投稿期间筛选 | 预设：不限/24h/周/月/半年/年 + 自定义起始~截止日期 |
| Tag 筛选 | 聚合 chips + 自由输入，OR 逻辑，默认全选（对齐画师行为），详情页 tag 可点击，独立 `illustration_tag` 表+索引 |
| 性能优化 | Fragment 提前返回（AJAX 免 count/tag 聚合），tag/artist 30s 缓存，sessionmaker 复用，SSL/连接重试 |
| Bug 修复 | `_post` token 刷新、`restrict` 参数格式、filter-after-limit 顺序、tag 迁移幂等 |

---

## 三、v0.0.7 需求（待实现）

### 3.1 自定义排序

画廊排序方式可选：
- 按发布时间（默认） / 下载时间 / 收藏数 / 画师名 / **Tag 热度**
- 升序 / 降序

Tag 热度定义：作品所有 tag 中，取出现次数最多的那个 tag 的频率值作为 `tag_score`，降序排列。

### 3.2 筛选面板新增"排序" section

复用现有手风琴面板模式，下拉或 tag chip 选择排序字段和方向。

### 3.3 Tag 频率统计 + 图表

- 后端：`GROUP BY tag` 查询所有已下载作品的 tag 出现次数，60s 缓存
- 图表：Chart.js CDN，横向条形图，Top N（可配置 10/20/50/100）

### 3.4 新增"工具"页

导航从 `作品 · 画师 · 设置` 改为 `作品 · 画师 · 工具 · 设置`。

工具页定位：既不浏览作品、也不改配置的后台功能。放置 Tag 统计图表、备份/还原。

### 3.5 备份 / 还原

- **备份**：`shutil.make_archive` 打包 DATA_ROOT 为 zip，文件名带时间戳
- **还原**：解压到临时目录 → 对比 DB 作品数/画师数 + images 文件数 → 展示摘要
- **冲突处理**：覆盖当前 / 取消 / 合并（去重合并，同名图片取较新的）

---

## 四、v0.0.8 需求（待规划）

### 4.1 应用内更新

- 查 GitHub API → 拿最新 release tag，比对当前版本
- 有新版本时提示下载 → 下载新 exe → 写 bat 脚本 → 启动 bat（等主程序退出后覆盖 exe 重启）
- 启动时自动查一次 + 工具页手动"检查更新"按钮

---

## 五、未排期 / 待讨论

| 需求 | 说明 | 状态 |
|------|------|------|
| 评分系统 | `rating` 字段已有但无 UI | 未讨论 |
| 批量操作 | 多选作品 → 批量隐藏/删除/收藏（长按/角标触发，不走工具页） | 未讨论 |
| 深色模式 | 项目本身深色主题，浏览器暗色模式自适应。做亮色切换 ROI 极低 | 搁置 |

---

## 五、版本号与 Git 约定

- 版本号格式：`v{major}.{minor}.{patch}`
- 从 master 开 worktree 分支开发
- 开发完成 → 合并 master + 打 tag + GitHub Release
- release 目录：`release/vX.Y.Z/`，包含 `.exe`
- 构建命令：`cd app && pyinstaller build.spec --distpath ../release/vX.Y.Z --workpath build_tmp --clean`

---

## 六、架构注意事项

- SQLite 单文件，多线程 WAL 模式
- 无前端框架，Jinja2 SSR + 原生 JS
- 后台任务 `threading.Thread(daemon=True)`
- 图片 `FileResponse` + `loading="lazy"`
- CSS 变量 `:root` 统一管理主题色
- 筛选状态全走 URL 参数，前端 AJAX + pushState
- Fragment 模板（`gallery_fragment.html` / `artist_fragment.html`）供 AJAX 无限滚动
- `illustration_tag` 独立表 + 索引，JSON tags 列保留兼容
