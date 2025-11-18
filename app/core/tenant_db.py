from functools import lru_cache
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.db_control import ControlSessionLocal
from app.control.models_control import MerchantDBConnection


def _build_dsn(conn: MerchantDBConnection) -> str:
    # Example: postgresql+asyncpg://user:pass@host:port/dbname
    return (
        f"postgresql+asyncpg://{conn.db_user}:{conn.db_password}"
        f"@{conn.db_host}:{conn.db_port}/{conn.db_name}"
    )


@lru_cache(maxsize=128)
def get_tenant_engine(merchant_id: str) -> AsyncEngine:
    # Lookup in control-plane DB
    with ControlSessionLocal() as session:
        conn = (
            session.query(MerchantDBConnection)
            .filter(MerchantDBConnection.merchant_id == merchant_id)
            .one()
        )
    print("DEBUG: Tenant DB Connection:", conn.db_host, conn.db_name, conn.db_user, conn.db_password)
    dsn = _build_dsn(conn)
    engine = create_async_engine(
        dsn,
        echo=False,
        pool_pre_ping=True,
    )
    return engine


def get_tenant_sessionmaker(merchant_id: str) -> sessionmaker:
    engine = get_tenant_engine(merchant_id)
    return sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )