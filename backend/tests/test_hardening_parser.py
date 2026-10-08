from decimal import Decimal

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

import app.ingestion.adapters.auctionator as adapter_module
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.fresh_simulator import generate_fresh, simulation_lua
from app.ingestion.partial_contracts import PartialBatch
from app.ingestion.saved_variables import CBORReader, FormatError, LuaReader, ParseBudget
from app.main import create_app
from tests.test_auctionator import CONTEXT, FIXTURE, fixture_result


@pytest.mark.parametrize("key", ["PvE", "PvP", "HC", "RP"])
def test_literal_rulesets_cannot_be_remapped_in_lua_or_http(key):
    for mapping in ({key: "HC"}, {key: key}):
        with pytest.raises(FormatError, match="external"):
            fixture_result(market_mapping=mapping)
    payload = fixture_result().batch.model_dump(mode="json")
    next(o for o in payload["observations"] if o["market_key"] == key)["ruleset"] = "RP" if key != "RP" else "PvE"
    with pytest.raises(ValidationError, match="literal market"):
        PartialBatch.model_validate(payload)
    with TestClient(create_app()) as client:
        assert client.post("/partial/imports", json=payload).status_code == 422


@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf", b" \r\n\t", b"\xef\xbb\xbf \r\n", b" \t\xef\xbb\xbf\n"])
def test_simulation_marker_bom_and_whitespace(prefix):
    database, _ = generate_fresh(items=1, days=1, markets=("PvE",))
    raw = prefix + simulation_lua(database)
    with pytest.raises(FormatError, match="dataset=simulated"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT)
    assert AuctionatorAdapter().load_bytes(raw, **CONTEXT, dataset="simulated").batch.dataset == "simulated"


@pytest.mark.parametrize("literal", [b"100.5", b"0.3333333333333333", b"1e-1"])
def test_legitimate_modernah_fractional_prices_explicitly_rejected(literal):
    # ModernAH GetInfo divides stack buyout by count, with no floor.
    raw = FIXTURE.read_bytes().replace(b'"m"] = 140', b'"m"] = ' + literal)
    with pytest.raises(FormatError, match="non-integer.*no rounding"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT)
    assert LuaReader(b"x=" + literal).parse()["x"] == Decimal(literal.decode())


def test_libcbor_fractional_price_rejection():
    with pytest.raises(FormatError, match="float"):
        CBORReader(bytes.fromhex("f93e00")).parse()  # Exactly 1.5, still unsupported.


def test_decimal_exponent_out_of_range_is_a_format_error():
    with pytest.raises(FormatError):
        LuaReader(b"x=1e999999999999999999999999").parse()


def test_construction_limit_precedes_next_observation_or_decode(monkeypatch):
    monkeypatch.setattr(adapter_module, "MAX_OBSERVATIONS", 3)
    actual = adapter_module.PartialObservation
    built = []

    def counted(**fields):
        built.append(fields)
        return actual(**fields)

    monkeypatch.setattr(adapter_module, "PartialObservation", counted)
    with pytest.raises(FormatError, match="construction limit"):
        fixture_result()
    assert len(built) == 3


def test_cbor_declared_container_rejected_before_children():
    reader = CBORReader(b"\xa5" + b"\x01\x02" * 5, budget=ParseBudget(3))
    with pytest.raises(FormatError, match="remaining parsing budget"):
        reader.parse()
    assert reader.pos == 1  # Header only, none of the declared children decoded.


def test_shared_budget_is_not_reset_per_cbor_string(monkeypatch):
    shared = ParseBudget(100)
    monkeypatch.setattr(adapter_module, "ParseBudget", lambda: shared)
    # Lua parsing consumes part of the SAME budget used by every decoded item.
    item = bytes.fromhex("a3616d18646168a164323530301864616c80")
    literal = b'"' + b"".join(f"\\{byte:03}".encode() for byte in item) + b'"'
    fields = b",".join(b'["' + str(i).encode() + b'"]=' + literal for i in range(1, 11))
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvE"]={' + fields + b'}}'
    with pytest.raises(FormatError, match="parsing budget|complexity"):
        AuctionatorAdapter().load_bytes(raw, **CONTEXT, allow_libcbor=True)
    assert shared.remaining < 20


def test_lua_budget_counts_implicit_and_named_keys_early():
    reader = LuaReader(b"x={1,2,3,4,5}", budget=ParseBudget(5))
    with pytest.raises(FormatError, match="complexity"):
        reader.parse()
    assert reader.pos < len(reader.raw)
