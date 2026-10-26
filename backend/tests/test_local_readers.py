from unittest.mock import MagicMock

import pytest

from app.ingestion.local_readers import LocalEvidenceReader
from scripts import read_local_evidence as cli


@pytest.mark.parametrize("method,args,kwargs", [
    ("markets", [], {"limit": 1001}), ("markets", [], {"offset": -1}),
    ("markets", [], {"offset": True}), ("states", [0], {}),
    ("states", [True], {}), ("state", [2**63], {}),
    ("facts", [1, 0], {}), ("facts", [1, 1], {"limit": 0}),
    ("receipts", [-1], {}), ("receipts", [1], {"offset": 2**31}),
])
def test_invalid_reader_selectors_never_connect(method, args, kwargs):
    connect = MagicMock(side_effect=AssertionError("invalid selector reached DB"))
    with pytest.raises(ValueError):
        getattr(LocalEvidenceReader(connect), method)(*args, **kwargs)
    connect.assert_not_called()


def test_read_cli_redacts_connection_failure(monkeypatch, capsys):
    monkeypatch.setenv("EVIDENCE_DSN", "private-secret-sentinel")
    assert cli.main(["markets", "--database-url-env", "EVIDENCE_DSN"]) == 1
    output = capsys.readouterr()
    assert "private-secret-sentinel" not in output.out + output.err and "Traceback" not in output.err


@pytest.mark.parametrize("args", [["facts"], ["states", "--export-id", "1"], ["receipts", "--market-id", "1"]])
def test_read_cli_requires_unambiguous_selectors(args):
    with pytest.raises(SystemExit) as error:
        cli.main(args + ["--database-url-env", "EVIDENCE_DSN"])
    assert error.value.code == 2
