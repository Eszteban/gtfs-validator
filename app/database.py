import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# SQLite as default development database, can be overridden with PostgreSQL via env var
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gtfs_validator.db")

# Normalize legacy postgres:// prefix if provided
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite requires check_same_thread=False for multi-threaded FastAPI workers
is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=os.getenv("SQL_ECHO", "false").lower() in ("true", "1"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing a database session to FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)

