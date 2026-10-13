"""Actual PostgreSQL in the existing per-test isolated schema, never development."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
from threading import Event
from time import perf_counter
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.db.connection import connect
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.adapters.file import FileAdapter
from app.ingestion.fresh_simulator import generate_fresh, lua_literal, simulation_lua
from app.ingestion.partial_service import PartialIngestionService
from app.ingestion.service import IngestionService, SnapshotImportInput
from app.main import create_app
from app.market.contracts import MetricsQuery
from app.market.repository import MarketRepository
from app.market.service import MarketAnalysisService
from tests.test_export_migration import fingerprint
from tests.test_ingestion_integration import snapshot_payload
from tests.test_market_validation import assert_openapi_json


@pytest.fixture(autouse=True)
def database(isolated_database):
    pass


def native(entries=None, *, markets=None, **context):
    entries = entries if entries is not None else {
        "123": {"l": {"10": 100, "11": 120, "12": 80},
                "h": {"10": 100, "11": 120, "12": 80}, "a": {"10": 5, "12": 0}, "m": 80}}
    database = {"__dbversion": 8, **(markets or {"PvE": {"version": 2, **entries}})}
    raw = ("AUCTIONATOR_PRICE_DATABASE=" + lua_literal(database)).encode()
    return AuctionatorAdapter().load_bytes(raw, source_id=context.pop("source_id", "test-source"),
                                          region=context.pop("region", "test"),
                                          dataset=context.pop("dataset", "simulated"), **context)


def market_id(source, market_key="PvE"):
    with connect() as c:
        return c.execute("SELECT id FROM partial_markets WHERE market_key=%s AND region=%s AND dataset=%s",
                         (market_key, source.batch.region, source.batch.dataset)).fetchone()["id"]


def params(source, *, mode="accumulated", item="123", market="PvE", **updates):
    return dict(market_id=market_id(source, market), item_key=item, source_id=source.batch.source_id,
                source_type=source.batch.source_type,
                temporal_basis=source.batch.scan_day_zero.isoformat() if source.batch.scan_day_zero else "unknown",
                series_mode=mode, window_type="observed_buckets", size=30) | updates


def metrics(source, **options):
    with TestClient(create_app()) as client:
        response = client.get("/market/metrics", params=params(source, **options))
    assert response.status_code == 200, response.text
    return response.json()


def value(response, name):
    return response["metrics"][name]["value"]


def test_known_calculations_real_sql_and_004_empty():
    source = native()
    PartialIngestionService().import_batch(replace(source, native=None))
    result = metrics(source)
    assert value(result, "minimum_copper") == "80"
    assert value(result, "mean_daily_minimum_copper") == "100"
    assert value(result, "median_daily_minimum_copper") == "100"
    assert value(result, "price_change_pct") == "-20"
    assert value(result, "minimum_stddev_copper") == "20"
    assert value(result, "minimum_cv_pct") == "20"
    assert value(result, "trend_copper_per_scan_index") == "-10"
    assert value(result, "availability_change_units") == "-5"
    assert value(result, "availability_change_pct") == "-100"
    assert result["coverage"]["price_observation_count"] == 3
    assert result["coverage"]["availability_observation_count"] == 2
    assert result["quality"]["minimum_unknown_origin_count"] == 3
    assert result["provenance"]["excluded_undated_count"] == 1
    assert all(p["bucket_start"] is None for p in result["points"])
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_exports").fetchone()["n"] == 0
    with TestClient(create_app()) as client:
        found = client.get("/market/series", params=dict(market_id=market_id(source), item_key="123")).json()
        assert len(found["series"]) == 1 and found["series"][0]["context"]["series_mode"] == "accumulated"
        unavailable = client.get("/market/metrics", params=params(source, mode="export", export_id=999))
        assert unavailable.status_code == 404


@pytest.mark.parametrize("reverse", [False, True])
def test_distinct_exports_and_reimport_do_not_mix_or_inflate_samples(reverse):
    sources = [native({"123": {"l": {}, "h": {"10": p}, "m": p}}) for p in (100, 200)]
    if reverse:
        sources.reverse()
    service = PartialIngestionService()
    imports = [service.import_batch(s) for s in sources]
    for s, result in zip(sources, imports):
        projected = metrics(s, mode="export", export_id=result.export_id)
        assert value(projected, "minimum_copper") == str(s.batch.observations[0].value)
        assert projected["quality"]["minimum_h_fallback_count"] == 1
        assert projected["coverage"]["price_observation_count"] == 1
        assert projected["provenance"]["selected_daily_row_count"] == 1
        assert projected["points"][0]["minimum_evidence"]["native_field"] == "h"
        assert service.import_batch(s).export_id == result.export_id
    accumulated = metrics(sources[0])
    assert value(accumulated, "minimum_copper") == "100"
    assert accumulated["points"][0]["daily_highest_minimum"] == 200
    with TestClient(create_app()) as client:
        page = client.get("/market/series", params=dict(market_id=market_id(sources[0]), item_key="123", limit=2)).json()
        assert page["has_more"] and len(page["series"]) == 2
        remaining = client.get("/market/series", params=dict(market_id=market_id(sources[0]), item_key="123", limit=2, offset=2)).json()
        assert not remaining["has_more"] and len(remaining["series"]) == 1
    assert metrics(sources[0])["coverage"]["price_observation_count"] == 1


@pytest.mark.parametrize("entry,presence,available", [
    ({"l": {}, "h": {"10": 100}}, "absent", None),
    ({"l": {}, "h": {"10": 100}, "a": {}}, "present", None),
    ({"l": {"10": 0}, "h": {"10": 100}, "a": {"10": 0}}, "present", 0),
])
def test_native_absent_empty_and_zero_have_distinct_semantics(entry, presence, available):
    source = native({"123": entry})
    imported = PartialIngestionService().import_batch(source)
    result = metrics(source, mode="export", export_id=imported.export_id)
    assert result["quality"]["availability_field_presence"] == presence
    assert result["points"][0]["daily_max_available"] == available
    assert result["coverage"]["availability_observation_count"] == int(available is not None)
    assert result["points"][0]["minimum_origin"] == ("l" if entry["l"] else "h_fallback")
    if entry["l"]:
        assert value(result, "minimum_copper") == "0"


def test_market_anchor_keeps_late_arrival_trailing_absences_and_market_gaps():
    source = native({
        "123": {"l": {"11": 100}, "h": {"11": 100}},
        "456": {"l": {}, "h": {"10": 20, "13": 30}},
    })
    imported = PartialIngestionService().import_batch(source)
    for mode in ("accumulated", "export"):
        options = {"export_id": imported.export_id} if mode == "export" else {}
        result = metrics(source, mode=mode, size=3, **options)
        assert [p["scan_day"] for p in result["points"]] == [10, 11, 13]
        assert result["window"]["anchor_day"] == 13
        assert result["coverage"]["missing_price_position_count"] == 2
        assert result["coverage"]["unobserved_market_position_count"] == 1
        assert "price_endpoints_inset" in {w["code"] for w in result["quality"]["warnings"]}
        with TestClient(create_app()) as client:
            requested = params(source, mode=mode, window_type="index_range", start_day=10, end_day=13, **options)
            requested.pop("size")
            ranged = client.get("/market/metrics", params=requested)
        assert ranged.status_code == 200
        assert [p["scan_day"] for p in ranged.json()["points"]] == [10, 11, 12, 13]
        assert ranged.json()["points"][2]["market_observed"] is False


def test_variants_markets_datasets_sources_regions_and_timebases_stay_separate():
    keys = ["123", "g:123:60", "gr:123:of the Bear", "p:123"]
    entries = {key: {"l": {}, "h": {"10": 100 + i}} for i, key in enumerate(keys)}
    contexts = [{}, {"dataset": "real"}, {"source_id": "other-source"}, {"region": "other-region"},
                {"scan_day_zero": "2020-01-01T00:00:00Z"}]
    for i, options in enumerate(contexts):
        modified = {key: {"l": {}, "h": {"10": 100 + j + i * 10}} for j, key in enumerate(keys)}
        source = native(markets={"PvE": {"version": 2, **modified}, "HC": {"version": 2, **entries}}, **options)
        imported = PartialIngestionService().import_batch(source)
        for key in keys:
            for mode in ("accumulated", "export"):
                extra = {"export_id": imported.export_id} if mode == "export" else {}
                result = metrics(source, item=key, mode=mode, **extra)
                assert value(result, "minimum_copper") == str(100 + keys.index(key) + i * 10)
                assert result["context"]["item_key"] == key
            assert value(metrics(source, item=key, market="HC"), "minimum_copper") == str(100 + keys.index(key))


def test_calendar_windows_are_market_anchored_and_unknown_calendar_rejected():
    unknown = native()
    known = native(scan_day_zero="2020-01-01T00:00:00Z")
    PartialIngestionService().import_batch(unknown)
    PartialIngestionService().import_batch(known)
    with TestClient(create_app()) as client:
        for source, status in ((unknown, 422), (known, 200)):
            requested = params(source, window_type="calendar_days", days=7)
            requested.pop("size")
            result = client.get("/market/metrics", params=requested)
            assert result.status_code == status
            if status == 200:
                assert result.json()["window"]["positions"] == list(range(6, 13))
                assert result.json()["window"]["calendar_start"] == "2020-01-07T00:00:00Z"
                assert result.json()["coverage"]["selected_position_count"] == 7
                assert result.json()["coverage"]["price_observation_count"] == 3


def test_empty_native_item_survives_catalog_edit_and_discovery():
    source = native({"123": {"l": {}, "h": {}}, "456": {"l": {}, "h": {"10": 100}}})
    imported = PartialIngestionService().import_batch(source)
    with connect() as c:
        c.execute("UPDATE partial_items SET item_key='999',external_item_id='999' WHERE item_key='123'")
    result = metrics(source, mode="export", export_id=imported.export_id)
    assert value(result, "minimum_copper") is None
    assert result["coverage"]["price_ratio"]["value"] == "0"
    with TestClient(create_app()) as client:
        found = client.get("/market/series", params=dict(market_id=market_id(source), item_key="123")).json()
        assert len(found["series"]) == 1 and found["series"][0]["context"]["item_key"] == "123"


def test_native_facts_survive_current_item_catalog_edit():
    source = native()
    imported = PartialIngestionService().import_batch(source)
    with connect() as c:
        c.execute("UPDATE partial_items SET item_key='999',external_item_id='999' WHERE item_key='123'")
    assert value(metrics(source, mode="export", export_id=imported.export_id), "minimum_copper") == "80"


@pytest.mark.parametrize("corruption", ["prices", "provenance"])
def test_incoherent_persisted_accumulation_returns_409(corruption):
    source = native()
    imported = PartialIngestionService().import_batch(source)
    with connect() as c:
        if corruption == "prices":
            c.execute("UPDATE partial_observations SET value=999 WHERE statistic='daily_minimum' AND scan_day=10")
        else:
            c.execute("UPDATE partial_import_runs SET source_id='wrong-source' WHERE id=%s", (imported.import_id,))
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params(source)).status_code == 409


def test_read_only_repeatable_read_and_preservation_of_existing_tables(monkeypatch):
    source = native()
    PartialIngestionService().import_batch(source)
    adapter = FileAdapter().load_payload(snapshot_payload(1))
    IngestionService().import_snapshot(SnapshotImportInput(adapter.snapshot, adapter.source_hash))
    with connect() as c:
        before = fingerprint(c)
        native_before = c.execute("SELECT t::text FROM partial_export_facts t ORDER BY id").fetchall()
    original = MarketRepository.observed_days
    checked = []

    def inspect(self, *args):
        settings = self.connection.execute("SHOW transaction_read_only").fetchone()
        isolation = self.connection.execute("SHOW transaction_isolation").fetchone()
        assert list(settings.values()) == ["on"]
        assert list(isolation.values()) == ["repeatable read"]
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            with self.connection.transaction():
                self.connection.execute("UPDATE partial_observations SET value=value")
        checked.append(True)
        return original(self, *args)

    monkeypatch.setattr(MarketRepository, "observed_days", inspect)
    assert value(metrics(source), "minimum_copper") == "80"
    assert checked
    with connect() as c:
        assert fingerprint(c) == before
        assert c.execute("SELECT t::text FROM partial_export_facts t ORDER BY id").fetchall() == native_before


def test_concurrent_ingestion_cannot_change_an_in_progress_analysis_snapshot(monkeypatch):
    source = native({"123": {"l": {"10": 100}, "h": {"10": 100}}})
    update = native({"123": {"l": {"10": 50}, "h": {"10": 100}}})
    PartialIngestionService().import_batch(source)
    request = MetricsQuery(**params(source)).analysis_request()
    read_started, write_done = Event(), Event()
    original = MarketRepository.observed_days

    def pause(self, *args):
        result = original(self, *args)
        read_started.set()
        assert write_done.wait(15)
        return result

    monkeypatch.setattr(MarketRepository, "observed_days", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(MarketAnalysisService().analyze, request)
        try:
            assert read_started.wait(15)
            PartialIngestionService().import_batch(update)
        finally:
            write_done.set()
        result = future.result(timeout=15)
    assert result.metrics.minimum_copper.value == 100
    monkeypatch.setattr(MarketRepository, "observed_days", original)
    assert value(metrics(source), "minimum_copper") == "50"


def test_full_16628_simulation_works_with_empty_native_tables_without_touching_phase2():
    database, _ = generate_fresh()
    source = AuctionatorAdapter().load_bytes(simulation_lua(database), source_id="fresh-seed-340",
                                            region="simulation", dataset="simulated")
    service = PartialIngestionService()
    service.import_batch(replace(source, native=None))
    service.import_batch(replace(source, native=None))
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == 16628
        assert c.execute("SELECT count(*) AS n FROM partial_exports").fetchone()["n"] == 0
        assert c.execute("SELECT count(*) AS n FROM auction_snapshots").fetchone()["n"] == 0
        before = fingerprint(c)
    for market in ("PvE", "PvP", "HC", "RP"):
        result = metrics(source, item="1900000000", market=market)
        assert result["coverage"]["price_observation_count"] == 30
        assert result["coverage"]["availability_observation_count"] == 30
        assert len(result["points"]) == 30
        assert result["provenance"]["selected_daily_row_count"] == 90
        assert result["provenance"]["excluded_undated_count"] == 1
    with connect() as c:
        assert fingerprint(c) == before


@pytest.mark.parametrize("days,prices", [
    ([10, 11, 12], [1, 2, 1]),
    ([0, 1, 2147483647], [1, 2, 3]),
    ([10, 11, 13], [100, 120, 80]),
    ([10, 11, 12], [1, 1, 2]),
])
@pytest.mark.parametrize("mode", ["accumulated", "export"])
def test_real_metrics_response_conforms_to_served_openapi(days, prices, mode):
    source = native({"123": {"l": {}, "h": {str(d): p for d, p in zip(days, prices)}}})
    imported = PartialIngestionService().import_batch(source)
    extra = {"export_id": imported.export_id} if mode == "export" else {}
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
        response = client.get("/market/metrics", params=params(source, mode=mode, **extra))
    assert response.status_code == 200
    schema = document["paths"]["/market/metrics"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    body = response.json()
    assert_openapi_json(body, schema, document)
    for metric in body["metrics"].values():
        assert metric["value"] is None or "e" not in metric["value"].lower()
    invalid = deepcopy(body)
    invalid["metrics"]["trend_copper_per_scan_index"]["value"] = "0E-39"
    with pytest.raises(AssertionError):
        assert_openapi_json(invalid, schema, document)


def test_discovery_query_budget_is_constant_for_large_pages_and_empty_native_items(monkeypatch):
    sources = []
    for i in range(100):
        source = native({"123": {"l": {}, "h": {"10": i + 1}, "m": i + 1},
                         "456": {"l": {}, "h": {}}}, source_id=f"page-{i:03d}")
        PartialIngestionService().import_batch(source)
        sources.append(source)
    mid = market_id(sources[0])
    statements = []

    class CountedConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, parameters=None):
            if not statement.startswith("SET TRANSACTION"):
                statements.append(statement)
            return self.connection.execute(statement, parameters)

    @contextmanager
    def counted_connect():
        with connect() as connection:
            yield CountedConnection(connection)

    monkeypatch.setattr("app.market.service.connect", counted_connect)
    budgets = {"export": 5, "accumulated": 4, "mixed": 7}
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
        schema = document["paths"]["/market/series"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        for mode, budget in budgets.items():
            for limit in (1, 10, 100):
                query = dict(market_id=mid, item_key="123", limit=limit)
                if mode == "mixed":
                    query["offset"] = 99  # One accumulated context followed by exports.
                else:
                    query["series_mode"] = mode
                statements.clear()
                started = perf_counter()
                response = client.get("/market/series", params=query)
                elapsed = perf_counter() - started
                assert response.status_code == 200, response.text
                body = response.json()
                assert len(body["series"]) == limit
                assert len(statements) <= budget
                if mode != "mixed" or limit > 1:
                    assert len(statements) == budget
                assert_openapi_json(body, schema, document)
                print(f"discovery mode={mode} limit={limit} SELECTs={len(statements)} seconds={elapsed:.4f}")
                for series in body["series"]:
                    assert series["item_first_day"] == series["item_last_day"] == 10
                    assert series["market_first_day"] == series["market_last_day"] == 10
                    assert series["excluded_undated_count"] == 1
                    assert series["context"]["dataset"] == "simulated"
        statements.clear()
        response = client.get("/market/series", params=dict(market_id=mid, item_key="456", limit=100))
        assert response.status_code == 200 and len(response.json()["series"]) == 100
        assert len(statements) == budgets["export"]
        assert all(s["item_first_day"] is None and s["excluded_undated_count"] == 0
                   for s in response.json()["series"])


def clone_export_for_corruption(imported, manifest, *, wrong_fact_identity=False):
    """SQL outside ingestion, with all 004 guards active, only in isolated testing."""
    with connect() as c:
        run = c.execute(
            """INSERT INTO partial_import_runs(source_type,source_id,source_version,database_version,dataset,
                 region,temporal_basis,source_hash,status,observations_seen,observations_changed)
               SELECT source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                 source_hash,'completed',observations_seen,0 FROM partial_import_runs WHERE id=%s RETURNING id""",
            (imported.import_id,),
        ).fetchone()["id"]
        export = c.execute(
            """INSERT INTO partial_exports(source_type,source_id,source_version,database_version,dataset,region,
                 temporal_basis,canonical_version,state_hash,structure_manifest,native_fact_count,first_import_id)
               SELECT source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                 canonical_version,%s,%s,native_fact_count,%s FROM partial_exports WHERE id=%s RETURNING id""",
            (sha256(uuid4().bytes).hexdigest(), Jsonb(manifest), run, imported.export_id),
        ).fetchone()["id"]
        c.execute(
            """INSERT INTO partial_export_facts(export_id,market_id,item_id,market_key,ruleset,item_key,
                 external_item_id,key_kind,original_item_key,native_field,scan_day,original_day_key,value)
               SELECT %s,market_id,item_id,market_key,ruleset,item_key,
                 CASE WHEN %s THEN '999' ELSE external_item_id END,key_kind,original_item_key,
                 native_field,scan_day,original_day_key,value FROM partial_export_facts WHERE export_id=%s""",
            (export, wrong_fact_identity, imported.export_id),
        )
        c.execute("UPDATE partial_exports SET sealed=true WHERE id=%s", (export,))
        c.execute("""INSERT INTO partial_export_imports(import_id,export_id,input_format,decoder_version)
                     VALUES (%s,%s,'lua_tables','auctionator340-v1')""", (run, export))
    return export, run


@pytest.mark.parametrize("corruption", ["object", "null", "scalar", "market_element", "items_object",
                                         "missing_market", "missing_item", "version_bool"])
def test_corrupt_manifests_return_409_without_poisoning_unrelated_contexts(corruption):
    source = native()
    imported = PartialIngestionService().import_batch(source)
    other = native({"456": {"l": {}, "h": {"10": 777}}})
    other_imported = PartialIngestionService().import_batch(other)
    manifest = deepcopy(source.native.manifest())
    if corruption in ("object", "null", "scalar", "market_element", "missing_market"):
        manifest["markets"] = {"object": {}, "null": None, "scalar": "invalid",
                               "market_element": [None], "missing_market": []}[corruption]
    elif corruption == "items_object":
        manifest["markets"][0]["items"] = {}
    elif corruption == "missing_item":
        manifest["markets"][0]["items"] = []
    else:
        manifest["version"] = True
    bad, _ = clone_export_for_corruption(imported, manifest)
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params(source, mode="export", export_id=bad)).status_code == 409
        selected = dict(market_id=market_id(source), item_key="123")
        assert client.get("/market/series", params=selected).status_code == 409
        assert client.get("/market/series", params=selected | {"series_mode": "export"}).status_code == 409
        assert client.get("/market/series", params=selected | {"series_mode": "accumulated"}).status_code == 200
        unrelated = client.get("/market/series", params=selected | {"item_key": "456"})
        assert unrelated.status_code == 200, unrelated.text
        assert {s["context"]["export_id"] for s in unrelated.json()["series"]
                if s["context"]["series_mode"] == "export"} == {other_imported.export_id}
        assert client.get("/market/metrics", params=params(other, item="456", mode="export",
                                                          export_id=other_imported.export_id)).status_code == 200
        assert client.get("/market/metrics", params=params(source, mode="export",
                                                          export_id=imported.export_id)).status_code == 200


@pytest.mark.parametrize("corruption", ["facts", "reception_source", "reception_failed", "field_presence"])
def test_batched_export_reads_preserve_fact_field_and_reception_validation(corruption):
    source = native()
    imported = PartialIngestionService().import_batch(source)
    manifest = source.native.manifest()
    if corruption == "field_presence":
        manifest["markets"][0]["items"][0]["fields_present"].remove("a")
    bad, run = clone_export_for_corruption(imported, manifest, wrong_fact_identity=corruption == "facts")
    if corruption in ("reception_source", "reception_failed"):
        with connect() as c:
            if corruption == "reception_source":
                c.execute("UPDATE partial_import_runs SET source_id='wrong-source' WHERE id=%s", (run,))
            else:
                c.execute("UPDATE partial_import_runs SET status='failed' WHERE id=%s", (run,))
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params(source, mode="export", export_id=bad)).status_code == 409
        assert client.get("/market/series", params=dict(market_id=market_id(source), item_key="123",
                                                       series_mode="export")).status_code == 409


@pytest.mark.parametrize("reception", ["first", "last"])
def test_batched_accumulation_checks_both_imports_without_poisoning_other_sources(reception):
    first = native({"123": {"l": {"10": 100}, "h": {"10": 100}}}, source_id="affected")
    last = native({"123": {"l": {"10": 50}, "h": {"10": 100}}}, source_id="affected")
    other = native({"456": {"l": {}, "h": {"11": 77}}}, source_id="unrelated")
    service = PartialIngestionService()
    first_import = service.import_batch(first)
    last_import = service.import_batch(last)
    service.import_batch(other)
    corrupt_id = first_import.import_id if reception == "first" else last_import.import_id
    with connect() as c:
        c.execute("UPDATE partial_import_runs SET source_id='wrong-source' WHERE id=%s", (corrupt_id,))
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params(first)).status_code == 409
        assert client.get("/market/series", params=dict(market_id=market_id(first), item_key="123",
                                                       series_mode="accumulated")).status_code == 409
        assert client.get("/market/metrics", params=params(other, item="456")).status_code == 200
        assert client.get("/market/series", params=dict(market_id=market_id(other), item_key="456",
                                                       series_mode="accumulated")).status_code == 200
