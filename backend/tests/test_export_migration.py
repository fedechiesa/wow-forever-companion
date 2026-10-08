"""Upgrade a populated 003 schema, exclusively inside the dedicated test DB."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app.core.config import settings
from app.db.connection import connect
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.adapters.file import FileAdapter
from app.ingestion.fresh_simulator import generate_fresh, simulation_lua
from app.ingestion.partial_service import PartialIngestionService
from app.ingestion.service import IngestionService, SnapshotImportInput
from app.main import create_app
import scripts.migrate as migrations


def fingerprint(c):
    tables = ("realms","items","auction_snapshots","auction_snapshot_items","import_runs",
              "partial_markets","partial_items","partial_observations","partial_import_runs")
    result = {}
    for table in tables:
        rows = c.execute(sql.SQL("SELECT t::text FROM {} t ORDER BY id").format(sql.Identifier(table))).fetchall()
        result[table] = (len(rows),hashlib.sha256(json.dumps(rows).encode()).hexdigest())
    result["sequences"] = {}
    schema = c.execute("SELECT current_schema() AS name").fetchone()["name"]
    for row in c.execute("SELECT sequencename FROM pg_sequences WHERE schemaname=%s",(schema,)).fetchall():
        name = row["sequencename"]
        result["sequences"][name] = c.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(sql.Identifier(name))).fetchone()
    return result


def test_004_preserves_16628_legacy_rows_phase2_and_no_fictitious_backfill(test_database_url,monkeypatch):
    schema = "test_"+uuid4().hex
    with psycopg.connect(test_database_url) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated_url = make_conninfo(test_database_url,options=f"-c search_path={schema} -c statement_timeout=15000")
    monkeypatch.setattr(settings,"database_url",isolated_url)
    all_files = migrations.migration_files()
    try:
        with monkeypatch.context() as old:
            old.setattr(migrations,"migration_files",lambda: all_files[:3])
            assert len(migrations.run_migrations()) == 3
        samples = Path(__file__).resolve().parents[2]/"data/samples"
        for path in sorted(samples.glob("*.json")):
            source = FileAdapter().load(path)
            IngestionService().import_snapshot(SnapshotImportInput(
                snapshot=source.snapshot,source_hash=source.source_hash,raw_reference=source.raw_reference))
        db,_ = generate_fresh()
        source = AuctionatorAdapter().load_bytes(simulation_lua(db),source_id="fresh-seed-340",
                                                 region="simulation",dataset="simulated")
        legacy = replace(source,native=None)
        service = PartialIngestionService()
        service.import_batch(legacy)
        service.import_batch(legacy)
        with connect() as c:
            before = fingerprint(c)
            assert before["partial_observations"][0] == 16628
            assert before["auction_snapshots"][0] == 7 and before["auction_snapshot_items"][0] == 69
        assert migrations.run_migrations() == ["004_create_partial_export_evidence.sql"]
        assert migrations.run_migrations() == []
        with connect() as c:
            after = fingerprint(c)
            # The two NEW sequences are expected; existing sequences are unchanged.
            for name,values in before["sequences"].items():
                assert after["sequences"][name] == values
            after["sequences"] = before["sequences"]
            assert after == before
            for table in ("partial_exports","partial_export_facts","partial_export_imports"):
                assert c.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        with TestClient(create_app()) as client:
            assert len(client.get("/snapshots").json()) == 7
            assert all(r["evidence_status"] == "unavailable" for r in client.get("/partial/imports").json())
        # Future explicit reimport saves the file available NOW, without rewriting
        # the 16,628 accumulated rows or inventing links to the two old imports.
        result = service.import_batch(source)
        assert result.status == "completed" and result.observations_changed == 0
        assert result.evidence_status == "created"
        with connect() as c:
            assert fingerprint(c)["partial_observations"] == before["partial_observations"]
            assert c.execute("SELECT import_id FROM partial_export_imports").fetchall() == [{"import_id":result.import_id}]
            assert c.execute("SELECT count(*) AS n FROM partial_export_facts").fetchone()["n"] == len(source.native.facts)
            print("003 -> 004: existing rows/hash preserved; native facts on later TEST reimport:",len(source.native.facts))
    finally:
        with psycopg.connect(test_database_url) as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
