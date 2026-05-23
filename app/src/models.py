from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import DATABASE_URL, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False)


def Session(**kw):
    """每次调用都使用当前 engine，确保路径变更后自动切换数据库。"""
    return sessionmaker(bind=engine)(**kw)


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
    is_bookmarked = Column(Boolean, default=False)
    rating = Column(Integer, default=0)

    artist = relationship("TrackedArtist", back_populates="illustrations")


def init_db():
    Base.metadata.create_all(engine)


def reinit_db():
    """重新初始化数据库连接（数据目录迁移后调用）。"""
    global engine
    engine.dispose()
    from .config import DATABASE_URL, DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
