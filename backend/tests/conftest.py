from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.core.config import settings
from scripts.migrate import run_migrations
from scripts.setup_test_database import validate_test_database_url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    try:
        return validate_test_database_url(settings.test_database_url, settings.database_url)
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)


@pytest.fixture
def isolated_database(test_database_url: str, monkeypatch: pytest.MonkeyPatch):
    schema = "test_" + uuid4().hex
    with psycopg.connect(test_database_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated_url = make_conninfo(test_database_url, options=f"-c search_path={schema} -c statement_timeout=15000")
    try:
        run_migrations(isolated_url)
        monkeypatch.setattr(settings, "database_url", isolated_url)
        yield
    finally:
        with psycopg.connect(test_database_url) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
