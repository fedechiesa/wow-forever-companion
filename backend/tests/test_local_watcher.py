"""Deterministic synthetic polling tests. No game, private source, DB or sleeps."""
from dataclasses import replace
from hashlib import sha256
import json
import locale
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event

import pytest

import app.local_capture.watcher as module
from app.local_capture import CaptureError, capture_file
from app.local_capture.watcher import AuctionatorWatcher, WatchError, WatchSettings
from scripts import watch_auctionator as cli
from test_local_capture import lua


SETTINGS = WatchSettings(poll_interval=0.25, debounce_seconds=1, stable_seconds=2,
                         retry_delay=1, max_attempts=2, recovery_interval=5)
CLI = Path(__file__).resolve().parents[1] / "scripts" / "watch_auctionator.py"
PROJECT = CLI.parents[2]


@pytest.fixture
def paths(tmp_path):
    source = tmp_path / "simulation-source" / "Auctionator.lua"
    source.parent.mkdir()
    return source, tmp_path / "private-archive"


def observer(paths, **options):
    events = []
    watcher = AuctionatorWatcher(*paths, settings=options.pop("settings", SETTINGS),
                                on_event=events.append, **options)
    return watcher, events


def archived(paths):
    directory = paths[1] / "captures"
    return sorted(directory.iterdir()) if directory.exists() else []


def drive(watcher, *times):
    for now in times:
        watcher.step(now)


def capture_count(monkeypatch):
    calls = []
    real = module.capture_file
    def record(*args, **kwargs):
        calls.append(kwargs.get("expected_source_sha256"))
        return real(*args, **kwargs)
    monkeypatch.setattr(module, "capture_file", record)
    return calls


def test_existing_source_is_inspected_at_start_then_captured_only_once(paths, monkeypatch):
    paths[0].write_bytes(lua())
    before = paths[0].stat()
    calls = capture_count(monkeypatch)
    watcher, events = observer(paths)
    drive(watcher, 0, 1)
    assert not archived(paths)
    assert watcher.last_successful_sha256 is None
    drive(watcher, 2, 3, 20, 100)
    assert len(calls) == len(archived(paths)) == 1
    assert calls == [sha256(lua()).hexdigest()]
    assert [e.kind for e in events] == ["watching", "waiting", "archived"]
    result = events[-1]
    assert (result.comparison, result.market_count, result.item_count, result.new_market_states) == ("first", 1, 1, 1)
    assert result.capture_id == calls[0][:12]
    after = paths[0].stat()
    assert paths[0].read_bytes() == lua() and before.st_mtime_ns == after.st_mtime_ns and before.st_mode == after.st_mode


def test_missing_source_can_appear_after_start_without_repetitive_messages(paths):
    watcher, events = observer(paths)
    drive(watcher, 0, 1, 2)
    assert [e.kind for e in events] == ["watching", "missing"]
    paths[0].write_bytes(lua())
    drive(watcher, 3, 4, 5)
    assert len(archived(paths)) == 1
    assert [e.kind for e in events] == ["watching", "missing", "available", "waiting", "archived"]


def test_multistage_write_restarts_quiet_period_before_parsing(paths, monkeypatch):
    calls = capture_count(monkeypatch)
    watcher, _ = observer(paths)
    paths[0].write_bytes(lua()[:30])
    drive(watcher, 0, 1)
    paths[0].write_bytes(lua()[:-1])
    drive(watcher, 1.5, 2.5)
    paths[0].write_bytes(lua())
    drive(watcher, 3, 4.9)
    assert not calls and not archived(paths)
    drive(watcher, 5, 6, 7)
    assert len(calls) == 1 and len(archived(paths)) == 1


def test_debounce_and_stabilization_both_apply(paths):
    paths[0].write_bytes(lua())
    watcher, _ = observer(paths, settings=replace(SETTINGS, debounce_seconds=5, stable_seconds=1))
    drive(watcher, 0, 1, 4.9)
    assert not archived(paths)
    watcher.step(5)
    assert len(archived(paths)) == 1


def test_identical_rewrite_is_not_reparsed_and_logs_once_after_settling(paths, monkeypatch):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    calls = capture_count(monkeypatch)
    drive(watcher, 0, 2)
    info = paths[0].stat()
    paths[0].write_bytes(lua())
    os.utime(paths[0], ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
    drive(watcher, 3, 5, 6, 20)
    assert len(calls) == 1 and len(archived(paths)) == 1
    assert [e.kind for e in events].count("identical") == 1


def test_config_only_change_keeps_originals_without_new_economic_state(paths):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    drive(watcher, 0, 2)
    paths[0].write_bytes(lua() + b'\nCONFIG={private="SYNTHETIC_SECRET"}\nVENDORS={["1"]=23}')
    drive(watcher, 3, 5, 8)
    successes = [e for e in events if e.kind == "archived"]
    assert len(archived(paths)) == 2 and len(successes) == 2
    assert successes[-1].comparison == "equivalent" and successes[-1].new_market_states == 0
    metadata = [json.loads((entry / "metadata.json").read_bytes()) for entry in archived(paths)]
    assert len({m["market_sha256"] for m in metadata}) == 1
    messages = "\n".join(cli.format_event(e) for e in events)
    assert "sin cambios económicos" in messages
    assert "SYNTHETIC_SECRET" not in messages and str(paths[0]) not in messages


def test_real_change_in_same_bucket_adds_independent_evidence(paths):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    drive(watcher, 0, 2)
    paths[0].write_bytes(lua(high=200, minimum=200))
    drive(watcher, 3, 5)
    assert len(archived(paths)) == 2
    states = [e for e in events if e.kind == "archived"]
    assert [e.new_market_states for e in states] == [1, 1]
    assert states[-1].comparison == "changed"
    metadata = [json.loads((entry / "metadata.json").read_bytes()) for entry in archived(paths)]
    assert all(m["markets"][0]["first_bucket"] == 2485 for m in metadata)
    assert len({m["market_sha256"] for m in metadata}) == 2


@pytest.mark.parametrize("atomic", [False, True])
def test_same_size_restored_mtime_change_is_detected_by_bytes(paths, atomic):
    paths[0].write_bytes(lua())
    watcher, _ = observer(paths)
    drive(watcher, 0, 2)
    info = paths[0].stat()
    replacement = lua(high=200)
    assert len(replacement) == info.st_size
    if atomic:
        temporary = paths[0].with_suffix(".new")
        temporary.write_bytes(replacement)
        os.utime(temporary, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(temporary, paths[0])
    else:
        paths[0].write_bytes(replacement)
        os.utime(paths[0], ns=(info.st_atime_ns, info.st_mtime_ns))
    assert paths[0].stat().st_mtime_ns == info.st_mtime_ns
    drive(watcher, 3, 5)
    assert len(archived(paths)) == 2


def test_delete_and_recreate_is_observed_and_deduplicated(paths, monkeypatch):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    calls = capture_count(monkeypatch)
    drive(watcher, 0, 2)
    paths[0].unlink()
    drive(watcher, 3, 4)
    paths[0].write_bytes(lua())
    drive(watcher, 5, 7)
    assert len(calls) == len(archived(paths)) == 1
    assert [e.kind for e in events].count("missing") == 1
    assert events[-1].kind == "identical"
    paths[0].unlink()
    watcher.step(8)
    paths[0].write_bytes(lua(high=200))
    drive(watcher, 9, 11)
    assert len(archived(paths)) == 2


def test_invalid_content_is_not_successfully_processed_and_corrected_bytes_retry(paths, monkeypatch):
    paths[0].write_bytes(b"invalid PRIVATE_CONTENT")
    watcher, events = observer(paths)
    calls = capture_count(monkeypatch)
    drive(watcher, 0, 2, 3, 4, 7)
    assert len(calls) == 2  # exhausted batch is paused until t=8
    assert watcher.last_successful_sha256 is None and not archived(paths)
    assert [e.kind for e in events].count("validation_error") == 1
    assert [e.kind for e in events].count("retry_deferred") == 1
    paths[0].write_bytes(lua())
    drive(watcher, 7.5, 9.5)
    assert len(archived(paths)) == 1 and watcher.last_successful_sha256 == sha256(lua()).hexdigest()
    assert "PRIVATE_CONTENT" not in str(events)


@pytest.mark.parametrize("failure", ["archive_busy", "archive_failed", "archive_integrity", "unexpected"])
def test_archive_failures_are_bounded_recover_later_and_never_mark_success(paths, monkeypatch, failure):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    calls = []
    real = module.capture_file
    broken = True
    def capture(*args, **kwargs):
        calls.append(1)
        if broken:
            if failure == "unexpected":
                raise OSError("SYNTHETIC_PRIVATE_EXCEPTION")
            raise CaptureError(failure)
        return real(*args, **kwargs)
    monkeypatch.setattr(module, "capture_file", capture)
    drive(watcher, 0, 2, 3, 4, 7)
    assert len(calls) == 2 and watcher.last_successful_sha256 is None
    broken = False
    drive(watcher, 8, 9, 20)
    assert len(calls) == 3 and len(archived(paths)) == 1
    assert "PRIVATE_EXCEPTION" not in str(events)


def test_probe_failures_are_bounded_then_source_can_recover(paths, monkeypatch):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    real = module._read_stable
    calls = []
    broken = True
    def read(*args, **kwargs):
        calls.append(1)
        if broken:
            raise PermissionError("PRIVATE_SOURCE")
        return real(*args, **kwargs)
    monkeypatch.setattr(module, "_read_stable", read)
    drive(watcher, 0, 0.5, 1, 2, 5)
    assert len(calls) == 2 and not archived(paths)
    assert [e.kind for e in events].count("unavailable") == 1
    broken = False
    drive(watcher, 6, 7, 8)
    assert len(archived(paths)) == 1
    assert [e.kind for e in events].count("available") == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows mandatory sharing")
def test_actual_windows_writer_lock_recovers_without_touching_source(paths):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    with paths[0].open("r+b"):
        drive(watcher, 0, 1, 2)
        assert not archived(paths)
    drive(watcher, 6, 8)
    assert len(archived(paths)) == 1
    assert paths[0].read_bytes() == lua()
    assert any(e.kind == "unavailable" for e in events)


def test_change_between_probe_and_capture_requires_new_stability_window(paths, monkeypatch):
    paths[0].write_bytes(lua())
    watcher, _ = observer(paths)
    real = module.capture_file
    changed = False
    def capture(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            paths[0].write_bytes(lua(high=200))
        return real(*args, **kwargs)
    monkeypatch.setattr(module, "capture_file", capture)
    drive(watcher, 0, 2)
    assert not archived(paths) and watcher.last_successful_sha256 is None
    drive(watcher, 3, 4.9)
    assert not archived(paths)
    watcher.step(5)
    assert len(archived(paths)) == 1
    assert watcher.last_successful_sha256 == sha256(lua(high=200)).hexdigest()


def test_restart_uses_persistent_core_deduplication(paths):
    paths[0].write_bytes(lua())
    first, _ = observer(paths)
    drive(first, 0, 2)
    second, events = observer(paths)
    drive(second, 0, 2, 3)
    assert len(archived(paths)) == 1 and events[-1].kind == "identical"
    assert events[-1].new_market_states == 0


def test_shutdown_on_ctrl_c_is_clean_and_retains_valid_capture(paths):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    times = iter([0, 2])
    calls = 0
    def wait(interval):
        nonlocal calls
        assert interval == SETTINGS.poll_interval
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
    watcher.run(clock=lambda: next(times), wait=wait)
    assert events[-1].kind == "stopped" and len(archived(paths)) == 1


def test_ctrl_c_during_capture_leaves_no_false_success(paths, monkeypatch):
    paths[0].write_bytes(lua())
    watcher, events = observer(paths)
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(module, "capture_file", interrupted)
    times = iter([0, 2])
    watcher.run(clock=lambda: next(times), wait=lambda _: None)
    assert watcher.last_successful_sha256 is None and not archived(paths)
    assert events[-1].kind == "stopped"


def test_stop_event_does_not_need_to_wait_for_poll_interval(paths):
    stop = Event()
    stop.set()
    watcher, events = observer(paths)
    watcher.run(stop_event=stop, wait=lambda _: pytest.fail("unnecessary wait"))
    assert [e.kind for e in events] == ["stopped"]


def test_parent_must_exist_but_file_can_be_missing(paths):
    AuctionatorWatcher(*paths)
    with pytest.raises(WatchError, match="source_parent_unavailable"):
        AuctionatorWatcher(paths[0].parent / "missing" / "Auctionator.lua", paths[1])


@pytest.mark.parametrize("kind", ["same", "nested", "ancestor"])
def test_source_and_archive_directories_must_be_independent(paths, kind):
    destination = {"same": paths[0].parent, "nested": paths[0].parent / "archive", "ancestor": paths[0].parent.parent}[kind]
    with pytest.raises(WatchError, match="overlapping_directories"):
        AuctionatorWatcher(paths[0], destination)
    assert not paths[1].exists()


def test_repository_archive_destination_is_rejected_before_watching(paths):
    with pytest.raises(WatchError, match="repository_destination"):
        AuctionatorWatcher(paths[0], PROJECT / "local-watcher-probe")
    assert not (PROJECT / "local-watcher-probe").exists()


def test_symlink_source_is_rejected_before_start(paths, tmp_path):
    target = tmp_path / "target.lua"
    target.write_bytes(lua())
    try:
        paths[0].symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(WatchError, match="unsafe_path"):
        observer(paths)


def test_runtime_symlink_is_not_followed_and_can_be_corrected(paths, tmp_path):
    watcher, events = observer(paths)
    target = tmp_path / "other.lua"
    target.write_bytes(lua())
    try:
        paths[0].symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    watcher.step(0)
    assert not archived(paths) and watcher.last_successful_sha256 is None
    assert events[-1].kind == "validation_error"
    paths[0].unlink()
    paths[0].write_bytes(lua())
    drive(watcher, 1, 3)
    assert len(archived(paths)) == 1


def test_oversized_source_is_not_processed_and_later_valid_data_recovers(paths, monkeypatch):
    from app.ingestion.saved_variables import MAX_BYTES
    with paths[0].open("wb") as stream:
        stream.truncate(MAX_BYTES + 1)
    calls = capture_count(monkeypatch)
    watcher, events = observer(paths)
    drive(watcher, 0, 1, 2)
    assert not calls and any(e.kind == "validation_error" for e in events)
    paths[0].write_bytes(lua())
    drive(watcher, 6, 8)
    assert len(archived(paths)) == 1


@pytest.mark.parametrize("options", [{"poll_interval": 0}, {"poll_interval": float("nan")},
                                      {"stable_seconds": -1}, {"debounce_seconds": float("inf")},
                                      {"max_attempts": 0}, {"max_attempts": True}, {"retry_delay": 0},
                                      {"recovery_interval": 0}, {"poll_interval": True}])
def test_invalid_timing_is_rejected(options):
    with pytest.raises(WatchError):
        replace(SETTINGS, **options)


@pytest.mark.parametrize("options", [{"source_version": "342"}, {"serialized_codec": "auto"},
                                      {"origin_id": "PRIVATE\\name"}, {"market_mapping": {"PvP": "PvP"}},
                                      {"market_mapping": {"external": "unknown"}}])
def test_invalid_capture_options_are_rejected_before_loop(paths, options):
    with pytest.raises(WatchError):
        observer(paths, **options)
    assert not paths[1].exists()


def test_capture_hash_guard_rejects_race_without_archiving(paths):
    paths[0].write_bytes(lua())
    with pytest.raises(CaptureError, match="source_changed"):
        capture_file(*paths, expected_source_sha256="0" * 64)
    assert not paths[1].exists() and paths[0].read_bytes() == lua()
    result = capture_file(*paths, expected_source_sha256=sha256(lua()).hexdigest())
    assert result.status == "archived"


@pytest.mark.parametrize("expected", ["", "x" * 64, "0" * 63, True])
def test_capture_hash_guard_rejects_invalid_options(paths, expected):
    paths[0].write_bytes(lua())
    with pytest.raises(CaptureError, match="invalid_options"):
        capture_file(*paths, expected_source_sha256=expected)
    assert not paths[1].exists()


def test_cli_ctrl_c_uses_local_runtime_and_emits_no_private_paths(paths, monkeypatch, capsys):
    paths[0].write_bytes(lua())
    real = AuctionatorWatcher.run
    def run(self):
        def wait(_):
            raise KeyboardInterrupt
        return real(self, clock=lambda: 0, wait=wait)
    monkeypatch.setattr(AuctionatorWatcher, "run", run)
    assert cli.main([str(paths[0]), "--destination", str(paths[1])]) == 0
    output = capsys.readouterr()
    assert "Observando Auctionator.lua" in output.out and "Observación detenida" in output.out
    assert str(paths[0]) not in output.out and output.err == ""


@pytest.mark.parametrize("interrupted", [False, True])
def test_cli_enables_and_restores_console_interrupts(paths, monkeypatch, interrupted):
    numbers = [signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
    originals = {number: object() for number in numbers}
    handlers = dict(originals)
    enabled = []
    monkeypatch.setattr(signal, "getsignal", lambda number: handlers[number])
    monkeypatch.setattr(signal, "signal", lambda number, handler: handlers.__setitem__(number, handler))
    monkeypatch.setattr(cli, "_enable_windows_ctrl_c", lambda: enabled.append(True))
    def run(_):
        assert all(handlers[number] is signal.default_int_handler for number in numbers)
        if interrupted:
            raise KeyboardInterrupt
    monkeypatch.setattr(AuctionatorWatcher, "run", run)
    assert cli.main([str(paths[0]), "--destination", str(paths[1])]) == 0
    assert handlers == originals and enabled == [True]


@pytest.mark.parametrize("utf8_mode", [False, True])
def test_real_cli_rejects_configuration_without_dotenv_or_database(paths, utf8_mode):
    paths[0].parent.joinpath(".env").write_text("UNKNOWN=PRIVATE_SECRET\nDATABASE_URL=invalid\n", encoding="ascii")
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    result = subprocess.run([sys.executable, "-X", "utf8=1" if utf8_mode else "utf8=0", "-B", str(CLI),
                             str(paths[0]), "--destination", str(paths[0].parent)], cwd=paths[0].parent,
                            capture_output=True, text=True, encoding="utf-8" if utf8_mode else locale.getencoding(),
                            timeout=15, env=env)
    assert result.returncode == 1
    assert "overlapping_directories" in result.stderr
    assert "PRIVATE_SECRET" not in result.stderr and str(paths[0]) not in result.stderr and "Traceback" not in result.stderr


def test_watcher_import_does_not_load_database_or_configuration(paths):
    code = ("import sys; from app.local_capture.watcher import AuctionatorWatcher; "
            "blocked=('psycopg','app.db','app.core.config','app.ingestion.partial_service','app.main'); "
            "assert not any(m==x or m.startswith(x+'.') for m in sys.modules for x in blocked)")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CLI.parents[1])
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=paths[0].parent,
                            capture_output=True, text=True, timeout=15, env=env)
    assert result.returncode == 0, result.stderr
