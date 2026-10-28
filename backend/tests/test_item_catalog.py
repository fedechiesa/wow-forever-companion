"""Local HTTP fixtures only. No public API, SQL, authentic capture or image IO."""
from datetime import datetime, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.catalog import (AHledgerClient, CatalogCache, CatalogError, CatalogItem,
                         MAX_BYTES, cache_seconds, http_get, retry_until)
from app.main import create_app


@pytest.fixture
def cache(tmp_path):
    return CatalogCache(tmp_path, clock=lambda: 1000.0)


def payload(**updates):
    return {"id": 2589, "name": "Linen Cloth", "quality": "COMMON", "itemClass": "Trade Goods",
            "itemSubclass": "Cloth", "icon": "https://render.worldofwarcraft.com/classic1x-us/icons/56/test.jpg",
            "vendorSell": 13, "attribution": {"url": "https://ahledger.com/items/2589?utm_source=ahledger_api"}} | updates


@pytest.fixture
def http_fixture():
    response = {"status": 200, "body": json.dumps(payload()).encode(),
                "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=300"}, "calls": 0}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            response["calls"] += 1
            self.send_response(response["status"])
            for key, value in response["headers"].items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response["body"])
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def transport(url):
        assert url == "https://api.ahledger.com/v1/items/2589?game=forever"
        status, headers, body = http_get(f"http://127.0.0.1:{server.server_port}/fixture")
        # Test clock is artificial; the HTTP server Date is not the provider's Date.
        del headers["Date"]
        return status, headers, body
    try:
        yield response, transport
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_local_http_valid_metadata_cache_and_no_economic_fields(cache, http_fixture):
    response, transport = http_fixture
    client = AHledgerClient(cache, transport)
    item = client.lookup(2589)
    assert item.name == "Linen Cloth" and item.category == "Trade Goods" and item.quality == "COMMON"
    assert item.language is item.build is item.icon_ref is None
    assert item.icon_permission == "unverified" and item.compatibility == "provider_product_only"
    assert "utm_source=ahledger_api" in item.attribution_url
    assert not {"vendorSell", "price", "minimum_copper"} & item.model_dump().keys()
    assert client.lookup(2589) == item and response["calls"] == 1
    cache.clock = lambda: 1300.0
    assert cache.read(2589) is None and cache.items() == []


@pytest.mark.parametrize("status", [400, 403, 404, 429, 500, 503])
def test_local_http_errors_without_retry(cache, http_fixture, status):
    response, transport = http_fixture
    response.update(status=status)
    response["headers"]["Retry-After"] = "120"
    if status == 404:
        assert AHledgerClient(cache, transport).lookup(2589) is None
    else:
        with pytest.raises(CatalogError, match=f"HTTP {status}"):
            AHledgerClient(cache, transport).lookup(2589)
    assert response["calls"] == 1 and cache.items() == []
    if status in (429, 500, 503):
        cache.clock = lambda: 1119.0
        with pytest.raises(CatalogError, match="cooldown"):
            AHledgerClient(cache, transport).lookup(2589)
        assert response["calls"] == 1
        cache.clock = lambda: 1120.0
        cache.cooldown()


@pytest.mark.parametrize("body", [b"{", b"[]", b'{"id":2589}', b'{"id":2589,"id":2589,"name":"bad"}',
    json.dumps(payload(id=2770)).encode(), json.dumps(payload(id=True)).encode(),
    json.dumps(payload(name=None)).encode(), json.dumps(payload(name="")).encode(),
    json.dumps(payload(quality=1)).encode(), json.dumps(payload(game="classic")).encode(),
    json.dumps(payload(attribution={"url":"https://evil.invalid"})).encode()])
def test_local_http_invalid_incomplete_contradictory(cache, http_fixture, body):
    response, transport = http_fixture
    response["body"] = body
    with pytest.raises(CatalogError, match="JSON"):
        AHledgerClient(cache, transport).lookup(2589)
    assert cache.items() == []


@pytest.mark.parametrize("control,age,expected", [
    ("public, max-age=300", "0", 300), ("max-age=300", "100", 200),
    ("max-age=30", "0", 30), ("max-age=30", "10", 20),
    ("max-age=300", "300", 0), ("no-store, max-age=300", "0", 0),
    ("no-cache, max-age=300", "0", 0), ("max-age=broken", "0", 0),
    ("", "0", 0), ("max-age=300,max-age=500", "0", 0), ("max-age=86400", "0", 300)])
def test_cache_headers(control, age, expected):
    assert cache_seconds({"Cache-Control":control, "Age":age}, 1000) == expected


@pytest.mark.parametrize("header", ["no-store", "no-cache", "max-age=0", ""])
def test_storage_requires_explicit_freshness(cache, http_fixture, header):
    response, transport = http_fixture
    response["headers"]["Cache-Control"] = header
    with pytest.raises(CatalogError, match="nothing stored"):
        AHledgerClient(cache, transport).lookup(2589)
    assert cache.items() == []


def test_retry_after_date_age_and_default():
    date = format_datetime(datetime.fromtimestamp(1120, timezone.utc), usegmt=True)
    assert retry_until(date, 1000) == 1120
    assert retry_until("invalid", 1000) == 1060
    assert retry_until("-3", 1000) == 1000
    assert cache_seconds({"Cache-Control":"max-age=300", "Date":date}, 1220) == 200


def test_local_http_resource_and_mime_limits(cache, http_fixture):
    response, transport = http_fixture
    response["body"] = b"x" * (MAX_BYTES + 1)
    with pytest.raises(CatalogError, match="budget"):
        AHledgerClient(cache, transport).lookup(2589)
    cache.clock = lambda: 1003.0
    response["body"] = b"{}"
    response["headers"]["Content-Type"] = "text/html"
    with pytest.raises(CatalogError, match="content type"):
        AHledgerClient(cache, transport).lookup(2589)


def test_transport_timeout_and_persistent_pacing(cache):
    transport = Mock(side_effect=TimeoutError)
    with pytest.raises(CatalogError, match="transport"):
        AHledgerClient(cache, transport).lookup(2589)
    with pytest.raises(CatalogError, match="cooldown"):
        AHledgerClient(CatalogCache(cache.path, cache.clock), transport).lookup(2589)
    assert transport.call_count == 1


def record(**updates):
    return CatalogItem(item_id=2589, name="Synthetic verified fixture", provider="ahledger",
        source_url="https://api.ahledger.com/v1/items/2589?game=forever",
        attribution_url="https://ahledger.com", fetched_at=1000.0, expires_at=1300.0, **updates)


def test_alternative_provider_is_explicit_and_icon_permission_separate(cache):
    alternative = record().model_dump() | {"provider":"foreverdb", "source_url":"https://foreverdb.net/api/v1/items/2589", "attribution_url":"https://foreverdb.net"}
    item = CatalogItem(**alternative)
    cache.write(item)
    assert cache.read(2589).provider == "foreverdb"
    assert record(icon_ref="/assets/catalog/test.png", icon_permission="authorized").icon_ref
    with pytest.raises(ValueError):
        record(icon_ref="https://render.worldofwarcraft.com/test.jpg", icon_permission="authorized")
    with pytest.raises(ValueError):
        record(icon_ref="/assets/catalog/test.png")


def test_ahledger_lookup_never_relabels_an_alternative_cached_source(cache, http_fixture):
    alternative = record().model_dump() | {"provider":"foreverdb", "source_url":"https://foreverdb.net/api/v1/items/2589", "attribution_url":"https://foreverdb.net"}
    cache.write(CatalogItem(**alternative))
    response, transport = http_fixture
    item = AHledgerClient(cache, transport).lookup(2589)
    assert response["calls"] == 1
    assert item.provider == "ahledger" and item.name == "Linen Cloth"
    assert cache.read(2589).provider == "ahledger"


def test_corrupt_or_mismatched_cache_falls_back(cache):
    cache.write(record())
    (cache.path / "2589.json").write_text('{"name":"bad"}')
    assert cache.items() == []
    (cache.path / "2770.json").write_text(record().model_dump_json())
    assert cache.read(2770) is None


def test_cache_capacity_and_exclusive_lookup(cache):
    for item_id in range(1, 129):
        cache.write(CatalogItem(**(record().model_dump() | {"item_id":item_id})))
    assert len(cache.items()) == 128
    with pytest.raises(CatalogError, match="full"):
        cache.write(record())
    with cache.lock():
        with pytest.raises(CatalogError, match="active"):
            AHledgerClient(cache, Mock()).lookup(2589)
    assert not (cache.path / "lookup.lock").exists()


def test_api_is_cache_only_no_sql_or_provider(cache, monkeypatch):
    from app.api import catalog
    cache.write(record())
    monkeypatch.setattr(catalog, "cache_path", lambda: cache.path)
    monkeypatch.setattr(catalog, "CatalogCache", lambda path: cache)
    monkeypatch.setattr("psycopg.connect", Mock(side_effect=AssertionError("SQL forbidden")))
    monkeypatch.setattr(AHledgerClient, "lookup", Mock(side_effect=AssertionError("provider forbidden")))
    with TestClient(create_app()) as client:
        response = client.get("/catalog/items")
        assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
        assert response.json()["items"][0]["name"] == record().name
        assert client.get("/catalog/items?ids=2589").status_code == 422
        assert client.post("/catalog/items").status_code == 405
        cache.clock = lambda: 1300.0
        assert client.get("/catalog/items").json()["items"] == []


def test_http_transport_deadline_and_socket_timeout(monkeypatch):
    from app import catalog
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.code, response.headers = 200, {}
    response.read1.return_value = b"x"
    opener = Mock()
    opener.open.return_value = response
    monkeypatch.setattr(catalog, "build_opener", lambda *args: opener)
    times = iter([0, 11])
    monkeypatch.setattr(catalog.time, "monotonic", lambda: next(times))
    with pytest.raises(CatalogError, match="budget"):
        http_get("http://local.invalid")
    assert opener.open.call_args.kwargs["timeout"] == 5


def test_no_redirects_missing_optional_fields_and_invalid_local_cooldown(cache):
    from app.catalog import NoRedirect
    assert NoRedirect().redirect_request(None, None, None, None, None, None) is None
    body = json.dumps({"id":2589,"name":"Synthetic minimal item"}).encode()
    item = AHledgerClient(cache, lambda url:(200,{"Content-Type":"application/json","Cache-Control":"max-age=300"},body)).lookup(2589)
    assert item.quality is item.category is item.build is item.language is None
    cache.clock = lambda: 1300.0
    (cache.path / "retry-after.txt").write_text("nan")
    with pytest.raises(CatalogError, match="Invalid local"):
        AHledgerClient(cache, Mock()).lookup(2589)


@pytest.mark.parametrize("ids", [["1","2","3","4","5"], ["2589","2589"], ["0"], ["2147483648"]])
def test_cli_rejects_unbounded_or_invalid_requests_before_any_lookup(ids, monkeypatch):
    from scripts import lookup_item_catalog
    lookup = Mock(side_effect=AssertionError("provider forbidden"))
    monkeypatch.setattr(lookup_item_catalog.AHledgerClient, "lookup", lookup)
    with pytest.raises(SystemExit) as error:
        lookup_item_catalog.main(ids)
    assert error.value.code == 2
    lookup.assert_not_called()


def test_cli_stops_batch_on_first_provider_error(tmp_path, monkeypatch):
    from scripts import lookup_item_catalog
    monkeypatch.setenv("ITEM_CATALOG_CACHE_DIR", str(tmp_path))
    lookup = Mock(side_effect=CatalogError("Provider HTTP 429; cooldown recorded, no retry."))
    monkeypatch.setattr(lookup_item_catalog.AHledgerClient, "lookup", lookup)
    assert lookup_item_catalog.main(["2589","2770"]) == 1
    lookup.assert_called_once_with(2589)
