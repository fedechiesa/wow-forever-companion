from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import settings  # noqa: E402
from scripts.migrate import run_migrations  # noqa: E402


def validate_test_database_url(test_url: str | None, development_url: str) -> str:
    if not test_url:
        raise ValueError("Set TEST_DATABASE_URL explicitly to a dedicated database ending in _test")
    test_info = conninfo_to_dict(test_url)
    development_info = conninfo_to_dict(development_url)
    name = test_info.get("dbname", "")
    if not name.endswith("_test") or name == development_info.get("dbname"):
        raise ValueError("Refusing test database: use a dedicated database ending in _test, distinct from development")
    return test_url


def main() -> int:
    test_url = validate_test_database_url(settings.test_database_url, settings.database_url)
    test_info = conninfo_to_dict(test_url)
    database_name = test_info["dbname"]
    admin_url = make_conninfo(test_url, dbname="postgres", options="")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)).fetchone()
        if not exists:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    applied = run_migrations(test_url)
    print(f"Test database ready: {database_name}; applied migrations: {applied}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
