from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from threading import Barrier, local

import psycopg
import pytest

from app.db.connection import connect
from app.ingestion.adapters.auctionator import PartialAdapterResult
from app.ingestion.partial_contracts import PartialBatch
from app.ingestion.partial_service import PartialIngestionService
from tests.test_auctionator import fixture_result


@pytest.fixture(autouse=True)
def database(isolated_database):
    pass


def result_for(payload):
    raw = json.dumps(payload, sort_keys=True).encode()
    return PartialAdapterResult(PartialBatch.model_validate(payload), hashlib.sha256(raw).hexdigest())


def deadlock_batches():
    payload = json.loads((Path(__file__).parent / "fixtures/deadlock_reconstruction.json").read_text())
    return [result_for(b) for b in payload["batches"]]


def test_negative_control_original_market_interleaved_order_really_deadlocks():
    """Replay the old catalog SQL order in test DB, not an exception mock.

    Constructed batches reproduce the reported lock inversion; they are not
    claimed as the unavailable original audit payloads.
    """
    barrier = Barrier(2)

    def legacy_catalog_sql(result):
        try:
            with connect() as c:
                keys = sorted({(o.market_key, o.item_key) for o in result.batch.observations})
                for index, (market, item) in enumerate(keys):
                    c.execute("""INSERT INTO partial_markets(market_key,ruleset,region,dataset)
                                 VALUES (%s,%s,'test-only','real') ON CONFLICT DO NOTHING""", (market, market))
                    c.execute("""INSERT INTO partial_items(item_key,external_item_id,key_kind)
                                 VALUES (%s,%s,'item') ON CONFLICT DO NOTHING""", (item, item))
                    if index == 0:
                        barrier.wait(timeout=10)
            return "committed"
        except psycopg.Error as error:
            return error.sqlstate

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(legacy_catalog_sql, deadlock_batches()))
    assert sorted(outcomes) == ["40P01", "committed"]
    print("negative control, old SQL order:", outcomes)


@pytest.mark.parametrize("existing_items", [False, True])
def test_same_conflicting_batches_complete_under_global_lock_order(existing_items, monkeypatch):
    if existing_items:
        with connect() as c:
            c.execute("""INSERT INTO partial_items(item_key,external_item_id,key_kind)
                         VALUES ('910','910','item'),('911','911','item')""")
    barrier, state = Barrier(2), local()
    trace = {}
    create = PartialIngestionService._create_run
    item_lock = PartialIngestionService._lock_item
    market_lock = PartialIngestionService._lock_market

    def start(self, c, result, *args):
        run_id = create(self, c, result, *args)
        if not hasattr(state, "key"):
            state.key = result.batch.observations[0].market_key
            trace[state.key] = []
            barrier.wait(timeout=10)
        return run_id

    def item(self, c, observation):
        trace[state.key].append(("item", observation.item_key))
        return item_lock(self, c, observation)

    def market(self, c, batch, observation):
        trace[state.key].append(("market", observation.market_key))
        return market_lock(self, c, batch, observation)

    monkeypatch.setattr(PartialIngestionService, "_create_run", start)
    monkeypatch.setattr(PartialIngestionService, "_lock_item", item)
    monkeypatch.setattr(PartialIngestionService, "_lock_market", market)
    batches = deadlock_batches()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda r: PartialIngestionService().import_batch(r), batches))
    assert [o.status for o in outcomes] == ["completed", "completed"]
    for operations in trace.values():
        assert operations[:2] == [("item", "910"), ("item", "911")]
        assert all(kind == "market" for kind, _ in operations[2:])
    monkeypatch.setattr(PartialIngestionService, "_create_run", create)
    monkeypatch.setattr(PartialIngestionService, "_lock_item", item_lock)
    monkeypatch.setattr(PartialIngestionService, "_lock_market", market_lock)
    for result in batches:
        assert PartialIngestionService().import_batch(result).status == "duplicate"
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == 8
        assert c.execute("SELECT count(*) AS n FROM partial_import_runs WHERE status='failed'").fetchone()["n"] == 0
    print("corrected, existing_items=", existing_items, "outcomes=", [o.status for o in outcomes], "locks=", trace)


def one_stat(statistic, value):
    source = fixture_result()
    payload = source.batch.model_dump()
    observation = next(o for o in payload["observations"] if o["market_key"] == "PvE" and o["item_key"] == "2772" and o["scan_day"] == 2500)
    observation.update(statistic=statistic, value=value)
    payload["observations"] = [observation]
    return result_for(payload)


@pytest.mark.parametrize("first", ["daily_minimum", "daily_highest_minimum"])
def test_separate_batches_cannot_create_contradictory_history(first):
    service = PartialIngestionService()
    low, high = one_stat("daily_minimum", 200), one_stat("daily_highest_minimum", 100)
    initial, rejected = (low, high) if first == "daily_minimum" else (high, low)
    assert service.import_batch(initial).status == "completed"
    with pytest.raises(psycopg.errors.CheckViolation):
        service.import_batch(rejected)
    with connect() as c:
        rows = c.execute("SELECT statistic,value FROM partial_observations").fetchall()
        assert rows == [{"statistic": first, "value": initial.batch.observations[0].value}]
        assert c.execute("SELECT status FROM partial_import_runs ORDER BY id").fetchall() == [{"status": "completed"}, {"status": "failed"}]


@pytest.mark.parametrize("consistent", [False, True])
def test_concurrent_split_statistics_are_coherent_or_atomic_rejection(consistent, monkeypatch):
    barrier = Barrier(2)
    create = PartialIngestionService._create_run
    state = local()

    def start(self, c, result, *args):
        run_id = create(self, c, result, *args)
        if not getattr(state, "started", False):
            state.started = True
            barrier.wait(timeout=10)
        return run_id

    monkeypatch.setattr(PartialIngestionService, "_create_run", start)

    def load(result):
        try:
            return PartialIngestionService().import_batch(result).status
        except psycopg.errors.CheckViolation:
            return "rejected"

    batches = [one_stat("daily_minimum", 80 if consistent else 200), one_stat("daily_highest_minimum", 100)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(load, batches))
    assert sorted(outcomes) == (["completed", "completed"] if consistent else ["completed", "rejected"])
    with connect() as c:
        values = {r["statistic"]: r["value"] for r in c.execute("SELECT statistic,value FROM partial_observations")}
        if consistent:
            assert values["daily_minimum"] <= values["daily_highest_minimum"]
        else:
            assert len(values) == 1
    print("split statistics consistent=", consistent, "outcomes=", outcomes)


def test_cross_batch_failure_rolls_back_other_observations_too():
    service = PartialIngestionService()
    service.import_batch(one_stat("daily_highest_minimum", 100))
    payload = one_stat("daily_minimum", 200).batch.model_dump()
    other = dict(payload["observations"][0], item_key="12345", external_item_id="12345", value=50)
    payload["observations"].append(other)
    with pytest.raises(psycopg.errors.CheckViolation):
        service.import_batch(result_for(payload))
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM partial_items").fetchone()["n"] == 1
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == 1


@pytest.mark.parametrize("failures", [1, 2, 3])
def test_deadlock_retry_is_bounded_and_failed_runs_not_recorded_on_success(monkeypatch, failures):
    original = PartialIngestionService._persist_observation
    calls = 0

    def deadlock(self, c, *args):
        nonlocal calls
        calls += 1
        if calls <= failures:
            raise psycopg.errors.DeadlockDetected("injected 40P01 after catalog writes")
        return original(self, c, *args)

    monkeypatch.setattr(PartialIngestionService, "_persist_observation", deadlock)
    if failures < 3:
        assert PartialIngestionService().import_batch(one_stat("daily_minimum", 100)).status == "completed"
    else:
        with pytest.raises(psycopg.errors.DeadlockDetected):
            PartialIngestionService().import_batch(one_stat("daily_minimum", 100))
    assert calls == min(failures + 1, 3)
    with connect() as c:
        assert c.execute("SELECT status FROM partial_import_runs").fetchall() == [{"status": "failed" if failures == 3 else "completed"}]
        assert c.execute("SELECT count(*) AS n FROM partial_observations").fetchone()["n"] == (0 if failures == 3 else 1)
