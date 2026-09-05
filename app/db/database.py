from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def create_session_factory(database_url: str):
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    return engine, sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )


settings = get_settings()

engine, SessionLocal = create_session_factory(
    settings.database_url
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
