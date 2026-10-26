"""End-to-end synthetic manual CLI and native v2 readers in a selected trial lab."""
import json
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

from app.core.config import settings
from app.db.trial import TrialDatabase
from app.ingestion.local_readers import LocalEvidenceReader
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.partial_service import PartialIngestionService
from app.local_capture.preflight import preflight_archive
from scripts import ingest_local_capture as cli
from scripts import read_local_evidence as read_cli
from test_341_persistence_integration import lab
from test_local_capture import lua
from test_manual_local_capture import archived_case, cli_args
from test_trial_database_integration import counts_and_sequences


@pytest.fixture
def reader(lab):
    return LocalEvidenceReader(lambda: psycopg.connect(lab[0], row_factory=dict_row))


@pytest.fixture
def case(tmp_path):
    raw = lua() + ('\nSYNTHETIC_TEST="' + uuid4().hex + '"').encode()
    return archived_case(tmp_path, raw, economy="synthetic-cli-" + uuid4().hex)


def ingest(case, lab, monkeypatch, capsys):
    monkeypatch.setenv("MANUAL_FIXTURE_DSN", lab[0])
    assert cli.main(cli_args(case, "ingest") + ["--database-url-env", "MANUAL_FIXTURE_DSN",
                                              "--expected-database", lab[1]]) == 0
    return json.loads(capsys.readouterr().out)


def market_for(reader, result, key="PvP"):
    identity = reader.state(result["export_id"])["structure_manifest"]["market_identities"][key]
    # Query the complete identity rather than relying on a label or list default.
    with reader._snapshot() as c:
        from psycopg.types.json import Jsonb
        return c.execute("SELECT id FROM public.partial_markets WHERE economic_identity=%s", (Jsonb(identity),)).fetchone()["id"]


def test_manual_cli_and_readers_roundtrip_preserve_exact_archive_and_receipts(case, lab, reader, monkeypatch, capsys):
    before = counts_and_sequences(lab[0])
    assert cli.main(cli_args(case)) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "preflight_passed"
    assert counts_and_sequences(lab[0]) == before
    a = ingest(case, lab, monkeypatch, capsys)
    b = ingest(case, lab, monkeypatch, capsys)
    assert a["status"] == "completed" and b["status"] == "duplicate" and a["export_id"] == b["export_id"]
    assert a["observations_changed"] == b["observations_changed"] == 0
    market = market_for(reader, a)
    states = reader.states(market)
    assert len(states) == 1 and states[0]["receipt_count"] == 2
    facts = reader.facts(a["export_id"], market)
    assert len(facts) == 3 and {f["native_field"] for f in facts} == {"h", "a", "m"}
    assert {f["scan_day"] for f in facts} == {2485, None}
    receipts = reader.receipts(a["export_id"])
    assert len(receipts) == 2 and {r["source_sha256"] for r in receipts} == {case[1]}
    metadata = json.loads((case[0] / "captures" / case[1] / "metadata.json").read_text())
    assert all(r["archive_metadata"] == metadata and r["acquired_at"].isoformat().replace("+00:00", "Z") == metadata["captured_at"] for r in receipts)
    assert all(r["archive_metadata"]["native_scan_timestamp"] is None for r in receipts)
    assert len({r["received_at"] for r in receipts}) == 2
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT count(*) FROM partial_observations WHERE market_id=%s", (market,)).fetchone() == (0,)


def test_two_observers_equivalent_files_do_not_multiply_native_facts(tmp_path, lab, reader, monkeypatch, capsys):
    economy = "fixture-economy-" + uuid4().hex
    a = archived_case(tmp_path, economy=economy, source_id="synthetic-observer-a")
    b = archived_case(tmp_path, lua() + b"\nCONFIG={synthetic=1}", economy=economy, source_id="synthetic-observer-b")
    first = ingest(a, lab, monkeypatch, capsys)
    second = ingest(b, lab, monkeypatch, capsys)
    assert first["export_id"] == second["export_id"] and a[1] != b[1]
    market = market_for(reader, first)
    assert len(reader.facts(first["export_id"], market)) == 3
    assert {r["observer_source_id"] for r in reader.receipts(first["export_id"])} == {"synthetic-observer-a", "synthetic-observer-b"}
    assert len(reader.states(market)) == 1


def test_states_same_bucket_are_selected_independently_and_not_a_time_series(tmp_path, lab, reader, monkeypatch, capsys):
    economy = "fixture-economy-" + uuid4().hex
    a = archived_case(tmp_path, economy=economy)
    b = archived_case(tmp_path, lua(high=200, minimum=200), economy=economy)
    x, y = ingest(a, lab, monkeypatch, capsys), ingest(b, lab, monkeypatch, capsys)
    market = market_for(reader, x)
    assert len(reader.states(market)) == 2
    assert x["export_id"] != y["export_id"]
    all_facts = [*reader.facts(x["export_id"], market), *reader.facts(y["export_id"], market)]
    assert {f["scan_day"] for f in all_facts if f["scan_day"] is not None} == {2485}
    assert {f["value"] for f in all_facts if f["native_field"] == "h"} == {100, 200}
    assert all(s["temporal_basis"] == "unknown" for s in reader.states(market))


def test_empty_market_is_discoverable_without_fact_join(tmp_path, lab, reader, monkeypatch, capsys):
    # The existing decoder requires at least one fact in a capture. An empty
    # market alongside a populated one is supported and must be discoverable.
    raw = lua()[:-1] + b',["PvE"]={version=2}}'
    result = ingest(archived_case(tmp_path, raw, economy="empty-" + uuid4().hex), lab, monkeypatch, capsys)
    market = market_for(reader, result, "PvE")
    assert reader.states(market)[0]["id"] == result["export_id"]
    assert reader.facts(result["export_id"], market) == []
    assert reader.state(result["export_id"])["native_fact_count"] == 3


def test_failed_cli_attempt_rolls_back_then_retry_reuses_state(case, lab, reader, monkeypatch, capsys):
    execute = psycopg.Connection.execute
    def fail(connection, query, params=None, **kwargs):
        if isinstance(query, str) and "INSERT INTO partial_export_imports" in query:
            raise psycopg.errors.CheckViolation("private-driver-sentinel")
        return execute(connection, query, params, **kwargs)
    monkeypatch.setenv("MANUAL_FIXTURE_DSN", lab[0])
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection, "execute", fail)
        assert cli.main(cli_args(case, "ingest") + ["--database-url-env", "MANUAL_FIXTURE_DSN", "--expected-database", lab[1]]) == 1
    assert "private-driver-sentinel" not in capsys.readouterr().err
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT count(*) FROM partial_capture_receipts WHERE source_sha256=%s", (case[1],)).fetchone() == (0,)
        assert c.execute("SELECT status,error_message FROM partial_import_runs WHERE source_hash=%s", (case[1],)).fetchone() == ("failed", "Trial import failed; database details withheld.")
    a, b = ingest(case, lab, monkeypatch, capsys), ingest(case, lab, monkeypatch, capsys)
    assert a["export_id"] == b["export_id"]
    market = market_for(reader, a)
    assert len(reader.facts(a["export_id"], market)) == 3 and len(reader.receipts(a["export_id"])) == 2


def test_manual_cli_retries_deadlock_without_duplicate_run_or_facts(case, lab, reader, monkeypatch, capsys):
    persist = PartialIngestionService._persist_export
    attempts = []
    def retry(service, *args):
        attempts.append(True)
        if len(attempts) == 1:
            raise psycopg.errors.DeadlockDetected("synthetic deadlock")
        return persist(service, *args)
    monkeypatch.setattr(PartialIngestionService, "_persist_export", retry)
    result = ingest(case, lab, monkeypatch, capsys)
    assert len(attempts) == 2
    market = market_for(reader, result)
    assert len(reader.facts(result["export_id"], market)) == 3
    assert len(reader.receipts(result["export_id"])) == 1
    with psycopg.connect(lab[0]) as c:
        assert c.execute("SELECT status FROM partial_import_runs WHERE source_hash=%s", (case[1],)).fetchall() == [("completed",)]


def test_v1_legacy_evidence_is_excluded_from_native_v2_views(lab, reader):
    source = AuctionatorAdapter().load_bytes(lua(), source_id="legacy-"+uuid4().hex,
                                           region="synthetic-eu", dataset="simulated")
    result = PartialIngestionService(lab[2].connection).import_batch(source)
    with psycopg.connect(lab[0]) as c:
        market = c.execute("SELECT market_id FROM partial_export_facts WHERE export_id=%s LIMIT 1", (result.export_id,)).fetchone()[0]
    assert all(m["id"] != market for m in reader.markets(limit=1000))
    with pytest.raises(ValueError, match="not found"):
        reader.states(market)
    with pytest.raises(ValueError, match="not found"):
        reader.state(result.export_id)


def test_reader_session_is_read_only_and_all_reads_preserve_rows_and_sequences(case, lab, reader, monkeypatch, capsys):
    result = ingest(case, lab, monkeypatch, capsys)
    market = market_for(reader, result)
    before = counts_and_sequences(lab[0])
    assert any(m["id"] == market for m in reader.markets(limit=1000))
    reader.states(market)
    reader.state(result["export_id"])
    reader.facts(result["export_id"], market)
    reader.receipts(result["export_id"])
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with reader._snapshot() as c:
            assert c.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
            c.execute("INSERT INTO partial_items(item_key,external_item_id,key_kind) VALUES ('99999','99999','item')")
    assert counts_and_sequences(lab[0]) == before


@pytest.mark.parametrize("action", ["markets", "states", "state", "facts", "receipts"])
def test_read_cli_all_native_v2_views(case, lab, reader, monkeypatch, capsys, action):
    result = ingest(case, lab, monkeypatch, capsys)
    market = market_for(reader, result)
    args = [action, "--database-url-env", "MANUAL_FIXTURE_DSN"]
    if action in ("states", "facts"):
        args += ["--market-id", str(market)]
    if action in ("state", "facts", "receipts"):
        args += ["--export-id", str(result["export_id"])]
    before = counts_and_sequences(lab[0])
    assert read_cli.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["contract"] == "local-evidence-reader-v2" and not output["analytics_enabled"]
    assert counts_and_sequences(lab[0]) == before


def test_reader_pagination_and_wrong_economy_rejected(case, tmp_path, lab, reader, monkeypatch, capsys):
    result = ingest(case, lab, monkeypatch, capsys)
    other = ingest(archived_case(tmp_path, economy="other-"+uuid4().hex), lab, monkeypatch, capsys)
    market, other_market = market_for(reader, result), market_for(reader, other)
    expected = reader.facts(result["export_id"], market)
    pages = [reader.facts(result["export_id"], market, limit=1, offset=i)[0] for i in range(3)]
    assert pages == expected
    assert reader.facts(result["export_id"], market, offset=3) == []
    assert reader.receipts(result["export_id"], offset=1) == []
    with pytest.raises(ValueError, match="does not contain"):
        reader.facts(result["export_id"], other_market)
    with pytest.raises(ValueError, match="not found"):
        reader.state(2**63-1)


def test_ingest_rejects_effective_protected_database_without_changes(case, lab, monkeypatch, capsys):
    before = counts_and_sequences(lab[0])
    monkeypatch.setattr(settings, "database_url", lab[0])
    monkeypatch.setenv("MANUAL_FIXTURE_DSN", make_conninfo(lab[0], host="localhost"))
    assert cli.main(cli_args(case, "ingest") + ["--database-url-env", "MANUAL_FIXTURE_DSN", "--expected-database", lab[1]]) == 1
    capsys.readouterr()
    assert counts_and_sequences(lab[0]) == before


def test_unprepared_target_is_never_migrated_or_written(case, lab):
    # Created only on the explicitly selected lab cluster. No default connection,
    # existing DB reset or schema_migrations edit is used for this rejection.
    name = "unprepared_" + uuid4().hex + "_test"
    with psycopg.connect(lab[0], autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = make_conninfo(lab[0], dbname=name)
    try:
        with TrialDatabase(dsn, settings.database_url, name) as target:
            with pytest.raises(ValueError, match="not prepared"):
                PartialIngestionService(trial_target=target).import_batch(preflight_archive(*case))
        with psycopg.connect(dsn) as c:
            c.read_only = True
            assert c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall() == []
        with pytest.raises(psycopg.errors.UndefinedTable):
            LocalEvidenceReader(lambda: psycopg.connect(dsn, row_factory=dict_row)).markets()
    finally:
        with psycopg.connect(lab[0], autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
