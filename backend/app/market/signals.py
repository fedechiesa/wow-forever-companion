"""Pure rule evaluation over one consistent 3A result; never fetch or persist data."""
from decimal import Decimal, localcontext

from app.market.contracts import MarketMetricsResponse, QualityWarning
from app.market.signal_contracts import (
    EvidenceReason, HistoricalDeviationSignal, HistoricalTrendSignal, MarketSignalsResponse,
    SignalEvidence, SignalParameters,
)
from app.market.statistics import analysis_context, compute_metrics, exact_ols_terms, metric, unavailable


def _evidence(analysis, parameters, prices, rule):
    n = len(prices)
    requested = analysis.window.requested_position_count
    span = analysis.coverage.index_span_position_count
    ratio = metric(Decimal(n) / requested, "ratio", n) if requested else unavailable("ratio", n, "no_axis")
    span_ratio = metric(Decimal(n) / span, "ratio", n) if span else unavailable("ratio", n, "no_axis")
    anchor = analysis.window.anchor_day
    lag = anchor - prices[-1].scan_day if anchor is not None and prices else None
    reasons = []

    def fail(code, message):
        reasons.append(EvidenceReason(code=code, message=message))

    if rule == "deviation" and max(0, n - 1) < parameters.min_history_observations:
        fail("insufficient_history", "The historical reference has too few prices after excluding the latest point.")
    if rule == "trend" and n < parameters.min_trend_observations:
        fail("insufficient_observations", "Too few usable prices for the configured historical trend rule.")
    if ratio.value is None or ratio.value < parameters.min_price_coverage:
        fail("insufficient_price_coverage", "Price count divided by requested positions is below the configured minimum.")
    if span_ratio.value is None or span_ratio.value < parameters.min_index_coverage:
        fail("insufficient_index_coverage", "Price count divided by the full selected index span is below the configured minimum.")
    if lag is None or lag > parameters.max_latest_price_lag:
        fail("latest_price_missing_or_stale", "No latest price exists within the configured index distance from the window anchor.")
    origins = {"l": analysis.quality.minimum_l_count,
               "h_fallback": analysis.quality.minimum_h_fallback_count,
               "unknown": analysis.quality.minimum_unknown_origin_count}
    if parameters.require_native_l and origins["l"] != n:
        fail("native_l_required", "The rule requires native l for every used price; fallback or unknown origin is present.")
    if parameters.require_known_temporal_basis and analysis.context.temporal_basis == "unknown":
        fail("known_temporal_basis_required", "The configured rule requires a verified temporal basis.")
    return SignalEvidence(
        status="insufficient" if reasons else "sufficient", reasons=reasons,
        usable_observation_count=n, historical_observation_count=max(0, n - 1),
        requested_price_ratio=ratio, index_span_price_ratio=span_ratio, latest_price_lag=lag,
        minimum_l_count=origins["l"], minimum_h_fallback_count=origins["h_fallback"],
        minimum_unknown_origin_count=origins["unknown"],
    )


def _fail(evidence, code, message):
    # Validate both fields together; never mutate the 3A input or shared evidence.
    return SignalEvidence(**(evidence.model_dump() | {
        "status": "insufficient", "reasons": [*evidence.reasons, EvidenceReason(code=code, message=message)],
    }))


def _deviation(analysis, parameters, prices):
    evidence = _evidence(analysis, parameters, prices, "deviation")
    previous = prices[:-1]
    # Reuse the exact 3A median implementation in a bounded second pass (<=365 points).
    reference = compute_metrics(previous).median_daily_minimum_copper
    if previous:
        reference = reference.model_copy(update={"first_day": previous[0].scan_day, "last_day": previous[-1].scan_day})
    observed = analysis.metrics.last_minimum_copper
    n = len(prices)
    signed = absolute = unavailable("copper", n, "insufficient_data" if n else "no_data")
    pct = unavailable("percent", n, "insufficient_data" if n else "no_data")
    if observed.value is not None and reference.value is not None:
        delta = observed.value - reference.value
        first, last = previous[0].scan_day, prices[-1].scan_day
        signed = metric(delta, "copper", n, first, last)
        absolute = metric(abs(delta), "copper", n, first, last)
        pct = (metric(100 * delta / reference.value, "percent", n, first, last) if reference.value != 0
               else unavailable("percent", n, "zero_reference", first, last))
        if reference.value == 0 and delta != 0:
            evidence = _fail(evidence, "zero_reference", "A nonzero deviation from a zero reference has no defined percentage.")
    direction = "no_significant_deviation"
    if evidence.status == "insufficient":
        direction = "insufficient_evidence"
    elif pct.value is not None and abs(pct.value) >= parameters.deviation_threshold_pct:
        direction = "above_reference" if pct.value > 0 else "below_reference"
    explanation = {
        "insufficient_evidence": "Historical deviation cannot be classified under the configured evidence requirements.",
        "above_reference": "The latest stored minimum is above the prior-price median by at least the configured percentage.",
        "below_reference": "The latest stored minimum is below the prior-price median by at least the configured percentage.",
        "no_significant_deviation": "The deviation does not reach the configured threshold, or the observed and reference prices are both zero.",
    }[direction]
    return HistoricalDeviationSignal(direction=direction, observed_price_copper=observed,
                                     reference_price_copper=reference, signed_deviation_copper=signed,
                                     absolute_deviation_copper=absolute, deviation_pct=pct,
                                     evidence=evidence, explanation=explanation)


def _trend(analysis, parameters, prices, slope_terms):
    evidence = _evidence(analysis, parameters, prices, "trend")
    metrics = analysis.metrics
    slope = metrics.trend_copper_per_scan_index
    delta, pct = metrics.price_change_copper, metrics.price_change_pct
    if slope.value is None or slope_terms is None:
        evidence = _fail(evidence, "unavailable_trend", "The 3A slope is unavailable for this sample or axis.")
    # Zero endpoint change is neutral without inventing a percentage from zero.
    if pct.value is None and delta.value is not None and delta.value != 0:
        evidence = _fail(evidence, "zero_baseline", "Endpoint percentage change is undefined with a zero first price.")
    direction = "no_significant_trend"
    numerator, denominator = slope_terms if slope_terms is not None else (0, 1)
    threshold_n, threshold_d = parameters.min_trend_slope_copper_per_scan_index.as_integer_ratio()
    if evidence.status == "insufficient":
        direction = "insufficient_evidence"
    elif (pct.value is not None and numerator != 0
          and abs(pct.value) >= parameters.trend_threshold_pct
          and abs(numerator) * threshold_d >= threshold_n * denominator
          and ((numerator > 0 and pct.value > 0) or (numerator < 0 and pct.value < 0))):
        direction = "ascending" if numerator > 0 else "descending"
    explanation = {
        "insufficient_evidence": "Historical trend cannot be classified under the configured evidence requirements.",
        "ascending": "The historical slope and endpoint change are positive and meet the configured magnitude thresholds.",
        "descending": "The historical slope and endpoint change are negative and meet the configured magnitude thresholds.",
        "no_significant_trend": "Slope and endpoint change do not jointly meet the configured direction and magnitude conditions.",
    }[direction]
    if direction == "no_significant_trend" and slope_terms is not None and numerator == 0:
        explanation = "The exact OLS numerator is zero; no directional historical trend is emitted."
    return HistoricalTrendSignal(
        direction=direction, first_price_copper=metrics.first_minimum_copper,
        last_price_copper=metrics.last_minimum_copper, slope_copper_per_scan_index=slope,
        price_change_copper=delta, price_change_pct=pct, evidence=evidence, explanation=explanation,
    )


def evaluate_signals(analysis: MarketMetricsResponse, parameters: SignalParameters) -> MarketSignalsResponse:
    """Thresholds are inclusive; insufficient evidence always takes precedence."""
    prices = sorted((p for p in analysis.points if p.daily_minimum is not None), key=lambda p: p.scan_day)
    warnings = [QualityWarning(code="statistical_rules_only", message=(
        "Threshold labels are descriptive rules, not probabilistic confidence, a forecast or a confirmed buying opportunity."
    )), QualityWarning(code="availability_not_sales", message=(
        "Availability does not establish sales, demand, liquidity or profitability; it is not used by these rules."
    ))]
    if analysis.context.series_mode == "accumulated":
        warnings.append(QualityWarning(code="accumulated_extremes", message=(
            "Prices are accumulated extremes across compatible imports, not a single addon export or current auction price."
        )))
    slope_terms = exact_ols_terms([(p.scan_day, p.daily_minimum) for p in prices])
    numerator = slope_terms[0] if slope_terms is not None else 0
    delta = analysis.metrics.price_change_copper.value
    if delta is not None and ((numerator > 0 and delta < 0) or (numerator < 0 and delta > 0)):
        warnings.append(QualityWarning(code="trend_direction_disagreement", message=(
            "Slope and endpoint change have opposite signs; no directional trend is emitted."
        )))
    with localcontext(analysis_context()):
        deviation = _deviation(analysis, parameters, prices)
        trend = _trend(analysis, parameters, prices, slope_terms)
    return MarketSignalsResponse(
        parameters=parameters, context=analysis.context, window=analysis.window, points=analysis.points,
        coverage=analysis.coverage, quality=analysis.quality, provenance=analysis.provenance,
        warnings=warnings, price_deviation=deviation, historical_trend=trend,
    )
