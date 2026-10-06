from __future__ import annotations

import pytest
import hashlib
from datetime import timezone
from pathlib import Path
from pydantic import ValidationError

from app.ingestion.adapters.file import FileAdapter


def valid_payload() -> dict:
    return {
        "realm": "Test Realm",
        "region": "test",
        "source_type": "simulated",
        "source_version": "0.1",
        "captured_at": "2026-10-01T00:00:00Z",
        "items": [
            {
                "external_item_id": "test-001",
                "name": "Test Item",
                "quality": "common",
                "min_buyout": 100,
                "avg_buyout": 150,
                "max_buyout": 200,
                "quantity_total": 10,
                "auction_count": 2,
            }
        ],
    }


def test_file_adapter_parses_valid_json_payload() -> None:
    result = FileAdapter().load_payload(valid_payload(), raw_reference="test:valid")

    assert result.snapshot.realm == "Test Realm"
    assert result.snapshot.items[0].external_item_id == "test-001"
    assert result.source_hash
    assert result.raw_reference == "test:valid"


def test_file_adapter_rejects_missing_required_fields() -> None:
    payload = valid_payload()
    del payload["realm"]

    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)


def test_file_adapter_rejects_negative_prices() -> None:
    payload = valid_payload()
    payload["items"][0]["min_buyout"] = -1

    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)


def test_file_adapter_rejects_invalid_price_order() -> None:
    payload = valid_payload()
    payload["items"][0]["min_buyout"] = 300

    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)


def test_file_adapter_rejects_duplicate_external_item_id() -> None:
    payload = valid_payload()
    payload["items"].append(dict(payload["items"][0]))

    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)


def test_file_adapter_reads_physical_json_fixture() -> None:
    path = Path(__file__).parent / "fixtures" / "snapshot_valid.json"
    result = FileAdapter().load(path)
    assert result.snapshot.realm == "Fixture Realm"
    assert result.snapshot.items[0].avg_buyout == 150
    assert result.source_hash == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.raw_reference == str(path)


INTEGER_FIELDS = ["min_buyout", "avg_buyout", "max_buyout", "quantity_total", "auction_count"]


@pytest.mark.parametrize("field", INTEGER_FIELDS)
@pytest.mark.parametrize("value", [-1, 2147483648, 1.0, True, "1"])
def test_integer_fields_reject_invalid_types_and_ranges(field, value) -> None:
    payload = valid_payload()
    payload["items"][0][field] = value
    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)


@pytest.mark.parametrize("value", [0, 2147483647])
def test_integer_bounds_are_valid(value) -> None:
    payload = valid_payload()
    payload["items"][0].update({field: value for field in INTEGER_FIELDS})
    result = FileAdapter().load_payload(payload)
    assert all(getattr(result.snapshot.items[0], field) == value for field in INTEGER_FIELDS)


@pytest.mark.parametrize("field", ["captured_at", "imported_at"])
@pytest.mark.parametrize("value", ["2026-10-01T00:00:00Z", "2026-09-30T21:00:00-03:00"])
def test_aware_timestamps_normalize_to_utc(field, value) -> None:
    payload = valid_payload()
    payload[field] = value
    timestamp = getattr(FileAdapter().load_payload(payload).snapshot, field)
    assert timestamp.tzinfo == timezone.utc
    assert timestamp.isoformat() == "2026-10-01T00:00:00+00:00"


@pytest.mark.parametrize("field", ["captured_at", "imported_at"])
def test_naive_timestamps_are_rejected(field) -> None:
    payload = valid_payload()
    payload[field] = "2026-10-01T00:00:00"
    with pytest.raises(ValidationError):
        FileAdapter().load_payload(payload)
