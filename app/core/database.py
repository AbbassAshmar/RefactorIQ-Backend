
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine_options = {
    "pool_pre_ping": True,
    "echo": settings.ENVIRONMENT == "development",
}
if not settings.APP_DATABASE_URL.startswith("sqlite"):
    _engine_options.update(pool_size=10, max_overflow=20)

engine = create_engine(settings.APP_DATABASE_URL, **_engine_options)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
