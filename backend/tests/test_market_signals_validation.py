"""FastAPI validation, error mapping and served OpenAPI, without database access."""
from decimal import Decimal
import builtins

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.main import create_app
from app.market.errors import SeriesIntegrityError, SeriesNotFound, WindowError
from app.market.signal_contracts import MarketSignalsResponse, SignalParameters
from app.market import signal_contracts
from app.market.signals import evaluate_signals
from tests.test_market_signals import analysis
from tests.test_market_signals import ZERO_SLOPE_COUNTEREXAMPLE
from tests.test_market_validation import BASE, assert_openapi_json


@pytest.mark.parametrize("updates", [
    {"series_mode": "export"}, {"export_id": 1}, {"item_key": "00123"}, {"size": 367},
    {"temporal_basis": "2020-01-01"}, {"source_id": " wrong"}, {"source_type": "other"},
    {"window_type": "calendar_days", "size": None, "days": 7},
    {"window_type": "index_range", "size": None, "start_day": 1, "end_day": 367},
    {"min_history_observations": 2}, {"min_trend_observations": 2}, {"deviation_threshold_pct": "0"},
    {"trend_threshold_pct": "NaN"}, {"min_price_coverage": "Infinity"}, {"min_price_coverage": "1.1"},
    {"min_index_coverage": "0"}, {"max_latest_price_lag": -1}, {"require_native_l": "sometimes"},
    {"min_trend_slope_copper_per_scan_index": "-1"}, {"unknown_threshold": 1},
])
def test_signals_reject_invalid_requests_before_database(monkeypatch, updates):
    monkeypatch.setattr("app.market.service.connect", lambda: pytest.fail("invalid request reached PostgreSQL"))
    params = {k: v for k, v in (BASE | updates).items() if v is not None}
    with TestClient(create_app()) as client:
        response = client.get("/market/signals", params=params)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("error,status", [(SeriesNotFound("missing"), 404), (SeriesIntegrityError("bad"), 409),
                                        (WindowError("bad window"), 422), (psycopg.OperationalError("secret connection details"), 503)])
def test_signals_use_existing_domain_errors(monkeypatch, error, status):
    def fail(*args):
        raise error
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", fail)
    with TestClient(create_app()) as client:
        response = client.get("/market/signals", params=BASE)
    assert response.status_code == status
    assert "secret connection details" not in response.text


def test_query_parameters_reach_pure_rules_with_decimal_exactness(monkeypatch):
    calls = []
    def inspect(self, request):
        calls.append(request)
        assert request.window.size == 8
        assert request.selector.item_key == "123"
        return analysis([100] * 7 + [80])
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", inspect)
    with TestClient(create_app()) as client:
        response = client.get("/market/signals", params=BASE | {
            "size": 8, "deviation_threshold_pct": "20.00000000000000000000000000000000000001",
            "min_trend_slope_copper_per_scan_index": "1e-50", "require_native_l": "false",
        })
        document = client.get("/openapi.json").json()
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["price_deviation"]["direction"] == "no_significant_deviation"
    assert result["parameters"]["deviation_threshold_pct"] == "20.00000000000000000000000000000000000001"
    assert result["parameters"]["min_trend_slope_copper_per_scan_index"] == "0." + "0" * 49 + "1"
    assert len(calls) == 1
    schema = document["paths"]["/market/signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert_openapi_json(result, schema, document)
    names = {p["name"] for p in document["paths"]["/market/signals"]["get"]["parameters"]}
    assert set(SignalParameters.model_fields) <= names
    assert MarketSignalsResponse.model_validate(result).parameters.deviation_threshold_pct == Decimal(result["parameters"]["deviation_threshold_pct"])


@pytest.mark.parametrize("values", [[0] * 8, [0] * 7 + [1], [], [100] * 7 + [80], [2147483647] * 7 + [2147483646]])
def test_all_signal_states_conform_to_served_openapi(values):
    result = evaluate_signals(analysis(values), SignalParameters()).model_dump(mode="json")
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
    schema = document["paths"]["/market/signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert_openapi_json(result, schema, document)


def test_evidence_contract_rejects_inconsistent_status():
    result = evaluate_signals(analysis([100] * 8), SignalParameters())
    evidence = result.price_deviation.evidence.model_dump() | {"status": "insufficient"}
    with pytest.raises(ValueError):
        type(result.price_deviation.evidence).model_validate(evidence)


@pytest.mark.parametrize("field", signal_contracts.SIGNAL_DECIMAL_FIELDS)
@pytest.mark.parametrize("raw", ["1e-50000", "1e-1000000000", "1e50000", "1e1000000000",
                                  "0e-1000000000", "0e1000000000", "NaN", "sNaN", "Infinity", "-Infinity"])
def test_all_decimal_fields_reject_unsafe_values_before_formatting(monkeypatch, field, raw):
    monkeypatch.setattr(signal_contracts, "format", lambda *a: pytest.fail("unsafe value reached fixed formatter"), raising=False)
    for value in (raw, Decimal(raw)):
        with pytest.raises(ValueError) as caught:
            SignalParameters(**{field: value})
        # Pydantic errors must retain compact exponent notation, never expand it.
        assert len(caught.value.json()) < 2048


@pytest.mark.parametrize("field", signal_contracts.SIGNAL_DECIMAL_FIELDS)
def test_serializer_guards_validation_bypass_without_expanding(monkeypatch, field):
    def checked_format(number, spec):
        assert abs(number.as_tuple().exponent) < 1000, "unsafe value reached fixed formatter"
        return builtins.format(number, spec)
    monkeypatch.setattr(signal_contracts, "format", checked_format, raising=False)
    invalid = SignalParameters.model_construct(**{field: Decimal("1e-1000000000")})
    with pytest.raises(ValueError, match="96 characters"):
        invalid.fixed_decimal(getattr(invalid, field))
    with pytest.raises(ValueError, match="96 characters"):
        invalid.model_dump_json()


@pytest.mark.parametrize("field,maximum,outside", [
    ("min_price_coverage", "1", "1.000000000000000000000000000000000000000000000000000000000001"),
    ("min_index_coverage", "1", "1.000000000000000000000000000000000000000000000000000000000001"),
    ("deviation_threshold_pct", "1e12", "1000000000000.000000000000000000000000000000000000000000000000000001"),
    ("trend_threshold_pct", "1e12", "1000000000000.000000000000000000000000000000000000000000000000000001"),
    ("min_trend_slope_copper_per_scan_index", "2147483647", "2147483647.000000000000000000000000000000000000000000000000000001"),
])
def test_decimal_magnitude_boundaries_and_equivalent_notations(field, maximum, outside):
    for raw in ("1e-64", "10e-65", "0." + "0" * 63 + "1", maximum):
        result = SignalParameters(**{field: raw})
        serialized = result.model_dump(mode="json")[field]
        assert "e" not in serialized.lower()
        assert len(serialized) <= 96
        assert getattr(result, field).as_tuple() == Decimal(raw).as_tuple()
        assert Decimal(serialized) == Decimal(raw)
        if Decimal(raw).as_tuple().exponent < 0:
            assert Decimal(serialized).as_tuple() == Decimal(raw).as_tuple()
    for raw in (outside, "9.999999999999999999999999999999999999999999999999999999999999e-65"):
        with pytest.raises(ValueError):
            SignalParameters(**{field: raw})


def test_decimal_representation_limits_are_explicit_without_normalization():
    at_limit = "0." + "0" * 94
    result = SignalParameters(min_trend_slope_copper_per_scan_index=at_limit)
    assert result.model_dump(mode="json")["min_trend_slope_copper_per_scan_index"] == at_limit
    assert len(at_limit) == 96
    with pytest.raises(ValueError, match="96 characters"):
        SignalParameters(min_trend_slope_copper_per_scan_index=at_limit + "0")
    assert SignalParameters(min_price_coverage=" " * 125 + "0.8").min_price_coverage == Decimal("0.8")
    with pytest.raises(ValueError, match="128 characters"):
        SignalParameters(min_price_coverage=" " * 126 + "0.8")


@pytest.mark.parametrize("field", signal_contracts.SIGNAL_DECIMAL_FIELDS)
@pytest.mark.parametrize("raw", ["1e-50000", "1e-1000000000", "1e1000000000", "NaN", "Infinity"])
def test_http_rejects_unsafe_decimals_with_bounded_errors_before_service(monkeypatch, field, raw):
    monkeypatch.setattr(signal_contracts, "format", lambda *a: pytest.fail("unsafe value reached fixed formatter"), raising=False)
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", lambda *a: pytest.fail("invalid request reached service"))
    with TestClient(create_app()) as client:
        response = client.get("/market/signals", params=BASE | {field: raw})
    assert response.status_code == 422
    assert len(response.content) < 2048


def test_http_exact_zero_counterexample_and_existing_metrics_are_preserved(monkeypatch):
    source = analysis(ZERO_SLOPE_COUNTEREXAMPLE, days=list(range(100, 115)))
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", lambda *a: source)
    with TestClient(create_app()) as client:
        before = client.get("/market/metrics", params=BASE | {"size": 15})
        response = client.get("/market/signals", params=BASE | {"size": 15})
        after = client.get("/market/metrics", params=BASE | {"size": 15})
        document = client.get("/openapi.json").json()
    assert before.status_code == response.status_code == after.status_code == 200
    assert before.content == after.content
    result = response.json()
    assert result["historical_trend"]["direction"] == "no_significant_trend"
    assert result["historical_trend"]["slope_copper_per_scan_index"] == before.json()["metrics"]["trend_copper_per_scan_index"]
    assert result["historical_trend"]["price_change_pct"]["value"] == "30"
    assert "trend_direction_disagreement" not in {w["code"] for w in result["warnings"]}
    schema = document["paths"]["/market/signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert_openapi_json(result, schema, document)


def test_http_valid_decimal_limits_match_served_openapi(monkeypatch):
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", lambda *a: analysis([100] * 7 + [80]))
    maxima = {"min_price_coverage": "1", "min_index_coverage": "1", "deviation_threshold_pct": "1e12",
              "trend_threshold_pct": "1e12", "min_trend_slope_copper_per_scan_index": "2147483647"}
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
        schema = document["paths"]["/market/signals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        for field, maximum in maxima.items():
            for raw in ("1e-64", maximum):
                response = client.get("/market/signals", params=BASE | {"size": 8, field: raw})
                assert response.status_code == 200, response.text
                result = response.json()
                assert len(result["parameters"][field]) <= 96
                assert Decimal(result["parameters"][field]) == Decimal(raw)
                assert_openapi_json(result, schema, document)
