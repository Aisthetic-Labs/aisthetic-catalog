from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

ControlBase = declarative_base()

control_engine = create_engine(
    settings.CONTROL_DB_DSN,
    pool_pre_ping=True,
)

ControlSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=control_engine,
)