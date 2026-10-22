"""Single-file polling observer. Parsing and archive decisions stay in 5A.1."""
from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import stat
from threading import Event
import time
from typing import Callable

from app.local_capture.archive import (
    CaptureError, _checked_path, _destination, _fingerprint, _read_stable,
    capture_file, default_archive_directory,
)
from app.local_capture.contracts import CaptureResult, Origin


class WatchError(Exception):
    """Configuration error code without paths or exception details."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WatchSettings:
    poll_interval: float = 2.0
    debounce_seconds: float = 2.0
    stable_seconds: float = 4.0
    retry_delay: float = 2.0
    max_attempts: int = 3
    recovery_interval: float = 30.0

    def __post_init__(self):
        for value, lower, upper in (
            (self.poll_interval, 0.25, 60), (self.debounce_seconds, 0, 300),
            (self.stable_seconds, 0.25, 300), (self.retry_delay, 0.25, 60),
            (self.recovery_interval, 1, 3600),
        ):
            if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
                raise WatchError("invalid_timing")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise WatchError("invalid_retry_limit")


@dataclass(frozen=True)
class WatchEvent:
    kind: str
    code: str | None = None
    capture_id: str | None = None
    comparison: str | None = None
    market_count: int | None = None
    item_count: int | None = None
    new_market_states: int | None = None


VALIDATION_CODES = {"invalid_content", "file_too_large", "metadata_too_large", "unsafe_file", "unsafe_path"}
TEMPORARY_CODES = {"source_unavailable", "source_changed", "archive_busy"}


class AuctionatorWatcher:
    """Observe one configured path; keep only the current candidate/success in RAM.

    step(now) has no sleeps and is deterministic with a supplied monotonic clock.
    run() adds moderate polling and clean KeyboardInterrupt/stop-event handling.
    """
    def __init__(self, source: Path, destination: Path | None = None, *,
                 settings: WatchSettings | None = None, origin_id=None, source_version=None,
                 serialized_codec=None, market_mapping=None,
                 on_event: Callable[[WatchEvent], None] | None = None):
        try:
            self.settings = settings if settings is not None else WatchSettings()
            if not isinstance(self.settings, WatchSettings):
                raise WatchError("invalid_settings")
            self.source = _checked_path(source)
            self.destination = _destination(destination if destination is not None else default_archive_directory())
            if not self.source.parent.is_dir():
                raise WatchError("source_parent_unavailable")
            if self.source.exists() and not stat.S_ISREG(self.source.lstat().st_mode):
                raise WatchError("invalid_source")
            if (self.source.parent == self.destination or self.source.parent in self.destination.parents
                    or self.destination in self.source.parents):
                raise WatchError("overlapping_directories")
            Origin(origin_id=origin_id)
            if source_version not in (None, "340", "341") or serialized_codec not in (None, "cbor-definite"):
                raise WatchError("invalid_options")
            mapping = dict(market_mapping) if market_mapping is not None else {}
            for key, rule in mapping.items():
                if (not isinstance(key, str) or not 1 <= len(key) <= 200 or key != key.strip()
                        or any(ord(c) < 32 for c in key) or key in ("PvE", "PvP", "HC", "RP")
                        or rule not in ("PvE", "PvP", "HC", "RP")):
                    raise WatchError("invalid_options")
            self.capture_options = dict(origin_id=origin_id, source_version=source_version,
                                        serialized_codec=serialized_codec, market_mapping=mapping)
        except WatchError:
            raise
        except CaptureError as error:
            raise WatchError(error.code) from None
        except (OSError, ValueError, TypeError, RuntimeError):
            raise WatchError("invalid_configuration") from None
        self.on_event = on_event
        self.last_successful_sha256: str | None = None
        self._last_result: CaptureResult | None = None
        self._candidate = None
        self._stable_since = 0.0
        self._capture_attempts = 0
        self._capture_after = 0.0
        self._probe_attempts = 0
        self._probe_after = 0.0
        self._availability = None
        self._reported_errors = set()
        self._started = False
        self._last_tick = -math.inf

    def _emit(self, kind, **details):
        if self.on_event is not None:
            self.on_event(WatchEvent(kind=kind, **details))

    def _error_once(self, kind, code):
        token = (kind, code)
        if token not in self._reported_errors:
            self._reported_errors.add(token)
            self._emit(kind, code=code)

    def _backoff(self, now, *, probe):
        attempts = self._probe_attempts + 1 if probe else self._capture_attempts + 1
        exhausted = attempts >= self.settings.max_attempts
        deadline = now + (self.settings.recovery_interval if exhausted else self.settings.retry_delay)
        if probe:
            self._probe_attempts, self._probe_after = (0 if exhausted else attempts), deadline
        else:
            self._capture_attempts, self._capture_after = (0 if exhausted else attempts), deadline
        if exhausted:
            self._error_once("retry_deferred", "probe" if probe else "capture")

    def _result_event(self, result, *, identical=False):
        self._emit(
            "identical" if identical or result.status == "duplicate" else "archived",
            capture_id=result.metadata.capture_id[:12], comparison=result.comparison.status,
            market_count=len(result.metadata.markets), item_count=result.metadata.item_count,
            new_market_states=0 if identical else len(result.comparison.new_market_states),
        )

    def step(self, now: float | None = None):
        now = time.monotonic() if now is None else now
        if not math.isfinite(now) or now < self._last_tick:
            raise WatchError("invalid_clock")
        self._last_tick = now
        if not self._started:
            self._started = True
            self._emit("watching")
        if now < self._probe_after:
            return
        try:
            raw = _read_stable(self.source)
            candidate = (sha256(raw).hexdigest(), _fingerprint(self.source.lstat()))
            del raw  # No second original retained in RAM while 5A.1 parses/copies it.
        except FileNotFoundError:
            self._candidate = None
            self._probe_attempts = 0
            if self._availability != "missing":
                self._emit("missing")
            self._availability = "missing"
            return
        except (CaptureError, OSError) as error:
            code = error.code if isinstance(error, CaptureError) else "source_unavailable"
            self._candidate = None
            if self._availability != code:
                self._reported_errors.clear()
            self._availability = code
            self._error_once("validation_error" if code in VALIDATION_CODES else "unavailable", code)
            self._backoff(now, probe=True)
            return
        if self._availability not in (None, "ready"):
            self._emit("available")
        self._availability = "ready"
        self._probe_attempts = 0
        self._probe_after = 0.0
        if candidate != self._candidate:
            self._candidate = candidate
            self._stable_since = now
            self._capture_attempts = 0
            self._capture_after = 0.0
            self._reported_errors.clear()
            self._emit("waiting")
            return
        quiet_period = max(self.settings.debounce_seconds, self.settings.stable_seconds)
        if now - self._stable_since < quiet_period or now < self._capture_after:
            return
        if candidate[0] == self.last_successful_sha256:
            # The prior success was validated by 5A.1. Rehashing still detects
            # in-place edits with unchanged size/mtime; do not parse it every poll.
            if self._capture_after != math.inf:
                self._result_event(self._last_result, identical=True)
                self._capture_after = math.inf
            return
        try:
            result = capture_file(self.source, self.destination, expected_source_sha256=candidate[0],
                                  **self.capture_options)
        except Exception as error:
            code = error.code if isinstance(error, CaptureError) else "archive_failed"
            kind = "validation_error" if code in VALIDATION_CODES else "unavailable" if code in TEMPORARY_CODES else "archive_error"
            self._error_once(kind, code if code in VALIDATION_CODES | TEMPORARY_CODES else "archive_failed")
            self._backoff(now, probe=False)
            if code == "source_changed":
                self._candidate = None  # A new quiet interval is required; never mark the probed bytes successful.
            return
        self.last_successful_sha256 = result.metadata.source_sha256
        self._last_result = result
        self._capture_after = math.inf
        self._capture_attempts = 0
        self._reported_errors.clear()
        self._result_event(result)

    def run(self, *, stop_event: Event | None = None, clock=time.monotonic, wait=time.sleep):
        try:
            while stop_event is None or not stop_event.is_set():
                self.step(clock())
                if stop_event is None:
                    wait(self.settings.poll_interval)
                else:
                    stop_event.wait(self.settings.poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self._emit("stopped")
