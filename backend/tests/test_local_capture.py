"""Synthetic local evidence only. No private capture, DB, migration or network."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import app.local_capture.archive as archive
from app.ingestion.saved_variables import MAX_BYTES
from app.local_capture import CaptureError, capture_file, default_archive_directory
from app.local_capture.contracts import CaptureMetadata, canonical_json
from app.local_capture.decoder import CaptureAdapter, MAX_CAPTURE_PRICE
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from test_auctionator_cbor import encode, literal


CLI = Path(__file__).resolve().parents[1] / "scripts" / "capture_auctionator.py"
PROJECT = CLI.parents[2]


def lua(*, high=100, low=None, available=2, minimum=100, day="2485", key="123", market="PvP"):
    lows = '{}' if low is None else '{["' + day + '"]=' + str(low) + '}'
    a = '' if available is None else ',a={["' + day + '"]=' + str(available) + '}'
    return ('AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["' + market + '"]={version=2,["' + key
            + '"]={l=' + lows + ',h={["' + day + '"]=' + str(high) + '},m=' + str(minimum) + a + '}}}').encode()


@pytest.fixture
def paths(tmp_path):
    source = tmp_path / "source" / "Auctionator.lua"
    source.parent.mkdir()
    source.write_bytes(lua())
    return source, tmp_path / "private-archive"


def capture(paths, raw=None, **options):
    source, destination = paths
    if raw is not None:
        source.write_bytes(raw)
    return capture_file(source, destination, **options)


def saved(paths, result):
    return paths[1] / "captures" / result.metadata.capture_id


def assert_error(code, call):
    with pytest.raises(CaptureError) as error:
        call()
    assert error.value.code == code
    assert str(error.value) == code


def replace_private_file(path, raw):
    # Simulate external corruption by the directory owner, outside the API.
    path.chmod(stat.S_IREAD | stat.S_IWRITE)
    path.write_bytes(raw)


def test_first_capture_contract_integrity_privacy_and_independence(paths):
    before = paths[0].stat()
    original = paths[0].read_bytes()
    start = datetime.now(timezone.utc)
    result = capture(paths, origin_id="station-1", source_version="341")
    end = datetime.now(timezone.utc)
    assert result.status == "archived" and result.comparison.status == "first"
    m = result.metadata
    assert m.capture_id == m.source_sha256 == sha256(original).hexdigest()
    assert m.market_hash_contract == "auctionator-native-market-v1"
    assert len(m.market_sha256) == 64 and m.source_bytes == len(original)
    assert start <= m.captured_at <= end and m.captured_at.utcoffset().total_seconds() == 0
    assert m.native_scan_timestamp is None and m.validation_status == "valid"
    assert (m.database_version, m.selected_source_version, m.input_format) == (8, "341", "lua_tables")
    assert not m.origin.source_path_stored and m.origin.origin_id == "station-1"
    assert m.item_count == 1 and m.native_fact_count == 3 and m.projected_statistic_count == 4
    market = m.markets[0]
    assert (market.market_key, market.ruleset, market.first_bucket, market.last_bucket) == ("PvP", "PvP", 2485, 2485)
    assert market.bucket_count == 1 and market.realm_database_version == 2
    assert result.comparison.new_market_states == [market.state_sha256]
    assert {"region", "dataset", "faction", "codec_producer", "capture_client_build"} <= set(m.pending_metadata)
    assert "native_buckets_are_not_civil_dates" in m.warnings
    entry = saved(paths, result)
    assert entry.joinpath("Auctionator.lua").read_bytes() == original
    assert CaptureMetadata.model_validate_json(entry.joinpath("metadata.json").read_bytes()) == m
    assert not entry.joinpath("Auctionator.lua").stat().st_mode & stat.S_IWRITE
    assert not entry.joinpath("metadata.json").stat().st_mode & stat.S_IWRITE
    assert entry.joinpath("Auctionator.lua").stat().st_nlink == 1
    paths[0].write_bytes(lua(high=200))
    assert entry.joinpath("Auctionator.lua").read_bytes() == original
    assert before.st_mtime_ns != paths[0].stat().st_mtime_ns or paths[0].read_bytes() != original


def test_exact_duplicate_does_not_rewrite_metadata_or_copy(paths, monkeypatch):
    result = capture(paths)
    entry = saved(paths, result)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in entry.iterdir()}
    monkeypatch.setattr(archive, "_write_new", lambda *args: pytest.fail("duplicate attempted a write"))
    duplicate = capture(paths, origin_id="another-opaque-alias")
    assert duplicate.status == "duplicate" and duplicate.metadata == result.metadata
    assert duplicate.comparison.new_market_states == []
    assert duplicate.comparison.equivalent_capture_id == result.metadata.capture_id
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in entry.iterdir()}
    assert len(list(paths[1].joinpath("captures").iterdir())) == 1
    assert not list(paths[1].joinpath("pending").iterdir())


def test_config_and_vendor_cache_changes_keep_independent_evidence_without_new_state(paths):
    first = capture(paths)
    raw = lua() + b'\nAUCTIONATOR_CONFIG={character="PRIVATE_CHARACTER"}\nAUCTIONATOR_VENDOR_PRICE_CACHE={["1"]=2}'
    second = capture(paths, raw)
    assert second.status == "archived" and second.comparison.status == "equivalent"
    assert second.metadata.capture_id != first.metadata.capture_id
    assert second.metadata.market_sha256 == first.metadata.market_sha256
    assert second.comparison.equivalent_capture_id == first.metadata.capture_id
    assert second.comparison.new_market_states == []
    assert saved(paths, second).joinpath("Auctionator.lua").read_bytes() == raw
    metadata = saved(paths, second).joinpath("metadata.json").read_text()
    assert "PRIVATE_CHARACTER" not in metadata and str(paths[0]) not in metadata
    assert len(list(paths[1].joinpath("captures").iterdir())) == 2


@pytest.mark.parametrize("changes", [{"low": 90}, {"high": 110}, {"available": 3}, {"minimum": 99}])
def test_every_native_field_change_is_detected_with_same_item_count_and_bucket(paths, changes):
    first = capture(paths)
    second = capture(paths, lua(**changes))
    assert second.metadata.market_sha256 != first.metadata.market_sha256
    assert second.metadata.item_count == first.metadata.item_count == 1
    assert second.metadata.markets[0].first_bucket == first.metadata.markets[0].first_bucket == 2485
    assert second.comparison.status == "changed" and len(second.comparison.new_market_states) == 1


def test_order_whitespace_and_codec_do_not_change_canonical_evidence(paths):
    first = capture(paths)
    raw = (b'\xef\xbb\xbf-- synthetic\nAUCTIONATOR_PRICE_DATABASE = { ["PvP"] = { ["123"] = '
           b'{a={["2485"]=2},m=100,h={["2485"]=100},l={}},version=2}, ["__dbversion"]=8}')
    reordered = capture(paths, raw)
    payload = encode({b"version": 2, b"123": {b"a": {b"2485": 2}, b"m": 100,
                                                   b"h": {b"2485": 100}, b"l": []}})
    raw_cbor = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]=' + literal(payload) + b'}'
    encoded = capture(paths, raw_cbor, serialized_codec="cbor-definite")
    assert first.metadata.market_sha256 == reordered.metadata.market_sha256 == encoded.metadata.market_sha256
    assert len({r.metadata.capture_id for r in (first, reordered, encoded)}) == 3
    assert encoded.metadata.input_format == "cbor_definite"
    assert encoded.comparison.new_market_states == []


def test_per_market_identity_does_not_duplicate_unchanged_market(paths):
    pvp = lua().split(b'["PvP"]=', 1)[1][:-1]
    pve = lua(high=200).split(b'["PvP"]=', 1)[1][:-1]
    first = capture(paths, b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]=' + pvp + b',["PvE"]=' + pve + b'}')
    second = capture(paths, b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]=' + pve + b',["PvE"]=' + pve + b'}')
    old = {m.market_key: m.state_sha256 for m in first.metadata.markets}
    new = {m.market_key: m.state_sha256 for m in second.metadata.markets}
    assert old["PvE"] == new["PvE"] and old["PvP"] != new["PvP"]
    assert second.comparison.new_market_states == [new["PvP"]]


def test_native_presence_is_not_erased_by_projection(paths):
    first = capture(paths, lua(low=None))
    second = capture(paths, lua(low=100))
    assert first.metadata.projected_statistic_count == second.metadata.projected_statistic_count
    assert first.metadata.market_sha256 != second.metadata.market_sha256


def test_returning_to_known_market_state_retains_file_but_adds_no_state(paths):
    first = capture(paths)
    capture(paths, lua(high=200))
    repeated = capture(paths, lua() + b'\nCONFIG={x=2}')
    assert repeated.comparison.status == "equivalent"
    assert repeated.comparison.equivalent_capture_id == first.metadata.capture_id
    assert repeated.comparison.new_market_states == []


@pytest.mark.parametrize("raw", [b"", b"os.execute('PRIVATE')", lua()[:-1], lua(low=101),
                                  lua(available=-1), lua(minimum=MAX_CAPTURE_PRICE + 1),
                                  lua() + b'\nCONFIG={password="PRIVATE"',
                                  b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=9}'])
def test_invalid_content_is_rejected_before_any_archive_creation(paths, raw):
    paths[0].write_bytes(raw)
    assert_error("invalid_content", lambda: capture(paths))
    assert not paths[1].exists()
    assert paths[0].read_bytes() == raw


def test_oversized_input_is_rejected_before_read_and_archive(paths, monkeypatch):
    with paths[0].open("wb") as stream:
        stream.truncate(MAX_BYTES + 1)
    monkeypatch.setattr(archive, "_open_read", lambda *args: pytest.fail("oversized input was opened"))
    assert_error("file_too_large", lambda: capture(paths))
    assert not paths[1].exists()


def test_missing_and_directory_sources_are_rejected(paths):
    assert_error("source_unavailable", lambda: capture_file(paths[0].parent / "missing.lua", paths[1]))
    assert_error("unsafe_file", lambda: capture_file(paths[0].parent, paths[1]))
    assert not paths[1].exists()


def test_inaccessible_source_is_rejected_without_disclosure(paths, monkeypatch):
    def denied(*args):
        raise PermissionError("PRIVATE_PATH")
    monkeypatch.setattr(archive, "_open_read", denied)
    assert_error("source_unavailable", lambda: capture(paths))
    assert not paths[1].exists()


def test_changed_content_between_reads_is_rejected_even_at_same_size(paths, monkeypatch):
    real = archive._read_pass
    passes = 0
    def changed(stream):
        nonlocal passes
        passes += 1
        raw = real(stream)
        return raw.replace(b"100", b"101") if passes == 2 else raw
    monkeypatch.setattr(archive, "_read_pass", changed)
    assert_error("source_changed", lambda: capture(paths))
    assert not paths[1].exists()


def test_metadata_change_between_reads_is_rejected(paths, monkeypatch):
    real = archive._read_pass
    def changed(stream):
        raw = real(stream)
        info = paths[0].stat()
        os.utime(paths[0], ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        return raw
    monkeypatch.setattr(archive, "_read_pass", changed)
    # Windows denies changing attributes through an incompatible second handle;
    # simulate the fingerprint independently to keep the test portable.
    if os.name == "nt":
        real_fingerprint = archive._fingerprint
        calls = 0
        def fingerprint(info):
            nonlocal calls
            calls += 1
            values = real_fingerprint(info)
            return (*values[:-1], values[-1] + (1 if calls >= 4 else 0))
        monkeypatch.setattr(archive, "_read_pass", real)
        monkeypatch.setattr(archive, "_fingerprint", fingerprint)
    assert_error("source_changed", lambda: capture(paths))


@pytest.mark.skipif(os.name != "nt", reason="Windows mandatory file sharing")
def test_windows_writer_open_prevents_capture(paths):
    with paths[0].open("r+b"):
        assert_error("source_unavailable", lambda: capture(paths))
    assert capture(paths).status == "archived"


@pytest.mark.skipif(os.name != "nt", reason="Windows mandatory file sharing")
def test_windows_capture_handle_denies_a_new_writer(paths, monkeypatch):
    real = archive._read_pass
    attempts = 0
    def read(stream):
        nonlocal attempts
        if attempts < 2:
            attempts += 1
            with pytest.raises(PermissionError):
                with paths[0].open("r+b"):
                    pass
        return real(stream)
    monkeypatch.setattr(archive, "_read_pass", read)
    assert capture(paths).status == "archived"
    assert attempts == 2


def test_copy_uses_validated_buffer_if_original_changes_after_read(paths, monkeypatch):
    raw = paths[0].read_bytes()
    real = archive.describe
    def changed(*args, **kwargs):
        result = real(*args, **kwargs)
        paths[0].write_bytes(lua(high=300))
        return result
    monkeypatch.setattr(archive, "describe", changed)
    result = capture(paths)
    assert result.metadata.source_sha256 == sha256(raw).hexdigest()
    assert saved(paths, result).joinpath("Auctionator.lua").read_bytes() == raw


@pytest.mark.parametrize("when", ["raw_partial", "metadata", "publish", "after_publish"])
def test_failure_preserves_evidence_and_retry_publishes_once(paths, monkeypatch, when):
    raw = paths[0].read_bytes()
    real_write, real_publish = archive._write_new, archive._publish
    def fail_write(path, payload):
        if when == "raw_partial" and path.name == "Auctionator.lua":
            path.write_bytes(payload[:10])
            raise OSError("PRIVATE_IO_FAILURE")
        if when == "metadata" and path.name == "metadata.json":
            raise OSError("PRIVATE_IO_FAILURE")
        real_write(path, payload)
    def fail_publish(stage, final):
        if when == "after_publish":
            real_publish(stage, final)
        raise OSError("PRIVATE_IO_FAILURE")
    monkeypatch.setattr(archive, "_write_new", fail_write)
    if when in ("publish", "after_publish"):
        monkeypatch.setattr(archive, "_publish", fail_publish)
    assert_error("archive_failed", lambda: capture(paths))
    copies = list(paths[1].rglob("Auctionator.lua"))
    assert copies and (when == "raw_partial" or any(p.read_bytes() == raw for p in copies))
    assert paths[0].read_bytes() == raw
    monkeypatch.setattr(archive, "_write_new", real_write)
    monkeypatch.setattr(archive, "_publish", real_publish)
    retried = capture(paths)
    assert retried.status == ("duplicate" if when == "after_publish" else "archived")
    assert saved(paths, retried).joinpath("Auctionator.lua").read_bytes() == raw
    assert len(list(paths[1].joinpath("captures").iterdir())) == 1
    assert capture(paths).status == "duplicate"


def test_pending_can_be_recovered_without_original_source(paths, monkeypatch):
    real = archive._publish
    monkeypatch.setattr(archive, "_publish", lambda *args: (_ for _ in ()).throw(OSError("failure")))
    assert_error("archive_failed", lambda: capture(paths))
    retained = next(paths[1].joinpath("pending").glob("*/Auctionator.lua"))
    paths[0].unlink()
    monkeypatch.setattr(archive, "_publish", real)
    result = capture_file(retained, paths[1])
    assert result.status == "archived"
    assert capture_file(saved(paths, result) / "Auctionator.lua", paths[1]).status == "duplicate"


def test_pending_comparison_is_recomputed_after_another_receipt(paths, monkeypatch):
    real = archive._publish
    monkeypatch.setattr(archive, "_publish", lambda *args: (_ for _ in ()).throw(OSError("failure")))
    assert_error("archive_failed", lambda: capture(paths))
    monkeypatch.setattr(archive, "_publish", real)
    other = capture(paths, lua() + b'\nCONFIG={x=1}')
    recovered = capture(paths, lua())
    assert recovered.comparison.status == "equivalent"
    assert recovered.comparison.equivalent_capture_id == other.metadata.capture_id
    assert recovered.comparison.new_market_states == []


def test_real_process_interruption_releases_lock_and_retains_complete_pending(paths):
    code = ("import os, sys; import app.local_capture.archive as a; "
            "a._publish = lambda *args: os._exit(77); "
            "a.capture_file(sys.argv[1], sys.argv[2])")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CLI.parents[1])
    interrupted = subprocess.run([sys.executable, "-B", "-c", code, str(paths[0]), str(paths[1])],
                                 cwd=paths[0].parent, env=env, capture_output=True, timeout=20)
    assert interrupted.returncode == 77
    assert not list(paths[1].joinpath("captures").iterdir())
    retained = next(paths[1].joinpath("pending").glob("*/Auctionator.lua"))
    assert retained.read_bytes() == paths[0].read_bytes()
    result = capture(paths)
    assert result.status == "archived" and result.comparison.status == "first"
    assert not list(paths[1].joinpath("pending").iterdir())


def test_interruption_before_readonly_seal_retains_raw_and_retries(paths, monkeypatch):
    real = Path.chmod
    def fail_seal(path, *args, **kwargs):
        if path.name == "metadata.json":
            raise OSError("failure before seal")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(Path, "chmod", fail_seal)
    assert_error("archive_failed", lambda: capture(paths))
    monkeypatch.setattr(Path, "chmod", real)
    assert capture(paths).status == "archived"
    assert list(paths[1].joinpath("pending").glob("incomplete-*/Auctionator.lua"))


@pytest.mark.parametrize("target", ["Auctionator.lua", "metadata.json", "extra", "missing"])
def test_corrupt_archive_blocks_dedup_and_preserves_original_files(paths, target):
    result = capture(paths)
    entry = saved(paths, result)
    if target == "extra":
        (entry / "unexpected").write_bytes(b"x")
    elif target == "missing":
        (entry / "metadata.json").chmod(stat.S_IWRITE | stat.S_IREAD)
        (entry / "metadata.json").unlink()
    else:
        replace_private_file(entry / target, b"corrupt")
    assert_error("archive_integrity", lambda: capture(paths))
    assert len(list(paths[1].joinpath("captures").iterdir())) == 1


def test_forged_metadata_hash_and_counts_are_recomputed(paths):
    result = capture(paths)
    path = saved(paths, result) / "metadata.json"
    metadata = json.loads(path.read_bytes())
    metadata["market_sha256"] = "0" * 64
    metadata["native_fact_count"] = 999
    replace_private_file(path, canonical_json(metadata))
    path.chmod(stat.S_IREAD)
    assert_error("archive_integrity", lambda: capture(paths))


def test_deeply_nested_corrupt_metadata_is_a_private_integrity_error(paths):
    result = capture(paths)
    path = saved(paths, result) / "metadata.json"
    replace_private_file(path, b"[" * 2000 + b"0" + b"]" * 2000)
    path.chmod(stat.S_IREAD)
    assert_error("archive_integrity", lambda: capture(paths))
    assert saved(paths, result).joinpath("Auctionator.lua").read_bytes() == lua()


def test_valid_but_wrong_raw_hash_and_duplicate_metadata_keys_are_rejected(paths):
    result = capture(paths)
    entry = saved(paths, result)
    raw_path, meta_path = entry / "Auctionator.lua", entry / "metadata.json"
    replace_private_file(raw_path, lua(high=101))
    raw_path.chmod(stat.S_IREAD)
    assert_error("archive_integrity", lambda: capture(paths))
    replace_private_file(raw_path, lua())
    raw_path.chmod(stat.S_IREAD)
    metadata = meta_path.read_bytes()
    replace_private_file(meta_path, b'{"schema_version":1,' + metadata[1:])
    meta_path.chmod(stat.S_IREAD)
    assert_error("archive_integrity", lambda: capture(paths))


def test_existing_empty_collision_is_never_overwritten(paths):
    target = paths[1] / "captures" / sha256(paths[0].read_bytes()).hexdigest()
    target.mkdir(parents=True)
    assert_error("archive_integrity", lambda: capture(paths))
    assert target.is_dir() and not list(target.iterdir())


def test_publish_checks_collision_without_replacing_any_content(tmp_path):
    stage, final = tmp_path / "stage", tmp_path / "final"
    stage.mkdir()
    final.mkdir()
    (stage / "valid").write_bytes(b"x")
    assert_error("archive_collision", lambda: archive._publish(stage, final))
    assert (stage / "valid").read_bytes() == b"x" and not list(final.iterdir())


def test_lock_contention_is_retryable_and_os_lock_is_released(paths):
    paths[1].mkdir()
    with archive._archive_lock(paths[1]):
        assert_error("archive_busy", lambda: capture(paths))
    assert capture(paths).status == "archived"


def test_repository_destinations_are_rejected_without_writing(paths, tmp_path, monkeypatch):
    assert_error("repository_destination", lambda: capture_file(paths[0], PROJECT / "local-private-captures"))
    assert not (PROJECT / "local-private-captures").exists()
    other = tmp_path / "other-repo"
    other.mkdir()
    (other / ".git").write_text("gitdir: synthetic-worktree", encoding="ascii")
    monkeypatch.setattr(archive, "REPOSITORY_ROOT", other)
    assert_error("repository_destination", lambda: capture_file(paths[0], other / "ignored" / "capture"))
    assert not (other / "ignored").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows 8.3 aliases")
def test_short_path_alias_cannot_bypass_repository_boundary(paths):
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetShortPathNameW.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
    kernel.GetShortPathNameW.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    size = kernel.GetShortPathNameW(str(PROJECT), buffer, len(buffer))
    if not size or Path(buffer.value) == PROJECT:
        pytest.skip("No distinct short alias available on this filesystem")
    target = Path(buffer.value) / "local-capture-alias-probe"
    assert_error("repository_destination", lambda: capture_file(paths[0], target))
    assert not (PROJECT / "local-capture-alias-probe").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows ambiguous path aliases")
@pytest.mark.parametrize("suffix", [" ", "."])
def test_ambiguous_windows_repository_alias_is_rejected(paths, suffix):
    target = Path(str(PROJECT) + suffix) / "local-capture-alias-probe"
    assert_error("unsafe_path", lambda: capture_file(paths[0], target))
    assert not (PROJECT / "local-capture-alias-probe").exists()


@pytest.mark.parametrize("value", [2147483648, 99999990200, MAX_CAPTURE_PRICE])
def test_large_integer_prices_are_exact_locally_and_still_rejected_for_import(paths, value):
    original = lua(high=value, minimum=value)
    paths[0].write_bytes(original)
    result = capture(paths)
    decoded = CaptureAdapter().decode_bytes(original)
    assert {f.value for f in decoded.native.facts if f.native_field in ("h", "m")} == {value}
    assert {o.value for o in decoded.native.projected_observations() if o.statistic != "daily_max_available"} == {value}
    assert capture(paths).status == "duplicate"
    assert saved(paths, result).joinpath("Auctionator.lua").read_bytes() == original
    with pytest.raises(ValueError):
        AuctionatorAdapter().load_bytes(original, source_id="synthetic", region="synthetic", source_version="341")
    # Even the local subclass cannot bypass the ingestion batch's signed-32-bit contract.
    with pytest.raises(ValueError):
        CaptureAdapter().load_bytes(original, source_id="synthetic", region="synthetic", source_version="341")
    assert paths[0].read_bytes() == original


@pytest.mark.parametrize("options", [{"high": MAX_CAPTURE_PRICE + 1}, {"minimum": MAX_CAPTURE_PRICE + 1},
                                      {"available": 2147483648}, {"day": "2147483648"}])
def test_local_prices_remain_bounded_and_other_numeric_limits_do_not_widen(paths, options):
    original = lua(**options)
    paths[0].write_bytes(original)
    assert_error("invalid_content", lambda: capture(paths))
    assert paths[0].read_bytes() == original
    assert not paths[1].exists()


def test_large_cbor_prices_roundtrip_with_identical_lua_evidence(paths):
    price = 99999990200
    first = capture(paths, lua(high=price, low=price - 1, minimum=price))
    payload = encode({b"version": 2, b"123": {b"a": {b"2485": 2}, b"m": price,
                                             b"h": {b"2485": price}, b"l": {b"2485": price - 1}}})
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["PvP"]=' + literal(payload) + b'}'
    encoded = capture(paths, raw, serialized_codec="cbor-definite")
    assert encoded.metadata.market_sha256 == first.metadata.market_sha256
    assert encoded.comparison.status == "equivalent" and encoded.comparison.new_market_states == []
    with pytest.raises(ValueError):
        AuctionatorAdapter().decode_bytes(raw, serialized_codec="cbor-definite")


def test_file_destination_is_rejected(paths):
    paths[1].write_bytes(b"keep")
    assert_error("invalid_destination", lambda: capture(paths))
    assert paths[1].read_bytes() == b"keep"


def test_default_is_external_and_cannot_bypass_repository_guard(paths, monkeypatch):
    assert PROJECT not in default_archive_directory().parents
    if os.name == "nt":
        monkeypatch.setenv("LOCALAPPDATA", str(PROJECT))
    else:
        monkeypatch.setattr(Path, "home", lambda: PROJECT)
    assert_error("repository_destination", lambda: capture_file(paths[0]))


@pytest.mark.parametrize("where", ["source", "source_parent", "destination", "destination_parent", "captures", "pending", "lock"])
def test_symlinks_and_linked_ancestors_are_rejected(paths, tmp_path, where):
    source, destination = paths
    link = tmp_path / "link"
    target = source if where == "source" else source.parent
    if where in ("destination", "destination_parent", "captures", "pending", "lock"):
        target = tmp_path / "elsewhere"
        target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("symlink creation unavailable without platform privilege")
    if where == "source":
        action = lambda: capture_file(link, destination)
    elif where == "source_parent":
        action = lambda: capture_file(link / source.name, destination)
    elif where == "destination":
        action = lambda: capture_file(source, link)
    elif where == "destination_parent":
        action = lambda: capture_file(source, link / "nested")
    else:
        destination.mkdir()
        name = {"captures": "captures", "pending": "pending", "lock": ".capture.lock"}[where]
        os.rename(link, destination / name)
        action = lambda: capture(paths)
    assert_error("unsafe_path", action)
    assert source.read_bytes() == lua()


def test_reparse_attribute_guard_without_symlink_privilege(paths, monkeypatch):
    real = Path.lstat
    class Linked:
        st_mode = stat.S_IFDIR
        st_file_attributes = archive.REPARSE_POINT
    def lstat(path, *args, **kwargs):
        return Linked() if path == paths[0].parent else real(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", lstat)
    assert_error("unsafe_path", lambda: capture(paths))


def test_existing_hardlinked_evidence_is_rejected(paths, tmp_path):
    result = capture(paths)
    path = saved(paths, result) / "Auctionator.lua"
    try:
        os.link(path, tmp_path / "alias.lua")
    except OSError:
        pytest.skip("hardlinks unsupported by filesystem")
    assert_error("unsafe_file", lambda: capture(paths))


def test_unknown_market_requires_explicit_mapping_and_does_not_guess_region(paths):
    raw = lua(market="Synthetic Realm")
    paths[0].write_bytes(raw)
    assert_error("invalid_content", lambda: capture(paths))
    result = capture(paths, market_mapping={"Synthetic Realm": "PvP"})
    assert result.metadata.markets[0].market_key == "Synthetic Realm"
    assert "region" in result.metadata.pending_metadata
    assert result.metadata.selected_source_version is None
    assert_error("capture_context_conflict", lambda: capture(paths, market_mapping={"Synthetic Realm": "PvE"}))


@pytest.mark.parametrize("options", [{"source_version": "342"}, {"origin_id": "C:\\PRIVATE"},
                                      {"origin_id": "unsafe\nname"}])
def test_invalid_options_are_sanitized(paths, options):
    assert_error("invalid_options", lambda: capture(paths, **options))
    assert not paths[1].exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows path syntax")
@pytest.mark.parametrize("destination", [r"\\server\private\capture", r"\\?\C:\capture", "capture:stream"])
def test_network_device_and_alternate_stream_paths_are_rejected(paths, destination):
    assert_error("unsafe_path", lambda: capture_file(paths[0], destination))


def run_cli(paths, *extra):
    return subprocess.run([sys.executable, "-B", str(CLI), str(paths[0]), "--destination", str(paths[1]), *extra],
                          cwd=paths[0].parent, capture_output=True, text=True, timeout=20)


def test_real_cli_is_offline_ignores_dotenv_and_prints_only_safe_summary(paths):
    paths[0].write_bytes(lua() + b'\nCONFIG={password="PRIVATE_SECRET"}')
    paths[0].parent.joinpath(".env").write_text("UNKNOWN=PRIVATE_SECRET\nDATABASE_URL=bad\n", encoding="ascii")
    result = run_cli(paths, "--source-version", "341")
    assert result.returncode == 0 and result.stderr == ""
    data = json.loads(result.stdout)
    assert data["status"] == "archived" and data["market_status"] == "first"
    assert "PRIVATE_SECRET" not in result.stdout and str(paths[0]) not in result.stdout
    assert json.loads(run_cli(paths).stdout)["status"] == "duplicate"
    paths[0].write_bytes(b'PRIVATE_SECRET malformed')
    failed = run_cli(paths)
    assert failed.returncode == 1 and failed.stdout == ""
    assert json.loads(failed.stderr) == {"error": "invalid_content"}
    assert "PRIVATE_SECRET" not in failed.stderr and "Traceback" not in failed.stderr


def test_cli_manual_market_mapping(paths):
    paths[0].write_bytes(lua(market="Synthetic Realm"))
    assert run_cli(paths, "--market-rule", "Synthetic Realm=PvP").returncode == 0
    assert json.loads(run_cli(paths, "--market-rule", "bad").stderr) == {"error": "invalid_options"}


def test_module_does_not_load_database_config_network_or_services(paths):
    code = ("import sys; from app.local_capture import capture_file; "
            "blocked = ('psycopg', 'app.db', 'app.core.config', 'app.ingestion.partial_service', 'app.main'); "
            "assert not any(m == x or m.startswith(x + '.') for m in sys.modules for x in blocked)")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CLI.parents[1])
    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=paths[0].parent,
                            capture_output=True, text=True, timeout=20, env=env)
    assert result.returncode == 0, result.stderr
