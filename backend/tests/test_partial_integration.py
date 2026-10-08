from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.db.connection import connect
from app.ingestion.adapters.auctionator import PartialAdapterResult
from app.ingestion.partial_contracts import PartialBatch
from app.ingestion.partial_service import PartialIngestionService
from app.main import create_app
from tests.test_auctionator import fixture_result


@pytest.fixture(autouse=True)
def database(isolated_database):
    pass


def test_partial_import_repeat_and_phase2_separation():
    source = fixture_result()
    first = PartialIngestionService().import_batch(source)
    second = PartialIngestionService().import_batch(source)
    assert first.status == "completed" and second.status == "duplicate"
    assert second.observations_changed == 0
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == len(source.batch.observations)
        for table in ("realms", "items", "auction_snapshots", "auction_snapshot_items", "import_runs"):
            assert c.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0


def test_history_order_variants_markets_real_simulated_and_unknown_dates():
    service = PartialIngestionService()
    service.import_batch(fixture_result())
    service.import_batch(fixture_result(dataset="simulated"))
    with TestClient(create_app()) as client:
        markets = client.get("/partial/markets").json()
        assert len(markets) == 8
        for market in markets:
            history = client.get("/partial/history", params={
                "market_id": market["id"], "item_key": "2772", "source_id": "fixture-account",
            })
            assert history.status_code == 200
            rows = history.json()
            assert all(r["market_key"] == market["market_key"] and r["dataset"] == market["dataset"] for r in rows)
            days = [r["scan_day"] for r in rows if r["scan_day"] is not None]
            assert days == sorted(days)
            assert all(r["day_start"] is None for r in rows)
            if market["market_key"] != "PvE":
                assert len(rows) == 3
                assert rows[0]["value"] == {"PvP": 200, "HC": 300, "RP": 400}[market["market_key"]]
        pve = next(m for m in markets if m["market_key"] == "PvE" and m["dataset"] == "real")
        items = client.get("/partial/items", params={"market_id": pve["id"]}).json()
        assert {i["item_key"] for i in items} == {"2772", "g:123:60", "gr:123:of the Bear", "p:123"}
        assert client.get("/partial/history", params={"item_key": "2772", "source_id": "fixture-account"}).status_code == 422
        assert client.get("/partial/history", params={"market_id": 999, "item_key": "2772", "source_id": "fixture-account"}).status_code == 404


def test_mid_import_failure_rolls_back_and_records_failure(monkeypatch):
    original = PartialIngestionService._persist_observation
    count = 0

    def fail_second(self, connection, *args):
        nonlocal count
        count += 1
        if count == 2:
            connection.execute("SELECT 1/0")
        return original(self, connection, *args)

    monkeypatch.setattr(PartialIngestionService, "_persist_observation", fail_second)
    with pytest.raises(psycopg.Error):
        PartialIngestionService().import_batch(fixture_result())
    with connect() as c:
        for table in ("partial_markets", "partial_items", "partial_observations"):
            assert c.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        assert c.execute("SELECT status,observations_changed FROM partial_import_runs").fetchall() == [{"status": "failed", "observations_changed": 0}]


def test_daily_extrema_evolve_and_stale_import_cannot_regress():
    service = PartialIngestionService()
    original = fixture_result()
    service.import_batch(original)
    payload = original.batch.model_dump()
    for o in payload["observations"]:
        if o["market_key"] == "PvE" and o["item_key"] == "2772" and o["scan_day"] == 2501:
            o["value"] = {"daily_minimum": 80, "daily_highest_minimum": 180, "daily_max_available": 30}[o["statistic"]]
    updated = PartialAdapterResult(PartialBatch.model_validate(payload), "a" * 64)
    assert service.import_batch(updated).observations_changed == 10  # Three extrema plus seven undated evidence rows.
    assert service.import_batch(original).status == "duplicate"
    with connect() as c:
        rows = c.execute("""SELECT statistic,value FROM partial_observations o JOIN partial_items i ON i.id=o.item_id
                            JOIN partial_markets m ON m.id=o.market_id
                            WHERE m.market_key='PvE' AND i.item_key='2772' AND scan_day=2501 ORDER BY statistic""").fetchall()
    assert rows == [{"statistic": "daily_highest_minimum", "value": 180}, {"statistic": "daily_max_available", "value": 30}, {"statistic": "daily_minimum", "value": 80}]


def test_concurrent_imports_and_http_same_semantics():
    result = fixture_result()
    with ThreadPoolExecutor(max_workers=2) as pool:
        imports = list(pool.map(lambda _: PartialIngestionService().import_batch(result), range(2)))
    assert sorted(r.status for r in imports) == ["completed", "duplicate"]
    with TestClient(create_app()) as client:
        response = client.post("/partial/imports", json=result.batch.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["status"] == "duplicate"
        assert len(client.get("/partial/imports").json()) == 3


def test_source_and_timebase_are_isolated():
    for source_id, epoch in [("a", None), ("b", None), ("a", "2020-01-01T00:00:00Z")]:
        PartialIngestionService().import_batch(fixture_result(source_id=source_id, scan_day_zero=epoch))
    with connect() as c:
        market_id = c.execute("SELECT id FROM partial_markets WHERE market_key='PvE'").fetchone()["id"]
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == 3 * len(fixture_result().batch.observations)
    with TestClient(create_app()) as client:
        response = client.get("/partial/history", params={"market_id": market_id, "item_key": "2772", "source_id": "a", "temporal_basis": "2020-01-01T00:00:00+00:00"})
    assert response.status_code == 200
    assert response.json()[0]["day_start"] is not None
    assert response.json()[-1]["day_start"] is None


def test_region_and_ruleset_mapping_conflict():
    service = PartialIngestionService()
    service.import_batch(fixture_result())
    service.import_batch(fixture_result(region="other-region"))
    payload = fixture_result().batch.model_dump()
    for observation in payload["observations"]:
        if observation["market_key"] == "PvE":
            observation["market_key"] = "External Realm Alliance"
    external = PartialAdapterResult(PartialBatch.model_validate(payload), "c" * 64)
    service.import_batch(external)
    for observation in payload["observations"]:
        if observation["market_key"] == "External Realm Alliance":
            observation["ruleset"] = "HC"
    conflicting = PartialAdapterResult(PartialBatch.model_validate(payload), "d" * 64)
    with pytest.raises(psycopg.IntegrityError):
        service.import_batch(conflicting)
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_markets").fetchone()["n"] == 9
        assert c.execute("SELECT count(*) AS n FROM partial_import_runs WHERE status='failed'").fetchone()["n"] == 1


@pytest.mark.parametrize("assignment", ["value=-1", "scan_day=-1", "statistic='sales'", "scan_day=NULL"])
def test_database_constraints_reject_invalid_daily_rows(assignment):
    PartialIngestionService().import_batch(fixture_result())
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as c:
            c.execute(f"UPDATE partial_observations SET {assignment} WHERE statistic='daily_minimum'")


def test_http_persistence_failure_returns_500(monkeypatch):
    def fail(self, connection, *args):
        connection.execute("SELECT 1/0")

    monkeypatch.setattr(PartialIngestionService, "_persist_observation", fail)
    with TestClient(create_app()) as client:
        response = client.post("/partial/imports", json=fixture_result().batch.model_dump(mode="json"))
    assert response.status_code == 500


def test_large_day_index_stays_verifiable_without_inventing_calendar():
    source = fixture_result(scan_day_zero="2020-01-01T00:00:00Z")
    payload = source.batch.model_dump()
    for o in payload["observations"]:
        if o["scan_day"] == 2501:
            o["scan_day"] = 2147483647
    PartialIngestionService().import_batch(PartialAdapterResult(PartialBatch.model_validate(payload), "b" * 64))
    with connect() as c:
        market_id = c.execute("SELECT id FROM partial_markets WHERE market_key='PvE'").fetchone()["id"]
    with TestClient(create_app()) as client:
        response = client.get("/partial/history", params={"market_id": market_id, "item_key": "2772", "source_id": "fixture-account", "temporal_basis": "2020-01-01T00:00:00+00:00", "start_day": 2147483647})
    assert response.status_code == 200
    assert all(row["scan_day"] == 2147483647 and row["day_start"] is None for row in response.json())
