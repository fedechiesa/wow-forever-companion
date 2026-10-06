from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.realms import resolve_realm_id
from app.api.schemas import (
    ItemDetailResponse,
    ItemHistoryPointResponse,
    ItemSummaryResponse,
)
from app.db.connection import connect

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemSummaryResponse])
def search_items(search: str = "", limit: int = 50) -> list[ItemSummaryResponse]:
    safe_limit = max(1, min(limit, 100))
    search_term = search.strip()
    with connect() as connection:
        if search_term:
            rows = connection.execute(
                """
                SELECT id, external_item_id, name, quality
                FROM items
                WHERE name ILIKE %s
                   OR external_item_id ILIKE %s
                ORDER BY name
                LIMIT %s
                """,
                (f"%{search_term}%", f"%{search_term}%", safe_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, external_item_id, name, quality
                FROM items
                ORDER BY name
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
    return [ItemSummaryResponse.model_validate(dict(row), from_attributes=False) for row in rows]


@router.get("/{item_id}", response_model=ItemDetailResponse)
def get_item(item_id: int) -> ItemDetailResponse:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, external_item_id, name, quality, created_at, updated_at
            FROM items
            WHERE id = %s
            """,
            (item_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return ItemDetailResponse.model_validate(dict(row), from_attributes=False)


@router.get("/{item_id}/history", response_model=list[ItemHistoryPointResponse])
def get_item_history(
    item_id: int,
    realm: str | None = None,
    region: str | None = None,
    realm_id: int | None = Query(default=None, gt=0, le=9223372036854775807),
) -> list[ItemHistoryPointResponse]:
    with connect() as connection:
        item_exists = connection.execute(
            "SELECT 1 FROM items WHERE id = %s",
            (item_id,),
        ).fetchone()
        if item_exists is None:
            raise HTTPException(status_code=404, detail="Item not found")

        selected_realm_id = resolve_realm_id(
            connection, realm_id=realm_id, realm=realm, region=region, require_single=True,
        )
        rows = connection.execute(
            """
            SELECT
                s.id AS snapshot_id,
                r.id AS realm_id,
                r.name AS realm,
                r.region,
                s.captured_at,
                si.min_buyout,
                si.avg_buyout,
                si.max_buyout,
                si.quantity_total,
                si.auction_count
            FROM auction_snapshot_items si
            JOIN auction_snapshots s ON s.id = si.snapshot_id
            JOIN realms r ON r.id = s.realm_id
            WHERE si.item_id = %s
              AND (%s::bigint IS NULL OR s.realm_id = %s)
            ORDER BY s.captured_at ASC, s.id ASC
            """,
            (item_id, selected_realm_id, selected_realm_id),
        ).fetchall()

    return [ItemHistoryPointResponse.model_validate(dict(row), from_attributes=False) for row in rows]
