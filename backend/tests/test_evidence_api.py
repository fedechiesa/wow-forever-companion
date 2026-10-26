"""Synthetic public contracts. No SQL, private capture or source path exposure."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.main import create_app
from app.api import evidence
from app.ingestion.local_readers import EvidenceSchemaUnavailable
from test_market_validation import assert_openapi_json


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(evidence, "connect", MagicMock(side_effect=AssertionError("unit test reached SQL")))
    return TestClient(create_app())


def market(**updates):
    return dict(id=2**53+1, dataset="simulated", economy="synthetic-economy", region="synthetic-eu",
                native_label="PvP", ruleset="PvP", auction_house_scope="shared", faction=None) | updates


@pytest.mark.parametrize("query", ["", "dataset=real", "dataset=launch&limit=0", "dataset=simulated&limit=101",
                                 "dataset=simulated&offset=-1", "dataset=simulated&offset=2147483648",
                                 "dataset=simulated&source_id=private", "dataset=simulated&dataset=launch"])
def test_invalid_filters_do_not_connect(client, query):
    assert client.get("/evidence/v2/markets?"+query).status_code == 422
    evidence.connect.assert_not_called()


@pytest.mark.parametrize("identifier", ["0", "-1", "9223372036854775808", "abc"])
def test_invalid_market_identifiers(client, identifier):
    assert client.get(f"/evidence/v2/markets/{identifier}/states?dataset=simulated").status_code == 422
    evidence.connect.assert_not_called()


def test_pagination_bigint_ids_and_generated_contract(client, monkeypatch):
    rows = [market(), market(id=2**53+2)]
    read = MagicMock(return_value=rows)
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_markets", read)
    response = client.get("/evidence/v2/markets?dataset=simulated&limit=1&offset=3")
    data = response.json()
    assert response.status_code == 200 and data["has_more"] and len(data["items"]) == 1
    assert data["items"][0]["id"] == "9007199254740993"
    read.assert_called_once_with("simulated", limit=2, offset=3)
    document = client.get("/openapi.json").json()
    assert_openapi_json(data, document["components"]["schemas"]["EvidenceMarketsPage"], document)


@pytest.mark.parametrize("label", ["C:\\private\\Account\\user", "/home/private", "Account Alice", "mail@example.com", "bad\nlabel"])
def test_private_looking_identity_fails_closed(client, monkeypatch, label):
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_markets", lambda *a, **k: [market(economy=label)])
    response = client.get("/evidence/v2/markets?dataset=simulated")
    assert response.status_code == 409 and "private" not in response.text and "Alice" not in response.text


def test_unexpected_private_columns_never_cross_public_contract(client, monkeypatch):
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_markets", lambda *a, **k: [market(source_id="PRIVATE_SENTINEL")])
    response = client.get("/evidence/v2/markets?dataset=simulated")
    assert response.status_code == 409 and "PRIVATE_SENTINEL" not in response.text


@pytest.mark.parametrize("low,high,expected,origin", [(0, 100, 0, "l"), (None, 0, 0, "h_fallback"), (None, None, None, None)])
def test_native_projection_preserves_zero_and_fallback(client, monkeypatch, low, high, expected, origin):
    row = dict(item_key="g:123:60", external_item_id="123", key_kind="gear_level", scan_day=2485,
               native_l=low, native_h=high, native_a=None, native_m=None, native_fact_count=1)
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_facts", lambda *a, **k: [row])
    response = client.get("/evidence/v2/markets/1/states/2/facts?dataset=simulated")
    assert response.status_code == 200
    data = response.json()["items"][0]
    assert data["minimum_copper"] == expected and data["minimum_origin"] == origin


def test_undated_m_is_not_assigned_to_bucket(client, monkeypatch):
    row = dict(item_key="123", external_item_id="123", key_kind="item", scan_day=None,
               native_l=None, native_h=None, native_a=None, native_m=2147483647, native_fact_count=1)
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_facts", lambda *a, **k: [row])
    result = client.get("/evidence/v2/markets/1/states/2/facts?dataset=simulated").json()["items"][0]
    assert result["scan_day"] is None and result["minimum_copper"] is None and result["native_m"] == 2147483647


@pytest.mark.parametrize("bad", [2147483648,1.5,True,-1])
def test_incompatible_public_prices_are_rejected(client, monkeypatch, bad):
    row = dict(item_key="123",external_item_id="123",key_kind="item",scan_day=None,
               native_l=None,native_h=None,native_a=None,native_m=bad,native_fact_count=1)
    monkeypatch.setattr(evidence.LocalEvidenceReader,"web_facts",lambda *a,**k:[row])
    assert client.get("/evidence/v2/markets/1/states/2/facts?dataset=simulated").status_code==409


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_only_get_routes(client, method):
    assert client.request(method, "/evidence/v2/markets?dataset=simulated").status_code == 405
    evidence.connect.assert_not_called()


@pytest.mark.parametrize("error,status", [(ValueError("private-secret"),404), (psycopg.OperationalError("private-secret"),503), (EvidenceSchemaUnavailable("private-secret"),503)])
def test_errors_are_sanitized(client, monkeypatch, error, status):
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(evidence.LocalEvidenceReader, "web_markets", fail)
    response = client.get("/evidence/v2/markets?dataset=simulated")
    assert response.status_code == status and "private-secret" not in response.text
