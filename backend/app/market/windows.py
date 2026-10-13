"""Addon indices are nominal 86400-second buckets, not scan timestamps."""
from datetime import datetime, timedelta

from app.market.contracts import ResolvedWindow, WindowSpec, canonical_basis
from app.market.errors import WindowError


def bucket_start(basis: str, day: int) -> datetime | None:
    basis = canonical_basis(basis)
    if basis == "unknown":
        return None
    try:
        return datetime.fromisoformat(basis) + timedelta(days=day)
    except OverflowError:
        return None


def resolve_window(spec: WindowSpec, basis: str, market_first: int | None,
                   market_last: int | None, observed_days: list[int]) -> ResolvedWindow:
    basis = canonical_basis(basis)
    if observed_days != sorted(set(observed_days)):
        raise WindowError("market axis must contain sorted unique indices")
    anchor = spec.end_day if spec.end_day is not None else market_last
    requested = spec.size if spec.window_type == "observed_buckets" else (
        spec.days if spec.window_type == "calendar_days" else spec.end_day - spec.start_day + 1
    )
    start = end = None
    calendar_start = calendar_end = None
    if spec.window_type == "observed_buckets":
        positions = [d for d in observed_days if anchor is not None and d <= anchor][-spec.size:]
        if positions:
            start, end = positions[0], positions[-1]
    elif spec.window_type == "index_range":
        start, end = spec.start_day, spec.end_day
        positions = list(range(start, end + 1))
    else:
        if basis == "unknown":
            raise WindowError("calendar_days requires a verified temporal_basis")
        positions = []
        if anchor is not None:
            start, end = anchor - spec.days + 1, anchor
            if start < 0:
                raise WindowError("calendar window starts before index zero")
            calendar_start = bucket_start(basis, start)
            calendar_end = bucket_start(basis, end + 1)
            if calendar_start is None or calendar_end is None:
                raise WindowError("calendar window exceeds representable datetime range")
            positions = list(range(start, end + 1))
    return ResolvedWindow(
        spec=spec, anchor_day=anchor, market_first_day=market_first, market_last_day=market_last,
        start_day=start, end_day=end, positions=positions, requested_position_count=requested,
        calendar_start=calendar_start, calendar_end_exclusive=calendar_end,
    )
