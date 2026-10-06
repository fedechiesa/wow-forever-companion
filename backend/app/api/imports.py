from __future__ import annotations

from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.api.schemas import ImportRunResponse, ImportSnapshotResponse
from app.db.connection import connect
from app.ingestion.adapters.file import FileAdapter
from app.ingestion.service import IngestionService, SnapshotImportInput

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/snapshots", response_model=ImportSnapshotResponse)
def import_snapshot(payload: dict[str, Any]) -> ImportSnapshotResponse:
    adapter = FileAdapter()
    try:
        adapter_result = adapter.load_payload(payload, raw_reference="http:POST /imports/snapshots")
    except (ValidationError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    service = IngestionService()
    try:
        result = service.import_snapshot(
            SnapshotImportInput(
                snapshot=adapter_result.snapshot,
                source_hash=adapter_result.source_hash,
                raw_reference=adapter_result.raw_reference,
            )
        )
    except psycopg.Error as error:
        raise HTTPException(status_code=500, detail="Snapshot import failed") from error

    return ImportSnapshotResponse(**result.model_dump())


@router.get("", response_model=list[ImportRunResponse])
def list_imports(limit: int = 50) -> list[ImportRunResponse]:
    safe_limit = max(1, min(limit, 100))
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                source_type,
                source_version,
                raw_reference,
                status,
                snapshot_id,
                items_seen,
                items_imported,
                error_message,
                started_at,
                finished_at
            FROM import_runs
            ORDER BY started_at DESC, id DESC
            LIMIT %s
            """,
            (safe_limit,),
        ).fetchall()
    return [ImportRunResponse.model_validate(dict(row), from_attributes=False) for row in rows]
