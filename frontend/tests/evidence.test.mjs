// Mounted evidence view with synthetic public API fixtures; no network or DB.
import test, { after, afterEach } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join } from "node:path";
import { readFileSync } from "node:fs";
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:5173/", pretendToBeVisual: true });
for (const name of ["window", "document", "HTMLElement", "HTMLInputElement", "Event", "MouseEvent"]) globalThis[name] = name === "window" ? dom.window : dom.window[name];
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let route;
globalThis.fetch = async (url, options) => route(new URL(url), options);
const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const { App } = require(join(process.env.TEST_BUILD_DIR, "App.cjs"));
const { createEvidenceApi } = require(join(process.env.TEST_BUILD_DIR, "api/evidence.js"));
const { assertResponse } = require(join(process.env.TEST_BUILD_DIR, "api/contracts.js"));
const { collectStateFacts, groupEvidenceItems, filterEvidenceItems } = require(join(process.env.TEST_BUILD_DIR, "features/evidence/items.js"));
const { MoneyValue } = require(join(process.env.TEST_BUILD_DIR, "components/MoneyValue.js"));
const { renderToStaticMarkup } = require("react-dom/server");

const markets = [1,2].map(id => ({ id: String(id), dataset: "simulated", economy: `Synthetic economy ${id}`, region: "synthetic-eu", native_label: "PvP", ruleset: "PvP", auction_house_scope: "shared", faction: null }));
const state = id => ({ id: String(id), state_hash: "a".repeat(64), native_label: "PvP", item_count: 1, native_fact_count: 4, receipt_count: 2, first_acquired_at: "2026-10-24T12:00:00Z", last_acquired_at: "2026-10-25T12:00:00Z" });
const rows = [{ item_key: "g:123:60", external_item_id: "123", key_kind: "gear_level", scan_day: 2485, native_l: 0, native_h: 2147483647, native_a: 0, native_m: null, minimum_copper: 0, minimum_origin: "l", native_fact_count: 3 },
  { item_key: "g:123:60", external_item_id: "123", key_kind: "gear_level", scan_day: null, native_l: null, native_h: null, native_a: null, native_m: 85490, minimum_copper: null, minimum_origin: null, native_fact_count: 1 }];
const receipt = { id: "9007199254740993", acquired_at: "2026-10-24T12:00:00Z", received_at: "2026-10-26T16:00:00Z", status: "duplicate", source_sha256: "b".repeat(64), input_format: "cbor_definite", codec_producer: "unverified", capture_build_known: false };
const json = (data,status=200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
function page(url, items, more=false) {
  return { contract: "5c1-v1", dataset: url.searchParams.get("dataset"), limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")), has_more: more, items };
}
function statesPage(url, items=[state(10),state(11)]) { return { ...page(url,items), market_id: url.pathname.split("/")[4] }; }
function detailPage(url,items,more=false) { return { ...statesPage(url,items), export_id: url.pathname.split("/")[6], has_more: more }; }
function mockApi(override=()=>undefined) {
  const calls=[];
  route = (url,options) => {
    calls.push({url,signal:options.signal});
    assert.ok(!options.method || options.method === "GET");
    const value=override(url,options);
    if (value!==undefined) return value;
    if (url.pathname === "/partial/markets") return json([]);
    if (url.pathname === "/evidence/v2/markets") return json(page(url,markets.map(m=>({...m,dataset:url.searchParams.get("dataset")}))));
    if (url.pathname.endsWith("/states")) return json(statesPage(url));
    if (url.pathname.endsWith("/facts")) return json(detailPage(url,rows));
    if (url.pathname.endsWith("/receipts")) return json(detailPage(url,[receipt]));
    throw new Error(`Unexpected request ${url}`);
  };
  return calls;
}
let root;
async function flush(ms=0) { await act(async()=> { await new Promise(r=>setTimeout(r,ms)); }); }
async function waitFor(predicate) { const until=Date.now()+2500; while (!predicate() && Date.now()<until) await flush(10); assert.ok(predicate(),document.body.textContent); }
async function mount() {
  const container=document.createElement("div"); document.body.append(container); root=createRoot(container);
  await act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(App))));
  await act(async()=>[...document.querySelectorAll(".view-nav button")].find(b=>b.textContent==="Evidencia de mercado").click());
}
function select(label) { const field=[...document.querySelectorAll("label")].find(x=>x.textContent.startsWith(label)); assert.ok(field,label); return field.querySelector("select"); }
async function change(label,value) { await act(async()=> { const element=select(label); element.value=value; element.dispatchEvent(new Event("change",{bubbles:true})); }); }
async function chooseMarket() { await change("Dataset de evidencia","simulated"); await waitFor(()=>select("Economía / mercado").options.length>1); await change("Economía / mercado","1"); await waitFor(()=>select("Estado económico").options.length>1); }
async function chooseState() { await chooseMarket(); await change("Estado económico","10"); await waitFor(()=>document.querySelector(".evidence-table")); }
async function openReceipts() { await act(async()=>document.querySelector(".evidence-provenance summary").click()); await waitFor(()=>document.querySelector(".evidence-receipts li")); }
async function openItem() { await act(async()=>document.querySelector(".evidence-item-details summary").click()); await waitFor(()=>document.querySelector(".evidence-native-records")); }
async function search(value) {
  await act(async()=> {
    const input=document.querySelector('input[type="search"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,value);
    input.dispatchEvent(new Event("input",{bubbles:true}));
  });
}
afterEach(async()=> { if(root) await act(async()=>root.unmount()); root=undefined; document.body.replaceChildren(); });
after(()=>dom.window.close());

test("explicit selection: no v2 request until dataset and no facts until state",async()=> {
  const calls=mockApi(); await mount(); await flush();
  assert.equal(calls.filter(c=>c.url.pathname.startsWith("/evidence")).length,0);
  await chooseMarket(); assert.equal(calls.filter(c=>c.url.pathname.endsWith("/facts")).length,0);
  await change("Estado económico","10"); await waitFor(()=>document.querySelector(".evidence-table"));
  assert.equal(calls.filter(c=>c.url.pathname.endsWith("/receipts")).length,0);
  assert.equal(document.querySelectorAll(".evidence-table tbody tr").length,1);
  assert.equal(document.querySelectorAll(".price-chart").length,0);
});

test("dataset without markets is empty, not an import or synchronization offer",async()=> {
  mockApi(url=>url.pathname==="/evidence/v2/markets"?json(page(url,[])):undefined);
  await mount(); await change("Dataset de evidencia","launch");
  await waitFor(()=>document.body.textContent.includes("Sin economías disponibles"));
  assert.equal(select("Estado económico").disabled,true);
  assert.equal(document.querySelectorAll('input[type="file"]').length,0);
});

test("empty market has no state and changing market clears the prior state immediately",async()=> {
  mockApi(url=>url.pathname==="/evidence/v2/markets/2/states"?json(statesPage(url,[])):undefined);
  await mount(); await chooseState(); await change("Economía / mercado","2");
  assert.equal(document.querySelector(".evidence-table"),null);
  await waitFor(()=>document.body.textContent.includes("Sin estados disponibles"));
  assert.equal(select("Estado económico").value,"");
});

test("exact currency, native IDs/variants, zeroes and undated m without invented names",async()=> {
  mockApi(); await mount(); await chooseState();
  let text=document.querySelector(".evidence-table").textContent;
  assert.match(text,/Item 123/); assert.match(text,/Nivel 60/); assert.match(text,/Sin fecha nativa/); assert.match(text,/0 unidades/);
  assert.doesNotMatch(text,/2485|copper|h · mayor mínimo/);
  assert.ok([...document.querySelectorAll(".coin-amount")].some(x=>x.textContent==="8g54s90c"));
  assert.doesNotMatch(text,/Lotus|Espada|ventas|precio actual/i);
  await openItem(); text=document.querySelector(".evidence-table").textContent;
  assert.match(text,/g:123:60/); assert.match(text,/Bucket nativo 2485/); assert.match(text,/m · último mínimo/);
  assert.ok([...document.querySelectorAll(".raw-copper")].some(x=>x.textContent==="2147483647"));
});

test("acquisition and SQL receipt are labelled separately; provenance is secondary",async()=> {
  mockApi(); await mount(); await chooseState();
  assert.equal(document.querySelector(".evidence-provenance").open,false);
  assert.match(document.querySelector(".evidence-state").textContent,/hora de copia, no la fecha de cada precio/);
  await openReceipts(); const text=document.querySelector(".evidence-provenance").textContent;
  assert.match(text,/Adquisición:/); assert.match(text,/Recepción SQL:/); assert.match(text,/productor no confirmado/);
  assert.match(text,/9007199254740993/); assert.doesNotMatch(text,/source_id|evidence_ref|Account|SavedVariables/);
});

test("loading, sanitized error and retry preserve explicit selection",async()=> {
  let release; let failed=false;
  mockApi(url=>url.pathname.endsWith("/facts")&&!failed?new Promise(resolve=>{release=()=>{failed=true;resolve(json({},503));};}):undefined);
  await mount(); await chooseMarket(); await change("Estado económico","10");
  await waitFor(()=>release); assert.match(document.body.textContent,/Cargando evidencia/);
  await act(async()=>release()); await waitFor(()=>document.querySelector('[role="alert"]'));
  assert.match(document.body.textContent,/No pudimos cargar la evidencia/);
  const retry=[...document.querySelectorAll("button")].find(b=>b.textContent.includes("Reintentar")); assert.ok(retry);
  await act(async()=>retry.click()); await waitFor(()=>document.querySelector(".evidence-table"));
  assert.equal(select("Estado económico").value,"10");
});

test("obsolete fact response is aborted and cannot replace another state",async()=> {
  let release; let signal;
  mockApi((url,options)=>url.pathname==="/evidence/v2/markets/1/states/10/facts"?new Promise(resolve=>{signal=options.signal;release=()=>resolve(json(detailPage(url,[{...rows[0],external_item_id:"999",item_key:"999",key_kind:"item"}])));}):undefined);
  await mount(); await chooseMarket(); await change("Estado económico","10"); await waitFor(()=>release);
  await change("Estado económico","11"); await waitFor(()=>document.querySelector(".evidence-table"));
  assert.equal(signal.aborted,true); await act(async()=>release()); await flush();
  assert.doesNotMatch(document.querySelector(".evidence-table").textContent,/Item 999/);
});

test("dataset change clears economy/state and removes prior evidence",async()=> {
  mockApi(); await mount(); await chooseState(); await change("Dataset de evidencia","stress_test");
  assert.equal(document.querySelector(".evidence-table"),null);
  assert.equal(select("Economía / mercado").value,""); assert.equal(select("Estado económico").value,"");
});

test("basic accessibility: labelled selectors, region, caption, headers and focusable disclosure",async()=> {
  mockApi(); await mount(); await chooseState();
  assert.ok(document.querySelector(".view-nav").getAttribute("aria-label"));
  assert.ok(document.querySelector(".evidence-table caption"));
  assert.equal(document.querySelectorAll('.evidence-table th[scope="col"]').length,5);
  assert.ok(document.querySelector('.evidence-table-scroll[role="region"][tabindex="0"]'));
  await act(async()=>document.querySelector(".evidence-provenance summary").focus());
  assert.equal(document.activeElement.tagName,"SUMMARY");
});

test("contract and context checks reject private fields, unsafe money and wrong selection",async()=> {
  const signal=new AbortController().signal;
  const fixtureUrl=new URL("http://fixture/evidence/v2/markets/1/states/10/facts?dataset=simulated&limit=100&offset=0");
  const good=detailPage(fixtureUrl,rows);
  assertResponse(good,"EvidenceFactsPage");
  assert.throws(()=>assertResponse({...good,source_id:"private"},"EvidenceFactsPage"));
  assert.throws(()=>assertResponse({...good,items:[{...rows[0],native_h:2147483648}]},"EvidenceFactsPage"));
  const api=createEvidenceApi("http://fixture",async()=>json({...good,export_id:"11"}));
  await assert.rejects(api.facts("simulated","1","10",0,signal),/evidence context/);
  await assert.rejects(api.facts("simulated","9223372036854775808","10",0,signal));
});

test("grouping keeps complete variants and native buckets, without choosing a latest bucket",()=> {
  const anotherBucket={...rows[0],scan_day:2486,native_l:50,minimum_copper:50};
  const variant={...rows[0],item_key:"g:123:61"};
  const pet={...rows[0],item_key:"p:123",key_kind:"pet"};
  const grouped=groupEvidenceItems([anotherBucket,...rows,variant,pet]);
  assert.equal(grouped.length,3);
  assert.equal(grouped[0].lastMinimum,85490);
  assert.deepEqual(grouped[0].history.map(r=>r.scan_day),[2485,2486]);
  assert.deepEqual(grouped[0].history.map(r=>r.minimum_copper),[0,50]);
  assert.equal(grouped[1].lastMinimum,null); assert.equal(grouped[2].kind,"pet");
  assert.deepEqual(filterEvidenceItems(grouped,"g:123:61").map(i=>i.key),["g:123:61"]);
  assert.equal(filterEvidenceItems(grouped,"Copper Ore").length,0);
});

test("missing values stay null and explicit zero stays zero",()=> {
  const grouped=groupEvidenceItems([{...rows[0],native_l:null,native_h:0,native_a:null,minimum_copper:0,minimum_origin:"h_fallback",native_fact_count:1}]);
  assert.equal(grouped[0].lastMinimum,null); assert.equal(grouped[0].history[0].native_a,null);
  assert.equal(grouped[0].history[0].minimum_copper,0);
});

test("grouping rejects repeated item/bucket and incompatible identity or time",()=> {
  assert.throws(()=>groupEvidenceItems([rows[0],rows[0]]),/repeated/);
  assert.throws(()=>groupEvidenceItems([rows[0],{...rows[1],external_item_id:"456"}]),/identity/);
  assert.throws(()=>groupEvidenceItems([{...rows[0],native_m:10}]),/native time/);
  assert.throws(()=>groupEvidenceItems([{...rows[1],native_a:1}]),/native time/);
});

const historical=(n,key="g:123:60")=>({ ...rows[0],item_key:key,external_item_id:key.split(":")[1],scan_day:n,native_l:n,native_h:null,native_a:null,minimum_copper:n,native_fact_count:1 });
const batch=(items,offset,more=false)=>({contract:"5c1-v1",dataset:"simulated",market_id:"1",export_id:"10",limit:100,offset,has_more:more,items});

test("all pages are collected before grouping: one item may cross a page boundary",async()=> {
  const history=Array.from({length:100},(_,i)=>historical(i)); const calls=[];
  const collected=await collectStateFacts(async offset=>{calls.push(offset);return offset===0?batch(history,0,true):batch([rows[1]],100);},101,new AbortController().signal);
  assert.deepEqual(calls,[0,100]);
  const grouped=groupEvidenceItems(collected);
  assert.equal(grouped.length,1); assert.equal(grouped[0].history.length,100); assert.equal(grouped[0].lastMinimum,85490);
});

test("pagination rejects missing pages, repeats, contradictory offsets and counts",async()=> {
  const signal=new AbortController().signal;
  await assert.rejects(collectStateFacts(async()=>batch([],0),1,signal),/incomplete/);
  await assert.rejects(collectStateFacts(async()=>batch([rows[1]],1),1,signal),/pagination/);
  await assert.rejects(collectStateFacts(async()=>batch([rows[1]],0,true),1,signal),/pagination/);
  await assert.rejects(collectStateFacts(async()=>batch([rows[1],rows[1]],0),2,signal),/repeated/);
  await assert.rejects(collectStateFacts(async()=>batch([rows[0]],0),1,signal),/size/);
  await assert.rejects(collectStateFacts(async()=>batch([],0),200001,signal),/size/);
});

test("cancellation between pages stops collection and suppresses partial results",async()=> {
  const controller=new AbortController(); let calls=0;
  await assert.rejects(collectStateFacts(async()=> {
    calls++;controller.abort();return batch(Array.from({length:100},(_,i)=>historical(i)),0,true);
  },101,controller.signal),{name:"AbortError"});
  assert.equal(calls,1);
});

test("multiple buckets stay in one item row with separate advanced records",async()=> {
  const facts=[...rows,{...rows[0],scan_day:2490,native_l:10000,minimum_copper:10000}];
  mockApi(url=>url.pathname.endsWith("/states")?json(statesPage(url,[{...state(10),native_fact_count:7}])):url.pathname.endsWith("/facts")?json(detailPage(url,facts)):undefined);
  await mount(); await chooseState();
  assert.equal(document.querySelectorAll(".evidence-item-row").length,1);
  const primary=document.querySelector(".evidence-item-row");
  assert.match(primary.textContent,/2 registros separados/); assert.match(primary.textContent,/Ver por registro/);
  assert.equal(primary.querySelectorAll(".money-compact").length,1);
  assert.equal(primary.querySelector(".evidence-native-records"),null);
  await openItem();
  assert.equal(document.querySelectorAll(".evidence-native-records>li").length,3);
  assert.match(primary.textContent,/Bucket nativo 2485/);assert.match(primary.textContent,/Bucket nativo 2490/);
});

test("missing fields show a short warning and fallback details without fabricated zero",async()=> {
  const facts=[{...rows[0],native_l:null,native_h:100,native_a:null,minimum_copper:100,minimum_origin:"h_fallback",native_fact_count:1}];
  mockApi(url=>url.pathname.endsWith("/states")?json(statesPage(url,[{...state(10),native_fact_count:1}])):url.pathname.endsWith("/facts")?json(detailPage(url,facts)):undefined);
  await mount();await chooseState();
  const text=document.querySelector(".evidence-item-row").textContent;
  assert.match(text,/Falta último mínimo/);assert.match(text,/disponibilidad/);assert.match(text,/Sin dato/);assert.doesNotMatch(text,/0 unidades/);
  await openItem();assert.match(document.querySelector(".evidence-item-row").textContent,/h · fallback, l ausente/);
});

test("ID/variant search covers all loaded items and local paging never refetches facts",async()=> {
  const facts=Array.from({length:26},(_,i)=>historical(2485,`g:${1000+i}:60`));
  const calls=mockApi(url=>url.pathname.endsWith("/states")?json(statesPage(url,[{...state(10),item_count:26,native_fact_count:26}])):url.pathname.endsWith("/facts")?json(detailPage(url,facts)):undefined);
  await mount();await chooseState();
  assert.equal(document.querySelectorAll(".evidence-item-row").length,25);
  const factCalls=calls.filter(c=>c.url.pathname.endsWith("/facts")).length;
  await act(async()=>[...document.querySelectorAll("button")].find(b=>b.textContent==="Siguiente · items").click());
  assert.equal(document.querySelectorAll(".evidence-item-row").length,1);assert.match(document.querySelector(".evidence-item-row").textContent,/Item 1025/);
  await search("g:1001:60");assert.equal(document.querySelectorAll(".evidence-item-row").length,1);assert.match(document.querySelector(".evidence-item-row").textContent,/Item 1001/);
  await search("unverified name");assert.match(document.body.textContent,/Sin coincidencias/);
  await search("");assert.equal(document.querySelectorAll(".evidence-item-row").length,25);
  assert.equal(calls.filter(c=>c.url.pathname.endsWith("/facts")).length,factCalls);
  assert.ok(calls.every(c=>c.url.pathname!=="/items"));
});

test("variants of one numeric ID stay in separate primary rows and filter independently",async()=> {
  const facts=[...rows,{...rows[0],item_key:"g:123:61"}];
  mockApi(url=>url.pathname.endsWith("/states")?json(statesPage(url,[{...state(10),item_count:2,native_fact_count:7}])):url.pathname.endsWith("/facts")?json(detailPage(url,facts)):undefined);
  await mount();await chooseState();assert.equal(document.querySelectorAll(".evidence-item-row").length,2);
  await search("g:123:61");assert.equal(document.querySelectorAll(".evidence-item-row").length,1);assert.match(document.querySelector(".evidence-item-row").textContent,/Nivel 61/);
});

test("compact MoneyValue preserves exact arithmetic and default detailed layout",()=> {
  for(const value of [0,85490,2147483647]) {
    const compact=renderToStaticMarkup(React.createElement(MoneyValue,{value,compact:true}));
    const detailed=renderToStaticMarkup(React.createElement(MoneyValue,{value}));
    assert.doesNotMatch(compact,/<details/);assert.match(compact,/money-compact/);
    assert.match(detailed,/<details/);assert.match(detailed,new RegExp(`>${value}</span> copper`));
    const compactNode=document.createElement("div"), detailedNode=document.createElement("div");
    compactNode.innerHTML=compact; detailedNode.innerHTML=detailed;
    assert.equal(compactNode.querySelector(".coin-amount").outerHTML,detailedNode.querySelector(".coin-amount").outerHTML);
  }
});

test("responsive summary keeps labelled item rows and inline denominations at mobile widths",async()=> {
  const original=window.innerWidth;Object.defineProperty(window,"innerWidth",{configurable:true,value:390});
  try {
    mockApi();await mount();await chooseState();
    assert.equal(document.querySelectorAll('.evidence-item-row[role="row"]').length,1);
    assert.equal(document.querySelectorAll(".evidence-item-row>td[data-label]").length,4);
    assert.equal(document.querySelector(".money-compact details"),null);
    const css=readFileSync(new URL("../src/styles.css",import.meta.url),"utf8");
    assert.match(css,/@media\(max-width:760px\)/);assert.match(css,/\.evidence-item-table \{ display:block; min-width:0/);
    assert.match(css,/\.evidence-table \.coin-amount \{[^}]*flex-wrap:nowrap/);
    assert.match(css,/\.evidence-table \.coin-denomination small \{ display:inline/);
  } finally { Object.defineProperty(window,"innerWidth",{configurable:true,value:original}); }
});
