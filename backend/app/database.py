import aiosqlite

from backend.app.config import settings

_DB_PRAGMAS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA cache_size=-64000;",
    "PRAGMA busy_timeout=5000;",
]


async def get_connection() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(settings.db_path)
    conn.row_factory = aiosqlite.Row
    for pragma in _DB_PRAGMAS:
        await conn.execute(pragma)
    return conn


async def init_db() -> None:
    from backend.app.persistence.migrations import run_migrations

    conn = await get_connection()
    try:
        await run_migrations(conn)
        await conn.commit()
    finally:
        await conn.close()
