from fastapi import APIRouter, HTTPException
from psycopg import Error as PsycopgError

from app.core.config import settings
from app.db.connection import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }


@router.get("/health/db")
def database_health_check() -> dict[str, str]:
    try:
        check_database_connection()
    except PsycopgError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    return {"status": "ok", "database": "reachable"}

