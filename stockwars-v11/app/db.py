from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from .config import settings

engine = create_async_engine(settings.database_url, pool_size=20, max_overflow=10, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def ensure_columns():
    """Lightweight auto-migration: adds columns that exist in the models but not yet in the database."""
    from sqlalchemy import inspect, text
    from .models import Base

    def run(conn):
        insp = inspect(conn)
        for t in Base.metadata.sorted_tables:
            if not insp.has_table(t.name):
                continue
            have = {c["name"] for c in insp.get_columns(t.name)}
            for col in t.columns:
                if col.name in have:
                    continue
                ddl = f"ALTER TABLE {t.name} ADD COLUMN {col.name} {col.type.compile(conn.dialect)}"
                d = col.default.arg if col.default is not None and getattr(col.default, "is_scalar", False) else None
                if d is not None:
                    ddl += " DEFAULT " + (f"'{d}'" if isinstance(d, str) else str(d))
                conn.execute(text(ddl))

    async with engine.begin() as c:
        await c.run_sync(run)
