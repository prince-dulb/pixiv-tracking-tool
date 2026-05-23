# Pixiv Tracking Tool — 项目规范

## 目录结构
```
pixiv-tracking-tool/
├── app/                  ← 当前编辑版本（源码、构建脚本等）
│   ├── src/              — 所有 Python 源码
│   ├── src/routes/       — FastAPI 路由模块
│   ├── src/templates/    — Jinja2 模板
│   ├── static/           — CSS/JS 等静态文件
│   ├── docs/             — 设计文档和计划
│   ├── run.py            — 入口
│   ├── build.spec        — PyInstaller 配置
│   ├── release.bat       — 发布构建脚本
│   └── start.bat         — 启动脚本
├── release/              — 发布版 exe
├── .claude/              — Claude 工作文件 + 分支存档
├── data/                 — SQLite 数据库文件（运行时生成）
├── images/               — 下载的作品图片（运行时生成，按画师ID分目录）
├── .env                  — 运行时配置
└── CLAUDE.md             — 项目规范（本文件）
```

## 技术栈
Python 3.12 + FastAPI + SQLAlchemy + SQLite + Jinja2 + APScheduler + gallery-dl

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

## 活动目录
- 默认在 `app/` 下活动，除非特殊说明
- 验证命令在 `app/` 下执行

## 验证命令
- `python run.py` — 启动 Web 服务
- `python -m src.web` — 启动 Web 服务（模块方式）
- `python -m pytest tests/ -v` — 运行测试（未来补充）
