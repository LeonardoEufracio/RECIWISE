from functools import lru_cache
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.engine import make_url
from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = get_settings().database_url
    options = ({"connect_args": {"connect_timeout": 5}, "pool_timeout": 5}
               if make_url(url).get_backend_name() == "postgresql" else {})
    return create_engine(url, pool_pre_ping=True, **options)


def get_db() -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=get_engine(), autoflush=False)
    with SessionLocal() as session:
        yield session
