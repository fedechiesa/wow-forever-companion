from copy import deepcopy
from datetime import datetime
import re

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.main import create_app
from app.market.contracts import SeriesContext
from app.market.errors import SeriesIntegrityError, SeriesNotFound, WindowError
from app.market.series import build_points


def assert_openapi_json(value, schema, document):
    """Check the response schema keywords actually emitted by this API, without a new dependency.

    Unknown keywords fail rather than silently leaving part of the contract unchecked.
    """
    supported = {"$ref", "anyOf", "type", "properties", "required", "additionalProperties", "items",
                 "enum", "const", "pattern", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                 "minLength", "maxLength", "minItems", "maxItems", "format", "title", "description", "default"}
    assert set(schema) <= supported, set(schema) - supported
    if "$ref" in schema:
        target = document
        for segment in schema["$ref"].removeprefix("#/").split("/"):
            target = target[segment.replace("~1", "/").replace("~0", "~")]
        assert_openapi_json(value, target, document)
        return
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                assert_openapi_json(value, alternative, document)
                break
            except AssertionError:
                pass
        else:
            raise AssertionError(f"{value!r} matches no OpenAPI alternative")
    expected = schema.get("type")
    if expected:
        types = {"null": type(None), "string": str, "integer": int, "boolean": bool,
                 "array": list, "object": dict}
        if expected == "number":
            assert type(value) in (int, float)
        else:
            assert type(value) is types[expected], (value, expected)
    if "enum" in schema:
        assert value in schema["enum"]
    if "const" in schema:
        assert value == schema["const"]
    if "pattern" in schema:
        assert re.search(schema["pattern"], value) is not None, (value, schema["pattern"])
    for keyword, compare in (("minimum", lambda a, b: a >= b), ("maximum", lambda a, b: a <= b),
                             ("exclusiveMinimum", lambda a, b: a > b), ("exclusiveMaximum", lambda a, b: a < b)):
        if keyword in schema:
            assert compare(value, schema[keyword])
    for keyword, compare in (("minLength", lambda a, b: a >= b), ("maxLength", lambda a, b: a <= b),
                             ("minItems", lambda a, b: a >= b), ("maxItems", lambda a, b: a <= b)):
        if keyword in schema:
            assert compare(len(value), schema[keyword])
    if schema.get("format") == "date-time":
        assert datetime.fromisoformat(value).utcoffset() is not None
    elif "format" in schema:
        raise AssertionError(f"Unhandled OpenAPI format: {schema['format']}")
    if isinstance(value, dict):
        assert set(schema.get("required", [])) <= set(value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(properties)
        for name, entry in value.items():
            if name in properties:
                assert_openapi_json(entry, properties[name], document)
            elif isinstance(schema.get("additionalProperties"), dict):
                assert_openapi_json(entry, schema["additionalProperties"], document)
    if isinstance(value, list) and "items" in schema:
        for entry in value:
            assert_openapi_json(entry, schema["items"], document)


BASE = dict(market_id=1, item_key="123", source_id="test-source", source_type="simulated",
            temporal_basis="unknown", series_mode="accumulated", window_type="observed_buckets", size=7)


def context(mode="accumulated"):
    return SeriesContext(**{k: v for k, v in BASE.items() if k not in ("window_type", "size")},
                         market_key="PvE", ruleset="PvE", region="test", dataset="simulated",
                         external_item_id="123", key_kind="item", value_semantics="accumulated_extreme") if mode == "accumulated" else SeriesContext(
        market_id=1, item_key="123", source_id="test-source", source_type="simulated", temporal_basis="unknown",
        series_mode="export", export_id=1, market_key="PvE", ruleset="PvE", region="test", dataset="simulated",
        external_item_id="123", key_kind="item", value_semantics="export_projection")


def accumulated_row(**updates):
    return dict(id=1, market_id=1, item_key="123", scan_day=10, statistic="daily_minimum", value=100,
                source_id="test-source", source_type="simulated", temporal_basis="unknown", evidence_key="daily",
                first_import_id=1, last_import_id=1, **updates)


def native_row(field, value=100, **updates):
    row = dict(id={"h": 1, "l": 2, "a": 3}[field], export_id=1, market_id=1, item_key="123", scan_day=10,
               native_field=field, value=value, market_key="PvE", ruleset="PvE", external_item_id="123", key_kind="item",
               original_item_key="00123", original_day_key="0010")
    row.update(updates)
    return row


@pytest.mark.parametrize("updates", [
    {"series_mode": "export"}, {"export_id": 1}, {"size": 367}, {"item_key": "00123"},
    {"source_id": " test-source"}, {"source_type": "other"}, {"temporal_basis": "2020-01-01"},
    {"window_type": "calendar_days", "size": None, "days": 7},
    {"window_type": "index_range", "size": None, "start_day": 1, "end_day": 367},
    {"unexpected": "field"},
])
def test_http_rejects_invalid_selection_before_database(monkeypatch, updates):
    monkeypatch.setattr("app.market.service.connect", lambda: pytest.fail("invalid request reached PostgreSQL"))
    params = {k: v for k, v in (BASE | updates).items() if v is not None}
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params).status_code == 422


@pytest.mark.parametrize("error,status", [(SeriesNotFound("missing"), 404), (SeriesIntegrityError("bad"), 409),
                                        (WindowError("bad window"), 422), (psycopg.OperationalError("unavailable"), 503)])
def test_http_domain_errors_are_stable(monkeypatch, error, status):
    def fail(*args):
        raise error
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", fail)
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=BASE).status_code == status


def test_query_indices_and_calendar_days_parse_from_strings(monkeypatch):
    def inspected(self, request):
        assert request.window.end_day == 29
        assert request.window.days == 7
        assert request.selector.temporal_basis == "2020-01-01T00:00:00+00:00"
        raise SeriesNotFound("validated")
    monkeypatch.setattr("app.market.service.MarketAnalysisService.analyze", inspected)
    params = BASE | dict(window_type="calendar_days", days=7, temporal_basis="2020-01-01T00:00:00Z", end_day=29)
    params.pop("size")
    with TestClient(create_app()) as client:
        assert client.get("/market/metrics", params=params).status_code == 404


def test_native_zero_and_fallback_evidence_are_preserved():
    fallback = build_points(context("export"), [10], [10], [native_row("h")])[0]
    assert fallback.minimum_origin == "h_fallback" and fallback.daily_minimum == 100
    assert fallback.minimum_evidence.row_id == fallback.highest_minimum_evidence.row_id
    explicit = build_points(context("export"), [10], [10], [native_row("h"), native_row("l", 0), native_row("a", 0)])[0]
    assert explicit.minimum_origin == "l" and explicit.daily_minimum == 0 and explicit.daily_max_available == 0
    assert explicit.minimum_evidence.row_id == 2


@pytest.mark.parametrize("rows", [
    [native_row("l")], [native_row("h"), native_row("l", 200)], [native_row("h"), native_row("h")],
    [native_row("h", export_id=2)], [native_row("h", scan_day=11)],
    [native_row("h"), native_row("a", original_day_key="10")],
])
def test_incoherent_native_series_is_rejected(rows):
    with pytest.raises(SeriesIntegrityError):
        build_points(context("export"), [10], [10], rows)


@pytest.mark.parametrize("mutation", ["duplicate", "source", "mode", "range", "value"])
def test_incoherent_accumulated_series_is_rejected(mutation):
    row = accumulated_row()
    rows = [row]
    if mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation == "source":
        row["source_id"] = "other"
    elif mutation == "mode":
        row["statistic"] = "last_minimum"
    elif mutation == "range":
        row["scan_day"] = 11
    else:
        row["value"] = True
    with pytest.raises(SeriesIntegrityError):
        build_points(context(), [10], [10], rows)


def test_accumulated_origin_unknown_and_missing_bucket_kept_null():
    points = build_points(context(), [10, 11], [10], [accumulated_row()])
    assert points[0].minimum_origin == "unknown"
    assert points[1].daily_minimum is None and points[1].daily_max_available is None
    assert not points[1].market_observed
