from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier, local

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.ingestion.adapters.file import FileAdapter
from app.ingestion.service import IngestionService, SnapshotImportInput
from app.main import create_app
from scripts.migrate import run_migrations


def snapshot_payload(day: int, item_name: str = "Test Lotus") -> dict:
    return {
        "realm": "Integration Realm",
        "region": "test",
        "source_type": "simulated-test",
        "source_version": "0.1",
        "captured_at": f"2026-10-{day:02d}T00:00:00Z",
        "items": [
            {
                "external_item_id": "test-lotus",
                "name": item_name,
                "quality": "uncommon",
                "min_buyout": 600000 + day * 10000,
                "avg_buyout": 620000 + day * 10000,
                "max_buyout": 660000 + day * 10000,
                "quantity_total": 20 + day,
                "auction_count": 5 + day,
            },
            {
                "external_item_id": "test-ore",
                "name": "Test Ore",
                "quality": "common",
                "min_buyout": 100,
                "avg_buyout": 150,
                "max_buyout": 200,
                "quantity_total": 1000,
                "auction_count": 80,
            },
        ],
    }


def import_payload(payload: dict, raw_reference: str) -> int:
    adapter_result = FileAdapter().load_payload(payload, raw_reference=raw_reference)
    result = IngestionService().import_snapshot(
        SnapshotImportInput(
            snapshot=adapter_result.snapshot,
            source_hash=adapter_result.source_hash,
            raw_reference=adapter_result.raw_reference,
        )
    )
    assert result.snapshot_id is not None
    return result.snapshot_id


@pytest.fixture(autouse=True)
def migrated_clean_database(isolated_database) -> None:
    pass


def test_importing_snapshot_persists_realm_snapshot_items_and_rows() -> None:
    snapshot_id = import_payload(snapshot_payload(1), "test:snapshot-1")

    with connect() as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM realms WHERE name = 'Integration Realm') AS realms,
                (SELECT COUNT(*) FROM auction_snapshots WHERE id = %s) AS snapshots,
                (SELECT COUNT(*) FROM items WHERE external_item_id LIKE 'test-%%') AS items,
                (SELECT COUNT(*) FROM auction_snapshot_items WHERE snapshot_id = %s) AS snapshot_items
            """,
            (snapshot_id, snapshot_id),
        ).fetchone()

    assert counts["realms"] == 1
    assert counts["snapshots"] == 1
    assert counts["items"] == 2
    assert counts["snapshot_items"] == 2


def test_importing_multiple_snapshots_generates_history() -> None:
    import_payload(snapshot_payload(1), "test:snapshot-1")
    import_payload(snapshot_payload(2), "test:snapshot-2")

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT s.captured_at, si.avg_buyout
            FROM auction_snapshot_items si
            JOIN auction_snapshots s ON s.id = si.snapshot_id
            JOIN items i ON i.id = si.item_id
            WHERE i.external_item_id = 'test-lotus'
            ORDER BY s.captured_at
            """
        ).fetchall()

    assert [row["avg_buyout"] for row in rows] == [630000, 640000]


def test_importing_same_snapshot_twice_does_not_duplicate_market_rows() -> None:
    payload = snapshot_payload(1)
    first_id = import_payload(payload, "test:snapshot-1")

    adapter_result = FileAdapter().load_payload(payload, raw_reference="test:snapshot-1-again")
    result = IngestionService().import_snapshot(
        SnapshotImportInput(
            snapshot=adapter_result.snapshot,
            source_hash=adapter_result.source_hash,
            raw_reference=adapter_result.raw_reference,
        )
    )

    with connect() as connection:
        snapshot_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM auction_snapshots
            WHERE realm_id IN (
                SELECT id FROM realms WHERE name = 'Integration Realm'
            )
            """
        ).fetchone()["count"]
        duplicate_runs = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM import_runs
            WHERE status = 'duplicate'
              AND raw_reference LIKE 'test:%'
            """
        ).fetchone()["count"]

    assert result.status == "duplicate"
    assert result.snapshot_id == first_id
    assert snapshot_count == 1
    assert duplicate_runs == 1


def test_item_name_change_keeps_identity_and_updates_catalog() -> None:
    import_payload(snapshot_payload(1), "test:snapshot-1")
    with connect() as connection:
        original_id = connection.execute("SELECT id FROM items WHERE external_item_id='test-lotus'").fetchone()["id"]
    changed = deepcopy(snapshot_payload(2, item_name="Renamed Test Lotus"))
    changed["items"][0]["quality"] = "rare"
    import_payload(changed, "test:snapshot-2-renamed")

    with connect() as connection:
        item = connection.execute(
            """
            SELECT id, name, quality
            FROM items
            WHERE external_item_id = 'test-lotus'
            """
        ).fetchone()
        history_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM auction_snapshot_items
            WHERE item_id = %s
            """,
            (item["id"],),
        ).fetchone()["count"]

    assert item["name"] == "Renamed Test Lotus"
    assert item["id"] == original_id
    assert item["quality"] == "rare"
    assert history_count == 2


def test_get_items_allows_search() -> None:
    import_payload(snapshot_payload(1), "test:snapshot-1")
    client = TestClient(create_app())

    response = client.get("/items", params={"search": "Test Lotus"})

    assert response.status_code == 200
    assert response.json()[0]["external_item_id"] == "test-lotus"


def test_get_item_history_returns_points_ordered_by_captured_at() -> None:
    import_payload(snapshot_payload(2), "test:snapshot-2")
    import_payload(snapshot_payload(1), "test:snapshot-1")

    with connect() as connection:
        item_id = connection.execute(
            "SELECT id FROM items WHERE external_item_id = 'test-lotus'"
        ).fetchone()["id"]

    client = TestClient(create_app())
    response = client.get(f"/items/{item_id}/history")

    assert response.status_code == 200
    payload = response.json()
    assert [point["avg_buyout"] for point in payload] == [630000, 640000]
    assert [point["captured_at"] for point in payload] == sorted(
        point["captured_at"] for point in payload
    )


@pytest.mark.parametrize("existing_realm", [False, True])
def test_concurrent_http_imports_complete_and_duplicate(existing_realm, monkeypatch) -> None:
    barrier = Barrier(2)
    thread_state = local()
    if existing_realm:
        with connect() as connection:
            connection.execute("INSERT INTO realms(name, region) VALUES (%s, %s)", ("Integration Realm", "test"))
        original = IngestionService._find_duplicate_snapshot

        def synchronized_lookup(self, *args, **kwargs):
            result = original(self, *args, **kwargs)
            if not getattr(thread_state, "checked", False):
                thread_state.checked = True
                assert result is None
                barrier.wait(timeout=10)
            return result

        monkeypatch.setattr(IngestionService, "_find_duplicate_snapshot", synchronized_lookup)
    else:
        original = IngestionService._get_or_create_realm

        def synchronized_realm(self, *args, **kwargs):
            barrier.wait(timeout=10)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(IngestionService, "_get_or_create_realm", synchronized_realm)

    with TestClient(create_app()) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: client.post("/imports/snapshots", json=snapshot_payload(1)), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    results = [response.json() for response in responses]
    assert sorted(result["status"] for result in results) == ["completed", "duplicate"]
    assert results[0]["snapshot_id"] == results[1]["snapshot_id"]
    assert sorted(result["items_imported"] for result in results) == [0, 2]
    with connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM realms").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM auction_snapshots").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM auction_snapshot_items").fetchone()["n"] == 2
        runs = connection.execute("SELECT status FROM import_runs ORDER BY status").fetchall()
    assert [row["status"] for row in runs] == ["completed", "duplicate"]
    print(f"concurrent existing_realm={existing_realm}: {[(r.status_code, r.json()) for r in responses]}")


def test_market_identity_disambiguates_same_name_and_different_regions() -> None:
    first = snapshot_payload(1)
    second = deepcopy(first)
    second["region"] = "other-region"
    second["items"][0]["avg_buyout"] = 650000
    import_payload(first, "test:region-a")
    import_payload(second, "test:region-b")
    with connect() as connection:
        realms = connection.execute("SELECT id, region FROM realms ORDER BY id").fetchall()
        item_id = connection.execute("SELECT id FROM items WHERE external_item_id='test-lotus'").fetchone()["id"]
    with TestClient(create_app()) as client:
        assert client.get(f"/items/{item_id}/history").status_code == 422
        assert client.get(f"/items/{item_id}/history", params={"realm": first["realm"]}).status_code == 422
        assert client.get("/snapshots", params={"realm": first["realm"]}).status_code == 422
        for realm, expected_price in zip(realms, [630000, 650000]):
            by_id = client.get(f"/items/{item_id}/history", params={"realm_id": realm["id"]})
            by_name = client.get(f"/items/{item_id}/history", params={"realm": first["realm"], "region": realm["region"]})
            assert by_id.status_code == by_name.status_code == 200
            assert by_id.json() == by_name.json()
            assert len(by_id.json()) == 1
            point = by_id.json()[0]
            assert (point["realm_id"], point["region"], point["avg_buyout"]) == (realm["id"], realm["region"], expected_price)
            snapshots = client.get("/snapshots", params={"realm_id": realm["id"]})
            assert snapshots.status_code == 200
            assert len(snapshots.json()) == 1
            assert snapshots.json()[0]["region"] == realm["region"]
            print(f"market identity: {point}")
        assert len(client.get("/snapshots").json()) == 2
        assert client.get("/snapshots", params={"realm_id": realms[0]["id"], "region": "other-region"}).status_code == 404


@pytest.mark.parametrize("region", [None, "", " ", "\t\n"])
def test_empty_regions_share_null_identity(region) -> None:
    payload = snapshot_payload(1)
    payload["region"] = region
    snapshot_id = import_payload(payload, "test:null-region")
    payload["region"] = None
    assert import_payload(payload, "test:null-again") == snapshot_id
    with connect() as connection:
        realms = connection.execute("SELECT region FROM realms").fetchall()
    assert realms == [{"region": None}]
    with TestClient(create_app()) as client:
        response = client.get("/snapshots", params={"realm": payload["realm"], "region": " "})
    assert response.status_code == 200
    assert response.json()[0]["region"] is None


@pytest.mark.parametrize("region", ["", " ", "\t\n", " padded "])
def test_database_rejects_non_normalized_region(region) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as connection:
            connection.execute("INSERT INTO realms(name, region) VALUES (%s, %s)", ("Invalid Realm", region))


def test_intermediate_failure_rolls_back_market_and_records_failed_run(monkeypatch) -> None:
    original = IngestionService._insert_snapshot_item
    inserted = 0

    def fail_second_item(self, connection, **kwargs):
        nonlocal inserted
        inserted += 1
        if inserted == 2:
            connection.execute("SELECT 1 / 0")
        original(self, connection, **kwargs)

    monkeypatch.setattr(IngestionService, "_insert_snapshot_item", fail_second_item)
    with TestClient(create_app()) as client:
        response = client.post("/imports/snapshots", json=snapshot_payload(1))
    assert response.status_code == 500
    assert inserted == 2
    with connect() as connection:
        for table in ["realms", "items", "auction_snapshots", "auction_snapshot_items"]:
            assert connection.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        runs = connection.execute("SELECT status, snapshot_id, items_seen, items_imported FROM import_runs").fetchall()
    assert runs == [{"status": "failed", "snapshot_id": None, "items_seen": 2, "items_imported": 0}]


def test_offset_timestamp_is_stored_as_utc_and_matches_same_instant() -> None:
    payload = snapshot_payload(1)
    payload["captured_at"] = "2026-09-30T21:00:00-03:00"
    payload["imported_at"] = "2026-10-01T04:00:00+02:00"
    first_id = import_payload(payload, "test:offset")
    payload["captured_at"] = "2026-10-01T00:00:00Z"
    assert import_payload(payload, "test:utc") == first_id
    with connect() as connection:
        row = connection.execute("SELECT captured_at, imported_at FROM auction_snapshots WHERE id=%s", (first_id,)).fetchone()
    assert row["captured_at"].isoformat() == "2026-10-01T00:00:00+00:00"
    assert row["imported_at"].isoformat() == "2026-10-01T02:00:00+00:00"


def test_incremental_migration_normalizes_legacy_empty_and_padded_regions() -> None:
    with connect() as connection:
        connection.execute("ALTER TABLE realms DROP CONSTRAINT chk_realms_normalized_region")
        connection.execute("DELETE FROM schema_migrations WHERE id='002_normalize_realm_regions.sql'")
        connection.execute("INSERT INTO realms(name, region) VALUES ('Legacy Empty', ''), ('Legacy Padded', ' test ')")
    assert run_migrations() == ["002_normalize_realm_regions.sql"]
    with connect() as connection:
        rows = connection.execute("SELECT name,region FROM realms ORDER BY name").fetchall()
    assert rows == [{"name": "Legacy Empty", "region": None}, {"name": "Legacy Padded", "region": "test"}]
    payload = snapshot_payload(1)
    payload.update(realm="Legacy Empty", region=" \t ")
    import_payload(payload, "test:legacy")
    with connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM realms WHERE name='Legacy Empty'").fetchone()["n"] == 1


def test_file_then_http_import_is_duplicate_even_with_different_hashes() -> None:
    path = Path(__file__).parent / "fixtures" / "snapshot_valid.json"
    adapter_result = FileAdapter().load(path)
    first = IngestionService().import_snapshot(SnapshotImportInput(
        adapter_result.snapshot, adapter_result.source_hash, adapter_result.raw_reference,
    ))
    payload = json.loads(path.read_text())
    assert FileAdapter().load_payload(payload).source_hash != adapter_result.source_hash
    with TestClient(create_app()) as client:
        response = client.post("/imports/snapshots", json=payload)
    assert first.status == "completed"
    assert response.status_code == 200
    assert response.json()["status"] == "duplicate"
    assert response.json()["snapshot_id"] == first.snapshot_id
    with connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM auction_snapshots").fetchone()["n"] == 1


@pytest.mark.parametrize("value", [0, 2147483647])
def test_http_integer_bounds_persist_exactly(value) -> None:
    payload = snapshot_payload(1)
    fields = ["min_buyout", "avg_buyout", "max_buyout", "quantity_total", "auction_count"]
    for item in payload["items"]:
        item.update({field: value for field in fields})
    with TestClient(create_app()) as client:
        response = client.post("/imports/snapshots", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    with connect() as connection:
        rows = connection.execute("SELECT min_buyout,avg_buyout,max_buyout,quantity_total,auction_count FROM auction_snapshot_items").fetchall()
    assert rows == [{field: value for field in fields}] * 2
