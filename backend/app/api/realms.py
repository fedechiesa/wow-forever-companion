import psycopg
from fastapi import HTTPException


def resolve_realm_id(
    connection: psycopg.Connection,
    *,
    realm_id: int | None,
    realm: str | None,
    region: str | None,
    require_single: bool = False,
) -> int | None:
    if realm_id is None and realm is None and region is None and not require_single:
        return None
    if region is not None and realm_id is None and realm is None:
        raise HTTPException(status_code=422, detail="region requires realm or realm_id")
    normalized_name = realm.strip() if realm is not None else None
    normalized_region = (region.strip() or None) if region is not None else None
    rows = connection.execute(
        """
        SELECT id FROM realms
        WHERE (%s::bigint IS NULL OR id = %s)
          AND (%s::text IS NULL OR name = %s)
          AND (NOT %s::boolean OR COALESCE(region, '') = COALESCE(%s, ''))
        ORDER BY id
        LIMIT 2
        """,
        (
            realm_id,
            realm_id,
            normalized_name,
            normalized_name,
            region is not None,
            normalized_region,
        ),
    ).fetchall()
    if len(rows) > 1:
        raise HTTPException(status_code=422, detail="Ambiguous realm; specify realm_id or realm and region")
    if not rows:
        if realm_id is not None or realm is not None or region is not None:
            raise HTTPException(status_code=404, detail="Realm not found")
        return None
    return int(rows[0]["id"])
