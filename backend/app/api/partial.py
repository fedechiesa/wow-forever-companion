import hashlib
import json
from datetime import datetime, timedelta

import psycopg
from fastapi import APIRouter, HTTPException, Query

from app.db.connection import connect
from app.ingestion.adapters.auctionator import PartialAdapterResult
from app.ingestion.partial_contracts import PartialBatch, PartialImportResult
from app.ingestion.partial_service import PartialIngestionService

router = APIRouter(prefix="/partial", tags=["partial Auctionator evidence"])


@router.post("/imports", response_model=PartialImportResult)
def import_partial(batch: PartialBatch):
    raw = json.dumps(batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    result = PartialAdapterResult(batch, hashlib.sha256(raw).hexdigest(), "http:POST /partial/imports")
    try:
        return PartialIngestionService().import_batch(result)
    except psycopg.Error as error:
        raise HTTPException(500, "Partial import failed") from error


@router.get("/imports")
def list_partial_imports(limit: int = Query(50, ge=1, le=100)):
    with connect() as c:
        return c.execute(
            """SELECT r.*,link.export_id,COALESCE(e.native_fact_count,0) AS native_facts_seen,
                      CASE WHEN e.id IS NULL THEN 'unavailable'
                           WHEN e.first_import_id=r.id THEN 'created' ELSE 'reused' END AS evidence_status
               FROM partial_import_runs r LEFT JOIN partial_export_imports link ON link.import_id=r.id
               LEFT JOIN partial_exports e ON e.id=link.export_id
               ORDER BY r.imported_at DESC,r.id DESC LIMIT %s""", (limit,),
        ).fetchall()


@router.get("/markets")
def list_partial_markets():
    with connect() as c:
        return c.execute("SELECT * FROM partial_markets ORDER BY dataset,region,market_key").fetchall()


@router.get("/items")
def list_partial_items(market_id: int = Query(gt=0, le=9223372036854775807),
                       limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=2147483647)):
    with connect() as c:
        if not c.execute("SELECT 1 FROM partial_markets WHERE id=%s", (market_id,)).fetchone():
            raise HTTPException(404, "Partial market not found")
        return c.execute(
            """SELECT DISTINCT i.* FROM partial_items i JOIN partial_observations o ON o.item_id=i.id
               WHERE o.market_id=%s ORDER BY i.item_key LIMIT %s OFFSET %s""", (market_id, limit, offset),
        ).fetchall()


@router.get("/history")
def partial_history(market_id: int = Query(gt=0, le=9223372036854775807),
                    item_key: str = Query(min_length=1, max_length=200),
                    source_id: str = Query(min_length=1, max_length=200),
                    temporal_basis: str = "unknown",
                    export_id: int | None = Query(None, gt=0, le=9223372036854775807),
                    start_day: int | None = Query(None, ge=0, le=2147483647),
                    end_day: int | None = Query(None, ge=0, le=2147483647),
                    limit: int = Query(5000, ge=1, le=10000), offset: int = Query(0, ge=0, le=2147483647)):
    if start_day is not None and end_day is not None and start_day > end_day:
        raise HTTPException(422, "start_day exceeds end_day")
    with connect() as c:
        if not c.execute("SELECT 1 FROM partial_markets WHERE id=%s", (market_id,)).fetchone():
            raise HTTPException(404, "Partial market not found")
        if export_id is not None:
            header = c.execute(
                "SELECT id FROM partial_exports WHERE id=%s AND sealed AND source_id=%s AND temporal_basis=%s",
                (export_id, source_id, temporal_basis),
            ).fetchone()
            if header is None:
                raise HTTPException(404, "Export not found for selected source/time basis")
            rows = _export_history(c, export_id, market_id, item_key, start_day, end_day, limit, offset)
        else:
            rows = c.execute(
            """SELECT o.*,i.item_key,i.external_item_id,i.key_kind,m.market_key,m.ruleset,m.region,m.dataset,
                      first_run.imported_at AS first_imported_at,last_run.imported_at AS last_imported_at,
                      last_run.source_hash,last_run.source_version,last_run.database_version,last_run.raw_reference
               FROM partial_observations o JOIN partial_items i ON i.id=o.item_id
               JOIN partial_markets m ON m.id=o.market_id
               JOIN partial_import_runs first_run ON first_run.id=o.first_import_id
               JOIN partial_import_runs last_run ON last_run.id=o.last_import_id
               WHERE o.market_id=%s AND i.item_key=%s AND o.source_id=%s AND o.temporal_basis=%s
                 AND (%s::integer IS NULL OR o.scan_day >= %s)
                 AND (%s::integer IS NULL OR o.scan_day <= %s)
               ORDER BY o.scan_day NULLS LAST,o.statistic,o.id LIMIT %s OFFSET %s""",
            (market_id, item_key, source_id, temporal_basis, start_day, start_day, end_day, end_day, limit, offset),
            ).fetchall()
    for row in rows:
        row["value_semantics"] = ("export_projection" if export_id is not None else
                                  "undated_normalized_state" if row["scan_day"] is None else "accumulated_extreme")
        row["day_start"] = None
        if row["scan_day"] is not None and row["temporal_basis"] != "unknown":
            try:
                row["day_start"] = datetime.fromisoformat(row["temporal_basis"]) + timedelta(days=row["scan_day"])
            except (ValueError, OverflowError):
                # Index remains valid even when its calendar representation is out of range.
                pass
    return rows


def _export_history(c, export_id, market_id, item_key, start_day, end_day, limit, offset):
    # Do not manufacture an l fact. The extra minimum row is explicitly a
    # GetPriceHistory projection, with its native origin preserved.
    return c.execute(
        """WITH facts AS (
               SELECT * FROM partial_export_facts WHERE export_id=%s AND market_id=%s AND item_key=%s
           ), projected AS (
               SELECT COALESCE(l.id,h.id) AS source_fact_id,h.export_id,h.market_id,h.item_id,h.market_key,h.ruleset,h.item_key,
                      h.external_item_id,h.key_kind,h.original_item_key,h.scan_day,h.original_day_key,
                      'daily_minimum'::text AS statistic,COALESCE(l.value,h.value) AS value,
                      CASE WHEN l.id IS NULL THEN 'h' ELSE 'l' END AS native_field,
                      CASE WHEN l.id IS NULL THEN 'h_fallback' ELSE 'l' END AS minimum_origin
               FROM facts h LEFT JOIN facts l ON l.item_id=h.item_id AND l.market_id=h.market_id
                   AND l.scan_day=h.scan_day AND l.native_field='l'
               WHERE h.native_field='h'
               UNION ALL
               SELECT f.id,f.export_id,f.market_id,f.item_id,f.market_key,f.ruleset,f.item_key,
                      f.external_item_id,f.key_kind,f.original_item_key,f.scan_day,f.original_day_key,
                      CASE f.native_field WHEN 'h' THEN 'daily_highest_minimum'
                           WHEN 'a' THEN 'daily_max_available' ELSE 'last_minimum' END,
                      f.value,f.native_field,NULL::text
               FROM facts f WHERE f.native_field IN ('h','a','m')
           )
           SELECT p.*,e.source_id,e.source_type,e.source_version,e.database_version,
                  e.region,e.dataset,e.temporal_basis,e.first_import_id,
                  r.imported_at AS first_received_at,r.source_hash,r.raw_reference
           FROM projected p JOIN partial_exports e ON e.id=p.export_id
           JOIN partial_import_runs r ON r.id=e.first_import_id
           WHERE (%s::integer IS NULL OR p.scan_day >= %s)
             AND (%s::integer IS NULL OR p.scan_day <= %s)
           ORDER BY p.scan_day NULLS LAST,p.statistic,p.source_fact_id LIMIT %s OFFSET %s""",
        (export_id,market_id,item_key,start_day,start_day,end_day,end_day,limit,offset),
    ).fetchall()
