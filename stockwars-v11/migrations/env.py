import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings
from app.models import Base

target_metadata = Base.metadata

def run_sync(conn):
    context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

async def main():
    eng = create_async_engine(settings.database_url)
    async with eng.connect() as c:
        await c.run_sync(run_sync)
    await eng.dispose()

asyncio.run(main())
