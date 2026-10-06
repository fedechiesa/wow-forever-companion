from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.realms import resolve_realm_id
from app.api.schemas import SnapshotSummaryResponse
from app.db.connection import connect

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("", response_model=list[SnapshotSummaryResponse])
def list_snapshots(
    realm: str | None = None,
    limit: int = 50,
    region: str | None = None,
    realm_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
) -> list[SnapshotSummaryResponse]:
    safe_limit = max(1, min(limit, 100))
    with connect() as connection:
        selected_realm_id = resolve_realm_id(
            connection, realm_id=realm_id, realm=realm, region=region,
        )
        rows = connection.execute(
            """
            SELECT
                s.id,
                r.id AS realm_id,
                r.name AS realm,
                r.region,
                s.source_type,
                s.source_version,
                s.captured_at,
                s.imported_at,
                COUNT(si.id)::int AS items_count
            FROM auction_snapshots s
            JOIN realms r ON r.id = s.realm_id
            LEFT JOIN auction_snapshot_items si ON si.snapshot_id = s.id
            WHERE (%s::bigint IS NULL OR s.realm_id = %s)
            GROUP BY s.id, r.id
            ORDER BY s.captured_at DESC, s.id DESC
            LIMIT %s
            """,
            (selected_realm_id, selected_realm_id, safe_limit),
        ).fetchall()

    return [SnapshotSummaryResponse.model_validate(dict(row), from_attributes=False) for row in rows]
