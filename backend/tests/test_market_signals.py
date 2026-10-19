"""Pure 3B.1 rules over simulated, explicitly constructed 3A evidence."""
from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
from fractions import Fraction

import pytest
from pydantic import ValidationError

from app.market.contracts import MarketMetricsResponse, ProvenanceSummary, WindowSpec
from app.market.quality import coverage, quality
from app.market.signal_contracts import SignalParameters
from app.market.signals import evaluate_signals
from app.market.statistics import compute_metrics, exact_ols_terms
from app.market.windows import resolve_window
from tests.test_market_statistics import point
from tests.test_market_validation import context


def analysis(values, *, days=None, requested=None, mode="accumulated", origins=None,
             basis="unknown", anchor=None, window_type="observed_buckets", available=None):
    days = days if days is not None else list(range(10, 10 + len(values)))
    points = [point(d, p, available[i] if available is not None else None) for i, (d, p) in enumerate(zip(days, values))]
    for i, p in enumerate(points):
        if p.daily_minimum is not None:
            p.minimum_origin = origins[i] if origins else ("l" if mode == "export" else "unknown")
    ctx = context(mode).model_copy(update={"temporal_basis": basis})
    spec = (WindowSpec(window_type=window_type, start_day=days[0], end_day=days[-1])
            if window_type == "index_range" else WindowSpec(window_type=window_type, size=requested or max(1, len(points)), end_day=anchor))
    window = resolve_window(spec, basis, days[0] if days else None, days[-1] if days else None, days)
    summary = coverage(points, window)
    return MarketMetricsResponse(
        context=ctx, window=window, points=points, metrics=compute_metrics(points), coverage=summary,
        quality=quality(ctx, points, window, summary, "unknown", 0),
        provenance=ProvenanceSummary(selected_daily_row_count=len(points), excluded_undated_count=0, referenced_import_ids=[]),
    )


def signals(values, **options):
    parameters = options.pop("parameters", SignalParameters())
    return evaluate_signals(analysis(values, **options), parameters)


def codes(signal):
    return {r.code for r in signal.evidence.reasons}


@pytest.mark.parametrize("last,direction,pct", [(80, "below_reference", "-20"), (120, "above_reference", "20"),
                                                 (81, "no_significant_deviation", "-19"), (119, "no_significant_deviation", "19")])
def test_deviation_inclusive_thresholds_and_latest_excluded(last, direction, pct):
    signal = signals([100] * 7 + [last]).price_deviation
    assert signal.direction == direction
    assert signal.reference_price_copper.value == 100
    assert signal.reference_price_copper.observation_count == 7
    assert signal.reference_price_copper.first_day == 10 and signal.reference_price_copper.last_day == 16
    assert signal.observed_price_copper.first_day == 17
    assert signal.signed_deviation_copper.value == last - 100
    assert signal.absolute_deviation_copper.value == abs(last - 100)
    assert signal.deviation_pct.value == Decimal(pct)


def test_robust_reference_survives_single_extreme_and_has_fractional_even_median():
    assert signals([100] * 6 + [2147483647, 80]).price_deviation.reference_price_copper.value == 100
    signal = signals([1, 1, 1, 1, 2, 2, 2, 2, 3]).price_deviation
    assert signal.reference_price_copper.value == Decimal("1.5")
    assert signal.deviation_pct.value == 100


def test_excluding_latest_changes_reference_and_prevents_circular_baseline():
    signal = signals([1, 2, 3, 100], parameters=SignalParameters(min_history_observations=3, min_trend_observations=3)).price_deviation
    assert signal.reference_price_copper.value == 2  # Including 100 would yield 2.5.
    assert signal.deviation_pct.value == 4900


def test_full_window_preserves_high_indices_and_does_not_change_sample_unit():
    days = list(range(2147483282, 2147483648))
    result = signals([100] * 365 + [80], days=days)
    assert result.price_deviation.direction == "below_reference"
    assert result.price_deviation.evidence.historical_observation_count == 365
    assert result.historical_trend.slope_copper_per_scan_index.last_day == 2147483647
    assert result.window.positions == days


@pytest.mark.parametrize("values,dev,trend", [
    ([0] * 8, "no_significant_deviation", "no_significant_trend"),
    ([100] * 8, "no_significant_deviation", "no_significant_trend"),
    ([0] * 7 + [100], "insufficient_evidence", "insufficient_evidence"),
    ([100] * 7 + [0], "below_reference", "descending"),
])
def test_zero_prices_zero_reference_and_equal_prices(values, dev, trend):
    result = signals(values)
    assert result.price_deviation.direction == dev
    assert result.historical_trend.direction == trend
    if not any(values):
        assert result.price_deviation.deviation_pct.reason == "zero_reference"
        assert result.historical_trend.price_change_pct.reason == "zero_baseline"
        assert result.price_deviation.evidence.status == "sufficient"
    if values[0] == 0 and values[-1] != 0:
        assert "zero_reference" in codes(result.price_deviation)
        assert "zero_baseline" in codes(result.historical_trend)


@pytest.mark.parametrize("values,direction", [
    (list(range(100, 108)), "no_significant_trend"),
    (list(range(100, 116, 2)), "ascending"),
    (list(range(114, 98, -2)), "descending"),
    ([100] * 8, "no_significant_trend"),
    ([100, 100, 100, 100, 100, 100, 110], "ascending"),
])
def test_trend_reuses_3a_values_and_threshold(values, direction):
    source = analysis(values)
    trend = evaluate_signals(source, SignalParameters()).historical_trend
    assert trend.direction == direction
    assert trend.slope_copper_per_scan_index == source.metrics.trend_copper_per_scan_index
    assert trend.price_change_copper == source.metrics.price_change_copper
    assert trend.price_change_pct == source.metrics.price_change_pct


def test_trend_requires_slope_and_endpoints_to_agree():
    result = signals([100, 1000, 900, 800, 700, 600, 500, 120])
    assert result.historical_trend.slope_copper_per_scan_index.value < 0
    assert result.historical_trend.price_change_pct.value == 20
    assert result.historical_trend.direction == "no_significant_trend"
    assert "trend_direction_disagreement" in {w.code for w in result.warnings}


@pytest.mark.parametrize("n", [0, 1, 2, 3, 6])
def test_small_samples_are_not_classified(n):
    result = signals([100 + i * 100 for i in range(n)])
    assert result.price_deviation.direction == result.historical_trend.direction == "insufficient_evidence"
    assert "insufficient_history" in codes(result.price_deviation)
    assert "insufficient_observations" in codes(result.historical_trend)


def test_distinct_minimum_history_and_trend_counts():
    result = signals([100] * 7)
    assert result.price_deviation.direction == "insufficient_evidence"
    assert result.historical_trend.direction == "no_significant_trend"
    result = signals([100] * 7 + [80])
    assert result.price_deviation.evidence.historical_observation_count == 7
    assert result.price_deviation.evidence.usable_observation_count == 8


def test_internal_gaps_retained_with_coverage_exactly_at_boundary():
    result = signals([100, 100, None, 100, 100, 100, None, 100, 100, 80])
    assert result.price_deviation.direction == "below_reference"
    assert result.price_deviation.evidence.requested_price_ratio.value == Decimal("0.8")
    assert result.coverage.missing_price_position_count == 2
    assert result.points[2].daily_minimum is None
    assert "missing_prices" in {w.code for w in result.quality.warnings}


def test_missing_prices_or_short_observed_window_cannot_claim_full_coverage():
    result = signals([100] * 8 + [None] * 3 + [80])
    assert "insufficient_price_coverage" in codes(result.price_deviation)
    result = signals([100] * 7 + [80], requested=30)
    assert result.coverage.price_ratio.value == 1  # Existing 3A semantics are unchanged.
    assert result.price_deviation.evidence.requested_price_ratio.value < Decimal("0.8")
    assert result.price_deviation.direction == "insufficient_evidence"


def test_sparse_axis_uses_actual_indices_and_separate_span_gate():
    values = [100, 110, 120, 130, 140, 150, 160, 170]
    dense = signals(values)
    sparse = signals(values, days=list(range(10, 90, 10)))
    assert sparse.historical_trend.slope_copper_per_scan_index.value == dense.historical_trend.slope_copper_per_scan_index.value / 10
    assert "insufficient_index_coverage" in codes(sparse.historical_trend)
    assert sparse.coverage.price_ratio.value == 1
    relaxed = signals(values, days=list(range(10, 90, 10)), parameters=SignalParameters(min_index_coverage="0.1"))
    assert relaxed.historical_trend.direction == "ascending"
    assert relaxed.historical_trend.slope_copper_per_scan_index.unit == "copper/scan_index"


def test_index_coverage_threshold_is_inclusive():
    values = [100] * 7 + [80]
    days = [0, 2, 4, 6, 8, 10, 12, 15]
    result = signals(values, days=days)
    assert result.price_deviation.evidence.index_span_price_ratio.value == Decimal("0.5")
    assert result.price_deviation.direction == "below_reference"


def test_trailing_gap_and_anchor_lag_require_explicit_permission():
    result = signals([100] * 7 + [80, None])
    assert result.price_deviation.evidence.latest_price_lag == 1
    assert "latest_price_missing_or_stale" in codes(result.price_deviation)
    relaxed = signals([100] * 7 + [80, None], parameters=SignalParameters(max_latest_price_lag=1))
    assert relaxed.price_deviation.direction == "below_reference"
    anchored = signals([100] * 7 + [80], anchor=100)
    assert anchored.price_deviation.evidence.latest_price_lag == 83
    assert anchored.price_deviation.direction == "insufficient_evidence"


@pytest.mark.parametrize("mode,origin", [("accumulated", "unknown"), ("export", "l"), ("export", "h_fallback")])
def test_mode_provenance_and_origin_policy(mode, origin):
    result = signals([100] * 7 + [80], mode=mode, origins=[origin] * 8)
    assert result.price_deviation.direction == "below_reference"
    assert result.context.series_mode == mode
    assert getattr(result.price_deviation.evidence, f"minimum_{'unknown_origin' if origin == 'unknown' else origin}_count") == 8
    strict = signals([100] * 7 + [80], mode=mode, origins=[origin] * 8,
                     parameters=SignalParameters(require_native_l=True))
    assert ("native_l_required" in codes(strict.price_deviation)) == (origin != "l")
    assert ("accumulated_extremes" in {w.code for w in result.warnings}) == (mode == "accumulated")


def test_fallback_latest_is_included_in_native_policy_and_unknown_calendar_is_explicit():
    result = signals([100] * 7 + [80], mode="export", origins=["l"] * 7 + ["h_fallback"],
                     parameters=SignalParameters(require_native_l=True, require_known_temporal_basis=True))
    assert {"native_l_required", "known_temporal_basis_required"} <= codes(result.price_deviation)
    assert "unknown_calendar" in {w.code for w in result.quality.warnings}
    known = signals([100] * 7 + [80], basis="2020-01-01T00:00:00+00:00",
                    parameters=SignalParameters(require_known_temporal_basis=True))
    assert known.price_deviation.direction == "below_reference"


def test_availability_does_not_affect_signals_or_imply_sales():
    first = signals([100] * 7 + [80], available=[1000, 1, 0, None, 10000, 1, 0, 0])
    second = signals([100] * 7 + [80], available=[None] * 8)
    assert first.price_deviation == second.price_deviation
    assert first.historical_trend == second.historical_trend
    assert "availability_not_sales" in {w.code for w in first.warnings}


def test_large_copper_small_percentage_and_serialization():
    signal = signals([2147483647] * 7 + [2147483646], parameters=SignalParameters(deviation_threshold_pct="1e-50")).price_deviation
    assert signal.direction == "below_reference"
    assert signal.signed_deviation_copper.value == -1
    assert abs(signal.deviation_pct.value) < Decimal("1e-6")
    assert "e" not in signal.model_dump(mode="json")["deviation_pct"]["value"].lower()
    assert signal.reference_price_copper.value == Decimal("2147483647")


def test_configurable_slope_magnitude_inclusive_and_percentage_boundary():
    values = [100, 102, 104, 106, 108, 110, 112, 114]
    assert signals(values, parameters=SignalParameters(min_trend_slope_copper_per_scan_index="2", trend_threshold_pct="14")).historical_trend.direction == "ascending"
    assert signals(values, parameters=SignalParameters(min_trend_slope_copper_per_scan_index="2.0001")).historical_trend.direction == "no_significant_trend"
    assert signals(values, parameters=SignalParameters(trend_threshold_pct="14.0001")).historical_trend.direction == "no_significant_trend"


def test_rules_preserve_source_and_ignore_hostile_decimal_context():
    source = analysis([100, 1000, 900, 800, 700, 600, 500, 120])
    original = source.model_dump_json()
    params = SignalParameters(deviation_threshold_pct="1e-50")
    expected = evaluate_signals(source, params).model_dump_json()
    with localcontext() as ambient:
        ambient.prec, ambient.Emax, ambient.Emin, ambient.rounding = 2, 2, -2, ROUND_UP
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        flags = dict(ambient.flags)
        assert evaluate_signals(source, params).model_dump_json() == expected
        assert flags == dict(ambient.flags)
    assert source.model_dump_json() == original


@pytest.mark.parametrize("updates", [
    {"min_history_observations": 2}, {"min_history_observations": 366}, {"min_trend_observations": 2},
    {"min_trend_observations": 367}, {"min_price_coverage": "0"}, {"min_price_coverage": "1.01"},
    {"min_index_coverage": "-0.1"}, {"deviation_threshold_pct": "0"}, {"trend_threshold_pct": "-1"},
    {"min_trend_slope_copper_per_scan_index": "-1"}, {"max_latest_price_lag": -1},
    {"deviation_threshold_pct": "NaN"}, {"trend_threshold_pct": "Infinity"}, {"unexpected": True},
])
def test_invalid_rule_parameters(updates):
    with pytest.raises(ValidationError):
        SignalParameters(**updates)


ZERO_SLOPE_COUNTEREXAMPLE = [100, 299, 103, 117, 92, 80, 94, 117, 153, 97, 114, 161, 150, 169, 130]


def test_exact_zero_slope_counterexample_is_neutral_without_changing_3a_metrics():
    source = analysis(ZERO_SLOPE_COUNTEREXAMPLE, days=list(range(100, 115)))
    before = source.model_dump_json()
    result = evaluate_signals(source, SignalParameters())
    assert source.metrics.trend_copper_per_scan_index.value != 0  # Legacy descriptive residual remains visible.
    assert result.historical_trend.slope_copper_per_scan_index == source.metrics.trend_copper_per_scan_index
    assert result.historical_trend.price_change_pct.value == 30
    assert result.historical_trend.direction == "no_significant_trend"
    assert result.historical_trend.evidence.status == "sufficient"
    assert "exact OLS numerator is zero" in result.historical_trend.explanation
    assert source.model_dump_json() == before
    numerator, denominator = exact_ols_terms(list(zip(range(100, 115), ZERO_SLOPE_COUNTEREXAMPLE)))
    assert Fraction(numerator, denominator) == 0


@pytest.mark.parametrize("sign,direction", [(1, "ascending"), (-1, "descending")])
def test_genuine_tiny_slopes_survive_without_epsilon(sign, direction):
    values = ZERO_SLOPE_COUNTEREXAMPLE.copy()
    values[8] += 1
    if sign < 0:
        values = [400 - p for p in values]
    days = [140000000 * i for i in range(15)]
    numerator, denominator = exact_ols_terms(list(zip(days, values)))
    assert Fraction(numerator, denominator) == Fraction(sign, 39200000000)
    result = signals(values, days=days, parameters=SignalParameters(min_index_coverage="1e-64"))
    assert result.historical_trend.direction == direction
    assert abs(result.historical_trend.slope_copper_per_scan_index.value) < Decimal("1e-10")
    assert signals(values, days=days).historical_trend.direction == "insufficient_evidence"


@pytest.mark.parametrize("threshold,expected", [
    ("0.000000008", "ascending"),
    ("0.000000007999999999999999999999999999999999999999999999999999", "ascending"),
    ("0.000000008000000000000000000000000000000000000000000000000001", "no_significant_trend"),
])
def test_exact_slope_threshold_comparison_preserves_digits_beyond_decimal_context(threshold, expected):
    result = signals([100 + 2 * i for i in range(7)], days=[250000000 * i for i in range(7)],
                     parameters=SignalParameters(min_index_coverage="1e-64",
                                                 min_trend_slope_copper_per_scan_index=threshold))
    assert result.historical_trend.slope_copper_per_scan_index.value == Decimal("8e-9")
    assert result.historical_trend.direction == expected


@pytest.mark.parametrize("values,days", [
    ([37] * 8, list(range(100, 108))),
    (ZERO_SLOPE_COUNTEREXAMPLE, [i * 100000000 for i in range(15)]),
    ([2147483647] * 15, list(range(2147483633, 2147483648))),
])
def test_exact_zero_constant_sparse_and_large_values(values, days):
    result = signals(values, days=days, parameters=SignalParameters(min_index_coverage="1e-64"))
    assert result.historical_trend.direction == "no_significant_trend"
    assert exact_ols_terms(list(zip(days, values)))[0] == 0


def test_exact_trend_uses_only_usable_points_across_internal_holes():
    result = signals([100, 102, None, 106, 108, None, 112, 114, 116, 118],
                     parameters=SignalParameters(min_trend_slope_copper_per_scan_index="2"))
    assert result.historical_trend.evidence.usable_observation_count == 8
    assert result.historical_trend.direction == "ascending"
    assert result.historical_trend.slope_copper_per_scan_index.value == 2


@pytest.mark.parametrize("samples", [[], [(1, 100)], [(1, 100), (2, 110)],
                                     [(1, 100), (1, 110), (2, 120)]])
def test_exact_ols_rejects_insufficient_or_duplicate_axes(samples):
    assert exact_ols_terms(samples) is None
