"""Pure descriptive statistics. Every derived operation uses Decimal precision 40."""
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext

from app.market.contracts import BucketPoint, MarketMetrics, MetricValue

PRECISION = 40


def analysis_context() -> Context:
    """Fresh deterministic context, independent of caller settings and flags."""
    return Context(prec=PRECISION, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                   capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])


def unavailable(unit: str, count: int, reason: str, first=None, last=None) -> MetricValue:
    status = "no_data" if reason in ("no_data", "no_axis") else (
        "insufficient_data" if reason == "insufficient_data" else "undefined"
    )
    return MetricValue(value=None, unit=unit, status=status, reason=reason,
                       observation_count=count, first_day=first, last_day=last)


def metric(value, unit: str, count: int, first=None, last=None) -> MetricValue:
    return MetricValue(value=Decimal(value), unit=unit, status="ok", observation_count=count,
                       first_day=first, last_day=last)


def change(samples: list[tuple[int, int]], unit: str) -> tuple[MetricValue, MetricValue]:
    with localcontext(analysis_context()):
        n = len(samples)
        first, last = (samples[0][0], samples[-1][0]) if samples else (None, None)
        if n < 2:
            reason = "no_data" if n == 0 else "insufficient_data"
            return unavailable(unit, n, reason, first, last), unavailable("percent", n, reason, first, last)
        baseline = Decimal(samples[0][1])
        delta = Decimal(samples[-1][1]) - baseline
        absolute = metric(delta, unit, n, first, last)
        percent = (metric(Decimal(100) * delta / baseline, "percent", n, first, last)
                   if baseline != 0 else unavailable("percent", n, "zero_baseline", first, last))
        return absolute, percent


def exact_ols_terms(samples: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Integer OLS numerator/denominator for 3B rule decisions, without rounding.

    Inputs are the validated integer bucket indices and copper prices. The public
    3A descriptive linear_slope calculation and its Decimal output stay unchanged.
    """
    n = len(samples)
    if n < 3 or len({d for d, _ in samples}) != n:
        return None
    xs = [d - samples[0][0] for d, _ in samples]
    ys = [p for _, p in samples]
    sx = sum(xs)
    numerator = n * sum(x * y for x, y in zip(xs, ys)) - sx * sum(ys)
    denominator = n * sum(x * x for x in xs) - sx * sx
    return (numerator, denominator) if denominator > 0 else None


def linear_slope(samples: list[tuple[int, int]]) -> MetricValue:
    with localcontext(analysis_context()):
        n = len(samples)
        unit = "copper/scan_index"
        if n < 3:
            return unavailable(unit, n, "no_data" if not n else "insufficient_data")
        # Center before summing; never replace sparse indices with ordinal positions.
        xs = [Decimal(d - samples[0][0]) for d, _ in samples]
        ys = [Decimal(v) for _, v in samples]
        xmean, ymean = sum(xs) / n, sum(ys) / n
        denominator = sum((x - xmean) ** 2 for x in xs)
        if denominator == 0 or len({d for d, _ in samples}) != n:
            return unavailable(unit, n, "invalid_axis")
        numerator = sum((x - xmean) * (y - ymean) for x, y in zip(xs, ys))
        return metric(numerator / denominator, unit, n, samples[0][0], samples[-1][0])


def compute_metrics(points: list[BucketPoint]) -> MarketMetrics:
    prices = sorted((p.scan_day, p.daily_minimum) for p in points if p.daily_minimum is not None)
    available = sorted((p.scan_day, p.daily_max_available) for p in points if p.daily_max_available is not None)
    n = len(prices)
    with localcontext(analysis_context()):
        if n:
            values = [Decimal(v) for _, v in prices]
            mean = sum(values) / n
            ordered = sorted(values)
            median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
            low = metric(min(values), "copper", n)
            avg = metric(mean, "copper", n)
            med = metric(median, "copper", n)
            first = metric(values[0], "copper", n, prices[0][0], prices[0][0])
            last = metric(values[-1], "copper", n, prices[-1][0], prices[-1][0])
        else:
            low = avg = med = first = last = unavailable("copper", 0, "no_data")
        if n >= 2:
            stddev = (sum((v - mean) ** 2 for v in values) / (n - 1)).sqrt()
            std = metric(stddev, "copper", n)
            cv = (metric(Decimal(100) * stddev / mean, "percent", n) if mean != 0
                  else unavailable("percent", n, "zero_mean"))
        else:
            reason = "no_data" if not n else "insufficient_data"
            std, cv = unavailable("copper", n, reason), unavailable("percent", n, reason)
        absolute, percent = change(prices, "copper")
        avail_absolute, avail_percent = change(available, "units")
        na = len(available)
        return MarketMetrics(
            minimum_copper=low, mean_daily_minimum_copper=avg, median_daily_minimum_copper=med,
            first_minimum_copper=first, last_minimum_copper=last, price_change_copper=absolute,
            price_change_pct=percent, minimum_stddev_copper=std, minimum_cv_pct=cv,
            trend_copper_per_scan_index=linear_slope(prices),
            first_max_available=(metric(available[0][1], "units", na, available[0][0], available[0][0])
                                 if na else unavailable("units", 0, "no_data")),
            last_max_available=(metric(available[-1][1], "units", na, available[-1][0], available[-1][0])
                                if na else unavailable("units", 0, "no_data")),
            availability_change_units=avail_absolute, availability_change_pct=avail_percent,
        )
