"""Offline selection of a published 5A archive and its explicit 006 context.

No settings, database imports or writes. A successful assessment is not target
authorization. The original remains in the private archive, never in SQL.
"""
import json
import re

from app.ingestion.capture_provenance import MAX_PROVENANCE_BYTES
from app.ingestion.local_lineage import VerifiedLocalContext, local_export_identity, prepare_local_capture
from app.local_capture.archive import _checked_path, _destination, _read_stable, _verify_entry


class PreflightError(ValueError):
    """Fixed public code, without paths, validation input or private evidence."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def preflight_archive(archive, capture_id, context_file):
    if not isinstance(capture_id, str) or not re.fullmatch(r"[0-9a-f]{64}", capture_id):
        raise PreflightError("invalid_capture_id")
    try:
        raw_context = _read_stable(_checked_path(context_file), single_link=True)
        if len(raw_context) > MAX_PROVENANCE_BYTES:
            raise ValueError("context too large")
        context = VerifiedLocalContext.model_validate(json.loads(raw_context, object_pairs_hook=unique_object))
    except Exception:
        raise PreflightError("invalid_verified_context") from None
    try:
        entry = _checked_path(_destination(archive) / "captures" / capture_id)
        metadata = _verify_entry(entry)
        raw = _read_stable(entry / "Auctionator.lua", single_link=True)
    except Exception:
        raise PreflightError("archive_integrity_failed") from None
    try:
        return prepare_local_capture(raw, metadata, context)
    except ValueError as error:
        if "price_exceeds_persistence_int32" in str(error):
            raise PreflightError("price_exceeds_persistence_int32") from None
        raise PreflightError("capture_context_mismatch") from None
    except Exception:
        raise PreflightError("capture_validation_failed") from None


def preflight_summary(result):
    metadata = result.local_capture.metadata
    return dict(status="preflight_passed", capture_id=metadata.capture_id,
                market_sha256=metadata.market_sha256, state_sha256=local_export_identity(result)[0],
                canonical_version=2, source_version="341", dataset=result.batch.dataset,
                native_fact_count=metadata.native_fact_count, market_count=len(metadata.markets),
                temporal_basis="unknown", native_scan_timestamp=None,
                import_performed=False, target_verified=False, analytics_enabled=False)
