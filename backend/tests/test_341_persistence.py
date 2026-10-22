"""Synthetic attestation and pre-writer regressions; no database connections."""
from dataclasses import replace
from hashlib import sha256
import json
from unittest.mock import MagicMock

import pytest

from app.db.trial import TrialDatabase
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.capture_provenance import CaptureProvenance, load_capture_provenance
from app.ingestion.partial_service import PartialIngestionService
from scripts import import_auctionator as cli
from tests.test_auctionator_cbor import encode, envelope, realm, item


CONTEXT = dict(source_id="stress-synthetic", region="synthetic-eu", dataset="stress_test",
               source_version="341", serialized_codec="cbor-definite")


def synthetic_source(high=100, *, key=b"123", phase="stress_test", source_id="stress-synthetic", prefix=b"", **updates):
    raw = prefix + envelope(encode({b"version": 2, key: item(h={b"2485": high}, m=high)}))
    dataset = {"stress_test": "stress_test", "launch": "real", "simulated": "simulated"}[phase]
    context = CONTEXT | {"source_id": source_id, "dataset": dataset}
    metadata = dict(source_sha256=sha256(raw).hexdigest(), format_version="341", source_id=source_id,
                    region=context["region"], dataset=dataset, capture_phase=phase, market_rulesets={"PvP": "PvP"},
                    region_evidence_ref="synthetic-fixture#region", market_evidence_ref="synthetic-fixture#market",
                    origin_evidence_ref="synthetic-fixture#origin", codec_producer="unverified") | updates
    return AuctionatorAdapter().load_bytes(raw, **context, provenance=metadata)


def metadata():
    return synthetic_source().native.provenance.model_dump()


@pytest.mark.parametrize("region", ["", "unknown", "unverified-offline-only", "PENDIENTE", "PvP", "es MX", " EU", "EU\n"])
def test_region_requires_explicit_identifier_and_evidence(region):
    with pytest.raises(ValueError):
        CaptureProvenance.model_validate(metadata() | {"region": region})


@pytest.mark.parametrize("field", ["region", "region_evidence_ref", "market_evidence_ref", "origin_evidence_ref", "source_sha256"])
def test_missing_metadata_is_rejected(field):
    data = metadata()
    del data[field]
    with pytest.raises(ValueError):
        CaptureProvenance.model_validate(data)


@pytest.mark.parametrize("updates", [{"version": True}, {"version": "1"}, {"region_evidence_ref": "PENDIENTE"},
                                    {"capture_addon_version": {"value": "341", "evidence_ref": "PENDIENTE"}}])
def test_placeholder_references_and_loose_versions_are_rejected(updates):
    with pytest.raises(ValueError):
        CaptureProvenance.model_validate(metadata() | updates)


@pytest.mark.parametrize("updates", [
    {"dataset": "real"}, {"capture_phase": "launch"}, {"format_version": "340"},
    {"codec_producer": "C_EncodingUtil"}, {"codec_producer_evidence_ref": "inferred-only"},
    {"capture_addon_version": {"value": "340", "evidence_ref": "capture-note"}},
    {"market_rulesets": {"PvP": "PvE"}},
])
def test_contradictory_attestations_are_rejected(updates):
    with pytest.raises(ValueError):
        CaptureProvenance.model_validate(metadata() | updates)


@pytest.mark.parametrize("updates", [
    {"region": "synthetic-us"}, {"source_id": "other-source"}, {"source_sha256": "a" * 64},
    {"market_rulesets": {"PvE": "PvE"}},
])
def test_metadata_must_bind_to_the_actual_input_and_context(updates):
    with pytest.raises(ValueError, match="context"):
        AuctionatorAdapter().load_bytes(envelope(encode(realm())), **CONTEXT, provenance=metadata() | updates)


def test_installed_observation_is_not_promoted_to_capture_confirmation():
    source = synthetic_source(installed_client_build={"value": "1.60.1.70532", "evidence_ref": "local-pe"},
                              installed_addon_version={"value": "341", "evidence_ref": "local-toc"})
    p = source.native.manifest()["provenance"]
    assert p["capture_client_build"] is None and p["capture_addon_version"] is None
    assert p["codec_producer"] == "unverified"
    assert p["installed_client_build"]["value"] == "1.60.1.70532"
    assert "source_sha256" not in p


def test_equivalent_input_bytes_reuse_canonical_context():
    a, b = synthetic_source(), synthetic_source(prefix=b"\n")
    assert a.source_hash != b.source_hash
    assert a.native.state_hash(a.batch) == b.native.state_hash(b.batch)


def test_new_profile_cannot_use_default_or_arbitrary_connection_factory():
    source = synthetic_source()
    factory = MagicMock()
    with pytest.raises(ValueError, match="TrialDatabase"):
        PartialIngestionService(factory).import_batch(source)
    factory.assert_not_called()
    with pytest.raises(ValueError, match="TrialDatabase"):
        PartialIngestionService(trial_target=factory)


def test_invalid_metadata_is_revalidated_before_any_writer():
    source = synthetic_source()
    target = object.__new__(TrialDatabase)
    target.connection = MagicMock(side_effect=AssertionError("unexpected writer"))
    service = PartialIngestionService(trial_target=target)
    malformed = source.native.provenance.model_copy(update={"capture_phase": "launch"})
    with pytest.raises(ValueError):
        service.import_batch(replace(source, native=source.native.model_copy(update={"provenance": malformed})))
    with pytest.raises(ValueError, match="provenance"):
        service.import_batch(replace(source, native=source.native.model_copy(update={"provenance": None})))
    target.connection.assert_not_called()


@pytest.mark.parametrize("missing", [True, False])
def test_unprepared_schema_cannot_advance_a_run_sequence(missing):
    import psycopg
    c = MagicMock()
    if missing:
        c.execute.return_value.fetchone.return_value = None
    else:
        c.execute.side_effect = psycopg.errors.UndefinedTable("private-test-secret")
    source = synthetic_source()
    with pytest.raises(ValueError, match="not prepared") as error:
        PartialIngestionService()._create_run(c, source, "completed")
    assert "private-test-secret" not in str(error.value)
    assert c.execute.call_count == 1 and "INSERT" not in c.execute.call_args.args[0]


def test_private_metadata_loader_rejects_duplicates_and_large_files(tmp_path):
    p = tmp_path / "context.json"
    p.write_text('{"region":"synthetic-eu","region":"synthetic-us"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_capture_provenance(p)
    p.write_bytes(b" " * 65537)
    with pytest.raises(ValueError, match="64 KiB"):
        load_capture_provenance(p)


def extended_args(p):
    return ["synthetic.lua", "--source-id", "stress-synthetic", "--region", "synthetic-eu", "--dataset", "stress_test",
            "--source-version", "341", "--serialized-codec", "cbor-definite", "--provenance-file", str(p)]


def test_extended_cli_requires_trial_before_loading_any_file(monkeypatch):
    target = MagicMock()
    monkeypatch.setattr(cli, "TrialDatabase", target)
    with pytest.raises(SystemExit) as error:
        cli.main(extended_args("missing.json"))
    assert error.value.code == 2
    target.assert_not_called()


def test_invalid_context_fails_before_target_and_is_sanitized(tmp_path, monkeypatch, capsys):
    target = MagicMock()
    monkeypatch.setattr(cli, "TrialDatabase", target)
    p = tmp_path / "context.json"
    p.write_text(json.dumps(metadata() | {"region_evidence_ref": "", "origin_evidence_ref": "private-test-secret"}), encoding="utf-8")
    args = extended_args(p) + ["--trial", "--database-url-env", "NOT_READ", "--expected-database", "synthetic_test"]
    assert cli.main(args) == 1
    target.assert_not_called()
    assert "private-test-secret" not in capsys.readouterr().err


def test_cli_and_metadata_must_agree_before_target(tmp_path, monkeypatch):
    target = MagicMock()
    monkeypatch.setattr(cli, "TrialDatabase", target)
    p = tmp_path / "context.json"
    p.write_text(json.dumps(metadata() | {"region": "synthetic-us"}), encoding="utf-8")
    assert cli.main(extended_args(p) + ["--trial", "--database-url-env", "NOT_READ",
                                      "--expected-database", "synthetic_test"]) == 1
    target.assert_not_called()
