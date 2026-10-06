import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.service import IngestionService
from app.main import create_app
from scripts.setup_test_database import validate_test_database_url


@pytest.fixture
def client_without_persistence(monkeypatch):
    def unexpected_import(*args, **kwargs):
        pytest.fail("Invalid HTTP payload reached persistence")

    monkeypatch.setattr(IngestionService, "import_snapshot", unexpected_import)
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("field", ["min_buyout", "avg_buyout", "max_buyout", "quantity_total", "auction_count"])
@pytest.mark.parametrize("value", [-1, 2147483648, 1.0, True])
def test_invalid_http_integers_fail_before_persistence(client_without_persistence, field, value):
    payload = json.loads((Path(__file__).parent / "fixtures" / "snapshot_valid.json").read_text())
    payload["items"][0][field] = value
    response = client_without_persistence.post("/imports/snapshots", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["captured_at", "imported_at"])
def test_naive_http_timestamp_fails_before_persistence(client_without_persistence, field):
    payload = json.loads((Path(__file__).parent / "fixtures" / "snapshot_valid.json").read_text())
    payload[field] = "2026-10-01T00:00:00"
    assert client_without_persistence.post("/imports/snapshots", json=payload).status_code == 422


@pytest.mark.parametrize("test_url", [None, "postgresql://localhost/development", "postgresql://localhost/same_test"])
def test_test_database_guard_rejects_missing_or_unsafe_target(test_url):
    with pytest.raises(ValueError):
        validate_test_database_url(test_url, "postgresql://localhost/same_test")


def test_test_database_guard_accepts_explicit_distinct_test_database():
    url = "postgresql://localhost/companion_test"
    assert validate_test_database_url(url, "postgresql://localhost/companion") == url
