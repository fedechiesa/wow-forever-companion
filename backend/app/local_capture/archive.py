"""Bounded reads and recoverable, append-only local evidence publication.

Only cooperating processes may write this private directory. Windows reads deny
write/delete sharing; other platforms additionally rely on double-read checks.
No promise of protection against an administrator or a hostile directory owner.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from app.ingestion.saved_variables import MAX_BYTES
from app.local_capture.decoder import CaptureAdapter
from app.local_capture.contracts import (
    CaptureMetadata, CaptureResult, Comparison, Origin, canonical_json, describe,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REPARSE_POINT = 0x400


class CaptureError(Exception):
    """Stable public code; never includes paths, Lua, driver or validation details."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def default_archive_directory() -> Path:
    base = (Path(os.environ["LOCALAPPDATA"]) if os.name == "nt" and os.environ.get("LOCALAPPDATA")
            else Path.home() / ".local" / "share")
    return base / "WoWForeverCompanion" / "local-capture"


def _checked_path(value) -> Path:
    supplied = Path(value).expanduser()
    if os.name == "nt" and any(p not in (".", "..") and p.endswith((" ", "."))
                               for p in supplied.parts):
        raise CaptureError("unsafe_path")  # Reject ambiguous Win32 trailing-dot/space aliases.
    path = Path(os.path.abspath(supplied))
    if os.name == "nt" and (path.drive.startswith("\\\\") or any(":" in p for p in path.parts[1:])):
        raise CaptureError("unsafe_path")  # No network/device paths or NTFS alternate streams.
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
            raise CaptureError("unsafe_path")
    # Existing ancestors can have 8.3 names on Windows. Resolve them before the
    # repository boundary check; a lexical comparison would allow an alias of
    # this project as a capture destination. Links were rejected above.
    return path.resolve()


def _destination(value) -> Path:
    path = _checked_path(value)
    if path == REPOSITORY_ROOT or REPOSITORY_ROOT in path.parents:
        raise CaptureError("repository_destination")
    # Protect this project explicitly, even if .git is absent (source checkout)
    # or .gitignore excludes the destination. A home-directory dotfiles repo
    # must not make OS application-data / temporary storage unusable.
    if path.exists() and not path.is_dir():
        raise CaptureError("invalid_destination")
    return path


def _mkdir(path):
    for component in reversed((path, *path.parents)):
        _checked_path(component)
        if component.is_dir():
            continue
        try:
            component.mkdir(mode=0o700)
        except FileExistsError:
            if not component.is_dir():
                raise CaptureError("invalid_destination") from None
    _checked_path(path)


def _fingerprint(info):
    # Windows 3.13 lstat reports creation time in ctime while fstat can report
    # change time. They are not comparable after a completed overwrite.
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            0 if os.name == "nt" else info.st_ctime_ns)


def _open_read(path):
    if os.name != "nt":
        return os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    # Python open() does not deny writers on Windows. Hold this handle for both
    # reads; an already-open writer also makes CreateFileW fail its share check.
    import ctypes
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(path), 0x80000000, 0x1, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "capture read unavailable")
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle(handle)
        raise


def _read_pass(stream):
    return stream.read(MAX_BYTES + 1)


def _read_stable(path, *, single_link=False):
    path = _checked_path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or (single_link and before.st_nlink != 1):
        raise CaptureError("unsafe_file")
    if before.st_size > MAX_BYTES:
        raise CaptureError("file_too_large")
    with os.fdopen(_open_read(path), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if _fingerprint(before) != _fingerprint(opened):
            raise CaptureError("source_changed")
        raw = _read_pass(stream)
        stream.seek(0)
        repeated = _read_pass(stream)
        after = os.fstat(stream.fileno())
    _checked_path(path)
    if (len(raw) > MAX_BYTES or len(repeated) > MAX_BYTES):
        raise CaptureError("file_too_large")
    if (raw != repeated or len(raw) != opened.st_size or _fingerprint(opened) != _fingerprint(after)
            or _fingerprint(after) != _fingerprint(path.lstat())):
        raise CaptureError("source_changed")
    return raw


@contextmanager
def _archive_lock(root):
    path = _checked_path(root / ".capture.lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CaptureError("unsafe_file")
        if not info.st_size:
            os.write(descriptor, b"0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise CaptureError("archive_busy") from None
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _sync_directory(path):
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _write_new(path, raw):
    """Exclusive creation; a failed/partial write stays in pending, never published."""
    _checked_path(path)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if _read_stable(path, single_link=True) != raw:
        raise CaptureError("archive_integrity")
    path.chmod(stat.S_IREAD)  # Read-only on Windows, 0400 on POSIX; no content rewrites.


def _verify_entry(entry):
    """Never trust a filename or cached metadata hash without checking its evidence."""
    _checked_path(entry)
    if not entry.is_dir() or {p.name for p in entry.iterdir()} != {"Auctionator.lua", "metadata.json"}:
        raise CaptureError("archive_integrity")
    try:
        for name in ("Auctionator.lua", "metadata.json"):
            if _checked_path(entry / name).stat().st_mode & stat.S_IWRITE:
                raise CaptureError("archive_integrity")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate metadata key")
                result[key] = value
            return result

        metadata = CaptureMetadata.model_validate(json.loads(
            _read_stable(entry / "metadata.json", single_link=True), object_pairs_hook=unique))
        raw = _read_stable(entry / "Auctionator.lua", single_link=True)
        mapping = {m.market_key: m.ruleset for m in metadata.markets if m.market_key not in ("PvE", "PvP", "HC", "RP")}
        decoded = CaptureAdapter().decode_bytes(raw, serialized_codec=metadata.selected_serialized_codec,
                                               market_mapping=mapping)
        expected = describe(decoded, source_bytes=len(raw), captured_at=metadata.captured_at,
                            origin=metadata.origin, source_version=metadata.selected_source_version,
                            serialized_codec=metadata.selected_serialized_codec)
        if entry.name != decoded.source_hash or expected != metadata:
            raise CaptureError("archive_integrity")
        return metadata
    except (ValueError, OSError, RecursionError):
        raise CaptureError("archive_integrity") from None


def _publish(stage, final):
    _checked_path(stage)
    _checked_path(final)
    if os.path.lexists(final):
        raise CaptureError("archive_collision")
    # Same filesystem and serialized by the OS lock. Complete nonempty directories
    # are never replaced. The private root must not have hostile concurrent writers.
    os.rename(stage, final)
    _sync_directory(final.parent)
    _sync_directory(stage.parent)


def capture_file(source: Path, destination: Path | None = None, *, origin_id=None,
                 source_version=None, serialized_codec=None, market_mapping=None,
                 expected_source_sha256: str | None = None) -> CaptureResult:
    """Validate the exact bytes read, then archive them. Does not import any data.

    A retry can use either the original source or a retained pending/Auctionator.lua.
    Different full hashes always retain independent originals, even for a known
    market state. Exact duplicates return the original immutable metadata.
    """
    try:
        root = _destination(destination if destination is not None else default_archive_directory())
        origin = Origin(origin_id=origin_id)
        if source_version not in (None, "340", "341"):
            raise CaptureError("invalid_options")
        if expected_source_sha256 is not None and (
            not isinstance(expected_source_sha256, str) or len(expected_source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_source_sha256)
        ):
            raise CaptureError("invalid_options")
        try:
            raw = _read_stable(source)
        except OSError:
            raise CaptureError("source_unavailable") from None
        if expected_source_sha256 is not None and sha256(raw).hexdigest() != expected_source_sha256:
            raise CaptureError("source_changed")
        try:
            decoded = CaptureAdapter().decode_bytes(raw, serialized_codec=serialized_codec,
                                                   market_mapping=market_mapping)
            metadata = describe(decoded, source_bytes=len(raw), captured_at=datetime.now(timezone.utc),
                                origin=origin, source_version=source_version, serialized_codec=serialized_codec)
        except ValueError:
            raise CaptureError("invalid_content") from None
        if len(canonical_json(metadata.model_dump(mode="json"))) > MAX_BYTES:
            raise CaptureError("metadata_too_large")
        _mkdir(root)
        with _archive_lock(root):
            _destination(root)
            completed, pending = root / "captures", root / "pending"
            _mkdir(completed)
            _mkdir(pending)
            previous = [_verify_entry(entry) for entry in sorted(completed.iterdir())]
            for old in previous:
                if old.capture_id == metadata.capture_id:
                    if old.market_sha256 != metadata.market_sha256:
                        raise CaptureError("capture_context_conflict")
                    return CaptureResult(status="duplicate", metadata=old, comparison=Comparison(
                        status="equivalent", equivalent_capture_id=old.capture_id, new_market_states=[]))
            equivalent = next((m for m in previous if m.market_sha256 == metadata.market_sha256), None)
            known = {m.state_sha256 for capture in previous for m in capture.markets}
            comparison = Comparison(
                status="equivalent" if equivalent else "changed" if previous else "first",
                equivalent_capture_id=equivalent.capture_id if equivalent else None,
                new_market_states=sorted({m.state_sha256 for m in metadata.markets} - known),
            )
            stage = _checked_path(pending / metadata.capture_id)
            if stage.exists():
                try:
                    recovered = _verify_entry(stage)
                    if recovered.market_sha256 != metadata.market_sha256:
                        raise CaptureError("capture_context_conflict")
                    metadata = recovered
                except CaptureError as error:
                    if error.code != "archive_integrity":
                        raise
                    # Retain even partial/corrupt artifacts for private recovery;
                    # never delete a valid Lua because a later metadata write failed.
                    quarantine = pending / ("incomplete-" + metadata.capture_id + "-" + uuid4().hex)
                    os.rename(stage, quarantine)
            if not stage.exists():
                _mkdir(stage)
                _write_new(stage / "Auctionator.lua", raw)
                _write_new(stage / "metadata.json", canonical_json(metadata.model_dump(mode="json")))
                _sync_directory(stage)
            _verify_entry(stage)
            _publish(stage, completed / metadata.capture_id)
            return CaptureResult(status="archived", metadata=metadata, comparison=comparison)
    except CaptureError:
        raise
    except ValueError:
        raise CaptureError("invalid_options") from None
    except OSError:
        raise CaptureError("archive_failed") from None
