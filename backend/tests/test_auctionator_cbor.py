"""Offline profile regressions. The authentic capture stays outside the repo.

Constructed vectors exercise failure paths, never stand in for authentic input.
Set AUCTIONATOR_REAL_CAPTURE to run the separate SHA-256-pinned capture test.
"""
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path

import pytest

import app.ingestion.adapters.auctionator as adapter_module
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.saved_variables import CBORReader, FormatError, LuaReader, ParseBudget, MAX_BYTES


CONTEXT = dict(source_id="offline-regression", region="unverified-offline-only", dataset="real")
PROFILE = dict(serialized_codec="cbor-definite", source_version="341")


def head(major, size):
    if size < 24:
        return bytes([major * 32 + size])
    for width, info in ((1, 24), (2, 25), (4, 26), (8, 27)):
        if size < 1 << (width * 8):
            return bytes([major * 32 + info]) + size.to_bytes(width, "big")
    raise ValueError("test integer too large")


def encode(value):
    """Small test-only encoder, independent of the production CBOR reader."""
    if value is None or type(value) is bool:
        return {None: b"\xf6", True: b"\xf5", False: b"\xf4"}[value]
    if type(value) is int:
        return head(0, value) if value >= 0 else head(1, -1 - value)
    if isinstance(value, bytes):
        return head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return head(3, len(raw)) + raw
    if isinstance(value, dict):
        return head(5, len(value)) + b"".join(encode(k) + encode(v) for k, v in value.items())
    if isinstance(value, list):
        return head(4, len(value)) + b"".join(encode(v) for v in value)
    raise TypeError(type(value))


def literal(payload):
    return b'"' + b"".join(f"\\{b:03}".encode() for b in payload) + b'"'


def envelope(payload, market="PvP"):
    return (b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,['
            + literal(market.encode()) + b']=' + literal(payload) + b'}')


def item(**updates):
    return {b"l": [], b"h": {b"2485": 100}, b"a": {b"2485": 2}, b"m": 100} | {
        k.encode(): v for k, v in updates.items()
    }


def realm(data=None):
    return {b"version": 2, b"123": item() if data is None else data}


def load(payload, **context):
    return AuctionatorAdapter().load_bytes(envelope(payload), **(CONTEXT | PROFILE | context))


def observation_set(observations):
    return {(o.market_key, o.ruleset, o.item_key, o.external_item_id, o.key_kind,
             o.scan_day, o.statistic, o.value) for o in observations}


def test_profile_is_explicit_and_does_not_claim_a_producer():
    raw = envelope(encode(realm()))
    with pytest.raises(FormatError, match="explicit"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT, source_version="341")
    result = load(encode(realm()))
    assert result.batch.source_version == "341"
    assert result.native.input_format == "cbor_definite"
    assert result.native.decoder_version == "auctionator-v8-v2"
    assert result.batch.source_id == CONTEXT["source_id"]
    assert result.batch.region == CONTEXT["region"]
    assert result.batch.scan_day_zero is None
    assert observation_set(result.native.projected_observations()) == observation_set(result.batch.observations)
    assert Counter(f.native_field for f in result.native.facts) == {"h": 1, "a": 1, "m": 1}


@pytest.mark.parametrize("codec", ["native", "auto", "cbor", "pickle", "libcbor", "", True, {}])
def test_unknown_or_ambiguous_profiles_are_rejected(codec):
    with pytest.raises(FormatError, match="unsupported serialized codec"):
        load(encode(realm()), serialized_codec=codec)


def test_conflicting_selections_are_rejected():
    with pytest.raises(FormatError, match="conflicting"):
        load(encode(realm()), allow_libcbor=True)


@pytest.mark.parametrize("version", [None, True, b"2", 0, 3])
def test_explicit_invalid_realm_versions_are_not_treated_as_absent(version):
    with pytest.raises(FormatError, match="realm database version"):
        load(encode(realm() | {b"version": version}))


@pytest.mark.parametrize("version", ["342", "auto", 341, True, None])
def test_unknown_versions_are_rejected(version):
    with pytest.raises(FormatError, match="source version"):
        load(encode(realm()), source_version=version)


def test_old_libcbor_and_lua_remain_supported_with_same_state():
    # One text-string CBOR vector from the pre-existing 340 tests.
    payload = bytes.fromhex("a26776657273696f6e026432373732a4616d18646168a164323530301864616c806161a1643235303005")
    old = AuctionatorAdapter().load_bytes(envelope(payload), **CONTEXT, allow_libcbor=True)
    generic = load(payload, source_version="340")
    assert old.native.input_format == "libcbor"  # Decoded inner maps are not Lua input.
    assert old.native.decoder_version == "auctionator340-v1"
    assert old.batch == generic.batch
    assert old.native.state_hash(old.batch) == generic.native.state_hash(generic.batch)
    fixture = Path(__file__).parent / "fixtures" / "auctionator_v8.lua"
    lua = AuctionatorAdapter().load(fixture, **CONTEXT)
    assert lua.batch.source_version == "340"
    assert lua.native.input_format == "lua_tables"


def test_actual_mixed_lua_and_cbor_items_are_reported_as_mixed():
    raw = (b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]={version=2,["123"]='
           + literal(encode(item())) + b'}}')
    result = AuctionatorAdapter().load_bytes(raw, **CONTEXT, **PROFILE)
    assert result.native.input_format == "mixed"


def test_new_profiles_are_blocked_before_database_or_failure_recording(monkeypatch):
    from app.ingestion.partial_service import PartialIngestionService

    def unexpected(*args, **kwargs):
        pytest.fail("offline profile reached persistence")

    monkeypatch.setattr(PartialIngestionService, "_record_failure", unexpected)
    for version in ("340", "341"):
        result = load(encode(realm()), source_version=version)
        with pytest.raises(ValueError, match="offline-only"):
            PartialIngestionService(connection_factory=unexpected).import_batch(result)
    # A caller must not turn the new input format into a persistent result by
    # copying only the legacy decoder label onto it.
    result = replace(result, batch=load(encode(realm()), source_version="340").batch,
                     native=result.native.model_copy(update={"decoder_version": "auctionator340-v1"}))
    with pytest.raises(ValueError, match="offline-only"):
        PartialIngestionService(connection_factory=unexpected).import_batch(result)


def test_http_contract_does_not_accept_offline_341(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.ingestion.partial_service import PartialIngestionService

    def unexpected(*args, **kwargs):
        pytest.fail("offline 341 payload reached import service")

    monkeypatch.setattr(PartialIngestionService, "import_batch", unexpected)
    result = load(encode(realm()))
    with TestClient(create_app()) as client:
        assert client.post("/partial/imports", json=result.batch.model_dump(mode="json")).status_code == 422


@pytest.mark.parametrize("availability", ["absent", "empty", "zero"])
@pytest.mark.parametrize("explicit_low", [False, True])
def test_sparse_fields_and_native_low_provenance_survive_cbor(availability, explicit_low):
    data = item(l={b"2485": 90} if explicit_low else [])
    if availability == "absent":
        del data[b"a"]
    else:
        data[b"a"] = {} if availability == "empty" else {b"2485": 0}
    result = load(encode(realm(data)))
    fields = result.native.markets[0].items[0].fields_present
    facts = result.native.facts
    assert ("a" in fields) == (availability != "absent")
    assert any(f.native_field == "a" for f in facts) == (availability == "zero")
    assert any(f.native_field == "l" for f in facts) == explicit_low
    minimum = next(o for o in result.batch.observations if o.statistic == "daily_minimum")
    assert minimum.value == (90 if explicit_low else 100)
    assert observation_set(result.native.projected_observations()) == observation_set(result.batch.observations)


@pytest.mark.parametrize("payload", [
    b"", b"\xa1", b"\xbf\xff", b"\xc0\x01", b"\xd9\x01\x00\xa0", b"\xff",
    b"\x5a\xff\xff\xff\xff", b"\xa2\x01\x02\x01\x03", b"\x01\x02",
    b"\x5c", b"\x9f\x01\xff", b"\xa1\xf5\x00",
])
def test_unsupported_or_malformed_payloads_fail_in_normal_adapter(payload):
    with pytest.raises(ValueError):
        load(payload)


def test_every_truncation_of_a_valid_payload_is_rejected():
    payload = encode(realm())
    for end in range(len(payload)):
        with pytest.raises(ValueError):
            load(payload[:end])


@pytest.mark.parametrize("number", [bytes.fromhex("f93e00"), bytes.fromhex("fa3fc00000"),
                                    bytes.fromhex("fb3ff8000000000000")])
def test_cbor_fractions_are_rejected_without_rounding(number):
    # Replace the m integer in a hand-built item map with float16/32/64 = 1.5.
    payload = (
        b"\xa2" + encode(b"version") + encode(2) + encode(b"123")
        + b"\xa3" + encode(b"l") + b"\x80" + encode(b"h") + encode({b"2485": 2})
        + encode(b"m") + number
    )
    with pytest.raises(FormatError, match="float"):
        load(payload)


@pytest.mark.parametrize("field", ["h", "a", "m"])
@pytest.mark.parametrize("value", [-1, 2147483648, True, None, b"1"])
def test_invalid_prices_and_quantities_are_rejected(field, value):
    update = {field: value if field == "m" else {b"2485": value}}
    with pytest.raises(ValueError):
        load(encode(realm(item(**update))))


def test_duplicates_across_byte_and_text_keys_fail_closed():
    # A CBOR byte key and text key normalize to the same Lua byte key.
    payload = b"\xa2" + encode(b"version") + encode(2) + encode("version") + encode(2)
    with pytest.raises(FormatError, match="duplicate"):
        load(payload)


@pytest.mark.parametrize("data", [
    item(l={b"2485": 101}), item(a={b"2486": 2}), item(h={2485: 100}),
    item(h={b"-1": 100}), item(h={b"2147483648": 100}), item(pending=True),
])
def test_contradictions_or_unsupported_fields_are_rejected(data):
    with pytest.raises(ValueError):
        load(encode(realm(data)))


def test_normalized_item_and_day_aliases_are_rejected():
    for data in (
        {b"version": 2, b"01": item(), b"1": item()},
        realm(item(h={b"02485": 100, b"2485": 100}, a={})),
    ):
        with pytest.raises(ValueError):
            load(encode(data))


@pytest.mark.parametrize("key", [b"123:60", b"item:123", b"g:123:x", b"p:123:1"])
def test_ambiguous_variants_are_rejected(key):
    with pytest.raises(ValueError):
        load(encode({b"version": 2, key: item()}))


def test_variants_and_original_identities_are_preserved():
    keys = (b"00123", b"g:123:060", b"gr:123:suffix", b"p:123")
    result = load(encode({b"version": 2} | {k: item() for k in keys}))
    shapes = result.native.markets[0].items
    assert {s.original_item_key for s in shapes} == {k.decode() for k in keys}
    assert {(s.item_key, s.key_kind) for s in shapes} == {
        ("123", "item"), ("g:123:60", "gear_level"), ("gr:123:suffix", "gear_suffix"), ("p:123", "pet")}


def test_market_mapping_never_guesses_or_remaps_literals():
    raw = envelope(encode(realm()), market="unknown realm")
    with pytest.raises(FormatError, match="mapping"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT, **PROFILE)
    result = AuctionatorAdapter().load_bytes(raw, **CONTEXT, **PROFILE,
                                           market_mapping={"unknown realm": "PvP"})
    assert {o.market_key for o in result.batch.observations} == {"unknown realm"}
    assert {o.ruleset for o in result.batch.observations} == {"PvP"}
    with pytest.raises(FormatError, match="external"):
        load(encode(realm()), market_mapping={"PvP": "PvE"})


def test_resource_limits_remain_enforced(monkeypatch):
    with pytest.raises(FormatError, match="complexity"):
        load(b"\x81" * 34 + b"\x01")
    with pytest.raises(FormatError, match="size limit"):
        CBORReader(b" " * (MAX_BYTES + 1))
    with pytest.raises(FormatError, match="16 MiB"):
        AuctionatorAdapter().load_bytes(b" " * (MAX_BYTES + 1), **CONTEXT, **PROFILE)
    with pytest.raises(FormatError, match="container length"):
        load(b"\xba\xff\xff\xff\xff")
    shared = ParseBudget(100)
    monkeypatch.setattr(adapter_module, "ParseBudget", lambda: shared)
    fields = b",".join(b"[" + literal(str(i).encode()) + b"]=" + literal(encode(item()))
                       for i in range(1, 11))
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]={' + fields + b'}}'
    with pytest.raises(FormatError, match="budget|complexity"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT, **PROFILE)


def test_native_structure_and_observation_limits_apply_to_new_profile(monkeypatch):
    monkeypatch.setattr(adapter_module, "MAX_OBSERVATIONS", 2)
    with pytest.raises(FormatError, match="observation construction limit"):
        load(encode(realm()))
    with pytest.raises(FormatError, match="structure construction limit"):
        load(encode({b"version": 2, b"1": {b"l": [], b"h": []}, b"2": item()}))


def test_authentic_341_capture_offline():
    location = os.environ.get("AUCTIONATOR_REAL_CAPTURE")
    if not location:
        pytest.skip("Private capture not configured; constructed vectors are not authentic evidence")
    path = Path(location)
    assert path.is_file(), "Configured authentic capture is missing"
    raw = path.read_bytes()
    expected_hash = "7d5cf3db48fa78ab19d3a359557470752e634da743cebe42833fb07c10aa458b"
    assert len(raw) == 4701 and sha256(raw).hexdigest() == expected_hash
    result = AuctionatorAdapter().load(path, **CONTEXT, **PROFILE)
    assert result.source_hash == expected_hash
    assert result.raw_reference == str(path)
    assert result.batch.source_version == "341"
    assert result.native.input_format == "cbor_definite"
    assert result.batch.scan_day_zero is None
    assert len(result.native.markets) == 1
    market = result.native.markets[0]
    assert (market.market_key, market.ruleset, market.realm_version) == ("PvP", "PvP", 2)
    expected = {"2589": (2000100, 26), "4604": (100, 6), "117": (100100, 1),
                "6303": (100, 16), "59": (10100, 1), "2447": (100, 7), "1372": (5000100, 1)}
    assert len(market.items) == len(expected) == 7
    assert {s.original_item_key for s in market.items} == set(expected)
    assert all(s.fields_present == ["a", "h", "l", "m"] and s.item_key == s.original_item_key
               and s.external_item_id == s.item_key and s.key_kind == "item" for s in market.items)
    payload = LuaReader(raw).parse()["AUCTIONATOR_PRICE_DATABASE"][b"PvP"]
    decoded = CBORReader(payload).parse()
    # Re-encode independently specified values, preserving only the map order
    # observed in the file. This checks every payload byte without storing it.
    reconstructed = {}
    for key in decoded:
        if key == b"version":
            reconstructed[key] = 2
        else:
            price, quantity = expected[key.decode()]
            reconstructed[key] = {b"a": {b"2485": quantity}, b"l": [],
                                  b"h": {b"2485": price}, b"m": price}
    assert encode(reconstructed) == payload
    facts = set()
    observations = set()
    for key, (price, quantity) in expected.items():
        assert decoded[key.encode()] == {b"l": {}, b"h": {b"2485": price}, b"a": {b"2485": quantity}, b"m": price}
        for field, stat, value, day in (("h", "daily_highest_minimum", price, 2485),
                                       ("a", "daily_max_available", quantity, 2485),
                                       ("m", "last_minimum", price, None)):
            facts.add((key, field, day, value, "2485" if day is not None else None))
            observations.add(("PvP", "PvP", key, key, "item", day, stat, value))
        observations.add(("PvP", "PvP", key, key, "item", 2485, "daily_minimum", price))
    assert len(result.native.facts) == 21
    assert {(f.original_item_key, f.native_field, f.scan_day, f.value, f.original_day_key)
            for f in result.native.facts} == facts
    assert len(result.batch.observations) == 28
    assert observation_set(result.batch.observations) == observations
    assert observation_set(result.native.projected_observations()) == observations
    assert len(result.native.state_hash(result.batch)) == 64
    assert sha256(path.read_bytes()).hexdigest() == expected_hash
