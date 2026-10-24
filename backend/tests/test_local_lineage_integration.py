"""Synthetic persistence and migration checks inside the explicitly selected lab."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.partial_service import PartialIngestionService
from app.db.trial import TrialDatabase
from app.core.config import settings
from test_341_persistence_integration import lab
from test_local_lineage import local_source
from test_local_capture import lua
from test_trial_database_integration import counts_and_sequences


@pytest.fixture
def scenario():
    defaults = dict(economy="fixture-economy-" + uuid4().hex, source_id="fixture-observer-" + uuid4().hex)
    return lambda **updates: local_source(**(defaults | updates))


def markets(c, exports):
    return c.execute("SELECT DISTINCT market_id FROM partial_export_facts WHERE export_id=ANY(%s)", (exports,)).fetchall()


def test_two_observers_one_economy_one_state_and_independent_receipts(lab, scenario):
    dsn, _, target = lab
    a, b = scenario(), scenario(source_id="observer-b-" + uuid4().hex)
    service = PartialIngestionService(trial_target=target)
    x, y = service.import_batch(a), service.import_batch(b)
    assert x.export_id == y.export_id and y.status == "duplicate"
    assert x.observations_changed == y.observations_changed == 0
    with psycopg.connect(dsn) as c:
        assert len(markets(c, [x.export_id,y.export_id])) == 1
        assert c.execute("SELECT count(*) FROM partial_export_facts WHERE export_id=%s", (x.export_id,)).fetchone() == (3,)
        assert c.execute("SELECT count(*) FROM partial_capture_receipts WHERE export_id=%s", (x.export_id,)).fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM partial_observations WHERE market_id=%s", markets(c,[x.export_id])[0]).fetchone() == (0,)
        refs = c.execute("SELECT capture_context->'provenance'->>'source_id' FROM partial_capture_receipts WHERE export_id=%s", (x.export_id,)).fetchall()
        assert {row[0] for row in refs} == {a.batch.source_id,b.batch.source_id}


@pytest.mark.parametrize("dimension", ["economy", "dataset", "faction"])
def test_same_native_label_never_merges_distinct_economic_partitions(lab, scenario, dimension):
    _, _, target = lab
    options = {"economy": [{}, {"economy": "other-economy-" + uuid4().hex}],
               "dataset": [{"dataset": "stress_test"}, {"dataset": "launch"}],
               "faction": [{}, {"scope": "faction", "faction": "Synthetic Alliance"},
                           {"scope": "faction", "faction": "Synthetic Horde"}]}[dimension]
    service = PartialIngestionService(trial_target=target)
    results = [service.import_batch(scenario(**option)) for option in options]
    assert len({r.export_id for r in results}) == len(options)
    with psycopg.connect(lab[0]) as c:
        assert len(markets(c, [r.export_id for r in results])) == len(options)


def test_equivalent_original_hashes_and_repeat_import_preserve_lineage(lab, scenario):
    _, _, target = lab
    a = scenario()
    b = scenario(raw=lua() + b"\nCONFIG={synthetic=1}")
    service = PartialIngestionService(trial_target=target)
    results = [service.import_batch(source) for source in (a,b,b)]
    assert len({r.export_id for r in results}) == 1
    assert [r.status for r in results] == ["completed", "duplicate", "duplicate"]
    with psycopg.connect(lab[0]) as c:
        receipts = c.execute("""SELECT source_sha256,market_sha256,acquired_at,archive_metadata
            FROM partial_capture_receipts WHERE export_id=%s ORDER BY import_id""", (results[0].export_id,)).fetchall()
        assert [r[0] for r in receipts] == [a.source_hash,b.source_hash,b.source_hash]
        assert len({r[1] for r in receipts}) == 1
        assert all(r[2] == a.local_capture.metadata.captured_at for r in receipts)
        assert receipts[0][3] == a.local_capture.metadata.model_dump(mode="json")
        assert c.execute("SELECT canonical_version FROM partial_exports WHERE id=%s", (results[0].export_id,)).fetchone() == (2,)


def test_different_states_in_same_bucket_are_preserved_without_new_temporal_samples(lab, scenario):
    service = PartialIngestionService(trial_target=lab[2])
    a, b = service.import_batch(scenario()), service.import_batch(scenario(raw=lua(high=200, minimum=200)))
    assert a.export_id != b.export_id
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT DISTINCT scan_day FROM partial_export_facts WHERE export_id=ANY(%s) AND scan_day IS NOT NULL", ([a.export_id,b.export_id],)).fetchall() == [(2485,)]
        assert c.execute("SELECT count(*) FROM partial_observations WHERE market_id=%s", markets(c,[a.export_id])[0]).fetchone() == (0,)


def test_conflicting_ruleset_rolls_back_market_evidence(lab, scenario):
    service = PartialIngestionService(trial_target=lab[2])
    original = service.import_batch(scenario())
    with pytest.raises(psycopg.IntegrityError, match="ruleset"):
        service.import_batch(scenario(raw=lua(market="PvE")))
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT count(*) FROM partial_export_facts WHERE export_id=%s", (original.export_id,)).fetchone() == (3,)
        assert c.execute("SELECT count(*) FROM partial_capture_receipts WHERE export_id=%s", (original.export_id,)).fetchone() == (1,)


def test_invalid_metadata_and_extreme_prices_change_no_rows_or_sequences(lab, scenario):
    before = counts_and_sequences(lab[0])
    source = scenario()
    bad = replace(source, local_capture=source.local_capture.model_copy(update={
        "metadata": source.local_capture.metadata.model_copy(update={"market_sha256": "a"*64})}))
    with pytest.raises(ValueError):
        PartialIngestionService(trial_target=lab[2]).import_batch(bad)
    with pytest.raises(ValueError, match="price_exceeds_persistence_int32"):
        scenario(raw=lua(high=2**63-1, minimum=2**63-1))
    assert counts_and_sequences(lab[0]) == before


def test_failure_after_receipt_rolls_back_evidence_then_retry_is_idempotent(lab, scenario, monkeypatch):
    source = scenario()
    service = PartialIngestionService(trial_target=lab[2])
    execute = psycopg.Connection.execute

    def fail_link(connection, query, params=None, **kwargs):
        if isinstance(query, str) and "INSERT INTO partial_export_imports" in query:
            raise psycopg.errors.CheckViolation("synthetic failure after receipt")
        return execute(connection, query, params, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection, "execute", fail_link)
        with pytest.raises(psycopg.errors.CheckViolation):
            service.import_batch(source)
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT status FROM partial_import_runs WHERE source_id=%s", (source.batch.source_id,)).fetchall() == [("failed",)]
        assert c.execute("SELECT count(*) FROM partial_exports WHERE source_id=%s", (source.batch.source_id,)).fetchone() == (0,)
        assert c.execute("""SELECT count(*) FROM partial_capture_receipts r
            JOIN partial_import_runs i ON i.id=r.import_id WHERE i.source_id=%s""", (source.batch.source_id,)).fetchone() == (0,)
    first, repeated = service.import_batch(source), service.import_batch(source)
    assert first.status == "completed" and repeated.status == "duplicate"
    assert first.export_id == repeated.export_id
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT count(*) FROM partial_export_facts WHERE export_id=%s", (first.export_id,)).fetchone() == (3,)
        assert c.execute("SELECT count(*) FROM partial_capture_receipts WHERE export_id=%s", (first.export_id,)).fetchone() == (2,)


@pytest.mark.parametrize("action", ["UPDATE partial_capture_receipts SET acquired_at=now() WHERE import_id=%s",
                                  "DELETE FROM partial_capture_receipts WHERE import_id=%s",
                                  "TRUNCATE partial_capture_receipts"])
def test_receipts_are_immutable_in_sql(lab, scenario, action):
    result = PartialIngestionService(trial_target=lab[2]).import_batch(scenario())
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(lab[0]) as c:
            c.execute(action, (result.import_id,) if "%s" in action else None)


@pytest.mark.parametrize("assignment", [
    "source_id='contradictory-observer'", "source_hash=repeat('a',64)",
    "region='contradictory-region'", "temporal_basis='contradictory-clock'",
    "raw_reference='contradictory-original'", "imported_at=imported_at+interval '1 second'",
    "observations_seen=observations_seen+1", "observations_changed=1", "status='failed'",
], ids=["source", "hash", "region", "clock", "reference", "received_at", "seen", "changed", "failed"])
def test_linked_run_cannot_reassign_capture_lineage(lab, scenario, assignment):
    result = PartialIngestionService(trial_target=lab[2]).import_batch(scenario())
    with psycopg.connect(lab[0]) as c:
        # Also roll back on the vulnerable implementation, so a red regression
        # cannot leave this synthetic receipt pointing at contradictory data.
        with c.transaction(force_rollback=True):
            with pytest.raises(psycopg.errors.CheckViolation, match="local capture run lineage"):
                with c.transaction():
                    c.execute("UPDATE partial_import_runs SET " + assignment + " WHERE id=%s", (result.import_id,))


def test_identified_market_cannot_be_edited_or_legacy_upgraded_by_assignment(lab, scenario):
    result = PartialIngestionService(trial_target=lab[2]).import_batch(scenario())
    with psycopg.connect(lab[0]) as c:
        market = markets(c,[result.export_id])[0][0]
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(lab[0]) as c:
            c.execute("UPDATE partial_markets SET ruleset='PvE' WHERE id=%s", (market,))


def test_shared_state_receives_concurrent_observers_without_duplicate_facts(lab, scenario):
    a, b = scenario(), scenario(source_id="parallel-"+uuid4().hex)
    barrier = Barrier(2)
    def write(source):
        with TrialDatabase(lab[0],settings.database_url,lab[1]) as target:
            barrier.wait(timeout=10)
            return PartialIngestionService(trial_target=target).import_batch(source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [a,b]))
    assert results[0].export_id == results[1].export_id
    assert sorted(r.evidence_status for r in results) == ["created", "reused"]
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT count(*) FROM partial_export_facts WHERE export_id=%s", (results[0].export_id,)).fetchone() == (3,)
        assert c.execute("SELECT count(*) FROM partial_capture_receipts WHERE export_id=%s", (results[0].export_id,)).fetchone() == (2,)


@pytest.mark.parametrize("input_format", ["lua_tables", "cbor_definite"])
def test_sql_link_cannot_bypass_validated_receipt_or_its_transport(lab, scenario, input_format):
    result = PartialIngestionService(trial_target=lab[2]).import_batch(scenario())
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(lab[0]) as c:
            # A separately audited receipt is mandatory even when run context
            # exactly matches the first observer, including its source_id.
            new = c.execute("""INSERT INTO partial_import_runs
                (source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                 source_hash,status,observations_seen,observations_changed)
                SELECT source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                       source_hash,'duplicate',observations_seen,0 FROM partial_import_runs WHERE id=%s
                RETURNING id""", (result.import_id,)).fetchone()[0]
            if input_format == "cbor_definite":
                # A receipt copied intact is still insufficient for a link that
                # contradicts the observed transport (the fixture is Lua).
                c.execute("""INSERT INTO partial_capture_receipts
                    SELECT %s,export_id,source_sha256,market_sha256,acquired_at,archive_metadata,capture_context
                    FROM partial_capture_receipts WHERE import_id=%s""", (new,result.import_id))
            c.execute("INSERT INTO partial_export_imports VALUES (%s,%s,%s,'auctionator-v8-v2')",
                      (new,result.export_id,input_format))


def schema_fingerprint(c):
    rows, sequences = {}, {}
    for (name,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename NOT IN ('schema_migrations','partial_capture_receipts')"):
        data = c.execute(sql.SQL("SELECT to_jsonb(t)-'economic_identity' FROM {} t ORDER BY 1").format(sql.Identifier(name))).fetchall()
        rows[name] = sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()
    for (name,) in c.execute("SELECT sequencename FROM pg_sequences WHERE schemaname=current_schema()"):
        sequences[name] = c.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(sql.Identifier(name))).fetchone()
    return rows, sequences


def test_006_preserves_populated_legacy_schema_and_sealed_evidence(lab):
    dsn = lab[0]
    schema = "lineage_migration_" + uuid4().hex
    files = sorted((Path(__file__).parents[1]/"migrations").glob("*.sql"))
    with psycopg.connect(dsn) as c:
        c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated = make_conninfo(dsn, options="-c search_path=" + schema)
    try:
        with psycopg.connect(isolated) as c:
            for path in files[:5]:
                c.execute(path.read_text(encoding="utf-8"))
        service = PartialIngestionService(lambda: psycopg.connect(isolated, row_factory=psycopg.rows.dict_row))
        source = AuctionatorAdapter().load_bytes(lua(), source_id="legacy-fixture", region="synthetic-eu")
        first = service.import_batch(source)
        with psycopg.connect(isolated) as c:
            before = schema_fingerprint(c)
            c.execute(files[5].read_text(encoding="utf-8"))
            assert schema_fingerprint(c) == before
            assert c.execute("SELECT economic_identity FROM partial_markets").fetchall() == [(None,)]
            assert c.execute("SELECT count(*) FROM partial_capture_receipts").fetchone() == (0,)
        repeated = service.import_batch(source)
        assert repeated.status == "duplicate" and repeated.export_id == first.export_id
        with pytest.raises(psycopg.errors.CheckViolation):
            with psycopg.connect(isolated) as c:
                c.execute("UPDATE partial_markets SET economic_identity=jsonb_build_object('version',1)")
    finally:
        with psycopg.connect(dsn) as c:
            c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
