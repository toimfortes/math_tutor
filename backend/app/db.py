from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.config import Settings


class Base(DeclarativeBase):
    pass


def create_session_factory(settings: Settings) -> sessionmaker:
    engine = create_engine(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
