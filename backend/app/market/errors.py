class SeriesNotFound(Exception):
    """The caller's exact selection does not exist."""


class SeriesIntegrityError(Exception):
    """Persisted evidence cannot safely form a compatible series."""


class WindowError(ValueError):
    """A requested window cannot be represented honestly."""
