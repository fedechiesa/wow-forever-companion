from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.auctionator_keys import normalize_item_key
from app.ingestion.fresh_simulator import generate_fresh, simulation_lua
from app.ingestion.partial_contracts import PartialBatch
from app.ingestion.saved_variables import CBORReader, FormatError, LuaReader
from fastapi.testclient import TestClient
from app.main import create_app
from app.ingestion.partial_service import PartialIngestionService

FIXTURE = Path(__file__).parent / "fixtures/auctionator_v8.lua"
CONTEXT = {"source_id": "fixture-account", "region": "wow-forever"}


def fixture_result(**context):
    return AuctionatorAdapter().load(FIXTURE, **(CONTEXT | context))


def test_verified_daily_semantics_and_unknown_fields():
    result = fixture_result()
    points = [o for o in result.batch.observations if o.market_key == "PvE" and o.item_key == "2772"]
    daily = {(o.scan_day, o.statistic): o.value for o in points}
    assert daily[(2500, "daily_minimum")] == 120  # Sparse l falls back to h.
    assert daily[(2501, "daily_minimum")] == 100
    assert daily[(2501, "daily_highest_minimum")] == 160
    assert daily[(2501, "daily_max_available")] == 25
    assert (2500, "daily_max_available") not in daily
    assert daily[(None, "last_minimum")] == 140
    assert result.batch.scan_day_zero is None
    assert {o.ruleset for o in result.batch.observations} == {"PvE", "PvP", "HC", "RP"}


@pytest.mark.parametrize("key,expected", [
    ("002772", ("2772", "2772", "item")),
    ("g:000123:060", ("g:123:60", "123", "gear_level")),
    ("gr:123:of the Bear", ("gr:123:of the Bear", "123", "gear_suffix")),
    ("p:123", ("p:123", "123", "pet")),
])
def test_verified_item_keys(key, expected):
    assert normalize_item_key(key) == expected


@pytest.mark.parametrize("key", ["0", "-1", "2147483648", "item:123", "g:123:x", "gr:123:", "p:123:1", "123:60"])
def test_invalid_item_keys(key):
    with pytest.raises(ValueError):
        normalize_item_key(key)


@pytest.mark.parametrize("raw", [
    b'x = os.execute("bad")', b'x = function() end', b'x = {} x[1] = 1',
    b'x = loadstring("bad")()', b'x = 1+2', b'x = {a=1,a=2}', b'x = 1 x=2',
    b'x = { [true] = 1 }', b'x = "\\999"', b'x = "\\x41"', b'x = {',
    b'x = [[long string]]', b'--[[long comment]]\nx=1', b'x = "unterminated',
])
def test_invalid_or_executable_lua_rejected(raw):
    with pytest.raises(FormatError):
        LuaReader(raw).parse()


def test_lua_bytes_escapes_comments_and_limits():
    assert LuaReader(b'-- comment\nx = "\\000\\255\\n\\\""').parse()["x"] == b'\x00\xff\n"'
    with pytest.raises(FormatError):
        LuaReader(b"x=" + b"{" * 34 + b"}" * 34).parse()
    with pytest.raises(FormatError):
        LuaReader(b" " * (16 * 1024 * 1024 + 1))


def test_libcbor_market_and_per_item_fixtures():
    # Independent definite-map vector following inspected LibCBOR (empty table => array 0).
    realm = bytes.fromhex("a26776657273696f6e026432373732a4616d18646168a164323530301864616c806161a1643235303005")
    decoded = CBORReader(realm).parse()
    assert decoded[b"2772"][b"h"][b"2500"] == 100
    literal = b'"' + b"".join(f"\\{byte:03}".encode() for byte in realm) + b'"'
    raw = b'AUCTIONATOR_PRICE_DATABASE={ ["__dbversion"]=8,["PvE"]=' + literal + b'}'
    with pytest.raises(FormatError, match="explicit"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT)
    result = AuctionatorAdapter().load_bytes(raw, **CONTEXT, allow_libcbor=True)
    assert len(result.batch.observations) == 4
    item = bytes.fromhex("a3616d18646168a164323530301864616c80")
    literal = b'"' + b"".join(f"\\{byte:03}".encode() for byte in item) + b'"'
    raw = b'AUCTIONATOR_PRICE_DATABASE={ ["__dbversion"]=8,["PvE"]={["2772"]=' + literal + b'}}'
    result = AuctionatorAdapter().load_bytes(raw, **CONTEXT, allow_libcbor=True)
    assert len(result.batch.observations) == 3


@pytest.mark.parametrize("raw", [b"", b"\xa1", b"\x7a\xff\xff\xff\xff", b"\xbf\xff", b"\xc0\x01",
                                b"\xfb" + b"\x00" * 8, b"\xa2\x01\x02\x01\x03", b"\x01\x02"])
def test_corrupt_or_unsupported_cbor(raw):
    with pytest.raises(FormatError):
        CBORReader(raw).parse()


def test_cbor_depth_limit():
    with pytest.raises(FormatError, match="complexity"):
        CBORReader(b"\x81" * 34 + b"\x01").parse()


@pytest.mark.parametrize("value", [-1, 2147483648, 1.5, True, "1"])
def test_contract_numeric_bounds(value):
    payload = fixture_result().batch.model_dump()
    payload["observations"][0]["value"] = value
    with pytest.raises(ValidationError):
        PartialBatch.model_validate(payload)


@pytest.mark.parametrize("value", [0, 2147483647])
def test_contract_numeric_edges(value):
    payload = fixture_result().batch.model_dump()
    for o in payload["observations"]:
        o["value"] = value
    assert PartialBatch.model_validate(payload).observations[0].value == value


def test_context_timestamp_validation_and_data_separation():
    assert fixture_result(scan_day_zero="2019-12-31T21:00:00-03:00").batch.scan_day_zero.isoformat() == "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValidationError):
        fixture_result(scan_day_zero="2020-01-01T00:00:00")
    payload = fixture_result().batch.model_dump()
    payload["dataset"] = "simulated"
    with pytest.raises(ValidationError):
        PartialBatch.model_validate(payload)


def test_legacy_market_requires_explicit_mapping():
    raw = FIXTURE.read_bytes().replace(b'"PvE"', b'"Everlook Alliance"')
    with pytest.raises(FormatError, match="mapping"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT)
    result = AuctionatorAdapter().load_bytes(raw, **CONTEXT, market_mapping={"Everlook Alliance": "PvE"})
    assert any(o.market_key == "Everlook Alliance" for o in result.batch.observations)


@pytest.mark.parametrize("old,new", [
    (b'"__dbversion"] = 8', b'"__dbversion"] = 7'),
    (b'"2501"] = 100', b'"2501"] = 900'),
    (b'"m"] = 140', b'"m"] = -1'),
    (b'"m"] = 140', b'"m"] = true'),
    (b'"2501"] = 25', b'"2502"] = 25'),
    (b'"2501"] = 160', b'"tomorrow"] = 160'),
])
def test_invalid_source_semantics(old, new):
    with pytest.raises(ValueError):
        AuctionatorAdapter().load_bytes(FIXTURE.read_bytes().replace(old, new), **CONTEXT)


def test_semantic_hash_ignores_order_and_whitespace():
    result = fixture_result()
    other = AuctionatorAdapter().load_bytes(b"\n" + FIXTURE.read_bytes(), **CONTEXT)
    assert result.source_hash != other.source_hash
    assert result.evidence_hash == other.evidence_hash
    reversed_batch = result.batch.model_copy(update={"observations": list(reversed(result.batch.observations))})
    assert result.evidence_hash == type(result)(reversed_batch, result.source_hash).evidence_hash


def test_simulator_reproducible_profiles_and_absences():
    database, catalog = generate_fresh()
    assert (database, catalog) == generate_fresh()
    assert database != generate_fresh(seed=341)[0]
    assert len(catalog) == 50 and all(item["fictional"] for item in catalog)
    assert len(database["PvE"][catalog[0]["item_key"]]["h"]) == 30
    assert len(database["PvE"][catalog[4]["item_key"]]["h"]) < 30
    assert len(database["PvE"][catalog[5]["item_key"]]["h"]) < 30
    result = AuctionatorAdapter().load_bytes(simulation_lua(database), **CONTEXT, dataset="simulated")
    assert len(result.batch.observations) == 16628
    assert result.batch.source_type == "simulated"
    assert all("auction_count" not in o.model_dump() for o in result.batch.observations)
    with pytest.raises(FormatError, match="simulated"):
        AuctionatorAdapter().load_bytes(simulation_lua(database), **CONTEXT)


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_id", "wrong_kind", "unknown_field", "dated_last", "undated_daily", "negative_day", "float_day", "market_conflict"])
def test_http_rejects_invalid_partial_evidence_before_persistence(monkeypatch, mutation):
    payload = fixture_result().batch.model_dump(mode="json")
    first = payload["observations"][0]
    if mutation == "duplicate":
        payload["observations"].append(dict(first))
    elif mutation == "wrong_id":
        first["external_item_id"] = "123"
    elif mutation == "wrong_kind":
        first["key_kind"] = "pet"
    elif mutation == "unknown_field":
        first["auction_count"] = 1
    elif mutation == "dated_last":
        next(o for o in payload["observations"] if o["statistic"] == "last_minimum")["scan_day"] = 2500
    elif mutation == "undated_daily":
        first["scan_day"] = None
    elif mutation == "negative_day":
        first["scan_day"] = -1
    elif mutation == "float_day":
        first["scan_day"] = 2500.0
    elif mutation == "market_conflict":
        first["ruleset"] = "HC"

    def unexpected(*args):
        pytest.fail("invalid partial evidence reached persistence")

    monkeypatch.setattr(PartialIngestionService, "import_batch", unexpected)
    with TestClient(create_app()) as client:
        assert client.post("/partial/imports", json=payload).status_code == 422
