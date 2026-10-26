"""Synthetic published archives only. Preflight must finish before DB startup."""
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.local_capture.archive import capture_file
from app.local_capture.decoder import CaptureAdapter
from app.local_capture.preflight import PreflightError, preflight_archive, preflight_summary
from scripts import ingest_local_capture as cli
from test_local_capture import lua
from test_local_lineage import local_source
from test_auctionator_cbor import encode, envelope


def archived_case(tmp_path, raw=None, *, codec=None, version="341", **context_options):
    raw = lua() if raw is None else raw
    source = tmp_path / "synthetic.lua"
    source.write_bytes(raw)
    archive = tmp_path / "archive"
    capture = capture_file(source, archive, source_version=version, serialized_codec=codec)
    # Reuse the existing fixture's reviewed synthetic identity, never private data.
    context = local_source(dataset="simulated", **context_options).local_capture.context.model_dump(mode="json")
    context["serialized_codec"] = codec
    context["provenance"]["source_sha256"] = sha256(raw).hexdigest()
    markets = CaptureAdapter().decode_bytes(raw, serialized_codec=codec).native.markets
    context["provenance"]["market_rulesets"] = {m.market_key: m.ruleset for m in markets}
    identity = context["market_identities"]["PvP"]
    context["market_identities"] = {}
    for market in markets:
        value = json.loads(json.dumps(identity))
        if market.market_key != "PvP":
            value["economy"]["value"] += "-" + market.market_key
        context["market_identities"][market.market_key] = value
    context_file = tmp_path / ("context-" + uuid4().hex + ".json")
    context_file.write_text(json.dumps(context), encoding="utf-8")
    return archive, capture.metadata.capture_id, context_file


def cli_args(case, action="preflight"):
    archive, capture_id, context = case
    return [action, "--archive", str(archive), "--capture-id", capture_id, "--context-file", str(context)]


@pytest.fixture(autouse=True)
def no_sql(monkeypatch):
    connect = MagicMock(side_effect=AssertionError("preflight reached SQL"))
    monkeypatch.setattr("psycopg.connect", connect)
    yield
    connect.assert_not_called()


@pytest.mark.parametrize("codec", [None, "cbor-definite"])
@pytest.mark.parametrize("price", [0, 2**31-1, 2**31, 2**53+1, 2**63-1])
def test_archive_price_boundaries_are_exact_and_block_whole_capture(tmp_path, codec, price):
    raw = (envelope(encode({b"version": 2, b"123": {b"l": [], b"h": {b"2485": price}, b"m": price}}))
           if codec else lua(high=price, minimum=price))
    case = archived_case(tmp_path, raw, codec=codec)
    original = case[0] / "captures" / case[1] / "Auctionator.lua"
    if price > 2**31-1:
        with pytest.raises(PreflightError, match="price_exceeds_persistence_int32"):
            preflight_archive(*case)
    else:
        result = preflight_archive(*case)
        assert {f.value for f in result.native.facts if f.native_field in ("h", "m")} == {price}
        assert not preflight_summary(result)["import_performed"]
    assert original.read_bytes() == raw


@pytest.mark.parametrize("mutation", ["region", "economy", "faction", "realm", "source_id", "scope", "hash", "ruleset", "codec", "contract"])
def test_explicit_context_cannot_be_omitted_or_contradict_archive(tmp_path, mutation):
    case = archived_case(tmp_path)
    context = json.loads(case[2].read_text())
    identity = context["market_identities"]["PvP"]
    if mutation in ("region", "source_id"):
        context["provenance"][mutation] = "unknown"
    elif mutation in ("economy", "realm", "faction"):
        del identity[mutation]
    elif mutation == "scope":
        identity["auction_house_scope"] = "faction"
    elif mutation == "hash":
        context["provenance"]["source_sha256"] = "a"*64
    elif mutation == "ruleset":
        context["provenance"]["market_rulesets"] = {"Other": "PvP"}
    elif mutation == "codec":
        context["serialized_codec"] = "cbor-definite"
    else:
        context["contract"] = "local-capture-context-v1"
    case[2].write_text(json.dumps(context))
    with pytest.raises(PreflightError):
        preflight_archive(*case)


@pytest.mark.parametrize("field,value", [("market_sha256", "b"*64), ("native_fact_count", 9), ("source_bytes", 0)])
def test_recomputed_metadata_detects_corruption(tmp_path, field, value):
    case = archived_case(tmp_path)
    path = case[0] / "captures" / case[1] / "metadata.json"
    data = json.loads(path.read_text())
    data[field] = value
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_text(json.dumps(data))
    path.chmod(stat.S_IREAD)
    with pytest.raises(PreflightError, match="archive_integrity_failed"):
        preflight_archive(*case)


@pytest.mark.parametrize("mutation", ["raw", "writeable", "extra", "missing", "pending"])
def test_only_intact_published_archive_is_selectable(tmp_path, mutation):
    case = archived_case(tmp_path)
    entry = case[0] / "captures" / case[1]
    if mutation == "pending":
        entry.rename(case[0] / "pending" / case[1])
    elif mutation == "extra":
        (entry / "extra.txt").write_text("synthetic")
    else:
        path = entry / "Auctionator.lua"
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
        if mutation == "missing":
            path.unlink()
        elif mutation == "raw":
            path.write_bytes(lua(high=200))
            path.chmod(stat.S_IREAD)
    with pytest.raises(PreflightError, match="archive_integrity_failed"):
        preflight_archive(*case)


@pytest.mark.parametrize("capture_id", ["../pending", "a"*63, "A"*64, "a"*65, ""])
def test_capture_selector_cannot_be_a_path(tmp_path, capture_id):
    case = archived_case(tmp_path)
    with pytest.raises(PreflightError, match="invalid_capture_id"):
        preflight_archive(case[0], capture_id, case[2])


@pytest.mark.parametrize("raw", ['{"contract":1,"contract":2}', '['*1500, ' '*65537, '{}'],
                         ids=["duplicate", "deep", "oversize", "empty"])
def test_context_json_limits_duplicates_and_depth(tmp_path, raw):
    case = archived_case(tmp_path)
    case[2].write_text(raw)
    with pytest.raises(PreflightError, match="invalid_verified_context"):
        preflight_archive(*case)


def test_explicit_340_archive_is_not_relabelled(tmp_path):
    case = archived_case(tmp_path, version="340")
    with pytest.raises(PreflightError, match="capture_context_mismatch"):
        preflight_archive(*case)


def test_unknown_archived_version_can_be_explicitly_selected_as_341(tmp_path):
    case = archived_case(tmp_path, version=None)
    assert preflight_archive(*case).batch.source_version == "341"


def test_cli_offline_preflight_has_no_settings_or_sql_imports_in_clean_process(tmp_path):
    case = archived_case(tmp_path)
    args = cli_args(case)
    code = """import sys
from scripts.ingest_local_capture import main
assert main(%r)==0
assert not {'app.core.config','app.db.connection','app.db.trial','psycopg'} & set(sys.modules)
""" % args
    env = dict(os.environ, DATABASE_URL="private-invalid-dsn", FRONTEND_ORIGINS="invalid")
    env.pop("AUCTIONATOR_REAL_CAPTURE", None)
    process = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).parents[1],
                             env=env, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    assert report["status"] == "preflight_passed" and not report["target_verified"]
    assert str(tmp_path) not in process.stdout + process.stderr


def test_ingest_does_not_initialize_target_after_failed_preflight(tmp_path, capsys):
    case = archived_case(tmp_path)
    case[2].write_text('private-sentinel-invalid-json')
    assert cli.main(cli_args(case, "ingest") + ["--database-url-env", "PRIVATE_DSN", "--expected-database", "fixture_test"]) == 1
    output = capsys.readouterr()
    assert "invalid_verified_context" in output.err
    assert "private-sentinel" not in output.err and str(tmp_path) not in output.err


@pytest.mark.parametrize("extra", [[], ["--database-url-env", "PRIVATE_DSN"],
                                   ["--database-url-env", "postgresql://secret", "--expected-database", "fixture_test"]])
def test_ingest_requires_explicit_target_selection(tmp_path, extra):
    with pytest.raises(SystemExit) as error:
        cli.main(cli_args(archived_case(tmp_path), "ingest") + extra)
    assert error.value.code == 2
