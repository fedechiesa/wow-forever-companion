from __future__ import annotations

import sys
from pathlib import Path

import psycopg


ROOT_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT_DIR / "migrations"
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings  # noqa: E402


def ensure_schema_migrations(connection: psycopg.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def applied_migrations(connection: psycopg.Connection) -> set[str]:
    rows = connection.execute("SELECT id FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def run_migrations(database_url: str | None = None) -> list[str]:
    applied: list[str] = []

    with psycopg.connect(database_url or settings.database_url) as connection:
        ensure_schema_migrations(connection)
        already_applied = applied_migrations(connection)

        for migration_path in migration_files():
            migration_id = migration_path.name
            if migration_id in already_applied:
                continue

            sql = migration_path.read_text(encoding="utf-8")
            try:
                with connection.transaction():
                    connection.execute(sql)
                    connection.execute(
                        "INSERT INTO schema_migrations (id) VALUES (%s)",
                        (migration_id,),
                    )
            except Exception as error:
                raise RuntimeError(f"Migration failed: {migration_id}") from error

            applied.append(migration_id)

    return applied


def main() -> int:
    applied = run_migrations()
    if applied:
        for migration_id in applied:
            print(f"Applied migration: {migration_id}")
    else:
        print("No pending migrations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
