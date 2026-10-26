"""Read-only public v2 API against synthetic evidence in an explicit lab."""
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg.rows import dict_row
import pytest

from app.api import evidence, partial
from app.ingestion.local_lineage import VerifiedLocalContext
from app.ingestion.local_readers import LocalEvidenceReader
from app.ingestion.partial_service import PartialIngestionService
from app.main import create_app
from test_341_persistence_integration import lab
from test_local_lineage import local_source
from test_local_capture import lua
from test_trial_database_integration import counts_and_sequences


@pytest.fixture
def scenario(lab, monkeypatch):
    economy = "web-fixture-"+uuid4().hex
    source_id = "PRIVATE_ACCOUNT_SENTINEL-"+uuid4().hex
    monkeypatch.setattr(evidence, "connect", lambda: psycopg.connect(lab[0], row_factory=dict_row))
    monkeypatch.setattr(partial, "connect", lambda: psycopg.connect(lab[0], row_factory=dict_row))
    service = PartialIngestionService(trial_target=lab[2])
    def write(**kwargs):
        source = local_source(economy=economy, source_id=source_id, **kwargs)
        data = source.local_capture.context.model_dump()
        data["provenance"]["origin_evidence_ref"] = "C:\\PRIVATE_PATH_SENTINEL\\Account\\SavedVariables"
        # Preserve private operator assertions on receipts; public API must not
        # serialize them, even while the private reader/CLI keeps them intact.
        context = VerifiedLocalContext.model_validate(data)
        native = source.native.model_copy(update={"provenance": context.provenance})
        source = replace(source, native=native, local_capture=source.local_capture.model_copy(update={"context": context}))
        return service.import_batch(source)
    return TestClient(create_app()), write, economy


def selected(client, economy, dataset="simulated"):
    markets = client.get(f"/evidence/v2/markets?dataset={dataset}&limit=100").json()["items"]
    return next(m["id"] for m in markets if m["economy"] == economy)


def url(market, state=None, action="states", dataset="simulated", **params):
    path = f"/evidence/v2/markets/{market}/states"
    if state is not None:
        path += f"/{state}/{action}"
    return path+f"?dataset={dataset}"+"".join(f"&{k}={v}" for k,v in params.items())


def test_reimports_and_same_bucket_states_do_not_multiply_facts(scenario):
    client, write, economy = scenario
    a, repeated = write(dataset="simulated"), write(dataset="simulated")
    b = write(dataset="simulated", raw=lua(high=200, minimum=200))
    market = selected(client, economy)
    states = client.get(url(market)).json()["items"]
    assert len(states) == 2 and {s["id"] for s in states} == {str(a.export_id),str(b.export_id)}
    assert a.export_id == repeated.export_id and states[0]["receipt_count"] == 2
    assert states[0]["native_fact_count"] == 3 and states[0]["item_count"] == 1
    rows = client.get(url(market,a.export_id,"facts")).json()["items"]
    assert len(rows) == 2 and sum(r["native_fact_count"] for r in rows) == 3
    assert {r["scan_day"] for r in rows} == {2485,None}
    assert rows[0]["minimum_copper"] == 100 and rows[0]["minimum_origin"] == "h_fallback"
    assert rows[1]["minimum_copper"] is None and rows[1]["native_m"] == 100
    receipts = client.get(url(market,a.export_id,"receipts")).json()["items"]
    assert len(receipts) == 2 and receipts[0]["source_sha256"] == receipts[1]["source_sha256"]


def test_public_rows_are_read_only_and_never_leak_private_context(scenario, lab, monkeypatch):
    client, write, economy = scenario
    result = write(dataset="simulated")
    market = selected(client, economy)
    before = counts_and_sequences(lab[0])
    execute = psycopg.Connection.execute
    checked = []
    def inspect(c, query, params=None, **kwargs):
        if isinstance(query,str) and "FROM public.partial_" in query:
            assert c.read_only is True
            assert execute(c,"SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
            checked.append(True)
        return execute(c,query,params,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection,"execute",inspect)
        for path in ("/evidence/v2/markets?dataset=simulated", url(market), url(market,result.export_id,"facts"), url(market,result.export_id,"receipts")):
            response = client.get(path)
            assert response.status_code == 200
            assert all(secret not in response.text for secret in ("PRIVATE_", "capture_context", "archive_metadata", "source_id", "evidence_ref", "raw_reference", "SavedVariables"))
    assert len(checked) >= 4
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with LocalEvidenceReader(evidence.connect)._snapshot() as c:
            c.execute("DELETE FROM partial_items WHERE false")
    assert counts_and_sequences(lab[0]) == before


@pytest.mark.parametrize("dataset", ["simulated", "stress_test", "launch"])
def test_dataset_partition_cannot_be_overridden(scenario, dataset):
    client, write, economy = scenario
    result = write(dataset=dataset)
    market = selected(client,economy,dataset)
    assert client.get(url(market,dataset=dataset)).status_code == 200
    for wrong in {"simulated","stress_test","launch"}-{dataset}:
        assert client.get(url(market,dataset=wrong)).status_code == 404
        assert client.get(url(market,result.export_id,"facts",dataset=wrong)).status_code == 404
        assert client.get(url(market,result.export_id,"receipts",dataset=wrong)).status_code == 404


def test_pagination_keeps_complete_bucket_l_and_h_together(scenario):
    client, write, economy = scenario
    result = write(dataset="simulated",raw=lua(low=0,high=2147483647,minimum=100))
    market = selected(client,economy)
    first = client.get(url(market,result.export_id,"facts",limit=1)).json()
    assert first["has_more"] and len(first["items"]) == 1
    row = first["items"][0]
    assert row["native_l"] == row["minimum_copper"] == 0 and row["native_h"] == 2147483647
    assert row["minimum_origin"] == "l" and row["native_fact_count"] == 3
    second = client.get(url(market,result.export_id,"facts",limit=1,offset=1)).json()
    assert not second["has_more"] and second["items"][0]["native_m"] == 100
    assert client.get(url(market,result.export_id,"facts",offset=2)).json()["items"] == []
    assert client.get(url(market,result.export_id,"receipts",offset=1)).json()["items"] == []


def test_state_from_other_economy_is_rejected(scenario, lab):
    client, write, economy = scenario
    own = write(dataset="simulated")
    other = PartialIngestionService(trial_target=lab[2]).import_batch(local_source(economy="other-"+uuid4().hex,dataset="simulated"))
    market = selected(client,economy)
    assert own.export_id != other.export_id
    assert client.get(url(market,other.export_id,"facts")).status_code == 404
    assert client.get(url(market,other.export_id,"receipts")).status_code == 404


def test_v2_markets_do_not_enter_legacy_dashboard_catalog(scenario):
    client,write,economy = scenario
    write(dataset="simulated")
    market = selected(client,economy)
    response = client.get("/partial/markets")
    assert response.status_code == 200
    assert all(str(m["id"]) != market and m.get("economic_identity") is None for m in response.json())


def test_empty_native_market_has_state_but_no_fact_rows(scenario, lab, tmp_path):
    client, _, economy = scenario
    from test_manual_local_capture import archived_case
    from app.local_capture.preflight import preflight_archive
    raw = lua()[:-1] + b',["PvE"]={version=2}}'
    case = archived_case(tmp_path,raw,economy=economy)
    result = PartialIngestionService(trial_target=lab[2]).import_batch(preflight_archive(*case))
    market = selected(client,economy+"-PvE")
    states = client.get(url(market)).json()["items"]
    assert len(states)==1 and states[0]["item_count"]==states[0]["native_fact_count"]==0
    assert client.get(url(market,result.export_id,"facts")).json()["items"]==[]
