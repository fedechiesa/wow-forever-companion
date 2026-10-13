from decimal import Decimal, Inexact, InvalidOperation, Rounded, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_UP, localcontext

import pytest
from pydantic import ValidationError

from app.market.contracts import BucketPoint, MetricValue
from app.market.statistics import change, compute_metrics, linear_slope
from app.market.quality import coverage
from app.market.contracts import WindowSpec
from app.market.windows import resolve_window


def point(day, price=None, available=None):
    return BucketPoint(scan_day=day, market_observed=True, daily_minimum=price,
                       minimum_origin="unknown" if price is not None else None, daily_max_available=available)


def test_manual_price_statistics_and_decimal_serialization():
    metrics = compute_metrics([point(10, 100), point(11, 120), point(12, 80)])
    expected = {"minimum_copper": 80, "mean_daily_minimum_copper": 100, "median_daily_minimum_copper": 100,
                "price_change_copper": -20, "price_change_pct": -20, "minimum_stddev_copper": 20,
                "minimum_cv_pct": 20, "trend_copper_per_scan_index": -10}
    for name, value in expected.items():
        result = getattr(metrics, name)
        assert result.value == Decimal(value) and result.status == "ok" and result.observation_count == 3
        assert isinstance(metrics.model_dump(mode="json")[name]["value"], str)
    assert metrics.price_change_copper.first_day == 10
    assert metrics.price_change_copper.last_day == 12


def test_even_median_fraction_and_noninteger_mean_are_not_rounded():
    metrics = compute_metrics([point(1, 1), point(2, 2)])
    assert metrics.median_daily_minimum_copper.value == Decimal("1.5")
    assert metrics.mean_daily_minimum_copper.value == Decimal("1.5")
    thirds = compute_metrics([point(1, 1), point(2, 1), point(3, 2)])
    assert thirds.mean_daily_minimum_copper.model_dump(mode="json")["value"] == "1.333333333333333333333333333333333333333"


@pytest.mark.parametrize("n", [0, 1, 2])
def test_small_samples_have_explicit_states(n):
    metrics = compute_metrics([point(i, 100 + i) for i in range(n)])
    assert metrics.minimum_copper.status == ("ok" if n else "no_data")
    assert metrics.price_change_copper.status == ("ok" if n == 2 else "insufficient_data" if n else "no_data")
    assert metrics.minimum_stddev_copper.status == ("ok" if n == 2 else "insufficient_data" if n else "no_data")
    assert metrics.trend_copper_per_scan_index.value is None
    assert metrics.trend_copper_per_scan_index.reason == ("insufficient_data" if n else "no_data")


def test_zero_baselines_and_zero_mean():
    metrics = compute_metrics([point(1, 0, 0), point(2, 20, 5)])
    assert metrics.price_change_copper.value == 20
    assert metrics.price_change_pct.reason == "zero_baseline"
    assert metrics.availability_change_units.value == 5
    assert metrics.availability_change_pct.reason == "zero_baseline"
    zeros = compute_metrics([point(1, 0), point(2, 0), point(3, 0)])
    assert zeros.minimum_stddev_copper.value == 0
    assert zeros.minimum_cv_pct.reason == "zero_mean"
    assert zeros.trend_copper_per_scan_index.value == 0


def test_availability_missing_is_excluded_but_explicit_zero_is_used():
    metrics = compute_metrics([point(10, available=5), point(11), point(12, available=0)])
    assert metrics.first_max_available.value == 5
    assert metrics.last_max_available.value == 0
    assert metrics.availability_change_units.value == -5
    assert metrics.availability_change_pct.value == -100
    assert metrics.availability_change_pct.observation_count == 2
    assert metrics.minimum_copper.status == "no_data"


def test_sparse_trend_uses_real_indices_and_high_indices_are_stable():
    samples = [(10, 100), (11, 120), (13, 80)]
    with localcontext() as ctx:
        ctx.prec = 40
        assert abs(linear_slope(samples).value - Decimal(-60) / 7) < Decimal("1e-36")
    shifted = [(2147483640 + d - 10, p) for d, p in samples]
    assert linear_slope(samples).value == linear_slope(shifted).value


@pytest.mark.parametrize("samples", [[(1, 1), (1, 2), (1, 3)], [(1, 1), (1, 2), (2, 3)]])
def test_invalid_trend_axis(samples):
    assert linear_slope(samples).reason == "invalid_axis"


def test_unsorted_input_is_ordered_by_index_not_reception():
    metrics = compute_metrics([point(12, 80), point(10, 100), point(11, 120)])
    assert metrics.price_change_copper.value == -20


def test_standard_deviation_is_sample_not_population():
    result = compute_metrics([point(0, 0), point(1, 2)]).minimum_stddev_copper
    with localcontext() as ctx:
        ctx.prec = 40
        assert result.value == Decimal(2).sqrt()


@pytest.mark.parametrize("invalid", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_response_forbids_nonfinite_decimal(invalid):
    with pytest.raises(ValidationError):
        MetricValue(value=invalid, unit="copper", status="ok", observation_count=2)


def test_change_handles_no_or_one_sample_without_fake_zero():
    assert change([], "copper")[0].reason == "no_data"
    assert change([(1, 100)], "copper")[0].reason == "insufficient_data"


@pytest.mark.parametrize("number", ["0E-39", "1E-50", "-1E-39", "1.234567890123456789012345678901234567890", "-123"])
def test_fixed_decimal_serialization_preserves_every_digit_and_openapi(number):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from tests.test_market_validation import assert_openapi_json

    metric = MetricValue(value=Decimal(number), unit="copper", status="ok", observation_count=3)
    result = metric.model_dump(mode="json")
    assert "e" not in result["value"].lower()
    assert Decimal(result["value"]).as_tuple() == Decimal(number).as_tuple()
    assert isinstance(metric.model_dump()["value"], Decimal)
    with TestClient(create_app()) as client:
        document = client.get("/openapi.json").json()
    schema = document["components"]["schemas"]["MetricValue"]
    assert_openapi_json(result, schema, document)
    invalid = result | {"value": "0E-39"}
    with pytest.raises(AssertionError):
        assert_openapi_json(invalid, schema, document)


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN])
def test_statistics_and_coverage_ignore_ambient_rounding_traps_and_limits(rounding):
    points = [point(10, 1000000, 1), point(11, 1000000), point(13, 1000001)]
    window = resolve_window(WindowSpec(window_type="observed_buckets", size=3), "unknown", 10, 13, [10, 11, 13])
    expected = compute_metrics(points).model_dump_json()
    expected_coverage = coverage(points, window).model_dump_json()
    expected_change = [m.model_dump_json() for m in change([(10, 3), (13, 1)], "copper")]
    expected_slope = linear_slope([(10, 1), (11, 1), (13, 2)]).model_dump_json()
    with localcontext() as ambient:
        ambient.rounding = rounding
        ambient.prec, ambient.Emax, ambient.Emin = 2, 2, -2
        ambient.traps[Inexact] = ambient.traps[Rounded] = True
        ambient.flags[InvalidOperation] = True  # Existing caller flags must also survive unchanged.
        flags_before = dict(ambient.flags)
        assert compute_metrics(points).model_dump_json() == expected
        assert coverage(points, window).model_dump_json() == expected_coverage
        assert [m.model_dump_json() for m in change([(10, 3), (13, 1)], "copper")] == expected_change
        assert linear_slope([(10, 1), (11, 1), (13, 2)]).model_dump_json() == expected_slope
        assert ambient.rounding == rounding and ambient.prec == 2
        assert ambient.traps[Inexact] and ambient.traps[Rounded]
        assert dict(ambient.flags) == flags_before
