from datetime import datetime
from sqlalchemy import create_engine, event, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import DATABASE_URL, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False,
                       connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """WAL 模式 + 忙等超时，支持多线程并发写入。"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


_sessionmaker = None


def Session(**kw):
    """复用 sessionmaker，避免每次创建新实例。"""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = sessionmaker(bind=engine)
    return _sessionmaker(**kw)


class Base(DeclarativeBase):
    pass


class TrackedArtist(Base):
    __tablename__ = "tracked_artist"

    id = Column(Integer, primary_key=True)
    pixiv_user_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    pixiv_account = Column(String)
    avatar_url = Column(String)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    last_checked_at = Column(DateTime)

    illustrations = relationship("Illustration", back_populates="artist", cascade="all, delete-orphan")


class Illustration(Base):
    __tablename__ = "illustration"

    id = Column(Integer, primary_key=True)
    pixiv_illust_id = Column(String, unique=True, nullable=False, index=True)
    artist_id = Column(Integer, ForeignKey("tracked_artist.id"), nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, default="illust")
    page_count = Column(Integer, default=1)
    tags = Column(Text)  # JSON array string
    bookmark_count = Column(Integer)
    view_count = Column(Integer)
    posted_at = Column(DateTime)
    downloaded_at = Column(DateTime, default=datetime.utcnow)
    file_paths = Column(Text)  # JSON array string
    is_hidden = Column(Boolean, default=False)
    is_bookmarked = Column(Boolean, default=False)
    rating = Column(Integer, default=0)

    artist = relationship("TrackedArtist", back_populates="illustrations")


def _column_exists(dbapi_connection, table, column):
    cursor = dbapi_connection.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    exists = any(row[1] == column for row in cursor.fetchall())
    cursor.close()
    return exists


def _migrate_existing_db():
    """幂等添加 v0.0.4 之后引入的列。"""
    with engine.begin() as conn:
        dbapi_connection = conn.connection.driver_connection
        if not _column_exists(dbapi_connection, "illustration", "is_hidden"):
            conn.exec_driver_sql("ALTER TABLE illustration ADD COLUMN is_hidden BOOLEAN DEFAULT 0")
        if not _column_exists(dbapi_connection, "illustration", "is_bookmarked"):
            conn.exec_driver_sql("ALTER TABLE illustration ADD COLUMN is_bookmarked BOOLEAN DEFAULT 0")


def init_db():
    Base.metadata.create_all(engine)
    _migrate_existing_db()


def reinit_db():
    """重新初始化数据库连接（数据目录迁移后调用）。"""
    global engine, _sessionmaker
    engine.dispose()
    _sessionmaker = None
    from .config import DATABASE_URL, DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DATABASE_URL, echo=False,
                           connect_args={"check_same_thread": False})
    event.listens_for(engine, "connect")(_set_sqlite_pragma)
    Base.metadata.create_all(engine)
    _migrate_existing_db()
