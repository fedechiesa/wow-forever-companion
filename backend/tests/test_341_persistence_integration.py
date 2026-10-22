"""Writes synthetic inputs only, exclusively in an explicitly selected trial lab."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
import os
from threading import Barrier, local
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.core.config import settings
from app.db.trial import TrialDatabase
from app.ingestion.partial_service import PartialIngestionService
from tests.test_341_persistence import synthetic_source
from tests.test_native_exports import native_source
from tests.test_trial_database_integration import counts_and_sequences
import scripts.migrate as migrations
from scripts import import_auctionator as cli
from tests.test_auctionator_cbor import envelope, encode, realm


@pytest.fixture
def lab():
    dsn = os.environ.get("TRIAL_INTEGRATION_DATABASE_URL")
    name = os.environ.get("TRIAL_INTEGRATION_DATABASE_NAME")
    if not dsn or not name:
        pytest.fail("Explicit trial laboratory required; no fallback")
    with TrialDatabase(dsn, settings.database_url, name) as target:
        yield dsn, name, target


def unique_source(**kwargs):
    return synthetic_source(source_id="stress-fixture-" + uuid4().hex, **kwargs)


def test_341_roundtrip_and_equivalent_receptions_are_idempotent(lab):
    dsn, _, target = lab
    source = unique_source(key=b"g:123:060")
    service = PartialIngestionService(trial_target=target)
    a = service.import_batch(source)
    b = service.import_batch(source)
    other_bytes = synthetic_source(key=b"g:123:060", source_id=source.batch.source_id, prefix=b"\n")
    c = service.import_batch(other_bytes)
    assert a.status == "completed" and a.evidence_status == "created"
    assert b.status == c.status == "duplicate" and b.export_id == c.export_id == a.export_id
    assert b.observations_changed == c.observations_changed == 0
    with psycopg.connect(dsn, row_factory=psycopg.rows.dict_row) as connection:
        connection.read_only = True
        header = connection.execute("SELECT * FROM partial_exports WHERE id=%s", (a.export_id,)).fetchone()
        assert header["sealed"] and header["source_version"] == "341" and header["dataset"] == "stress_test"
        assert header["structure_manifest"] == source.native.manifest()
        p = header["structure_manifest"]["provenance"]
        assert p["capture_phase"] == "stress_test" and p["codec_producer"] == "unverified"
        assert "source_sha256" not in p
        facts = connection.execute("SELECT original_item_key,item_key,native_field,scan_day,value FROM partial_export_facts WHERE export_id=%s", (a.export_id,)).fetchall()
        assert len(facts) == 3 and {f["original_item_key"] for f in facts} == {"g:123:060"}
        assert {f["item_key"] for f in facts} == {"g:123:60"}
        assert {f["native_field"] for f in facts} == {"h", "a", "m"}
        links = connection.execute("SELECT input_format,decoder_version FROM partial_export_imports WHERE export_id=%s", (a.export_id,)).fetchall()
        assert len(links) == 3 and all(x == {"input_format": "cbor_definite", "decoder_version": "auctionator-v8-v2"} for x in links)
        assert connection.execute("SELECT count(*) AS n FROM partial_observations WHERE source_id=%s", (source.batch.source_id,)).fetchone()["n"] == 4


def test_exports_preserve_each_state_without_fabricating_new_buckets(lab):
    dsn, _, target = lab
    first = unique_source()
    second = synthetic_source(200, source_id=first.batch.source_id)
    service = PartialIngestionService(trial_target=target)
    a, b = service.import_batch(first), service.import_batch(second)
    assert a.export_id != b.export_id
    with psycopg.connect(dsn) as c:
        c.read_only = True
        assert c.execute("SELECT DISTINCT scan_day FROM partial_observations WHERE source_id=%s AND scan_day IS NOT NULL", (first.batch.source_id,)).fetchall() == [(2485,)]
        values = dict(c.execute("SELECT statistic,value FROM partial_observations WHERE source_id=%s AND scan_day=2485", (first.batch.source_id,)).fetchall())
        assert values["daily_minimum"] == 100 and values["daily_highest_minimum"] == 200


def test_stress_launch_and_simulated_datasets_have_distinct_markets(lab):
    dsn, _, target = lab
    source_id = "isolation-" + uuid4().hex
    service = PartialIngestionService(trial_target=target)
    results = [service.import_batch(synthetic_source(source_id=source_id, phase=p)) for p in ("stress_test", "launch", "simulated")]
    with psycopg.connect(dsn) as c:
        c.read_only = True
        rows = c.execute("SELECT e.dataset,f.market_id FROM partial_exports e JOIN partial_export_facts f ON e.id=f.export_id WHERE e.id=ANY(%s) GROUP BY e.dataset,f.market_id", ([r.export_id for r in results],)).fetchall()
        assert {r[0] for r in rows} == {"stress_test", "real", "simulated"}
        assert len({r[1] for r in rows}) == 3


def test_invalid_metadata_or_factory_changes_no_rows_or_sequences(lab):
    dsn, _, target = lab
    before = counts_and_sequences(dsn)
    source = unique_source()
    bad = source.native.provenance.model_copy(update={"region": "unverified-offline-only"})
    with pytest.raises(ValueError):
        PartialIngestionService(trial_target=target).import_batch(replace(source, native=source.native.model_copy(update={"provenance": bad})))
    with pytest.raises(ValueError, match="TrialDatabase"):
        PartialIngestionService(lambda: psycopg.connect(dsn)).import_batch(source)
    assert counts_and_sequences(dsn) == before


def test_failed_run_and_retry_use_only_the_revalidated_trial_factory(lab, monkeypatch):
    dsn, _, target = lab
    source = unique_source()
    real = PartialIngestionService._persist_observation
    calls = []

    def fail(self, *args):
        calls.append(True)
        raise psycopg.errors.CheckViolation("private-test-secret")

    monkeypatch.setattr(PartialIngestionService, "_persist_observation", fail)
    service = PartialIngestionService(trial_target=target)
    with pytest.raises(psycopg.errors.CheckViolation):
        service.import_batch(source)
    with psycopg.connect(dsn) as c:
        c.read_only = True
        assert c.execute("SELECT status,error_message FROM partial_import_runs WHERE source_id=%s", (source.batch.source_id,)).fetchall() == [("failed", "Trial import failed; database details withheld.")]
        assert c.execute("SELECT count(*) FROM partial_exports WHERE source_id=%s", (source.batch.source_id,)).fetchone()[0] == 0

    calls.clear()
    def retry(self, *args):
        if not calls:
            calls.append(True)
            raise psycopg.errors.DeadlockDetected("retry")
        return real(self, *args)
    monkeypatch.setattr(PartialIngestionService, "_persist_observation", retry)
    result = service.import_batch(source)
    assert result.status == "completed" and result.native_facts_seen == 3


@pytest.mark.parametrize("identical", [True, False])
def test_concurrent_341_exports_are_atomic(lab, monkeypatch, identical):
    dsn, name, _ = lab
    barrier, state = Barrier(2), local()
    real = PartialIngestionService._create_run
    first = unique_source()
    second = synthetic_source(100 if identical else 200, source_id=first.batch.source_id)
    def synchronized(self, *args):
        run = real(self, *args)
        if not getattr(state, "started", False):
            state.started = True
            barrier.wait(timeout=10)
        return run
    monkeypatch.setattr(PartialIngestionService, "_create_run", synchronized)
    def write(source):
        with TrialDatabase(dsn, settings.database_url, name) as target:
            return PartialIngestionService(trial_target=target).import_batch(source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (first, second)))
    assert sorted(r.evidence_status for r in results) == (["created", "reused"] if identical else ["created", "created"])


def test_new_native_evidence_remains_immutable(lab):
    dsn, _, target = lab
    result = PartialIngestionService(trial_target=target).import_batch(unique_source())
    for statement in ("UPDATE partial_exports SET structure_manifest='{}' WHERE id=%s",
                      "DELETE FROM partial_export_facts WHERE export_id=%s"):
        with psycopg.connect(dsn) as c:
            with pytest.raises(psycopg.errors.CheckViolation):
                with c.transaction():
                    c.execute(statement, (result.export_id,))


def test_341_cli_roundtrip_with_explicit_verified_context(lab, tmp_path, monkeypatch, capsys):
    dsn, name, _ = lab
    source = unique_source()
    capture = tmp_path / "synthetic.lua"
    capture.write_bytes(envelope(encode(realm())))
    metadata = tmp_path / "context.json"
    metadata.write_text(source.native.provenance.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_TRIAL_DSN", dsn)
    args = [str(capture), "--source-id", source.batch.source_id, "--region", source.batch.region,
            "--dataset", "stress_test", "--source-version", "341", "--serialized-codec", "cbor-definite",
            "--provenance-file", str(metadata), "--trial", "--database-url-env", "SYNTHETIC_TRIAL_DSN",
            "--expected-database", name]
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert cli.main(args) == 0
    second = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert first["status"] == "completed" and second["status"] == "duplicate"
    assert first["export_id"] == second["export_id"]


def test_cli_wrong_input_hash_stops_before_rows_or_sequences(lab, tmp_path, monkeypatch, capsys):
    dsn, name, _ = lab
    source = unique_source()
    capture = tmp_path / "synthetic.lua"
    capture.write_bytes(b"\n" + envelope(encode(realm())))
    metadata = tmp_path / "context.json"
    metadata.write_text(source.native.provenance.model_dump_json(), encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_TRIAL_DSN", dsn)
    before = counts_and_sequences(dsn)
    assert cli.main([str(capture), "--source-id", source.batch.source_id, "--region", source.batch.region,
                     "--dataset", "stress_test", "--source-version", "341", "--serialized-codec", "cbor-definite",
                     "--provenance-file", str(metadata), "--trial", "--database-url-env", "SYNTHETIC_TRIAL_DSN",
                     "--expected-database", name]) == 1
    output = capsys.readouterr()
    assert "Traceback" not in output.err and "password" not in output.err
    assert counts_and_sequences(dsn) == before


def fingerprint(c):
    rows = {}
    schema = c.execute("SELECT current_schema()").fetchone()[0]
    for (name,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s AND tablename<>'schema_migrations'", (schema,)):
        data = c.execute(sql.SQL("SELECT t::text FROM {} t ORDER BY t::text").format(sql.Identifier(schema, name))).fetchall()
        rows[name] = (len(data), sha256(json.dumps(data).encode()).hexdigest())
    sequences = {}
    for (name,) in c.execute("SELECT sequencename FROM pg_sequences WHERE schemaname=%s", (schema,)):
        sequences[name] = c.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(sql.Identifier(schema, name))).fetchone()
    return rows, sequences


def test_005_preserves_existing_340_exports_and_sequences(lab, monkeypatch):
    dsn, _, _ = lab
    schema = "migration_" + uuid4().hex
    with psycopg.connect(dsn) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated = make_conninfo(dsn, options="-c search_path=" + schema)
    files = migrations.migration_files()
    try:
        with monkeypatch.context() as old:
            old.setattr(migrations, "migration_files", lambda: files[:4])
            assert len(migrations.run_migrations(isolated)) == 4
        def connect():
            return psycopg.connect(isolated, row_factory=psycopg.rows.dict_row)
        result = PartialIngestionService(connect).import_batch(native_source())
        with psycopg.connect(isolated) as c:
            before = fingerprint(c)
        assert migrations.run_migrations(isolated) == ["005_auctionator_341_provenance.sql"]
        assert migrations.run_migrations(isolated) == []
        with psycopg.connect(isolated) as c:
            assert fingerprint(c) == before
            assert c.execute("SELECT sealed FROM partial_exports WHERE id=%s", (result.export_id,)).fetchone() == (True,)
    finally:
        with psycopg.connect(dsn) as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
