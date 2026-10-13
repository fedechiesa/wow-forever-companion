"""Coverage describes stored evidence, never scan completeness or confidence."""
from decimal import Decimal, localcontext

from app.market.contracts import (
    BucketPoint, CoverageSummary, QualitySummary, QualityWarning, ResolvedWindow, SeriesContext,
)
from app.market.statistics import analysis_context, metric, unavailable


def coverage(points: list[BucketPoint], window: ResolvedWindow) -> CoverageSummary:
    count = len(points)
    prices = sum(p.daily_minimum is not None for p in points)
    available = sum(p.daily_max_available is not None for p in points)
    observed = sum(p.market_observed for p in points)
    span = window.end_day - window.start_day + 1 if window.start_day is not None else 0
    with localcontext(analysis_context()):
        price_ratio = metric(Decimal(prices) / count, "ratio", prices) if count else unavailable("ratio", 0, "no_axis")
        availability_ratio = (metric(Decimal(available) / count, "ratio", available)
                              if count else unavailable("ratio", 0, "no_axis"))
    return CoverageSummary(
        selected_position_count=count, observed_market_bucket_count=observed,
        price_observation_count=prices, availability_observation_count=available,
        missing_price_position_count=count - prices, missing_availability_position_count=count - available,
        index_span_position_count=span, unobserved_market_position_count=span - observed,
        price_ratio=price_ratio, availability_ratio=availability_ratio,
    )


def quality(context: SeriesContext, points: list[BucketPoint], window: ResolvedWindow,
            summary: CoverageSummary, availability_presence: str, undated_count: int) -> QualitySummary:
    warnings = []

    def warn(code, message):
        warnings.append(QualityWarning(code=code, message=message))

    warn("stored_minima_only", "Minima are stored values, not guaranteed minima of all scans or auctions.")
    warn("session_bucket_assignment", "The addon fixes the nominal 86400-second bucket index during its session.")
    if context.dataset == "simulated":
        warn("simulated_dataset", "Synthetic prices, availability and item identities do not validate Forever data.")
    if context.temporal_basis == "unknown":
        warn("unknown_calendar", "Indices have no verified calendar dates.")
    elif any(p.bucket_start is None for p in points):
        warn("calendar_out_of_range", "Some valid indices exceed the representable datetime range.")
    if summary.price_observation_count < 7:
        warn("small_sample", "Fewer than seven price buckets; seven is a presentation threshold, not a confidence guarantee.")
    if len(points) < window.requested_position_count:
        warn("incomplete_window", "Fewer market buckets are available than requested.")
    if summary.missing_price_position_count:
        warn("missing_prices", "Selected positions without price are excluded from price calculations.")
    if summary.missing_availability_position_count:
        warn("missing_availability", "Missing availability is unknown, not zero.")
    if summary.unobserved_market_position_count:
        warn("market_axis_gaps", "Some indices in the span have no stored evidence for this market context.")
    prices = [p for p in points if p.daily_minimum is not None]
    available = [p for p in points if p.daily_max_available is not None]
    if not prices:
        warn("no_price_data", "No price buckets exist in this selection.")
    elif prices[0].scan_day != window.start_day or prices[-1].scan_day != window.anchor_day:
        warn("price_endpoints_inset", "Price changes use observed endpoints inside the market-anchored window.")
    if available and (available[0].scan_day != window.start_day or available[-1].scan_day != window.anchor_day):
        warn("availability_endpoints_inset", "Availability changes use their own observed endpoints.")
    if any(p.daily_minimum == 0 for p in prices):
        warn("explicit_zero_price", "Stored zero prices are retained; percentages with zero baselines are undefined.")
    origins = {origin: sum(p.minimum_origin == origin for p in prices) for origin in ("l", "h_fallback", "unknown")}
    if origins["unknown"]:
        warn("unknown_minimum_origin", "Accumulated rows do not establish whether the minimum originated in l or h fallback.")
    if origins["h_fallback"]:
        warn("h_fallback", "Some minimum values use native h because l is absent; earlier minima may not have been retained.")
    if undated_count:
        warn("undated_evidence_excluded", "Undated minima in the selected item context are excluded from all temporal metrics.")
    return QualitySummary(warnings=warnings, minimum_l_count=origins["l"],
                          minimum_h_fallback_count=origins["h_fallback"], minimum_unknown_origin_count=origins["unknown"],
                          availability_field_presence=availability_presence)
