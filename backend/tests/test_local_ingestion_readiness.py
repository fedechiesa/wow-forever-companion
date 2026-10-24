"""Synthetic offline 5B.1 regressions; no real captures or database required."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from app.db.trial import TrialDatabase
from app.ingestion.adapters.auctionator import AuctionatorAdapter, PartialAdapterResult
from app.ingestion.partial_contracts import PartialBatch, PartialObservation
from app.ingestion.partial_service import PartialIngestionService
from app.local_capture.contracts import Origin, describe
from app.local_capture.decoder import CaptureAdapter, CaptureObservation, MAX_CAPTURE_PRICE
from app.local_capture.readiness import LocalCaptureContext, assess_local_capture
from test_auctionator_cbor import encode, envelope
from test_local_capture import lua


ACQUIRED = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def case(raw=None, *, codec=None):
    raw = lua() if raw is None else raw
    decoded = CaptureAdapter().decode_bytes(raw, serialized_codec=codec)
    metadata = describe(decoded, source_bytes=len(raw), captured_at=ACQUIRED, origin=Origin(),
                        source_version="341", serialized_codec=codec)
    markets = {m.market_key: m.ruleset for m in decoded.native.markets}
    context = dict(contract="local-capture-context-v1", serialized_codec=codec,
                   provenance=dict(source_sha256=sha256(raw).hexdigest(), format_version="341",
                                   source_id="synthetic-history", region="synthetic-eu", dataset="stress_test",
                                   capture_phase="stress_test", market_rulesets=markets,
                                   region_evidence_ref="synthetic#region", market_evidence_ref="synthetic#market",
                                   origin_evidence_ref="synthetic#origin"),
                   market_identities={key: dict(realm={"value": "Synthetic Realm", "evidence_ref": "synthetic#realm"},
                                               faction=None, auction_house_scope="realm",
                                               scope_evidence_ref="synthetic#shared-ah") for key in markets})
    return raw, metadata, context


def assess(raw=None, *, codec=None):
    raw, metadata, context = case(raw, codec=codec)
    return assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))


@pytest.fixture(autouse=True)
def prohibit_database(monkeypatch):
    import psycopg
    connect = MagicMock(side_effect=AssertionError("offline tests must not connect"))
    monkeypatch.setattr(psycopg, "connect", connect)
    yield
    connect.assert_not_called()


@pytest.mark.parametrize("value", [0, 1, 2**31 - 1, 2**31, 2**53 - 1, 2**53, MAX_CAPTURE_PRICE])
@pytest.mark.parametrize("codec", [None, "cbor-definite"])
def test_exact_price_boundaries_preserve_all_evidence(value, codec):
    if codec:
        raw = envelope(encode({b"version": 2, b"123": {b"l": {b"2485": value}, b"h": {b"2485": value},
                                                        b"m": value, b"a": {b"2485": 2}}}))
    else:
        raw = lua(high=value, low=value, minimum=value)
    report = assess(raw, codec=codec)
    facts = CaptureAdapter().decode_bytes(raw, serialized_codec=codec).native.facts
    assert [f.value for f in facts if f.native_field in ("l", "h", "m")] == [value] * 3
    assert json.loads(json.dumps([f.model_dump(mode="json") for f in facts])) == [f.model_dump() for f in facts]
    assert report.numeric_persistence_compatible == (value <= 2**31 - 1)
    assert report.out_of_range_price_fact_count == (3 if value > 2**31 - 1 else 0)
    assert ("price_exceeds_persistence_int32" in report.blocking_reasons) == (value > 2**31 - 1)
    assert not report.import_enabled and not report.analytics_enabled
    assert report.status == "evidence_only"
    if value > 2**31 - 1:
        with pytest.raises(ValueError):
            AuctionatorAdapter().load_bytes(raw, source_id="synthetic", region="synthetic-eu", dataset="real",
                                            serialized_codec=codec)


@pytest.mark.parametrize("value", [-1, 2**63, 2**64 - 1, 2**64])
def test_price_overflow_is_rejected_without_transforming_it(value):
    with pytest.raises(ValueError):
        assess(lua(high=value, minimum=value))


@pytest.mark.parametrize("value", [-1, 2**31, 2**63 - 1, True, 1.5, "2"])
def test_quantities_remain_strict_int32(value):
    common = dict(market_key="PvP", ruleset="PvP", item_key="123", external_item_id="123", key_kind="item",
                  statistic="daily_max_available", scan_day=2485, value=value)
    for model in (CaptureObservation, PartialObservation):
        with pytest.raises(ValueError):
            model(**common)


def test_quantity_ceiling_does_not_become_a_price_or_scan_count():
    report = assess(lua(available=2**31 - 1))
    assert report.numeric_persistence_compatible
    assert report.capture.markets[0].bucket_count == 1
    assert report.capture.markets[0].first_bucket == 2485


@pytest.mark.parametrize("options", [dict(day=str(2**31)), dict(key=str(2**31)), dict(key=f"g:123:{2**31}")])
def test_price_domain_does_not_widen_indices_ids_or_gear_levels(options):
    with pytest.raises(ValueError):
        assess(lua(**options))


@pytest.mark.parametrize("key", ["123", "g:123:20", "gr:123:-5:variant", "p:123"])
def test_complete_variant_keys_survive_preflight(key):
    raw, metadata, context = case(lua(key=key))
    report = assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))
    assert report.capture.market_sha256 == metadata.market_sha256
    decoded = CaptureAdapter().decode_bytes(raw)
    assert {f.item_key for f in decoded.native.facts} == {key}


@pytest.mark.parametrize("field", ["region", "source_id", "dataset", "capture_phase", "source_sha256",
                                  "region_evidence_ref", "market_evidence_ref", "origin_evidence_ref"])
def test_missing_mandatory_context_fails_closed(field):
    raw, metadata, context = case()
    del context["provenance"][field]
    with pytest.raises(ValueError):
        assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))


@pytest.mark.parametrize("source_id", ["", " source ", "source\nother", "PENDIENTE", "unknown", "todo"])
def test_unusable_source_ids_are_not_import_context(source_id):
    _, _, context = case()
    context["provenance"]["source_id"] = source_id
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context)


@pytest.mark.parametrize("update", [{"region": ""}, {"region": "PvP"}, {"region": "unknown"},
                                     {"dataset": "real"}, {"capture_phase": "launch"}])
def test_missing_region_and_contradictory_phase_are_rejected(update):
    _, _, context = case()
    context["provenance"].update(update)
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context)


@pytest.mark.parametrize("update", [{"market_identities": {}}, {"market_identities": {"PvE": {}}},
                                     {"serialized_codec": "libcbor"}])
def test_complete_native_market_identity_and_explicit_codec_required(update):
    _, _, context = case()
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context | update)


@pytest.mark.parametrize("field", ["realm", "faction", "auction_house_scope", "scope_evidence_ref"])
def test_identity_fields_have_no_implicit_defaults(field):
    _, _, context = case()
    del context["market_identities"]["PvP"][field]
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context)


def test_faction_scope_requires_verified_faction_and_realm():
    raw, metadata, context = case()
    identity = context["market_identities"]["PvP"]
    identity["auction_house_scope"] = "faction"
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context)
    identity["faction"] = {"value": "Synthetic Faction", "evidence_ref": "synthetic#faction"}
    assert not assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context)).import_enabled
    identity["realm"]["value"] = "PENDIENTE"
    with pytest.raises(ValueError):
        LocalCaptureContext.model_validate(context)


@pytest.mark.parametrize("field", ["source_sha256", "market_sha256"])
def test_hashes_are_checked_in_full_including_last_digit(field):
    raw, metadata, context = case()
    original = getattr(metadata, field)
    changed = original[:-1] + ("0" if original[-1] != "0" else "1")
    updates = {field: changed}
    if field == "source_sha256":
        updates["capture_id"] = changed
    with pytest.raises(ValueError, match="disagree"):
        assess_local_capture(raw, metadata.model_copy(update=updates), LocalCaptureContext.model_validate(context))


def test_market_hash_counts_and_codec_are_recomputed_from_archived_buffer():
    raw, metadata, context = case()
    valid = LocalCaptureContext.model_validate(context)
    tampered = metadata.markets[0].model_copy(update={"state_sha256": "a" * 64})
    for changed in (metadata.model_copy(update={"markets": [tampered]}),
                    metadata.model_copy(update={"native_fact_count": 999}),
                    metadata.model_copy(update={"selected_source_version": "340"})):
        with pytest.raises(ValueError):
            assess_local_capture(raw, changed, valid)
    with pytest.raises(ValueError, match="codec"):
        assess_local_capture(raw, metadata, valid.model_copy(update={"serialized_codec": "cbor-definite"}))
    context["provenance"]["source_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="provenance"):
        assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))


def test_acquisition_is_preserved_and_never_used_as_native_time():
    report = assess()
    assert report.capture.captured_at == ACQUIRED
    assert report.capture.native_scan_timestamp is None
    assert "scan_day_zero" not in report.context.model_dump()
    assert report.capture.markets[0].first_bucket == report.capture.markets[0].last_bucket == 2485
    assert "imported_at" not in report.model_dump()


def adapted(raw, context):
    p = context["provenance"]
    return AuctionatorAdapter().load_bytes(raw, source_id=p["source_id"], region=p["region"], dataset=p["dataset"],
                                          source_version=p["format_version"], provenance=p)


def test_equivalent_serializations_keep_both_file_hashes_and_reuse_export_state():
    raw, metadata, context = case()
    raw2, metadata2, context2 = case(raw + b'\nCONFIG={x="synthetic"}')
    a, b = adapted(raw, context), adapted(raw2, context2)
    assert metadata.source_sha256 != metadata2.source_sha256
    assert metadata.market_sha256 == metadata2.market_sha256
    assert a.native.state_hash(a.batch) == b.native.state_hash(b.batch)
    assert a.evidence_hash == b.evidence_hash
    report = assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))
    assert assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context)) == report
    assert report.capture == metadata
    assert a.source_hash == metadata.source_sha256 and b.source_hash == metadata2.source_sha256


def test_two_changed_captures_in_same_bucket_are_states_not_two_time_points():
    raw, metadata, context = case()
    raw2, metadata2, context2 = case(lua(high=200, minimum=200))
    a, b = adapted(raw, context), adapted(raw2, context2)
    assert metadata.market_sha256 != metadata2.market_sha256
    assert a.native.state_hash(a.batch) != b.native.state_hash(b.batch)
    assert {o.scan_day for source in (a, b) for o in source.batch.observations if o.scan_day is not None} == {2485}
    assert all(o.scan_day is None for source in (a, b) for o in source.batch.observations if o.statistic == "last_minimum")


def test_source_region_and_dataset_partition_contextual_states_without_rewriting_native_hash():
    raw, metadata, context = case()
    base = adapted(raw, context)
    variants = [{"source_id": "another-history"}, {"region": "synthetic-us"},
                {"dataset": "real", "capture_phase": "launch"}]
    for update in variants:
        changed = context | {"provenance": context["provenance"] | update}
        report = assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(changed))
        source = adapted(raw, changed)
        assert report.capture.market_sha256 == metadata.market_sha256
        assert source.native.state_hash(source.batch) != base.native.state_hash(base.batch)
        assert source.evidence_hash != base.evidence_hash


def test_realm_and_faction_scope_need_a_persistence_design_before_import():
    raw, metadata, context = case()
    original = assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))
    different = json.loads(json.dumps(context))
    different["market_identities"]["PvP"]["realm"]["value"] = "Another Synthetic Realm"
    changed = assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(different))
    assert original.context != changed.context
    assert original.capture.market_sha256 == changed.capture.market_sha256
    # Existing export identity has no realm/faction dimension. Do not silently
    # encode it in source_id, rewrite the native key or claim this is SQL-ready.
    a, b = adapted(raw, context), adapted(raw, different)
    assert a.native.state_hash(a.batch) == b.native.state_hash(b.batch)
    assert all("market_identity_persistence_requires_design" in r.blocking_reasons
               and not r.import_enabled for r in (original, changed))


def test_one_extreme_item_blocks_whole_capture_without_filtering_valid_items():
    first, second = lua(), lua(key="456", high=MAX_CAPTURE_PRICE, minimum=MAX_CAPTURE_PRICE)
    extra_item = second.split(b'version=2,', 1)[1][:-2]
    raw = first[:-2] + b"," + extra_item + b"}}"
    report = assess(raw)
    assert report.capture.item_count == 2 and report.capture.native_fact_count == 6
    assert report.out_of_range_price_fact_count == 2
    assert not report.numeric_persistence_compatible and not report.import_enabled
    assert {f.item_key for f in CaptureAdapter().decode_bytes(raw).native.facts} == {"123", "456"}


def test_simulation_marker_cannot_be_relabelled_as_authentic():
    raw, metadata, context = case(b"-- SIMULATED prices and availability;\n" + lua())
    with pytest.raises(ValueError, match="simulated"):
        assess_local_capture(raw, metadata, LocalCaptureContext.model_validate(context))


@pytest.mark.parametrize("version", ["340", "341"])
@pytest.mark.parametrize("value", [2**31, MAX_CAPTURE_PRICE, -1, True, 1.5])
def test_invalid_model_instances_fail_before_connection_retry_or_failed_run(version, value):
    raw, _, context = case()
    source = adapted(raw, context)
    bad = source.batch.observations[0].model_copy(update={"value": value})
    if version == "340":
        batch = PartialBatch(source_type="auctionator", source_id="synthetic", region="synthetic-eu", dataset="real",
                             observations=[o.model_dump() for o in source.batch.observations])
        source = PartialAdapterResult(batch.model_copy(update={"observations": [bad]}), source.source_hash)
        service = PartialIngestionService()
    else:
        source = replace(source, batch=source.batch.model_copy(update={"observations": [bad]}))
        service = PartialIngestionService(trial_target=object.__new__(TrialDatabase))
    service._connect = MagicMock(side_effect=AssertionError("writer reached"))
    service._record_failure = MagicMock(side_effect=AssertionError("failed run reached"))
    with pytest.raises(ValueError):
        service.import_batch(source)
    service._connect.assert_not_called()
    service._record_failure.assert_not_called()


def test_local_observation_subclass_cannot_bypass_legacy_persistence_limit():
    observation = CaptureObservation(market_key="PvP", ruleset="PvP", item_key="123", external_item_id="123",
                                     key_kind="item", statistic="daily_minimum", scan_day=2485, value=MAX_CAPTURE_PRICE)
    batch = PartialBatch(source_type="auctionator", source_id="synthetic", region="synthetic-eu", dataset="real",
                         observations=[observation])
    assert batch.observations[0].value == MAX_CAPTURE_PRICE  # Original bypass reproduction.
    service = PartialIngestionService()
    service._connect = MagicMock(side_effect=AssertionError("unexpected writer"))
    with pytest.raises(ValueError):
        service.import_batch(PartialAdapterResult(batch, "a" * 64))
    service._connect.assert_not_called()


def test_valid_legacy_batch_is_rebuilt_before_writer_and_extended_guard_stays_closed():
    raw, _, context = case()
    extended = adapted(raw, context)
    service = PartialIngestionService()
    service._import_batch = MagicMock(return_value="synthetic-writer-sentinel")
    with pytest.raises(ValueError, match="TrialDatabase"):
        service.import_batch(extended)
    service._import_batch.assert_not_called()
    legacy = AuctionatorAdapter().load_bytes(raw, source_id="synthetic", region="synthetic-eu")
    assert service.import_batch(legacy) == "synthetic-writer-sentinel"
    rebuilt = service._import_batch.call_args.args[0]
    assert rebuilt == legacy and rebuilt is not legacy and rebuilt.batch is not legacy.batch


def test_offline_readiness_does_not_load_database_config_or_service_modules():
    code = ("import sys; import app.local_capture.readiness; "
            "assert not any(n == 'psycopg' or n.startswith(('app.db', 'app.core.config', "
            "'app.ingestion.partial_service')) for n in sys.modules)")
    run = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
