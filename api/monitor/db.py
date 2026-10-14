"""Connection pool and a minimal, Flyway-like migration runner (numbered SQL files, applied once, in order)."""

from importlib import resources

import asyncpg

from monitor.catalog import MACHINES

type Pool = asyncpg.Pool[asyncpg.Record]


async def connect(dsn: str) -> Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=8, command_timeout=30)


async def migrate(pool: Pool) -> list[str]:
    applied: list[str] = []
    async with pool.acquire() as con:
        await con.execute("SELECT pg_advisory_lock(4711)")  # one migrator at a time
        try:
            await con.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (name text PRIMARY KEY, "
                "applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {r["name"] for r in await con.fetch("SELECT name FROM schema_version")}
            files = sorted(
                (f for f in resources.files("monitor.migrations").iterdir() if f.name.endswith(".sql")),
                key=lambda f: f.name,
            )
            for f in files:
                if f.name in done:
                    continue
                # One script, one simple-protocol call: PostgreSQL runs it as a single implicit transaction.
                await con.execute(f.read_text(encoding="utf-8"))
                await con.execute("INSERT INTO schema_version (name) VALUES ($1)", f.name)
                applied.append(f.name)
        finally:
            await con.execute("SELECT pg_advisory_unlock(4711)")
    await sync_machines(pool)
    return applied


async def sync_machines(pool: Pool) -> None:
    """The catalog in code is the master data; the table mirrors it for foreign keys and ad-hoc queries."""
    await pool.executemany(
        "INSERT INTO machine (id, name, kind, cycle_s, position) VALUES ($1, $2, $3, $4, $5) "
        "ON CONFLICT (id) DO UPDATE SET name = $2, kind = $3, cycle_s = $4, position = $5",
        [(m.id, m.name, m.kind, m.cycle_s, i) for i, m in enumerate(MACHINES)],
    )
