"""One point per selected index; missing values never become zero."""
from pydantic import ValidationError

from app.ingestion.native_exports import FIELD_STATISTIC, NativeFact
from app.ingestion.partial_contracts import PartialObservation
from app.market.contracts import BucketPoint, EvidenceReference, SeriesContext
from app.market.errors import SeriesIntegrityError
from app.market.windows import bucket_start


def build_points(context: SeriesContext, positions: list[int], observed_days: list[int],
                 rows: list[dict]) -> list[BucketPoint]:
    if positions != sorted(set(positions)) or len(positions) > 366:
        raise SeriesIntegrityError("invalid selected axis")
    selected, observed = set(positions), set(observed_days)
    grouped: dict[int, dict[str, dict]] = {}
    try:
        for row in rows:
            day = row["scan_day"]
            if day is None or day not in selected or day not in observed:
                raise SeriesIntegrityError("daily evidence lies outside the selected market axis")
            if row["market_id"] != context.market_id or row["item_key"] != context.item_key:
                raise SeriesIntegrityError("evidence identity disagrees with selection")
            common = dict(market_key=context.market_key, ruleset=context.ruleset,
                          item_key=context.item_key, external_item_id=context.external_item_id,
                          key_kind=context.key_kind, scan_day=day, value=row["value"])
            if context.series_mode == "export":
                field = row["native_field"]
                if (field == "m" or row["export_id"] != context.export_id
                        or row["market_key"] != context.market_key or row["ruleset"] != context.ruleset
                        or row["external_item_id"] != context.external_item_id or row["key_kind"] != context.key_kind):
                    raise SeriesIntegrityError("native evidence context disagrees")
                NativeFact(**common, statistic=FIELD_STATISTIC[field], native_field=field,
                           original_item_key=row["original_item_key"], original_day_key=row["original_day_key"])
                identity = field
            else:
                if (row["source_id"], row["source_type"], row["temporal_basis"]) != (
                    context.source_id, context.source_type, context.temporal_basis
                ) or row["evidence_key"] != "daily":
                    raise SeriesIntegrityError("accumulated evidence context disagrees")
                PartialObservation(**common, statistic=row["statistic"])
                identity = row["statistic"]
            values = grouped.setdefault(day, {})
            if identity in values:
                raise SeriesIntegrityError("duplicate daily evidence identity")
            values[identity] = row

        def ref(row):
            if row is None:
                return None
            if context.series_mode == "export":
                return EvidenceReference(table="partial_export_facts", row_id=row["id"],
                                         native_field=row["native_field"], original_item_key=row["original_item_key"],
                                         original_day_key=row["original_day_key"])
            return EvidenceReference(table="partial_observations", row_id=row["id"],
                                     first_import_id=row["first_import_id"], last_import_id=row["last_import_id"])

        result = []
        for day in positions:
            values = grouped.get(day, {})
            if context.series_mode == "export":
                high, native_low, available = values.get("h"), values.get("l"), values.get("a")
                if values and high is None:
                    raise SeriesIntegrityError("orphan native day without h")
                if high is not None and any(r["original_day_key"] != high["original_day_key"] for r in values.values()):
                    raise SeriesIntegrityError("native day aliases disagree")
                low = native_low if native_low is not None else high
                origin = ("l" if native_low is not None else "h_fallback") if low is not None else None
            else:
                low, high, available = (values.get("daily_minimum"), values.get("daily_highest_minimum"),
                                        values.get("daily_max_available"))
                origin = "unknown" if low is not None else None
            result.append(BucketPoint(
                scan_day=day, bucket_start=bucket_start(context.temporal_basis, day), market_observed=day in observed,
                daily_minimum=low["value"] if low is not None else None,
                daily_highest_minimum=high["value"] if high is not None else None,
                daily_max_available=available["value"] if available is not None else None,
                minimum_origin=origin, minimum_evidence=ref(low), highest_minimum_evidence=ref(high),
                availability_evidence=ref(available),
            ))
        return result
    except (ValidationError, KeyError, TypeError, ValueError) as error:
        raise SeriesIntegrityError("invalid or incoherent daily evidence") from error
