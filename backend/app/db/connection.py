import psycopg

from app.core.config import settings


def check_database_connection() -> None:
    with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

