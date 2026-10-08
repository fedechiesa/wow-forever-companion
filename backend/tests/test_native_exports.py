"""Constructed fixtures from inspected Auctionator code, not Forever exports."""
from dataclasses import replace

from pydantic import ValidationError
import pytest

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.partial_service import PartialIngestionService
from app.ingestion.saved_variables import FormatError


def native_source(high=100, low=None, *, key="00123", day="02500", available=None,
                  a_present=False, prefix=b"", **context):
    lows = '{}' if low is None else '{["' + day + '"]=' + str(low) + '}'
    a = ',a={}' if a_present else ''
    if available is not None:
        a = ',a={["' + day + '"]=' + str(available) + '}'
    raw = ('AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvE"]={version=2,["' + key
           + '"]={l=' + lows + ',h={["' + day + '"]=' + str(high) + '},m=' + str(high) + a + '}}}').encode()
    return AuctionatorAdapter().load_bytes(prefix+raw, source_id=context.pop("source_id", "export-fixture"),
                                          region=context.pop("region", "export-test"), **context)


def test_l_presence_changes_native_identity_but_not_normalized_values():
    absent, present = native_source(), native_source(low=100)
    assert absent.evidence_hash == present.evidence_hash
    assert absent.native.state_hash(absent.batch) != present.native.state_hash(present.batch)
    assert {f.native_field for f in absent.native.facts} == {"h", "m"}
    assert {f.native_field for f in present.native.facts} == {"l", "h", "m"}
    assert absent.native.facts[0].original_item_key == "00123"
    assert absent.native.facts[0].original_day_key == "02500"


def test_absent_empty_and_zero_availability_are_distinct():
    sources = [native_source(), native_source(a_present=True), native_source(available=0)]
    assert len({s.native.state_hash(s.batch) for s in sources}) == 3
    assert "a" not in sources[0].native.markets[0].items[0].fields_present
    assert "a" in sources[1].native.markets[0].items[0].fields_present
    assert not any(f.native_field == "a" for f in sources[1].native.facts)
    assert next(f.value for f in sources[2].native.facts if f.native_field == "a") == 0


def test_empty_items_markets_and_original_keys_survive_manifest():
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["HC"]={},["PvE"]={version=2,["0009"]={l={},h={}},["00123"]={l={},h={},m=0}}}'
    source = AuctionatorAdapter().load_bytes(raw, source_id="shape", region="export-test")
    manifest = source.native.manifest()
    assert manifest["markets"][0] == {"market_key": "HC", "ruleset": "HC", "realm_version": None, "items": []}
    assert {i["original_item_key"] for i in manifest["markets"][1]["items"]} == {"0009", "00123"}


def test_normalized_aliases_in_empty_items_are_rejected():
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvE"]={["01"]={l={},h={}},["1"]={l={},h={},m=0}}}'
    with pytest.raises(ValidationError, match="colliding"):
        AuctionatorAdapter().load_bytes(raw, source_id="shape", region="export-test")


def test_native_coherence_and_projection_checked_before_database(monkeypatch):
    with pytest.raises(ValidationError):
        native_source(low=200)
    source = native_source()
    other = native_source(high=200)
    monkeypatch.setattr("app.ingestion.partial_service.connect", lambda: pytest.fail("invalid evidence reached DB"))
    with pytest.raises(ValueError, match="disagree"):
        PartialIngestionService().import_batch(replace(source, batch=other.batch))


def test_native_structure_limit_applies_before_empty_items_expand(monkeypatch):
    import app.ingestion.adapters.auctionator as module
    monkeypatch.setattr(module, "MAX_OBSERVATIONS", 2)
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvE"]={["1"]={l={},h={}},["2"]={l={},h={}},["3"]={l={},h={},m=0}}}'
    with pytest.raises(FormatError, match="structure construction limit"):
        AuctionatorAdapter().load_bytes(raw, source_id="bounded", region="export-test")


def test_decoded_cbor_and_lua_reuse_same_native_state():
    # Inspected LibCBOR map: m=100, h['2500']=100, l={}.
    item = bytes.fromhex("a3616d18646168a164323530301864616c80")
    literal = b'"' + b"".join(f"\\{byte:03}".encode() for byte in item) + b'"'
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvE"]={version=2,["123"]=' + literal + b'}}'
    cbor = AuctionatorAdapter().load_bytes(raw, source_id="export-fixture", region="export-test", allow_libcbor=True)
    lua = native_source(key="123", day="2500")
    assert cbor.native.input_format == "mixed"
    assert cbor.source_hash != lua.source_hash
    assert cbor.native.state_hash(cbor.batch) == lua.native.state_hash(lua.batch)
