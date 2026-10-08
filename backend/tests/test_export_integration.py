from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, local

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.db.connection import connect
from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.partial_service import PartialIngestionService
from app.main import create_app
from tests.test_native_exports import native_source


@pytest.fixture(autouse=True)
def database(isolated_database):
    pass


def count(c, table):
    return c.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def history(client, result, **params):
    with connect() as c:
        market = c.execute("SELECT id FROM partial_markets WHERE market_key='PvE' AND dataset='real'").fetchone()["id"]
    return client.get("/partial/history", params=dict(market_id=market,item_key="123",
                                                    source_id="export-fixture",**params))


@pytest.mark.parametrize("reverse", [False, True])
def test_exports_and_accumulated_history_keep_distinct_semantics(reverse):
    sources = [native_source(100), native_source(200)]
    if reverse:
        sources.reverse()
    results = [PartialIngestionService().import_batch(s) for s in sources]
    assert results[0].export_id != results[1].export_id
    with TestClient(create_app()) as client:
        for source, result in zip(sources,results):
            rows = history(client,result,export_id=result.export_id).json()
            low = next(r for r in rows if r["statistic"] == "daily_minimum")
            assert low["value"] == source.batch.observations[0].value
            assert low["minimum_origin"] == "h_fallback"
            assert low["original_item_key"] == "00123" and low["original_day_key"] == "02500"
            assert all(r["day_start"] is None and r["value_semantics"] == "export_projection" for r in rows)
            assert next(r for r in rows if r["statistic"] == "last_minimum")["scan_day"] is None
        rows = history(client,results[0]).json()
        assert next(r["value"] for r in rows if r["statistic"] == "daily_minimum") == 100
        assert next(r["value"] for r in rows if r["statistic"] == "daily_highest_minimum") == 200
        assert history(client,results[0],export_id=999999).status_code == 404
        assert history(client,results[0],export_id=results[0].export_id,start_day=2501).json() == []
    with connect() as c:
        assert count(c,"partial_exports") == 2 and count(c,"partial_export_facts") == 4
        assert count(c,"partial_export_imports") == 2
        assert c.execute("SELECT count(*) AS n FROM partial_export_facts WHERE native_field='l'").fetchone()["n"] == 0
        print("native PostgreSQL:", c.execute("SELECT export_id,native_field,scan_day,value FROM partial_export_facts ORDER BY export_id,native_field").fetchall())
        print("accumulated PostgreSQL:",c.execute("SELECT scan_day,statistic,value FROM partial_observations WHERE scan_day=2500 ORDER BY statistic").fetchall())


def test_new_l_evidence_with_identical_projection_is_completed_without_aggregate_change():
    service = PartialIngestionService()
    absent = service.import_batch(native_source())
    present = service.import_batch(native_source(low=100))
    assert present.status == "completed" and present.observations_changed == 0
    assert present.evidence_status == "created" and absent.export_id != present.export_id
    with TestClient(create_app()) as client:
        rows = history(client,present,export_id=present.export_id).json()
        assert next(r for r in rows if r["statistic"] == "daily_minimum")["minimum_origin"] == "l"


def test_reimports_reuse_evidence_but_preserve_each_reception_and_http_compatibility():
    source = native_source()
    service = PartialIngestionService()
    first = service.import_batch(source)
    whitespace = native_source(prefix=b"\n \t")
    assert whitespace.source_hash != source.source_hash
    second = service.import_batch(replace(whitespace,raw_reference="other-path.lua"))
    assert second.export_id == first.export_id and second.evidence_status == "reused"
    assert second.status == "duplicate" and second.observations_changed == 0
    with connect() as c:
        assert count(c,"partial_exports") == 1 and count(c,"partial_export_facts") == 2
        assert count(c,"partial_export_imports") == 2
        assert c.execute("SELECT raw_reference FROM partial_import_runs WHERE id=%s",(second.import_id,)).fetchone()["raw_reference"] == "other-path.lua"
    with TestClient(create_app()) as client:
        response = client.post("/partial/imports",json=source.batch.model_dump(mode="json"))
        assert response.status_code == 200 and response.json()["status"] == "duplicate"
        assert response.json()["export_id"] is None and response.json()["evidence_status"] == "unavailable"
        imports = client.get("/partial/imports").json()
        assert [r["evidence_status"] for r in imports] == ["unavailable","reused","created"]


@pytest.mark.parametrize("identical", [False, True])
def test_native_concurrent_imports_are_atomic_and_idempotent(identical,monkeypatch):
    barrier, state = Barrier(2), local()
    create = PartialIngestionService._create_run

    def synchronized(self,c,result,*args):
        run_id = create(self,c,result,*args)
        if not getattr(state,"started",False):
            state.started = True
            barrier.wait(timeout=10)
        return run_id

    monkeypatch.setattr(PartialIngestionService,"_create_run",synchronized)
    sources = [native_source(),native_source(100 if identical else 200)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda s: PartialIngestionService().import_batch(s),sources))
    assert sorted(r.evidence_status for r in results) == (["created","reused"] if identical else ["created","created"])
    monkeypatch.setattr(PartialIngestionService,"_create_run",create)
    for source,result in zip(sources,results):
        repeated = PartialIngestionService().import_batch(source)
        assert repeated.status == "duplicate" and repeated.export_id == result.export_id
    with connect() as c:
        assert count(c,"partial_exports") == (1 if identical else 2)
        assert count(c,"partial_export_imports") == 4
        assert c.execute("SELECT count(*) AS n FROM partial_import_runs WHERE status='failed'").fetchone()["n"] == 0
    print("native concurrent identical=",identical,"outcomes=",[(r.status,r.evidence_status,r.export_id) for r in results])


def test_native_shared_items_different_markets_follow_global_order():
    def source(markets):
        parts = [f'["{market}"]={{["{item}"]={{l={{}},h={{["2500"]=100}},m=100}}}}' for market,item in markets]
        raw = ('AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,'+','.join(parts)+'}').encode()
        return AuctionatorAdapter().load_bytes(raw,source_id="native-locks",region="export-test")
    sources = [source([("HC",911),("RP",910)]),source([("PvE",910),("PvP",911)])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda s: PartialIngestionService().import_batch(s),sources))
    assert all(r.status == "completed" and r.evidence_status == "created" for r in results)
    with connect() as c:
        assert count(c,"partial_exports") == 2 and count(c,"partial_export_facts") == 8
    print("shared items / separate native markets:",[(r.status,r.evidence_status) for r in results])


def test_real_simulated_source_region_and_timebase_never_merge():
    contexts = [{},{"dataset":"simulated"},{"source_id":"other"},{"region":"other"},
                {"scan_day_zero":"2020-01-01T00:00:00Z"}]
    results = [PartialIngestionService().import_batch(native_source(**context)) for context in contexts]
    assert len({r.export_id for r in results}) == 5
    with connect() as c:
        assert count(c,"partial_exports") == 5 and count(c,"partial_export_facts") == 10
        assert count(c,"partial_markets") == 3


def test_import_link_rejects_wrong_dataset_even_with_manual_sql():
    source = native_source()
    PartialIngestionService().import_batch(source)
    simulated = PartialIngestionService().import_batch(native_source(dataset="simulated"))
    with pytest.raises(psycopg.errors.CheckViolation,match="context mismatch"):
        with connect() as c:
            run_id = PartialIngestionService()._create_run(c,source,"completed")
            c.execute("""INSERT INTO partial_export_imports(import_id,export_id,input_format,decoder_version)
                         VALUES (%s,%s,'lua_tables','auctionator340-v1')""",(run_id,simulated.export_id))
    with connect() as c:
        assert count(c,"partial_import_runs") == 2 and count(c,"partial_export_imports") == 2


@pytest.mark.parametrize("operation", [
    "UPDATE partial_exports SET source_id='changed'", "UPDATE partial_exports SET sealed=FALSE",
    "DELETE FROM partial_exports", "TRUNCATE partial_exports CASCADE",
    "UPDATE partial_export_facts SET value=999", "DELETE FROM partial_export_facts",
    "TRUNCATE partial_export_facts", "UPDATE partial_export_imports SET decoder_version='changed'",
    "DELETE FROM partial_export_imports", "TRUNCATE partial_export_imports",
])
def test_sealed_evidence_rejects_accidental_manual_mutations(operation):
    PartialIngestionService().import_batch(native_source(low=50))
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as c:
            c.execute(operation)
    with connect() as c:
        assert count(c,"partial_exports") == 1 and count(c,"partial_export_facts") == 3
        assert count(c,"partial_export_imports") == 1


def test_cannot_append_facts_to_sealed_export():
    result = PartialIngestionService().import_batch(native_source())
    with pytest.raises(psycopg.errors.CheckViolation,match="append facts"):
        with connect() as c:
            c.execute("""INSERT INTO partial_export_facts(export_id,market_id,item_id,market_key,ruleset,item_key,
                         external_item_id,key_kind,original_item_key,native_field,scan_day,original_day_key,value)
                         SELECT export_id,market_id,item_id,market_key,ruleset,item_key,external_item_id,key_kind,
                         original_item_key,'a',scan_day,original_day_key,0 FROM partial_export_facts
                         WHERE export_id=%s AND native_field='h'""",(result.export_id,))


@pytest.mark.parametrize("failure", ["unsealed","count","contradictory","presealed"])
def test_manual_header_requires_complete_coherent_sealed_evidence(failure):
    source = native_source(low=50)
    first = PartialIngestionService().import_batch(source)
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as c:
            run_id = PartialIngestionService()._create_run(c,source,"completed")
            new_id = c.execute("""INSERT INTO partial_exports(source_type,source_id,source_version,database_version,
                dataset,region,temporal_basis,canonical_version,state_hash,structure_manifest,native_fact_count,
                first_import_id,sealed)
                SELECT source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                canonical_version,%s,structure_manifest,native_fact_count,%s,%s FROM partial_exports WHERE id=%s
                RETURNING id""",("d"*64,run_id,failure=="presealed",first.export_id)).fetchone()["id"]
            if failure != "unsealed":
                if failure == "contradictory":
                    c.execute("""INSERT INTO partial_export_facts(export_id,market_id,item_id,market_key,ruleset,item_key,
                        external_item_id,key_kind,original_item_key,native_field,scan_day,original_day_key,value)
                        SELECT %s,market_id,item_id,market_key,ruleset,item_key,external_item_id,key_kind,
                        original_item_key,native_field,scan_day,original_day_key,
                        CASE WHEN native_field='l' THEN 200 ELSE value END
                        FROM partial_export_facts WHERE export_id=%s""",(new_id,first.export_id))
                c.execute("UPDATE partial_exports SET sealed=TRUE WHERE id=%s",(new_id,))
    with connect() as c:
        assert count(c,"partial_exports") == 1 and count(c,"partial_export_imports") == 1


@pytest.mark.parametrize("stage", ["facts","aggregate","link"])
def test_complete_rollback_at_every_native_persistence_stage(monkeypatch,stage):
    method = "_persist_export" if stage == "facts" else "_persist_observation" if stage == "aggregate" else "_validate_daily_coherence"
    original = getattr(PartialIngestionService,method)

    def fail(self,c,*args):
        value = original(self,c,*args)
        c.execute("SELECT 1/0")
        return value

    monkeypatch.setattr(PartialIngestionService,method,fail)
    with pytest.raises(psycopg.errors.DivisionByZero):
        PartialIngestionService().import_batch(native_source(low=50))
    with connect() as c:
        for table in ("partial_exports","partial_export_facts","partial_export_imports",
                      "partial_observations","partial_items","partial_markets"):
            assert count(c,table) == 0
        assert c.execute("SELECT status FROM partial_import_runs").fetchall() == [{"status":"failed"}]


def test_empty_catalog_entries_are_preserved_and_snapshot_identity_is_stable():
    raw = b'AUCTIONATOR_PRICE_DATABASE={["__dbversion"]=8,["HC"]={},["PvE"]={["9"]={l={},h={}},["00123"]={l={},h={["02500"]=100},m=100}}}'
    source = AuctionatorAdapter().load_bytes(raw,source_id="export-fixture",region="export-test")
    result = PartialIngestionService().import_batch(source)
    with connect() as c:
        assert count(c,"partial_items") == 2 and count(c,"partial_markets") == 2
        c.execute("UPDATE partial_items SET item_key='999',external_item_id='999' WHERE item_key='123'")
    with TestClient(create_app()) as client:
        rows = history(client,result,export_id=result.export_id).json()
        assert rows and all(r["item_key"] == "123" and r["external_item_id"] == "123" for r in rows)


@pytest.mark.parametrize("failures", [1, 3])
def test_native_deadlock_retry_rolls_back_sealed_evidence_too(monkeypatch,failures):
    original = PartialIngestionService._persist_observation
    calls = 0

    def injected(self,c,*args):
        nonlocal calls
        calls += 1
        if calls <= failures:
            raise psycopg.errors.DeadlockDetected("injected after native seal")
        return original(self,c,*args)

    monkeypatch.setattr(PartialIngestionService,"_persist_observation",injected)
    if failures == 3:
        with pytest.raises(psycopg.errors.DeadlockDetected):
            PartialIngestionService().import_batch(native_source())
    else:
        assert PartialIngestionService().import_batch(native_source()).evidence_status == "created"
    with connect() as c:
        for table in ("partial_exports","partial_export_imports"):
            assert count(c,table) == (0 if failures == 3 else 1)
        assert count(c,"partial_export_facts") == (0 if failures == 3 else 2)
        assert c.execute("SELECT status FROM partial_import_runs").fetchall() == [{"status":"failed" if failures == 3 else "completed"}]
