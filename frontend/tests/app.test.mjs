// Mounted React tests with synthetic API fixtures only; no real network or DB.
import test, { afterEach, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:5173/", pretendToBeVisual: true });
for (const name of ["window", "document", "HTMLElement", "HTMLInputElement", "SVGElement", "Event", "MouseEvent", "KeyboardEvent"]) globalThis[name] = name === "window" ? dom.window : dom.window[name];
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let route;
globalThis.fetch = async (url, options) => route(new URL(url), options);
const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const { App } = require(join(process.env.TEST_BUILD_DIR, "App.cjs"));
const { PriceChart } = require(join(process.env.TEST_BUILD_DIR, "features/market/PriceChart.js"));
const { chartGeometry } = require(join(process.env.TEST_BUILD_DIR, "features/market/chart.js"));
const { assertResponse } = require(join(process.env.TEST_BUILD_DIR, "api/contracts.js"));

const markets = [
  { id: 1, market_key: "PvE", ruleset: "PvE", region: "simulation", dataset: "simulated" },
  { id: 2, market_key: "PvP", ruleset: "PvP", region: "simulation", dataset: "simulated" },
];
const items = [101, 102, 103].map((id, i) => ({ id: i + 1, item_key: String(id), external_item_id: String(id), key_kind: "item" }));
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
function context(marketId, itemKey) {
  return { market_id: marketId, item_key: itemKey, source_id: `fixture-source-${marketId}`, source_type: "simulated", temporal_basis: "unknown", series_mode: "accumulated", export_id: null,
    market_key: markets.find(m => m.id === marketId).market_key, ruleset: markets.find(m => m.id === marketId).ruleset,
    region: "simulation", dataset: "simulated", external_item_id: itemKey, key_kind: "item", source_version: "340", database_version: 8, value_semantics: "accumulated_extreme" };
}
function series(marketId, itemKey, last = 129) {
  return { series: [{ context: context(marketId, itemKey), item_first_day: 100, item_last_day: last, market_first_day: 100, market_last_day: last, excluded_undated_count: 0, availability_field_presence: "unknown", first_received_at: null }], limit: 100, offset: 0, has_more: false };
}
function metricsResponse(url, empty = false) {
  const q = url.searchParams, marketId = Number(q.get("market_id")), itemKey = q.get("item_key");
  const range = q.get("window_type") === "index_range";
  const requested = range ? Number(q.get("end_day")) - Number(q.get("start_day")) + 1 : Number(q.get("size"));
  const count = range ? requested : Math.min(requested, 30);
  const start = range ? Number(q.get("start_day")) : 130 - count;
  const price = marketId * 1000 + Number(itemKey);
  const metric = (value, unit) => ({ value: empty ? null : String(value), unit, status: empty ? "no_data" : "ok", reason: empty ? "no_price_data" : null, observation_count: empty ? 0 : count, first_day: null, last_day: null });
  const points = Array.from({ length: count }, (_, i) => ({ scan_day: start + i, bucket_start: null, market_observed: true, daily_minimum: empty ? null : price, daily_highest_minimum: empty ? null : price,
    daily_max_available: empty ? null : 5, minimum_origin: empty ? null : "unknown", minimum_evidence: null, highest_minimum_evidence: null, availability_evidence: null }));
  const data = {
    analysis_version: "3a-v1", decimal_precision: 40, context: context(marketId, itemKey),
    window: { spec: { window_type: range ? "index_range" : "observed_buckets", size: range ? null : requested, start_day: range ? start : null, end_day: q.has("end_day") ? Number(q.get("end_day")) : null, days: null },
      anchor_day: start + count - 1, market_first_day: 100, market_last_day: Math.max(129, start + count - 1), start_day: start, end_day: start + count - 1,
      positions: points.map(p => p.scan_day), requested_position_count: requested, calendar_start: null, calendar_end_exclusive: null }, points,
    metrics: {
      minimum_copper: metric(price, "copper"), mean_daily_minimum_copper: metric(price, "copper"), median_daily_minimum_copper: metric(price, "copper"),
      first_minimum_copper: metric(price, "copper"), last_minimum_copper: metric(price, "copper"), price_change_copper: metric(0, "copper"), price_change_pct: metric(0, "percent"),
      minimum_stddev_copper: metric(0, "copper"), minimum_cv_pct: metric(0, "percent"), trend_copper_per_scan_index: metric(0, "copper/scan_index"),
      first_max_available: metric(5, "units"), last_max_available: metric(5, "units"), availability_change_units: metric(0, "units"), availability_change_pct: metric(0, "percent"),
    },
    coverage: { selected_position_count: count, observed_market_bucket_count: count, price_observation_count: empty ? 0 : count, availability_observation_count: empty ? 0 : count,
      missing_price_position_count: empty ? count : 0, missing_availability_position_count: empty ? count : 0, index_span_position_count: count, unobserved_market_position_count: 0,
      price_ratio: { ...metric(empty ? 0 : 1, "ratio"), value: empty ? "0" : "1", status: "ok", reason: null },
      availability_ratio: { ...metric(empty ? 0 : 1, "ratio"), value: empty ? "0" : "1", status: "ok", reason: null } },
    quality: { warnings: [{ code: "simulated_dataset", message: "Synthetic fixture" }], minimum_l_count: 0, minimum_h_fallback_count: 0, minimum_unknown_origin_count: empty ? 0 : count, availability_field_presence: "unknown", sample_warning_threshold: 7 },
    provenance: { selected_daily_row_count: empty ? 0 : count * 3, excluded_undated_count: 0, referenced_import_ids: [], export_state_hash: null, first_received_at: null },
  };
  assertResponse(data, "MarketMetricsResponse");
  return data;
}

let root;
function mockApi(override = () => undefined) {
  const calls = [];
  route = (url, options) => {
    assert.equal(url.origin, "http://test.invalid");
    calls.push({ url, signal: options.signal });
    const result = override(url, options);
    if (result !== undefined) return result;
    if (url.pathname === "/partial/markets") return json(markets);
    if (url.pathname === "/partial/items") return json(items);
    if (url.pathname === "/market/series") return json(series(Number(url.searchParams.get("market_id")), url.searchParams.get("item_key")));
    if (url.pathname === "/market/metrics") return json(metricsResponse(url));
    throw new Error(`Unexpected test request: ${url}`);
  };
  return calls;
}
async function mount(Component = App, props = {}) {
  const container = document.createElement("div"); document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(React.createElement(React.StrictMode, null, React.createElement(Component, props))));
}
async function flush(ms = 0) { await act(async () => { await new Promise(resolve => setTimeout(resolve, ms)); }); }
async function waitFor(predicate, message) {
  const deadline = Date.now() + 2500;
  while (!predicate() && Date.now() < deadline) await flush(10);
  assert.ok(predicate(), message);
}
function control(label, selector = "select") {
  const match = [...document.querySelectorAll("label")].find(element => element.textContent.trim().startsWith(label));
  assert.ok(match, `Missing label ${label}`);
  return match.querySelector(selector);
}
async function change(element, value) {
  await act(async () => {
    if (element instanceof HTMLInputElement) Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(element, value);
    else element.value = value;
    element.dispatchEvent(new Event(element.tagName === "INPUT" ? "input" : "change", { bubbles: true }));
  });
}
async function chooseItem(key) {
  const button = [...document.querySelectorAll(".item-button")].find(element => element.querySelector("strong").textContent === `Item ${key}`);
  assert.ok(button, `Missing item ${key}`);
  await act(async () => button.click());
}
async function chooseMarket(id = "1") { await change(control("Mercado"), id); await waitFor(() => document.querySelector(".item-button"), "Catalog should load"); }
afterEach(async () => { if (root) await act(async () => root.unmount()); root = undefined; document.body.replaceChildren(); });
after(() => dom.window.close());

test("mounted App: market/item selection automatically loads results once, and advanced options open/close", async () => {
  const calls = mockApi(); await mount();
  assert.equal(calls.filter(c => c.url.pathname === "/partial/markets").length, 1, "StrictMode must not duplicate the request");
  const advanced = document.querySelector(".advanced-panel details"); assert.equal(advanced.open, false);
  await act(async () => advanced.querySelector("summary").click()); assert.equal(advanced.open, true);
  await act(async () => advanced.querySelector("summary").click()); assert.equal(advanced.open, false);
  await chooseMarket(); await chooseItem("101");
  assert.match(document.body.textContent, /Cargando gráfico y estadísticas/);
  await waitFor(() => document.querySelector(".results"), "Results must load automatically");
  assert.equal(document.querySelector(".result-heading h2").textContent, "Item 101");
  assert.match(document.querySelector(".results").textContent, /SIMULATED/);
  assert.equal(calls.filter(c => c.url.pathname === "/market/metrics").length, 1);
  const query = calls.find(c => c.url.pathname === "/market/metrics").url.searchParams;
  assert.equal(query.get("size"), "30"); assert.equal(query.get("series_mode"), "accumulated"); assert.equal(query.has("export_id"), false);
});

test("mounted App: late metrics cannot overwrite a newer market/item, and old results disappear while loading", async () => {
  let releaseOld, oldSignal;
  const calls = mockApi((url, options) => {
    if (url.pathname === "/market/metrics" && url.searchParams.get("market_id") === "1" && url.searchParams.get("item_key") === "102") {
      oldSignal = options.signal;
      return new Promise(resolve => { releaseOld = () => resolve(json(metricsResponse(url))); });
    }
  });
  await mount(); await chooseMarket(); await chooseItem("101"); await waitFor(() => document.querySelector(".results"), "Initial results");
  await chooseItem("102"); assert.equal(document.querySelector(".results"), null);
  await waitFor(() => releaseOld, "Pending old request");
  await chooseMarket("2"); await waitFor(() => document.querySelector(".results"), "New market must reload the compatible item");
  assert.equal(oldSignal.aborted, true);
  assert.match(document.querySelector(".result-heading").textContent, /PvP/);
  await act(async () => releaseOld()); await flush();
  assert.equal(document.querySelector(".result-heading h2").textContent, "Item 102");
  assert.match(document.querySelector(".result-heading").textContent, /PvP/);
  assert.ok(calls.some(c => c.url.pathname === "/market/metrics" && c.url.searchParams.get("market_id") === "2"));
});

test("mounted App: obsolete discovery responses never trigger metrics for an old item", async () => {
  let releaseOld, oldSignal;
  const calls = mockApi((url, options) => {
    if (url.pathname === "/market/series" && url.searchParams.get("item_key") === "102") {
      oldSignal = options.signal;
      return new Promise(resolve => { releaseOld = () => resolve(json(series(1, "102"))); });
    }
  });
  await mount(); await chooseMarket(); await chooseItem("102"); await waitFor(() => releaseOld, "Old discovery pending");
  await chooseItem("103"); await waitFor(() => document.querySelector(".results"), "New item results");
  await act(async () => releaseOld()); await flush();
  assert.equal(oldSignal.aborted, true);
  assert.equal(document.querySelector(".result-heading h2").textContent, "Item 103");
  assert.equal(calls.filter(c => c.url.pathname === "/market/metrics" && c.url.searchParams.get("item_key") === "102").length, 0);
});

test("mounted App: loading and empty market/catalog states are explicit", async () => {
  let releaseMarkets, releaseItems;
  mockApi(url => {
    if (url.pathname === "/partial/markets") return new Promise(resolve => releaseMarkets = resolve);
    if (url.pathname === "/partial/items") return new Promise(resolve => releaseItems = resolve);
  });
  await mount(); assert.match(document.body.textContent, /Cargando mercados/);
  await act(async () => releaseMarkets(json(markets)));
  await change(control("Mercado"), "1"); await waitFor(() => releaseItems, "Catalog request starts");
  assert.match(document.body.textContent, /Cargando items/);
  await act(async () => releaseItems(json([])));
  assert.match(document.body.textContent, /Sin items disponibles/); assert.equal(document.querySelector(".results"), null);
});

test("mounted App: database HTTP errors expose retry, and retry recovers results", async () => {
  let fail = true;
  mockApi(url => url.pathname === "/market/metrics" && fail ? json({}, 503) : undefined);
  await mount(); await chooseMarket(); await chooseItem("101");
  await waitFor(() => document.querySelector('[role="alert"]'), "Metrics error visible");
  assert.match(document.querySelector('[role="alert"]').textContent, /PostgreSQL/);
  fail = false;
  await act(async () => document.querySelector('[role="alert"] button').click());
  await waitFor(() => document.querySelector(".results"), "Retry should recover");
});

test("mounted App: connection failure retries safely into an empty market list", async () => {
  let offline = true;
  mockApi(url => {
    if (url.pathname === "/partial/markets") {
      if (offline) throw new TypeError("Synthetic offline failure");
      return json([]);
    }
  });
  await mount();
  await waitFor(() => document.querySelector('[role="alert"]'), "Connection error must be visible");
  assert.match(document.querySelector('[role="alert"]').textContent, /conectar con FastAPI/);
  offline = false;
  await act(async () => document.querySelector('[role="alert"] button').click());
  await waitFor(() => document.body.textContent.includes("Todavía no hay mercados"), "Retry must show empty market state");
  assert.equal(document.querySelector(".results"), null);
});

test("mounted App: an empty price response renders absence, and compatible advanced filters persist across items", async () => {
  const calls = mockApi(url => url.pathname === "/market/metrics" ? json(metricsResponse(url, true)) : undefined);
  await mount(); await chooseMarket(); await chooseItem("101"); await waitFor(() => document.querySelector(".chart-empty"), "Empty price response");
  assert.match(document.querySelector(".chart-empty").textContent, /No hay mínimos guardados/);
  await act(async () => document.querySelector(".advanced-panel summary").click());
  await change(control("Cantidad de buckets", "input"), "7");
  await waitFor(() => calls.some(c => c.url.pathname === "/market/metrics" && c.url.searchParams.get("size") === "7"), "Window update is automatic");
  await chooseItem("102"); await waitFor(() => document.querySelector(".result-heading h2")?.textContent === "Item 102", "New item results");
  assert.equal(control("Cantidad de buckets", "input").value, "7");
  assert.ok(calls.some(c => c.url.pathname === "/market/metrics" && c.url.searchParams.get("item_key") === "102" && c.url.searchParams.get("size") === "7"));
});

test("mounted App: generated 501-position range is bounded, while an explicit oversized edit is rejected", async () => {
  mockApi(url => url.pathname === "/market/series" ? json(series(1, url.searchParams.get("item_key"), 600)) : undefined);
  await mount(); await chooseMarket(); await chooseItem("101"); await waitFor(() => document.querySelector(".results"), "Initial results");
  await act(async () => document.querySelector(".advanced-panel summary").click());
  await change(control("Tipo"), "index_range");
  assert.equal(control("Índice inicial", "input").value, "235"); assert.equal(control("Índice final", "input").value, "600");
  await change(control("Índice inicial", "input"), "100");
  assert.match(document.querySelector('[role="alert"]').textContent, /366/);
  assert.equal(control("Índice inicial", "input").value, "100", "Explicit input must not be silently truncated");
  assert.equal(document.querySelector(".results"), null);
});

for (const count of [30, 366]) {
  test(`mounted SVG: mouse/touch select the nearest of ${count} repeated points; keyboard still selects exact buckets`, async () => {
    const points = Array.from({ length: count }, (_, i) => ({ scan_day: 100 + i, daily_minimum: 100, daily_max_available: i, minimum_origin: "unknown", market_observed: true, bucket_start: null }));
    await mount(PriceChart, { data: { context: context(1, "101"), points } });
    const svg = document.querySelector("svg");
    // jsdom has no layout/CTM. Supply a known screen scale/translation and
    // dispatch native pointer events through React's mounted event system.
    svg.getScreenCTM = () => ({ inverse: () => ({ a: 2, b: 0, c: 0, d: 2, e: -20, f: -40 }) });
    const dots = chartGeometry(points).dots;
    for (const [index, pointerType, type] of [[0, "mouse", "pointermove"], [5, "touch", "pointerdown"], [count - 1, "mouse", "pointermove"]]) {
      const event = new Event(type, { bubbles: true });
      Object.assign(event, { clientX: dots[index].x / 2 + 10, clientY: dots[index].y / 2 + 20, pointerType });
      await act(async () => svg.dispatchEvent(event));
      assert.match(document.querySelector(".chart-detail strong").textContent, new RegExp(` ${100 + index}$`));
      assert.ok([...document.querySelectorAll(".chart-hit")].every(circle => circle.getAttribute("pointer-events") === "none"));
    }
    const keyboardPoint = document.querySelectorAll(".chart-hit")[1];
    await act(async () => keyboardPoint.focus());
    assert.match(document.querySelector(".chart-detail strong").textContent, / 101$/);
    await act(async () => keyboardPoint.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    assert.match(document.querySelector(".chart-detail strong").textContent, / 101$/);
    const labels = [...svg.querySelectorAll('text[text-anchor="end"]')].filter(t => t.textContent.endsWith(" c")).map(t => t.textContent);
    assert.equal(new Set(labels).size, labels.length);
  });
}
