from contextlib import nullcontext
from unittest.mock import MagicMock

import psycopg
import pytest

import app.db.trial as trial
from app.db.trial import DatabaseIdentity, TrialDatabase, TrialSafetyError
from scripts import import_auctionator as cli


DEV = "host=localhost port=5432 dbname=companion user=tester password=private-test-secret"
LAB = "host=localhost port=5432 dbname=companion_test user=tester password=private-test-secret"
DEV_ID = DatabaseIdentity("100", 1, "companion")
LAB_ID = DatabaseIdentity("100", 2, "companion_test")
IMPORT_ARGS = ["fixture.lua", "--source-id", "unit", "--region", "test", "--dataset", "simulated"]
TRIAL_ARGS = ["--trial", "--database-url-env", "BETA_TEST_DSN", "--expected-database", "companion_test"]


def connection():
    c = MagicMock()
    c.closed = False
    c.read_only = True
    c.info.transaction_status = trial.TransactionStatus.IDLE
    c.__enter__.return_value = c
    c.transaction.side_effect = lambda: nullcontext()
    return c


@pytest.fixture(autouse=True)
def clean_routing_environment(monkeypatch):
    for key in trial._ROUTING_ENV:
        monkeypatch.delenv(key, raising=False)


def fake_targets(monkeypatch, identities=None):
    monkeypatch.setattr(cli.settings, "database_url", DEV)
    protected, target = connection(), connection()
    opened = MagicMock(side_effect=[protected, target])
    read = MagicMock(side_effect=identities or [
        (DEV_ID, False), (LAB_ID, False), (DEV_ID, False), (LAB_ID, False),
    ])
    monkeypatch.setattr(trial, "_open", opened)
    monkeypatch.setattr(trial, "_identity", read)
    return protected, target, opened, read


def test_explicit_target_writes_on_same_validated_connection(monkeypatch):
    protected, target, opened, read = fake_targets(monkeypatch)
    with TrialDatabase(LAB, DEV, "companion_test") as selected:
        assert selected.identity == LAB_ID
        assert not target.execute.called  # Mocked identity reads; no writer yet.
        with selected.connection() as writer:
            assert writer is target and writer.read_only is False
            assert read.call_args.args == (target,)
            writer.execute("INSERT TEST")
    assert opened.call_count == 2 and read.call_count == 4
    assert [call.args[0] for call in read.call_args_list] == [protected, target, protected, target]
    protected.execute.assert_not_called()
    target.close.assert_called()


@pytest.mark.parametrize("dsn", [None, "", "postgresql://bad:%NOT-VALID@host/db",
    "dbname=companion_test", LAB + " options='-c search_path=other'",
    LAB.replace("localhost", "host1,host2"), LAB.replace("5432", "0"),
    LAB + " service=hidden", LAB + " replication=database"])
def test_incomplete_ambiguous_parameters_rejected_without_connect(monkeypatch, dsn):
    opened = MagicMock()
    monkeypatch.setattr(trial, "_open", opened)
    with pytest.raises(TrialSafetyError):
        TrialDatabase(dsn, DEV, "companion_test")
    opened.assert_not_called()


@pytest.mark.parametrize("name", [None, "", "companion", "wrong_test", "evil\n_test"])
def test_expected_name_is_explicit_and_matches_selection(name):
    with pytest.raises(TrialSafetyError):
        TrialDatabase(LAB, DEV, name)


def test_routing_environment_is_not_implicitly_trusted(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.2")
    with pytest.raises(TrialSafetyError, match="clean shell"):
        TrialDatabase(LAB, DEV, "companion_test")


@pytest.mark.parametrize("target_id,recovery", [
    (DatabaseIdentity("100", 1, "companion_test"), False),  # Effective DB, not URL spelling/name.
    (DatabaseIdentity("100", 2, "other_test"), False),
    (LAB_ID, True),
])
def test_bad_effective_identity_never_yields_writer(monkeypatch, target_id, recovery):
    protected, target, _, _ = fake_targets(monkeypatch, [(DEV_ID, False), (target_id, recovery)])
    with pytest.raises(TrialSafetyError):
        with TrialDatabase(LAB, DEV, "companion_test"):
            pytest.fail("unsafe target accepted")
    target.execute.assert_not_called()
    target.close.assert_called()
    protected.close.assert_called()


def test_target_changed_between_preview_and_write_rejected(monkeypatch):
    _, target, _, _ = fake_targets(monkeypatch, [
        (DEV_ID, False), (LAB_ID, False), (DEV_ID, False),
        (DatabaseIdentity("101", 2, "companion_test"), False),
    ])
    with TrialDatabase(LAB, DEV, "companion_test") as selected:
        with pytest.raises(TrialSafetyError, match="changed"):
            with selected.connection():
                pytest.fail("changed identity reached writer")
    target.execute.assert_not_called()


def test_connection_and_identity_errors_do_not_disclose_driver_messages(monkeypatch):
    secret = "private-test-secret"
    monkeypatch.setattr(psycopg, "connect", MagicMock(side_effect=psycopg.OperationalError(secret)))
    with pytest.raises(TrialSafetyError) as error:
        trial._open(trial._parameters(LAB))
    assert secret not in str(error.value)
    c = connection()
    c.execute.side_effect = psycopg.errors.InsufficientPrivilege(secret)
    with pytest.raises(TrialSafetyError) as error:
        trial._identity(c)
    assert secret not in str(error.value)


@pytest.mark.parametrize("args", [
    ["--trial"], ["--trial", "--expected-database", "companion_test"],
    ["--database-url-env", "BETA_TEST_DSN"], ["--check-target"], [],
])
def test_cli_missing_selection_or_import_arguments_fails_before_load_or_service(monkeypatch, args):
    load, service = MagicMock(), MagicMock()
    monkeypatch.setattr(cli, "load", load)
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    with pytest.raises(SystemExit) as error:
        cli.main(args)
    assert error.value.code == 2
    load.assert_not_called()
    service.assert_not_called()


def test_cli_no_target_value_does_not_fall_back_to_test_database_url(monkeypatch, capsys):
    monkeypatch.delenv("BETA_TEST_DSN", raising=False)
    monkeypatch.setattr(cli.settings, "test_database_url", LAB)
    load, service = MagicMock(), MagicMock()
    monkeypatch.setattr(cli, "load", load)
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    assert cli.main(IMPORT_ARGS + TRIAL_ARGS) == 1
    load.assert_not_called()
    service.assert_not_called()
    assert "private-test-secret" not in capsys.readouterr().err


def test_check_target_is_read_only_and_does_not_require_input_file(monkeypatch, capsys):
    _, target, _, read = fake_targets(monkeypatch)
    monkeypatch.setenv("BETA_TEST_DSN", LAB)
    load, service = MagicMock(), MagicMock()
    monkeypatch.setattr(cli, "load", load)
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    assert cli.main(TRIAL_ARGS + ["--check-target"]) == 0
    assert read.call_count == 2
    load.assert_not_called()
    service.assert_not_called()
    target.execute.assert_not_called()
    output = capsys.readouterr()
    assert "companion_test" in output.out and "private-test-secret" not in output.out + output.err


def test_trial_cli_passes_factory_and_suppresses_all_import_exception_details(monkeypatch, capsys):
    fake_targets(monkeypatch)
    monkeypatch.setenv("BETA_TEST_DSN", LAB)
    service = MagicMock()
    service.return_value.import_batch.side_effect = RuntimeError("private-test-secret")
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    monkeypatch.setattr(cli, "load", MagicMock(return_value=object()))
    assert cli.main(IMPORT_ARGS + TRIAL_ARGS) == 1
    assert callable(service.call_args.args[0]) and service.call_args.kwargs == {"redact_errors": True}
    output = capsys.readouterr()
    assert "private-test-secret" not in output.out + output.err


def test_ordinary_cli_keeps_default_service_and_does_not_validate_trial(monkeypatch, capsys):
    value = object()
    selected = MagicMock(side_effect=AssertionError("unexpected trial"))
    service = MagicMock()
    service.return_value.import_batch.return_value.model_dump_json.return_value = '{"status":"completed"}'
    monkeypatch.setattr(cli, "TrialDatabase", selected)
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    monkeypatch.setattr(cli, "load", MagicMock(return_value=value))
    assert cli.main(IMPORT_ARGS) == 0
    service.assert_called_once_with()
    service.return_value.import_batch.assert_called_once_with(value)
    assert '"completed"' in capsys.readouterr().out


@pytest.mark.parametrize("identity,recovery", [
    (DatabaseIdentity("101", 1, "companion"), False),
    (DatabaseIdentity("100", 3, "companion"), False),
    (DatabaseIdentity("100", 1, "renamed"), False),
    (LAB_ID, False),  # Original audit counterexample: protected backend becomes target.
    (DEV_ID, True),
])
def test_protected_change_never_yields_writer(monkeypatch, identity, recovery):
    protected, target, _, _ = fake_targets(monkeypatch, [
        (DEV_ID, False), (LAB_ID, False), (identity, recovery),
    ])
    with TrialDatabase(LAB, DEV, "companion_test") as selected:
        with pytest.raises(TrialSafetyError, match="Protected database identity"):
            with selected.connection():
                pytest.fail("changed protection reached writer")
    protected.execute.assert_not_called()
    target.execute.assert_not_called()
    target.close.assert_called()


@pytest.mark.parametrize("failure", ["closed", "permission", "connection", "busy", "writable"])
def test_protected_failure_never_yields_writer(monkeypatch, failure):
    protected, target, _, _ = fake_targets(monkeypatch)
    with TrialDatabase(LAB, DEV, "companion_test") as selected:
        if failure == "closed":
            protected.closed = True
        elif failure == "busy":
            protected.info.transaction_status = trial.TransactionStatus.INTRANS
        elif failure == "writable":
            protected.read_only = False
        else:
            error = psycopg.errors.InsufficientPrivilege if failure == "permission" else psycopg.OperationalError
            protected.execute.side_effect = error("private-test-secret")
            # Exercise the real read-only query/error boundary, not a fabricated safety error.
            monkeypatch.setattr(trial, "_identity", REAL_IDENTITY)
        with pytest.raises(TrialSafetyError) as error:
            with selected.connection():
                pytest.fail("unverified protection reached writer")
        assert "private-test-secret" not in str(error.value)
    target.execute.assert_not_called()


REAL_IDENTITY = trial._identity


@pytest.mark.parametrize("stage", ["reconnect", "retry", "failure_record"])
@pytest.mark.parametrize("changed", ["protected", "target"])
def test_later_sessions_revalidate_both_before_writing(monkeypatch, stage, changed):
    from app.ingestion.adapters.auctionator import AuctionatorAdapter
    import app.ingestion.partial_service as service_module
    from pathlib import Path

    result = AuctionatorAdapter().load(
        Path(__file__).parent / "fixtures/auctionator_v8.lua",
        source_id="synthetic-guard", region="test", dataset="simulated",
    )
    protected, first, later = connection(), connection(), connection()
    protected_reads = 0
    target_reads = 0

    def identity(c):
        nonlocal protected_reads, target_reads
        if c is protected:
            protected_reads += 1
            return (LAB_ID if changed == "protected" and protected_reads == 3 else DEV_ID), False
        target_reads += 1
        return (DatabaseIdentity("101", 2, "companion_test")
                if changed == "target" and target_reads == 3 else LAB_ID), False

    monkeypatch.setattr(trial, "_open", MagicMock(side_effect=[protected, first, later]))
    monkeypatch.setattr(trial, "_identity", identity)
    fallback = MagicMock(side_effect=AssertionError("global connection fallback"))
    monkeypatch.setattr(service_module, "connect", fallback)
    monkeypatch.setattr(service_module.time, "sleep", MagicMock())
    create = MagicMock(side_effect=psycopg.errors.DeadlockDetected("private-test-secret")
                       if stage == "retry" else psycopg.errors.CheckViolation("private-test-secret"))
    monkeypatch.setattr(service_module.PartialIngestionService, "_create_run", create)
    with TrialDatabase(LAB, DEV, "companion_test") as selected:
        if stage == "reconnect":
            with selected.connection():
                pass
        with pytest.raises(TrialSafetyError):
            if stage == "reconnect":
                with selected.connection():
                    pytest.fail("changed reconnect reached writer")
            else:
                service_module.PartialIngestionService(selected.connection, redact_errors=True).import_batch(result)
    assert protected_reads == 3
    assert create.call_count == (0 if stage == "reconnect" else 1)
    later.execute.assert_not_called()
    fallback.assert_not_called()


def test_ordinary_cli_runtime_exception_is_sanitized(monkeypatch, capsys):
    service = MagicMock(side_effect=RuntimeError("postgresql://tester:private-test-secret@host/db"))
    monkeypatch.setattr(cli, "PartialIngestionService", service)
    assert cli.main(IMPORT_ARGS) == 1
    output = capsys.readouterr()
    assert "private-test-secret" not in output.out + output.err
    assert "postgresql://" not in output.out + output.err
