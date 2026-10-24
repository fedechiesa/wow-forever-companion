"""Synthetic verified economic identity and pre-writer lineage checks."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from app.db.trial import TrialDatabase
from app.ingestion.local_lineage import VerifiedLocalContext, local_export_identity, prepare_local_capture
from app.ingestion.partial_service import PartialIngestionService
from test_local_capture import lua
from test_local_ingestion_readiness import case


def local_source(*, raw=None, economy="synthetic-realm-a", source_id="synthetic-observer-a",
                 dataset="stress_test", scope="shared", faction=None, region="synthetic-eu"):
    raw, metadata, old = case(raw)
    p = old["provenance"] | dict(source_id=source_id, region=region, dataset=dataset,
                                 capture_phase=dataset if dataset != "simulated" else "simulated")
    context = VerifiedLocalContext(
        contract="verified-local-capture-v1", provenance=p, serialized_codec=None,
        market_identities={key: dict(economy={"value": economy, "evidence_ref": "fixture#economy"},
                                      realm={"value": economy, "evidence_ref": "fixture#realm"},
                                      faction=({"value": faction, "evidence_ref": "fixture#faction"} if faction else None),
                                      auction_house_scope=scope, scope_evidence_ref="fixture#ah-scope")
                           for key in p["market_rulesets"]},
    )
    return prepare_local_capture(raw, metadata, context)


def test_two_realms_with_native_pvp_are_distinct_economies_and_states():
    a, b = local_source(), local_source(economy="synthetic-realm-b")
    assert a.local_capture.context.identities() != b.local_capture.context.identities()
    assert a.local_capture.metadata.market_sha256 == b.local_capture.metadata.market_sha256
    assert local_export_identity(a)[0] != local_export_identity(b)[0]


def test_two_observers_share_economy_and_state_but_keep_their_attestations():
    a, b = local_source(), local_source(source_id="synthetic-observer-b")
    assert a.local_capture.context.identities() == b.local_capture.context.identities()
    assert local_export_identity(a)[0] == local_export_identity(b)[0]
    assert a.native.provenance.source_id != b.native.provenance.source_id
    assert local_export_identity(a)[1]["provenance"] != local_export_identity(b)[1]["provenance"]


def test_lifecycle_datasets_have_distinct_verified_economies():
    sources = [local_source(dataset=d) for d in ("stress_test", "launch", "simulated")]
    assert len({local_export_identity(s)[0] for s in sources}) == 3
    assert {s.batch.dataset for s in sources} == {"stress_test", "launch", "simulated"}


@pytest.mark.parametrize("region", [None, "", "unknown", "PvP", "PENDIENTE"])
def test_region_unknown_never_becomes_an_importable_economy(region):
    with pytest.raises(ValueError):
        local_source(region=region)


def test_shared_ah_is_one_economy_and_partitioned_factions_are_distinct():
    shared = local_source()
    a = local_source(scope="faction", faction="Synthetic Alliance")
    b = local_source(scope="faction", faction="Synthetic Horde")
    assert len({local_export_identity(s)[0] for s in (shared, a, b)}) == 3
    assert shared.local_capture.context.identities()["PvP"]["faction"] is None
    with pytest.raises(ValueError, match="faction AH"):
        local_source(scope="faction")
    with pytest.raises(ValueError, match="shared AH"):
        local_source(faction="Synthetic Alliance")


def test_equivalent_originals_and_acquisition_times_share_economic_state():
    a, b = local_source(), local_source(raw=lua() + b"\nSYNTHETIC_CONFIG={x=1}")
    assert a.source_hash != b.source_hash
    assert a.local_capture.metadata.market_sha256 == b.local_capture.metadata.market_sha256
    assert local_export_identity(a)[0] == local_export_identity(b)[0]
    changed_metadata = b.local_capture.metadata.model_copy(update={
        "captured_at": b.local_capture.metadata.captured_at + timedelta(hours=1)})
    b = replace(b, local_capture=b.local_capture.model_copy(update={"metadata": changed_metadata}))
    assert local_export_identity(a)[0] == local_export_identity(b)[0]


def test_same_bucket_can_contain_distinct_immutable_states_without_new_day():
    a, b = local_source(), local_source(raw=lua(high=200, minimum=200))
    assert local_export_identity(a)[0] != local_export_identity(b)[0]
    assert {o.scan_day for s in (a,b) for o in s.batch.observations if o.scan_day is not None} == {2485}
    assert a.local_capture.metadata.native_scan_timestamp is b.local_capture.metadata.native_scan_timestamp is None


@pytest.mark.parametrize("price", [2**31, 2**53, 2**63-1])
def test_large_prices_block_entire_preparation_before_any_service(price, monkeypatch):
    connect = MagicMock(side_effect=AssertionError("unexpected SQL"))
    monkeypatch.setattr("psycopg.connect", connect)
    with pytest.raises(ValueError, match="price_exceeds_persistence_int32"):
        local_source(raw=lua(high=price, minimum=price))
    connect.assert_not_called()


@pytest.mark.parametrize("field,value", [("source_sha256", "a"*64), ("market_sha256", "b"*64),
                                        ("native_fact_count", 99)])
def test_forged_lineage_fails_before_connection_or_failed_run(field, value):
    source = local_source()
    source = replace(source, local_capture=source.local_capture.model_copy(update={
        "metadata": source.local_capture.metadata.model_copy(update={field: value})}))
    target = object.__new__(TrialDatabase)
    target.connection = MagicMock(side_effect=AssertionError("writer reached"))
    service = PartialIngestionService(trial_target=target)
    service._record_failure = MagicMock()
    with pytest.raises(ValueError):
        service.import_batch(source)
    target.connection.assert_not_called()
    service._record_failure.assert_not_called()


def test_local_path_cannot_bypass_trial_or_use_arbitrary_factory():
    source = local_source()
    factory = MagicMock()
    with pytest.raises(ValueError, match="TrialDatabase"):
        PartialIngestionService(factory).import_batch(source)
    factory.assert_not_called()


@pytest.mark.parametrize("dataset", ["launch", "stress_test", "simulated"])
def test_341_without_local_identity_cannot_reach_a_writer(dataset):
    source = replace(local_source(dataset=dataset), local_capture=None)
    target = object.__new__(TrialDatabase)
    target.connection = MagicMock()
    with pytest.raises(ValueError, match="341 requires"):
        PartialIngestionService(trial_target=target).import_batch(source)
    target.connection.assert_not_called()


def test_missing_006_fails_before_first_insert_or_sequence():
    source = local_source()
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = None
    for status in ("completed", "failed"):
        connection.reset_mock()
        with pytest.raises(ValueError, match="verified local lineage"):
            PartialIngestionService()._create_run(connection, source, status)
        assert connection.execute.call_count == 1
        assert "006_verified_local_lineage.sql" in connection.execute.call_args.args[0]


def test_no_defaults_or_native_label_alias_collisions_in_verified_identity():
    source = local_source()
    data = source.local_capture.context.model_dump()
    for field in ("economy", "faction", "realm", "auction_house_scope", "scope_evidence_ref"):
        bad = source.local_capture.context.model_dump()
        del bad["market_identities"]["PvP"][field]
        with pytest.raises(ValueError):
            VerifiedLocalContext.model_validate(bad)
    data["provenance"]["market_rulesets"]["Alias"] = "PvP"
    data["market_identities"]["Alias"] = data["market_identities"]["PvP"]
    with pytest.raises(ValueError, match="reconciliation"):
        VerifiedLocalContext.model_validate(data)
