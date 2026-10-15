"""Run the actual CLI in child processes, with private temporary configuration only."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


CLI = Path(__file__).resolve().parents[1] / "scripts/import_auctionator.py"
SECRET = "AUDIT7"
DSN = f"postgresql://x:{SECRET}@h:5432/lab_test"
ARGS = ["--trial", "--database-url-env", "BETA_TRIAL_DATABASE_URL",
        "--expected-database", "lab_test", "--check-target"]


def run_cli(directory, args=ARGS, **overrides):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("PG") and key.upper() not in {
               "DATABASE_URL", "TEST_DATABASE_URL", "BETA_TRIAL_DATABASE_URL"}}
    env.update(overrides)
    return subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=directory,
                          env=env, text=True, capture_output=True, timeout=15)


def assert_private_failure(result, message):
    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert all(value not in result.stdout + result.stderr for value in
               (SECRET, DSN, "postgresql://", "input_value", "Traceback"))


@pytest.mark.parametrize("args", [ARGS, ["fixture.lua", "--source-id", "unit",
                                      "--region", "test", "--dataset", "simulated"]])
def test_unknown_dotenv_dsn_is_rejected_without_pydantic_disclosure(tmp_path, args):
    # Reproduces the audit using a temporary .env, never backend/.env.
    (tmp_path / ".env").write_text(f"BETA_TRIAL_DATABASE_URL={DSN}\n", encoding="utf-8")
    assert_private_failure(run_cli(tmp_path, args), "CLI initialization failed")


def test_pydantic_validation_error_from_another_unknown_key_is_sanitized(tmp_path):
    (tmp_path / ".env").write_text(f"UNKNOWN_CONFIGURATION={DSN}\n", encoding="utf-8")
    assert_private_failure(run_cli(tmp_path), "CLI initialization failed")


def test_configuration_decode_failure_is_sanitized(tmp_path):
    (tmp_path / ".env").write_bytes(b"UNKNOWN=" + DSN.encode() + b"\xff")
    assert_private_failure(run_cli(tmp_path), "CLI initialization failed")


@pytest.mark.parametrize("connection", ["target", "protected"])
@pytest.mark.parametrize("suffix,message", [
    ("h:badport/lab_test", "Use explicit single-host"),
    ("h:5432/lab_test?not-a-key=value", "Invalid database connection configuration"),
])
def test_invalid_dsn_is_rejected_before_connect_without_disclosure(tmp_path, connection, suffix, message):
    invalid = f"postgresql://x:{SECRET}@{suffix}"
    env = {"BETA_TRIAL_DATABASE_URL": invalid if connection == "target" else DSN}
    if connection == "protected":
        env["DATABASE_URL"] = invalid
    assert_private_failure(run_cli(tmp_path, **env), message)


def test_missing_required_target_does_not_use_settings_default(tmp_path):
    assert_private_failure(run_cli(tmp_path), "Both database connections must be explicitly configured")


def test_missing_required_trial_argument_exits_without_disclosure(tmp_path):
    result = run_cli(tmp_path, ["--trial", "--database-url-env", "BETA_TRIAL_DATABASE_URL"],
                     BETA_TRIAL_DATABASE_URL=DSN)
    assert result.returncode == 2
    assert "requires --database-url-env and --expected-database" in result.stderr
    assert all(value not in result.stdout + result.stderr for value in (SECRET, DSN, "Traceback"))


def test_real_cli_help_with_valid_default_configuration(tmp_path):
    result = run_cli(tmp_path, ["--help"])
    assert result.returncode == 0
    assert "--trial" in result.stdout and result.stderr == ""
