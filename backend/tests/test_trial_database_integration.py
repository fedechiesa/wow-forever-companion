"""Real PostgreSQL trial checks; require an explicitly provisioned dedicated lab."""
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app.core.config import settings
from app.db.trial import TrialDatabase, TrialSafetyError
import app.db.trial as trial
from app.ingestion.partial_service import PartialIngestionService
from scripts import import_auctionator as cli


FIXTURE = Path(__file__).parent / "fixtures" / "auctionator_v8.lua"


@pytest.fixture(scope="module")
def lab():
    dsn = os.environ.get("TRIAL_INTEGRATION_DATABASE_URL")
    name = os.environ.get("TRIAL_INTEGRATION_DATABASE_NAME")
    if not dsn or not name:
        pytest.fail("Explicit TRIAL_INTEGRATION_DATABASE_URL/NAME required; never fall back to development")
    with TrialDatabase(dsn, settings.database_url, name) as target:
        with target.connection() as c:
            migrations = c.execute("SELECT id FROM public.schema_migrations ORDER BY id").fetchall()
            assert len(migrations) == 5
    return dsn, name


def counts_and_sequences(dsn):
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION READ ONLY")
        rows = {}
        for name, in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall():
            rows[name] = c.execute(sql.SQL("SELECT t::text FROM {} t ORDER BY t::text").format(sql.Identifier("public", name))).fetchall()
        sequences = {}
        for name, in c.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public'").fetchall():
            sequences[name] = c.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(sql.Identifier("public", name))).fetchone()
        return rows, sequences


def args_for(lab, monkeypatch, source=None):
    dsn, name = lab
    monkeypatch.setenv("TRIAL_SELECTED_DSN", dsn)
    return [str(FIXTURE), "--source-id", source or uuid4().hex, "--region", "trial-integration",
            "--dataset", "simulated", "--trial", "--database-url-env", "TRIAL_SELECTED_DSN",
            "--expected-database", name]


def test_real_check_target_and_idempotent_trial_import(lab, monkeypatch, capsys):
    dsn, name = lab
    args = args_for(lab, monkeypatch)
    before = counts_and_sequences(dsn)
    assert cli.main(["--trial", "--database-url-env", "TRIAL_SELECTED_DSN",
                     "--expected-database", name, "--check-target"]) == 0
    assert counts_and_sequences(dsn) == before
    assert cli.main(args) == 0
    output = capsys.readouterr().out.splitlines()
    first = json.loads(output[-1])
    assert first["status"] == "completed" and first["evidence_status"] == "created"
    assert cli.main(args) == 0
    second = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert second["status"] == "duplicate" and second["observations_changed"] == 0
    assert second["export_id"] == first["export_id"] and second["evidence_status"] == "reused"


@pytest.mark.parametrize("alias", [False, True])
def test_real_same_effective_database_rejected_without_rows_or_sequence_changes(lab, alias):
    dsn, name = lab
    alternate = make_conninfo(dsn, host="127.0.0.1", sslmode="disable") if alias else dsn
    before = counts_and_sequences(dsn)
    with pytest.raises(TrialSafetyError, match="effective DATABASE_URL"):
        with TrialDatabase(alternate, dsn, name):
            pytest.fail("same actual database accepted")
    assert counts_and_sequences(dsn) == before


@pytest.mark.parametrize("change", ["user", "sslmode", "port", "protected"])
def test_real_bad_connections_cannot_reach_writer(lab, change):
    dsn, name = lab
    bad = {"user": {"user": "missing_" + uuid4().hex},
           "sslmode": {"sslmode": "invalid_mode"}, "port": {"port": "1"},
           "protected": {"user": "missing_" + uuid4().hex}}[change]
    alternate = make_conninfo(dsn, **bad)
    before = counts_and_sequences(dsn)
    with pytest.raises(TrialSafetyError):
        with TrialDatabase(dsn if change == "protected" else alternate,
                           alternate if change == "protected" else settings.database_url, name):
            pytest.fail("unverified connection accepted")
    assert counts_and_sequences(dsn) == before


def test_real_wrong_password_sanitized_and_cli_does_not_load_or_write(lab, monkeypatch, capsys):
    dsn, name = lab
    secret = "wrong-private-password-" + uuid4().hex
    monkeypatch.setenv("TRIAL_SELECTED_DSN", make_conninfo(dsn, password=secret))
    monkeypatch.setattr(cli, "load", lambda _: pytest.fail("connection failure reached parser"))
    before = counts_and_sequences(dsn)
    assert cli.main(["--trial", "--database-url-env", "TRIAL_SELECTED_DSN",
                     "--expected-database", name, "--check-target"]) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err and "Traceback" not in output.err
    assert counts_and_sequences(dsn) == before


def test_real_failure_record_uses_trial_factory_and_redacts_details(lab, monkeypatch, capsys):
    dsn, _ = lab
    source = uuid4().hex
    args = args_for(lab, monkeypatch, source)
    secret = "secret-from-driver-do-not-log"

    def fail(*args):
        raise psycopg.errors.CheckViolation(secret)

    monkeypatch.setattr(PartialIngestionService, "_persist_observation", fail)
    assert cli.main(args) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION READ ONLY")
        row = c.execute("SELECT status,error_message FROM partial_import_runs WHERE source_id=%s", (source,)).fetchone()
        assert row == ("failed", "Trial import failed; database details withheld.")
        assert c.execute("SELECT count(*) FROM partial_exports WHERE source_id=%s", (source,)).fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM partial_observations WHERE source_id=%s", (source,)).fetchone()[0] == 0


def test_real_ordinary_cli_still_uses_database_url(lab, monkeypatch, capsys):
    dsn, _ = lab
    monkeypatch.setattr(settings, "database_url", dsn)
    args = [str(FIXTURE), "--source-id", uuid4().hex, "--region", "ordinary-regression", "--dataset", "simulated"]
    assert cli.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"


def test_real_retry_sessions_are_revalidated(lab, monkeypatch, capsys):
    args = args_for(lab, monkeypatch)
    original = PartialIngestionService._persist_observation
    verify = TrialDatabase._verify
    checked = []
    failed = False

    def track(self, c):
        result = verify(self, c)
        checked.append(c.info.backend_pid)
        return result

    def deadlock_once(self, *args):
        nonlocal failed
        if not failed:
            failed = True
            raise psycopg.errors.DeadlockDetected("synthetic retry")
        return original(self, *args)

    monkeypatch.setattr(TrialDatabase, "_verify", track)
    monkeypatch.setattr(PartialIngestionService, "_persist_observation", deadlock_once)
    assert cli.main(args) == 0
    assert len(checked) == 3  # preview, first transaction, retried transaction
    assert checked[0] == checked[1] and checked[2] != checked[1]
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "completed"


@pytest.mark.parametrize("failure", ["identity", "query"])
def test_real_sessions_protected_revalidation_failure_preserves_target(lab, monkeypatch, failure):
    dsn, name = lab
    before = counts_and_sequences(dsn)
    read = trial._identity
    with TrialDatabase(dsn, settings.database_url, name) as target:
        def invalid_protected(c):
            identity, recovery = read(c)
            if c is target._protected_connection:
                if failure == "query":
                    # Simulate permission/query failure; no grants/revokes or DB changes.
                    raise TrialSafetyError("Cannot verify PostgreSQL cluster/database identity with read-only queries.")
                return target.identity, recovery  # Original audit's A -> target B change.
            return identity, recovery

        monkeypatch.setattr(trial, "_identity", invalid_protected)
        with pytest.raises(TrialSafetyError):
            with target.connection():
                pytest.fail("unsafe protected identity reached writer")
    assert counts_and_sequences(dsn) == before
