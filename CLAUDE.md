# Pixiv Tracking Tool — 项目规范

## 技术栈
Python 3.12 + FastAPI + SQLAlchemy + SQLite + pixivpy3 + Jinja2 + APScheduler

## 目录约定
- `src/` — 所有 Python 源码
- `src/routes/` — FastAPI 路由模块
- `src/templates/` — Jinja2 模板
- `static/` — CSS/JS 等静态文件
- `data/` — SQLite 数据库文件
- `images/{artist_id}/` — 下载的作品图片，按画师ID分目录

## 命名约定
- 文件名：snake_case
- Python 模块：snake_case
- 类名：PascalCase
- 函数/变量：snake_case
- 数据库表名：snake_case，SQLAlchemy 模型用 singular（TrackedArtist, Illustration）

## 编码规范
- 不写类型注解（够简单，类型从命名可推断）
- 不写 docstring（函数名 + 参数名已经说明意图）
- 只在非显而易见的逻辑处写简短注释
- 环境变量统一从 .env 加载，不进代码、不进 git
- 所有路径相对于项目根目录

## 验证命令
- `python -m src.web` — 启动 Web 服务
- `python src/auth.py` — 测试认证流程
- `python -m pytest tests/ -v` — 运行测试（未来补充）
