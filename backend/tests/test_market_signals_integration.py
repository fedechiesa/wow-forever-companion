"""All writes use the authorized dedicated test DB and an isolated UUID schema."""
from dataclasses import replace

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
import pytest

from app.db.connection import connect
from app.ingestion.adapters.file import FileAdapter
from app.ingestion.partial_service import PartialIngestionService
from app.ingestion.service import IngestionService, SnapshotImportInput
from app.main import create_app
from app.market.repository import MarketRepository
from tests.test_export_migration import fingerprint
from tests.test_ingestion_integration import snapshot_payload
from tests.test_market_integration import native, params
from tests.test_market_validation import assert_openapi_json


@pytest.fixture(autouse=True)
def database(isolated_database):
    pass


def source_for(values=None, *, item="123", fallback=False, **context):
    values = values if values is not None else [100] * 7 + [80]
    prices = {str(10 + i): p for i, p in enumerate(values) if p is not None}
    return native({item: {"l": {} if fallback else prices, "h": prices,
                          "a": {"10": 10000, "17": 0}, "m": 999999}}, **context)


def full_fingerprint(c):
    result = fingerprint(c)
    for name in ("schema_migrations", "partial_exports", "partial_export_facts", "partial_export_imports"):
        result[name] = c.execute(sql.SQL("SELECT t::text FROM {} t ORDER BY t::text").format(sql.Identifier(name))).fetchall()
    return result


@pytest.mark.parametrize("mode", ["accumulated", "export"])
def test_signals_real_sql_preserve_metrics_tables_rows_sequences_and_openapi(monkeypatch, mode):
    source = source_for()
    imported = PartialIngestionService().import_batch(source)
    snapshot = FileAdapter().load_payload(snapshot_payload(1))
    IngestionService().import_snapshot(SnapshotImportInput(snapshot.snapshot, snapshot.source_hash))
    with connect() as c:
        before = full_fingerprint(c)
    checked = []
    original = MarketRepository.observed_days

    def inspect(self, *args):
        assert list(self.connection.execute("SHOW transaction_read_only").fetchone().values()) == ["on"]
        assert list(self.connection.execute("SHOW transaction_isolation").fetchone().values()) == ["repeatable read"]
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with self.connection.transaction():
                self.connection.execute("UPDATE partial_observations SET value=value")
        checked.append(True)
        return original(self, *args)

    monkeypatch.setattr(MarketRepository, "observed_days", inspect)
    options = {"export_id": imported.export_id} if mode == "export" else {}
    query = params(source, mode=mode, size=8, **options)
    with TestClient(create_app()) as client:
        metrics_before = client.get("/market/metrics", params=query)
        response = client.get("/market/signals", params=query)
        metrics_after = client.get("/market/metrics", params=query)
        document = client.get("/openapi.json").json()
    assert metrics_before.status_code == response.status_code == metrics_after.status_code == 200
    assert metrics_before.content == metrics_after.content
    result = response.json()
    assert result["price_deviation"]["direction"] == "below_reference"
    assert result["price_deviation"]["reference_price_copper"]["value"] == "100"
    assert result["price_deviation"]["deviation_pct"]["value"] == "-20"
    assert result["historical_trend"]["direction"] == "descending"
    assert result["historical_trend"]["slope_copper_per_scan_index"] == metrics_before.json()["metrics"]["trend_copper_per_scan_index"]
    for key in ("context", "window", "points", "coverage", "quality", "provenance"):
        assert result[key] == metrics_before.json()[key]
    assert result["provenance"]["excluded_undated_count"] == 1  # m=999999 never becomes the observed price.
    assert result["price_deviation"]["observed_price_copper"]["value"] == "80"
    schema = document["paths"]["/market/signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert_openapi_json(result, schema, document)
    assert len(checked) == 3  # Exactly one 3A read transaction per request.
    with connect() as c:
        assert full_fingerprint(c) == before


def test_004_empty_supports_accumulation_and_honors_native_and_window_requirements():
    source = source_for()
    PartialIngestionService().import_batch(replace(source, native=None))
    with TestClient(create_app()) as client:
        result = client.get("/market/signals", params=params(source, size=8)).json()
        short = client.get("/market/signals", params=params(source, size=30)).json()
        strict = client.get("/market/signals", params=params(source, size=8) | {"require_native_l": "true"}).json()
        missing = client.get("/market/signals", params=params(source, mode="export", export_id=999, size=8))
    assert result["price_deviation"]["direction"] == "below_reference"
    assert short["price_deviation"]["direction"] == strict["price_deviation"]["direction"] == "insufficient_evidence"
    assert "native_l_required" in {r["code"] for r in strict["price_deviation"]["evidence"]["reasons"]}
    assert missing.status_code == 404
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_exports").fetchone()["n"] == 0


def test_exports_not_merged_and_reimports_not_counted_as_observations():
    service = PartialIngestionService()
    first, second = source_for(), source_for([200] * 7 + [240], fallback=True)
    first_import, second_import = service.import_batch(first), service.import_batch(second)
    assert service.import_batch(first).export_id == first_import.export_id
    with TestClient(create_app()) as client:
        below = client.get("/market/signals", params=params(first, mode="export", export_id=first_import.export_id, size=8)).json()
        above = client.get("/market/signals", params=params(second, mode="export", export_id=second_import.export_id, size=8)).json()
        accumulated = client.get("/market/signals", params=params(first, size=8)).json()
        strict = client.get("/market/signals", params=params(second, mode="export", export_id=second_import.export_id, size=8) | {"require_native_l": "true"}).json()
    assert below["price_deviation"]["direction"] == accumulated["price_deviation"]["direction"] == "below_reference"
    assert above["price_deviation"]["direction"] == "above_reference"
    assert above["price_deviation"]["evidence"]["minimum_h_fallback_count"] == 8
    assert strict["price_deviation"]["direction"] == "insufficient_evidence"
    assert below["provenance"]["export_state_hash"] != above["provenance"]["export_state_hash"]
    assert below["price_deviation"]["evidence"]["usable_observation_count"] == 8


@pytest.mark.parametrize("mode", ["accumulated", "export"])
def test_context_variant_source_region_and_window_are_retained(mode):
    source = source_for(item="g:123:60", source_id="specific-source", region="specific-region",
                        scan_day_zero="2020-01-01T00:00:00Z")
    imported = PartialIngestionService().import_batch(source)
    extra = {"export_id": imported.export_id} if mode == "export" else {}
    query = params(source, mode=mode, item="g:123:60", window_type="index_range", start_day=10, end_day=17, **extra)
    query.pop("size")
    with TestClient(create_app()) as client:
        response = client.get("/market/signals", params=query | {"require_known_temporal_basis": "true"})
        other = client.get("/market/signals", params=query | {"source_id": "missing-source"})
        invalid = client.get("/market/signals", params=query | {"item_key": "123"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["context"]["item_key"] == "g:123:60"
    assert result["context"]["region"] == "specific-region"
    assert result["context"]["source_id"] == "specific-source"
    assert result["context"]["temporal_basis"] == "2020-01-01T00:00:00+00:00"
    assert result["context"]["series_mode"] == mode
    assert result["window"]["spec"] == {"window_type": "index_range", "start_day": 10, "end_day": 17, "size": None, "days": None}
    assert result["window"]["positions"] == list(range(10, 18))
    assert result["price_deviation"]["direction"] == "below_reference"
    assert other.status_code == invalid.status_code == 404


def test_calendar_window_and_empty_price_window_have_structured_evidence():
    source = source_for(scan_day_zero="2020-01-01T00:00:00Z")
    PartialIngestionService().import_batch(source)
    calendar = params(source, window_type="calendar_days", days=14)
    calendar.pop("size")
    empty = params(source, window_type="index_range", start_day=100, end_day=107)
    empty.pop("size")
    with TestClient(create_app()) as client:
        ranged = client.get("/market/signals", params=calendar)
        response = client.get("/market/signals", params=empty)
    assert ranged.status_code == response.status_code == 200
    assert ranged.json()["window"]["calendar_start"] is not None
    assert "insufficient_price_coverage" in {r["code"] for r in ranged.json()["price_deviation"]["evidence"]["reasons"]}
    result = response.json()
    assert result["price_deviation"]["direction"] == result["historical_trend"]["direction"] == "insufficient_evidence"
    assert result["price_deviation"]["observed_price_copper"]["value"] is None
