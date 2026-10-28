"""Opt-in operational rehearsal: synthetic files and an explicitly selected new lab.

Never selects development or a real SavedVariables path. The artifact directory
must be new and outside the repository. No provider API or game client is used.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from app.core.config import settings
from app.db.trial import TrialDatabase, TrialSafetyError, _open, _parameters
from app.ingestion.local_readers import LocalEvidenceReader
from app.ingestion.partial_service import PartialIngestionService
from app.local_capture.archive import capture_file
from app.local_capture.preflight import preflight_archive
from test_local_capture import lua
from test_trial_database_integration import counts_and_sequences

BACKEND = Path(__file__).resolve().parents[1]
PREFIX = b"-- SIMULATED prices and availability; prelaunch readiness fixture only\n"


def wait_for(check, process=None, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None:
            assert process.poll() is None, "Synthetic watcher stopped unexpectedly"
        if check():
            return
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for synthetic rehearsal condition")


def context(capture_id):
    return dict(contract="verified-local-capture-v1", serialized_codec=None,
        provenance=dict(version=1, source_sha256=capture_id, format_version="341",
            source_id="readiness-synthetic-observer", region="synthetic-eu", dataset="simulated",
            capture_phase="simulated", market_rulesets={"PvP":"PvP"},
            region_evidence_ref="synthetic#region", market_evidence_ref="synthetic#market",
            origin_evidence_ref="synthetic#origin", codec_producer="unverified"),
        market_identities={"PvP":dict(economy=dict(value="readiness-synthetic-economy", evidence_ref="synthetic#economy"),
            realm=None, faction=None, auction_house_scope="shared", scope_evidence_ref="synthetic#scope")})


@pytest.fixture
def rehearsal():
    keys = ["PRELAUNCH_INTEGRATION_DATABASE_URL", "PRELAUNCH_PROTECTED_DATABASE_URL",
            "PRELAUNCH_INTEGRATION_DATABASE_NAME", "PRELAUNCH_ARTIFACTS_DIR"]
    if not all(os.environ.get(key) for key in keys):
        pytest.skip("Opt-in requires explicit new laboratory and private artifact directory")
    dsn, protected, name, directory = [os.environ[key] for key in keys]
    assert settings.database_url == protected, "DATABASE_URL must be the new lab reference, never development"
    root = Path(directory).resolve() / ("run-" + uuid4().hex)
    assert BACKEND.parent not in root.parents and not root.exists()
    root.mkdir(parents=True)
    with TrialDatabase(dsn, protected, name) as target:
        with target.connection() as c:
            assert len(c.execute("SELECT id FROM schema_migrations").fetchall()) == 6
            assert c.execute("SELECT count(*) AS n FROM partial_exports").fetchone()["n"] == 0, "Fresh lab required"
        yield root, dsn, protected, name, target


def test_synthetic_watcher_to_protected_ingestion_and_v2(rehearsal, monkeypatch):
    root, dsn, protected, name, target = rehearsal
    protected_before = counts_and_sequences(protected)
    source = root / "input" / "Auctionator.lua"
    source.parent.mkdir()
    def write(raw):
        # Windows deliberately denies a writer while the archive reader holds its
        # stable-read handle. A synthetic producer waits, as WoW's save can do.
        for attempt in range(50):
            try:
                source.write_bytes(raw)
                return
            except PermissionError:
                time.sleep(0.025)
        raise AssertionError("Synthetic writer could not acquire source file")
    archive = root / "archive"
    log = root / "watcher.log"
    raw_a = PREFIX + lua(key="2589", low=0, high=100, minimum=100)
    raw_b = PREFIX + lua(key="2589", low=5, high=200, minimum=200, available=3)
    captures = lambda: list((archive / "captures").glob("*/metadata.json"))
    events = lambda: log.read_text(encoding="utf-8") if log.exists() else ""
    env = os.environ.copy()
    # Deliberately unavailable backend/DB; watcher and preflight must never connect.
    env.update(DATABASE_URL="postgresql://unavailable@127.0.0.1:1/offline_test", PRELAUNCH_SQL_DENY="1")
    def cli(script, *args, offline=False):
        result = subprocess.run([sys.executable,"-X","utf8","-B",str(BACKEND/"scripts"/script),*map(str,args)],
            cwd=root, env=env if offline else os.environ.copy(), capture_output=True, text=True, encoding="utf-8", timeout=25)
        return result
    def start():
        stream = log.open("a", encoding="utf-8")
        process = subprocess.Popen([sys.executable,"-X","utf8","-B",str(BACKEND/"scripts/watch_auctionator.py"),
            str(source),"--destination",str(archive),"--source-version","341","--poll-interval","0.25",
            "--debounce","0.25","--stable-seconds","0.5","--retry-delay","0.25","--recovery-interval","1"],
            cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        return process, stream
    def stop(process, stream):
        # Abrupt termination also proves restart does not rely on in-memory history.
        process.terminate()
        process.wait(timeout=10)
        stream.close()
    process, stream = start()
    try:
        wait_for(lambda: "Archivo ausente" in events(), process)
        write(b"AUCTIONATOR_PRICE_DATABASE={")
        wait_for(lambda: "Error de validación" in events(), process)
        assert captures() == []
        write(raw_a[:-1])
        time.sleep(0.2)
        write(raw_a)
        time.sleep(0.2)
        assert captures() == []  # Quiet/stable interval has not elapsed.
        wait_for(lambda: len(captures())==1, process)
        write(raw_b)
        wait_for(lambda: len(captures())==2, process)
        write(raw_a)
        wait_for(lambda: "Archivo idéntico" in events(), process)
        assert len(captures()) == 2
    finally:
        stop(process, stream)
    previous = events().count("Archivo idéntico")
    process, stream = start()
    try:
        wait_for(lambda: events().count("Archivo idéntico") > previous, process)
        assert len(captures()) == 2
    finally:
        stop(process, stream)
    expected = {sha256(raw_a).hexdigest():raw_a, sha256(raw_b).hexdigest():raw_b}
    for capture_id, raw in expected.items():
        saved = archive/"captures"/capture_id/"Auctionator.lua"
        assert saved.read_bytes() == raw and sha256(saved.read_bytes()).hexdigest() == capture_id
    assert source.read_bytes()==raw_a
    assert counts_and_sequences(protected)==protected_before
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM partial_exports").fetchone()[0] == 0

    prepared = {}
    for capture_id in expected:
        file = root / f"context-{capture_id}.json"
        file.write_text(json.dumps(context(capture_id)),encoding="utf-8")
        result = cli("ingest_local_capture.py","preflight","--archive",archive,"--capture-id",capture_id,"--context-file",file,offline=True)
        assert result.returncode==0, result.stderr
        summary=json.loads(result.stdout)
        assert not summary["import_performed"] and not summary["target_verified"]
        prepared[capture_id]=file
    monkeypatch.setenv("PRELAUNCH_SELECTED_DSN",dsn)
    check = cli("import_auctionator.py","--trial","--check-target","--database-url-env","PRELAUNCH_SELECTED_DSN","--expected-database",name)
    assert check.returncode==0,check.stderr
    before_guard=counts_and_sequences(dsn)
    with pytest.raises(TrialSafetyError):
        with TrialDatabase(dsn,dsn,name):
            pytest.fail("Same effective destination accepted")
    assert counts_and_sequences(dsn)==before_guard
    def ingest(capture_id):
        result=cli("ingest_local_capture.py","ingest","--archive",archive,"--capture-id",capture_id,
            "--context-file",prepared[capture_id],"--database-url-env","PRELAUNCH_SELECTED_DSN","--expected-database",name)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    first=ingest(sha256(raw_a).hexdigest())
    second=ingest(sha256(raw_b).hexdigest())
    duplicate=ingest(sha256(raw_a).hexdigest())
    assert first["status"]==second["status"]=="completed"
    assert duplicate["status"]=="duplicate" and first["export_id"]==duplicate["export_id"]!=second["export_id"]
    assert all(row["observations_changed"]==0 for row in (first,second,duplicate))

    reader=LocalEvidenceReader(lambda:_open(_parameters(dsn)))
    markets=reader.markets()
    market=next(m for m in markets if m["economic_identity"]["economy"]=="readiness-synthetic-economy")
    market_id=market["id"]
    assert len(reader.states(market_id))==2
    assert len(reader.receipts(first["export_id"]))==2
    facts=reader.facts(first["export_id"],market_id)
    assert {row["scan_day"] for row in facts}=={2485,None}
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT count(*) FROM partial_export_facts").fetchone()[0]==8
        assert c.execute("SELECT count(*) FROM partial_capture_receipts").fetchone()[0]==3
        assert c.execute("SELECT count(*) FROM partial_observations").fetchone()[0]==0
    stable=counts_and_sequences(dsn)[0]

    # Fail after native rows were written inside the transaction; only the failed
    # import audit may survive. PostgreSQL sequence values are not transactional.
    write(PREFIX+lua(key="2589",high=333,minimum=333))
    third=capture_file(source,archive,source_version="341")
    third_id=third.metadata.capture_id
    third_context=root/f"context-{third_id}.json"
    third_context.write_text(json.dumps(context(third_id)),encoding="utf-8")
    failing=preflight_archive(archive,third_id,third_context)
    service=PartialIngestionService(trial_target=target)
    persist=service._persist_export
    def fail_after_write(*args):
        persist(*args)
        raise psycopg.errors.CheckViolation("synthetic rollback rehearsal")
    with monkeypatch.context() as patch:
        patch.setattr(service,"_persist_export",fail_after_write)
        with pytest.raises(psycopg.Error):
            service.import_batch(failing)
    after=counts_and_sequences(dsn)[0]
    assert all(after[table]==rows for table,rows in stable.items() if table!="partial_import_runs")
    assert len(after["partial_import_runs"])==len(stable["partial_import_runs"])+1
    before_range=counts_and_sequences(dsn)
    blocked=[]
    for price in (2**31,2**63-1):
        raw=PREFIX+lua(key="2589",high=price,minimum=price)
        write(raw)
        captured=capture_file(source,archive,source_version="341")
        file=root/f"context-{captured.metadata.capture_id}.json"
        file.write_text(json.dumps(context(captured.metadata.capture_id)),encoding="utf-8")
        result=cli("ingest_local_capture.py","ingest","--archive",archive,"--capture-id",captured.metadata.capture_id,
            "--context-file",file,"--database-url-env","PRELAUNCH_SELECTED_DSN","--expected-database",name)
        assert result.returncode==1 and "price_exceeds_persistence_int32" in result.stderr
        assert (archive/"captures"/captured.metadata.capture_id/"Auctionator.lua").read_bytes()==raw
        blocked.append(price)
    assert counts_and_sequences(dsn)==before_range
    assert counts_and_sequences(protected)==protected_before
    report=dict(contract="prelaunch-synthetic-rehearsal-v1",root=str(root),archive=str(archive),
        market_id=market_id,first=first,second=second,duplicate=duplicate,capture_ids=list(expected),
        watcher_captures=2,watcher_restart_deduplicated=True,partial_rejected=True,backend_offline=True,
        facts=8,receipts=3,bucket=2485,rollback="only_failed_import_audit_survives",blocked_prices=blocked,
        protected_reference_unchanged=True,development_connections=0,context_files={key:str(value) for key,value in prepared.items()})
    (root/"result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (root.parent/"latest.json").write_text(json.dumps(report),encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key not in ("root","archive","context_files")}))
