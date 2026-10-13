import pytest
from pydantic import ValidationError

from app.market.contracts import AnalysisRequest, WindowSpec
from app.market.errors import WindowError
from app.market.quality import coverage, quality
from app.market.windows import bucket_start, resolve_window
from tests.test_market_statistics import point


def test_observed_buckets_preserve_sparse_indices_and_short_window():
    spec = WindowSpec(window_type="observed_buckets", size=7)
    result = resolve_window(spec, "unknown", 2500, 2508, [2500, 2502, 2508])
    assert result.positions == [2500, 2502, 2508]
    assert result.anchor_day == 2508 and result.requested_position_count == 7
    assert result.calendar_start is None
    summary = coverage([point(d, 100) for d in result.positions], result)
    assert summary.price_ratio.value == 1
    assert summary.index_span_position_count == 9
    assert summary.unobserved_market_position_count == 6


def test_index_range_includes_market_absences_and_item_late_arrival():
    window = resolve_window(WindowSpec(window_type="index_range", start_day=10, end_day=12), "unknown", 10, 12, [10, 12])
    points = [point(10), point(11), point(12, 100, 0)]
    points[1].market_observed = False
    summary = coverage(points, window)
    assert summary.price_observation_count == 1 and summary.availability_observation_count == 1
    assert summary.missing_price_position_count == 2
    assert summary.observed_market_bucket_count == 2
    assert summary.unobserved_market_position_count == 1
    assert summary.price_ratio.model_dump(mode="json")["value"].startswith("0.333333")


@pytest.mark.parametrize("days", [7, 14, 30])
def test_verified_calendar_uses_market_anchor_and_86400_second_boundaries(days):
    window = resolve_window(WindowSpec(window_type="calendar_days", days=days),
                            "2019-12-31T21:00:00-03:00", 0, 29, [28, 29])
    assert window.positions == list(range(30 - days, 30))
    assert window.anchor_day == 29
    assert window.calendar_end_exclusive.isoformat() == "2020-01-31T00:00:00+00:00"
    assert (window.calendar_end_exclusive - window.calendar_start).total_seconds() == days * 86400


def test_explicit_end_and_unknown_dates():
    result = resolve_window(WindowSpec(window_type="observed_buckets", size=2, end_day=11), "unknown", 10, 99, [10, 11, 99])
    assert result.positions == [10, 11] and result.anchor_day == 11
    assert bucket_start("unknown", 2500) is None


@pytest.mark.parametrize("basis", ["unknown", "2020-01-01", "invalid"])
def test_unverified_calendar_is_rejected(basis):
    with pytest.raises(ValueError):
        resolve_window(WindowSpec(window_type="calendar_days", days=7), basis, 0, 30, [30])


def test_calendar_overflow_and_pre_epoch_are_rejected_but_index_remains_valid():
    assert bucket_start("2020-01-01T00:00:00Z", 2147483647) is None
    for end in (3, 2147483647):
        with pytest.raises(WindowError):
            resolve_window(WindowSpec(window_type="calendar_days", days=7, end_day=end),
                           "2020-01-01T00:00:00Z", 0, end, [end])
    result = resolve_window(WindowSpec(window_type="index_range", start_day=2147483647, end_day=2147483647),
                            "2020-01-01T00:00:00Z", 0, 2147483647, [2147483647])
    assert result.positions == [2147483647]


def test_no_market_axis_has_null_coverage_not_zero():
    result = resolve_window(WindowSpec(window_type="observed_buckets", size=7), "unknown", None, None, [])
    assert coverage([], result).price_ratio.reason == "no_axis"
    explicit = resolve_window(WindowSpec(window_type="index_range", start_day=10, end_day=12), "unknown", None, None, [])
    points = [point(d) for d in explicit.positions]
    for p in points:
        p.market_observed = False
    assert coverage(points, explicit).price_ratio.value == 0


@pytest.mark.parametrize("data", [
    dict(window_type="observed_buckets", size=367),
    dict(window_type="observed_buckets", size=0),
    dict(window_type="observed_buckets", size=1, days=7),
    dict(window_type="index_range", start_day=0, end_day=366),
    dict(window_type="index_range", start_day=4, end_day=3),
    dict(window_type="index_range", start_day=1),
    dict(window_type="calendar_days", days=8),
    dict(window_type="calendar_days", days=7, size=1),
])
def test_invalid_window_contracts(data):
    with pytest.raises(ValidationError):
        WindowSpec(**data)


def test_maximum_366_and_single_zero_index():
    assert len(resolve_window(WindowSpec(window_type="index_range", start_day=0, end_day=365), "unknown", 0, 365, []).positions) == 366
    assert resolve_window(WindowSpec(window_type="observed_buckets", size=1), "unknown", 0, 0, [0]).positions == [0]
