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
const { MarketSignals } = require(join(process.env.TEST_BUILD_DIR, "features/market/MarketSignals.js"));
const { MoneyValue } = require(join(process.env.TEST_BUILD_DIR, "components/MoneyValue.js"));
const { signalsMatchAnalysis, deviationLabels, trendLabels, reasonLabels } = require(join(process.env.TEST_BUILD_DIR, "features/market/signals.js"));

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
  const calendar = q.get("window_type") === "calendar_days";
  const requested = range ? Number(q.get("end_day")) - Number(q.get("start_day")) + 1 : Number(q.get(calendar ? "days" : "size"));
  const count = range ? requested : Math.min(requested, 30);
  const start = range ? Number(q.get("start_day")) : 130 - count;
  const price = marketId * 1000 + Number(itemKey.split(":")[0]);
  const selectedContext = { ...context(marketId, itemKey),
    source_id: q.get("source_id") ?? context(marketId, itemKey).source_id,
    source_type: q.get("source_type") ?? "simulated", temporal_basis: q.get("temporal_basis") ?? "unknown",
    series_mode: q.get("series_mode") ?? "accumulated", export_id: q.has("export_id") ? Number(q.get("export_id")) : null,
    value_semantics: q.get("series_mode") === "export" ? "export_projection" : "accumulated_extreme" };
  const metric = (value, unit) => ({ value: empty ? null : String(value), unit, status: empty ? "no_data" : "ok", reason: empty ? "no_price_data" : null, observation_count: empty ? 0 : count, first_day: null, last_day: null });
  const points = Array.from({ length: count }, (_, i) => ({ scan_day: start + i, bucket_start: null, market_observed: true, daily_minimum: empty ? null : price, daily_highest_minimum: empty ? null : price,
    daily_max_available: empty ? null : 5, minimum_origin: empty ? null : "unknown", minimum_evidence: null, highest_minimum_evidence: null, availability_evidence: null }));
  const data = {
    analysis_version: "3a-v1", decimal_precision: 40, context: selectedContext,
    window: { spec: { window_type: range ? "index_range" : calendar ? "calendar_days" : "observed_buckets", size: range || calendar ? null : requested, start_day: range ? start : null, end_day: q.has("end_day") ? Number(q.get("end_day")) : null, days: calendar ? requested : null },
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

function signalsResponse(url, empty = false) {
  const a = metricsResponse(url, empty), m = a.metrics;
  const ratio = { ...a.coverage.price_ratio };
  const evidence = {
    status: empty ? "insufficient" : "sufficient",
    reasons: empty ? [{ code: "insufficient_observations", message: "Not enough prices." }] : [],
    usable_observation_count: a.coverage.price_observation_count,
    historical_observation_count: Math.max(0, a.coverage.price_observation_count - 1),
    requested_price_ratio: ratio, index_span_price_ratio: ratio, latest_price_lag: empty ? null : 0,
    minimum_l_count: 0, minimum_h_fallback_count: 0, minimum_unknown_origin_count: a.coverage.price_observation_count,
  };
  const { metrics, ...shared } = a;
  const data = { ...shared, analysis_version: "3b1-v1", metrics_analysis_version: "3a-v1",
    parameters: { min_history_observations: 7, min_trend_observations: 7, min_price_coverage: "0.8", min_index_coverage: "0.5", deviation_threshold_pct: "20", trend_threshold_pct: "10", min_trend_slope_copper_per_scan_index: "0", max_latest_price_lag: 0, require_native_l: false, require_known_temporal_basis: false },
    warnings: [{ code: "statistical_rules_only", message: "Descriptive rules only." }],
    price_deviation: { signal_type: "historical_price_deviation", direction: empty ? "insufficient_evidence" : "no_significant_deviation", observed_price_copper: m.last_minimum_copper,
      reference_price_copper: m.median_daily_minimum_copper, reference_method: "median_excluding_latest", signed_deviation_copper: m.price_change_copper, absolute_deviation_copper: m.price_change_copper, deviation_pct: m.price_change_pct, evidence: structuredClone(evidence), explanation: "Synthetic deviation explanation." },
    historical_trend: { signal_type: "historical_price_trend", direction: empty ? "insufficient_evidence" : "no_significant_trend", first_price_copper: m.first_minimum_copper, last_price_copper: m.last_minimum_copper,
      slope_copper_per_scan_index: m.trend_copper_per_scan_index, price_change_copper: m.price_change_copper, price_change_pct: m.price_change_pct, evidence: structuredClone(evidence), explanation: "Synthetic trend explanation." },
  };
  assertResponse(data, "MarketSignalsResponse");
  return JSON.parse(JSON.stringify(data)); // Independent MetricValue fixtures, as in parsed HTTP JSON.
}
const fixtureUrl = () => new URL("http://test.invalid/market/signals?market_id=1&item_key=101&window_type=observed_buckets&size=30");

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
    if (url.pathname === "/market/signals") return json(signalsResponse(url));
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

test("mounted currency: exact copper opens through the native disclosure for keyboard/touch", async () => {
  await mount(MoneyValue, { value: "85490.12345000000000000001", kind: "derived" });
  assert.equal(document.querySelector(".coin-amount").textContent, "≈8g54s90c");
  assert.match(document.querySelector(".coin-amount").getAttribute("aria-label"), /8 oro, 54 plata/);
  assert.ok([...document.querySelectorAll(".coin-denomination")].every(t => t.getAttribute("aria-hidden") === "true"));
  const disclosure = document.querySelector("details"), summary = disclosure.querySelector("summary");
  assert.equal(disclosure.open, false);
  await act(async () => summary.focus()); assert.equal(document.activeElement, summary);
  await act(async () => summary.click()); assert.equal(disclosure.open, true);
  assert.equal(disclosure.querySelector(".raw-copper").textContent, "85490.12345000000000000001");
});

test("mounted SVG: focus/touch detail and titles show coins plus exact native copper", async () => {
  const points = [85490, 10000, 0].map((price, i) => ({ scan_day: 100 + i, daily_minimum: price, daily_max_available: 85490, minimum_origin: "unknown", market_observed: true, bucket_start: null }));
  await mount(PriceChart, { data: { context: context(1, "101"), points } });
  const hit = document.querySelector(".chart-hit");
  assert.match(hit.getAttribute("aria-label"), /8g 54s 90c; 85490 copper exactos/);
  assert.match(hit.querySelector("title").textContent, /8g 54s 90c · 85490 copper exactos/);
  await act(async () => hit.focus());
  assert.equal(document.querySelector(".chart-detail .coin-amount").textContent, "8g54s90c");
  assert.match(document.querySelector(".chart-detail").textContent, /Disponibilidad máxima: 85490/);
  const summary = document.querySelector(".chart-detail summary");
  await act(async () => summary.click());
  assert.equal(document.querySelector(".chart-detail details").open, true);
  assert.equal(document.querySelector(".chart-detail .raw-copper").textContent, "85490");
  const svg = document.querySelector("svg");
  svg.getScreenCTM = () => ({ inverse: () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }) });
  const dot = chartGeometry(points).dots[2], event = new Event("pointerdown", { bubbles: true });
  Object.assign(event, { clientX: dot.x, clientY: dot.y, pointerType: "touch" });
  await act(async () => svg.dispatchEvent(event));
  assert.equal(document.querySelector(".chart-detail .coin-amount").textContent, "0c");
  assert.match(document.querySelector(".chart-detail strong").textContent, /Índice 102/);
});

test("mounted signals: coins change presentation while directions, percentages, evidence and API values stay intact", async () => {
  const url = fixtureUrl(), data = signalsResponse(url);
  data.price_deviation.observed_price_copper.value = "85490";
  data.price_deviation.reference_price_copper.value = "1102045.5";
  data.price_deviation.signed_deviation_copper.value = "-1600.5";
  data.price_deviation.direction = "below_reference";
  data.price_deviation.deviation_pct.value = "-20.1234567890123456789";
  data.historical_trend.slope_copper_per_scan_index.value = "-0.00000000000000000001";
  data.historical_trend.direction = "descending";
  const before = JSON.stringify(data);
  await mount(MarketSignals, { analysis: metricsResponse(url), resource: { status: "success", data } });
  const cards = document.querySelectorAll(".signal-values .metric-card");
  const find = label => [...cards].find(c => c.querySelector(".metric-label").textContent === label);
  assert.equal(find("Último mínimo guardado").querySelector(".coin-amount").textContent, "8g54s90c");
  assert.equal(find("Referencia: mediana sin el último").querySelector(".coin-amount").textContent, "≈110g20s46c");
  assert.equal(find("Diferencia con signo").querySelector(".coin-amount").textContent, "≈−16s1c");
  assert.equal(find("Cobertura de la ventana solicitada").querySelector(".coin-amount"), null);
  const deviation = document.querySelector('[data-direction="below_reference"]');
  assert.match(deviation.querySelector(".exact-value").textContent, /−20,12… %/);
  assert.equal(deviation.querySelector(".exact-value").querySelector(".coin-amount"), null);
  assert.match(find("Pendiente descriptiva").textContent, /\/ índice/);
  assert.match(find("Pendiente descriptiva").querySelector(".metric-number").textContent, /−0,00000000000000000001/);
  assert.equal(find("Pendiente descriptiva").querySelector(".coin-amount"), null);
  assert.equal(find("Diferencia con signo").querySelector(".raw-copper").textContent, "-1600.5");
  assert.match(document.querySelector(".signal-parameters").textContent, /min_trend_slope_copper_per_scan_index0/);
  assert.equal(document.querySelector(".signal-parameters .coin-amount"), null);
  assert.equal(JSON.stringify(data), before);
});

test("mounted results: price table uses coins and keeps availability and bucket indices numeric", async () => {
  const { MarketResults } = require(join(process.env.TEST_BUILD_DIR, "features/market/MarketResults.js"));
  const data = metricsResponse(fixtureUrl()); data.points[0].daily_minimum = 85490; data.points[0].daily_max_available = 85490;
  await mount(MarketResults, { data });
  const row = document.querySelector(".evidence-table tbody tr");
  assert.match(row.querySelector("th").textContent, /Índice 100/);
  assert.equal(row.querySelector(".coin-amount").textContent, "8g54s90c");
  assert.equal(row.querySelectorAll("td")[1].textContent, "85490");
  assert.equal(row.querySelectorAll("td")[1].querySelector(".coin-amount"), null);
  assert.equal(row.querySelector(".raw-copper").textContent, "85490");
});

for (const [rule, labels] of [["price_deviation", deviationLabels], ["historical_trend", trendLabels]]) {
  for (const [direction, label] of Object.entries(labels)) {
    test(`signals render ${rule}/${direction} with explicit evidence and accessible headings`, async () => {
      const url = fixtureUrl(), data = signalsResponse(url);
      data[rule].direction = direction;
      if (direction === "insufficient_evidence") {
        data[rule].evidence.status = "insufficient";
        data[rule].evidence.reasons = [{ code: "insufficient_history", message: "Missing history." }];
      }
      await mount(MarketSignals, { analysis: metricsResponse(url), resource: { status: "success", data }, onRetry() {}, onReload() {} });
      const card = document.querySelector(`[data-direction="${direction}"]`);
      assert.ok(card); assert.equal(card.querySelector("h3").textContent, label);
      assert.equal(document.getElementById(card.getAttribute("aria-labelledby")), card.querySelector("h3"));
      const panel = document.querySelector(".signals-panel");
      assert.equal(document.getElementById(panel.getAttribute("aria-labelledby")).textContent, "Señales del histórico");
      assert.match(card.textContent, direction === "insufficient_evidence" ? /Evidencia insuficiente.*insufficient_history/s : /Evidencia suficiente/);
      assert.equal(document.querySelector(".signal-detail").open, false);
      assert.match(panel.textContent, /SIMULATED/); assert.match(panel.textContent, /no confirma una oportunidad/);
      assert.equal(card.querySelector("svg, img"), null, "No buy/sell icon assigned to directions");
    });
  }
}

test("signals preserve zero, undefined percentages and exact tiny Decimal values", async () => {
  const url = fixtureUrl(), data = signalsResponse(url);
  data.price_deviation.deviation_pct.value = "-0.0000000000000000000000000000000000000047";
  data.price_deviation.signed_deviation_copper.value = "-0.5000000000000000000000000000000000000001";
  data.historical_trend.price_change_pct = { ...data.historical_trend.price_change_pct, value: null, status: "undefined", reason: "zero_baseline" };
  data.historical_trend.price_change_copper.value = "0";
  data.price_deviation.observed_price_copper.value = "0";
  assertResponse(data, "MarketSignalsResponse");
  await mount(MarketSignals, { analysis: metricsResponse(url), resource: { status: "success", data } });
  assert.match(document.querySelector(".signals-panel").textContent, /−0,0000000000000000000000000000000000000047/);
  assert.ok([...document.querySelectorAll(".signals-panel .raw-copper")].some(node => node.textContent === "-0.5000000000000000000000000000000000000001"));
  assert.match(document.querySelector(".signals-panel").textContent, /0c/);
  assert.match(document.querySelector("#trend-title").parentElement.textContent, /Porcentaje no definido/);
  assert.equal(document.querySelector("#trend-title").textContent, "Sin tendencia significativa", "Never infer direction from a descriptive metric");
  const exact = document.querySelector(".exact-value details");
  await act(async () => exact.querySelector("summary").click());
  assert.equal(exact.open, true, "Exact value is available with a native accessible disclosure");
  const broken = structuredClone(data); broken.price_deviation.signed_deviation_copper.value = 0.5;
  assert.throws(() => assertResponse(broken, "MarketSignalsResponse"));
  broken.price_deviation.signed_deviation_copper.value = "0.5"; broken.historical_trend.direction = "ascending_buy";
  assert.throws(() => assertResponse(broken, "MarketSignalsResponse"));
});

test("signals explain every structured insufficient-evidence reason and empty data", async () => {
  const url = fixtureUrl(), data = signalsResponse(url, true);
  data.price_deviation.evidence.reasons = Object.keys(reasonLabels).map(code => ({ code, message: `Fixture ${code}` }));
  await mount(MarketSignals, { analysis: metricsResponse(url, true), resource: { status: "success", data } });
  assert.match(document.querySelector(".signals-panel").textContent, /Sin mínimos guardados en esta ventana/);
  for (const [code, message] of Object.entries(reasonLabels)) {
    assert.ok(document.querySelector(".signals-panel").textContent.includes(code));
    assert.ok(document.querySelector(".signals-panel").textContent.includes(message));
  }
  assert.equal(document.querySelectorAll('[data-direction="insufficient_evidence"]').length, 2);
});

test("mounted App: signals load independently, match the metrics query, and retry preserves chart and metrics", async () => {
  let release, fail = true;
  const calls = mockApi(url => {
    if (url.pathname === "/market/signals" && fail) return new Promise(resolve => release = () => resolve(json({}, 503)));
  });
  await mount(); await chooseMarket(); await chooseItem("101");
  await waitFor(() => document.querySelector(".chart-panel") && release, "Metrics shown while signals pending");
  const chart = document.querySelector(".chart-panel"), metric = document.querySelector(".accent-card");
  assert.equal(document.querySelector(".signals-panel").getAttribute("aria-busy"), "true");
  assert.match(document.querySelector(".signals-panel").textContent, /Calculando señales/);
  await act(async () => release());
  await waitFor(() => document.querySelector('.signals-panel [role="alert"]'), "Partial signals error");
  assert.equal(document.querySelector(".chart-panel"), chart); assert.equal(document.querySelector(".accent-card"), metric);
  fail = false; await act(async () => document.querySelector('.signals-panel button').click());
  await waitFor(() => document.querySelector(".signal-card"), "Signals retry recovers");
  assert.equal(document.querySelector(".chart-panel"), chart); assert.equal(document.querySelector(".accent-card"), metric);
  assert.equal(calls.filter(c => c.url.pathname === "/market/metrics").length, 1);
  const signalCalls = calls.filter(c => c.url.pathname === "/market/signals");
  assert.equal(signalCalls.length, 2);
  assert.equal(signalCalls[0].url.search, calls.find(c => c.url.pathname === "/market/metrics").url.search);
  assert.equal(document.querySelector(".advanced-panel details").open, false);
});

test("mounted App: obsolete signals are aborted and cannot overwrite a newer item or market", async () => {
  let release, oldSignal;
  mockApi((url, options) => {
    if (url.pathname === "/market/signals" && url.searchParams.get("market_id") === "1" && url.searchParams.get("item_key") === "101") {
      oldSignal = options.signal;
      return new Promise(resolve => release = () => resolve(json(signalsResponse(url))));
    }
  });
  await mount(); await chooseMarket(); await chooseItem("101"); await waitFor(() => release && document.querySelector(".chart-panel"), "Old signals pending");
  await chooseItem("102"); assert.equal(document.querySelector(".signals-panel"), null);
  await chooseMarket("2"); await waitFor(() => document.querySelector(".signal-card"), "New signals and metrics");
  assert.equal(oldSignal.aborted, true);
  await act(async () => release()); await flush();
  assert.equal(document.querySelector(".result-heading h2").textContent, "Item 102");
  assert.match(document.querySelector(".result-heading").textContent, /PvP/);
  assert.equal(document.querySelector('.signals-panel [role="alert"]'), null);
});

test("mounted App: window changes hide old signals immediately and ignore late errors", async () => {
  let rejectOld, signalOld;
  const calls = mockApi((url, options) => {
    if (url.pathname === "/market/signals" && url.searchParams.get("size") === "30") {
      signalOld = options.signal; return new Promise((resolve, reject) => rejectOld = reject);
    }
  });
  await mount(); await chooseMarket(); await chooseItem("101"); await waitFor(() => rejectOld && document.querySelector(".results"), "Pending initial signals");
  await act(async () => document.querySelector(".advanced-panel summary").click());
  await change(control("Cantidad de buckets", "input"), "14");
  assert.equal(document.querySelector(".signals-panel"), null);
  await waitFor(() => document.querySelector(".signal-card"), "New window signals");
  await act(async () => rejectOld(new TypeError("Late network failure"))); await flush();
  assert.equal(signalOld.aborted, true); assert.equal(document.querySelector('.signals-panel [role="alert"]'), null);
  const s = calls.find(c => c.url.pathname === "/market/signals" && c.url.searchParams.get("size") === "14");
  assert.equal(s.url.search, calls.find(c => c.url.pathname === "/market/metrics" && c.url.searchParams.get("size") === "14").url.search);
});

for (const field of ["context", "window", "points", "coverage", "quality", "provenance"]) {
  test(`signals reject mismatching ${field} instead of combining snapshots`, () => {
    const url = fixtureUrl(), a = metricsResponse(url), s = signalsResponse(url);
    assert.equal(signalsMatchAnalysis(a, s), true);
    if (field === "points") s.points[0].daily_minimum = 99;
    else s[field] = { ...s[field], unexpected_snapshot_change: true };
    assert.equal(signalsMatchAnalysis(a, s), false);
  });
}

test("mounted App: changed evidence offers reload of both snapshots and keeps existing chart until retry", async () => {
  let mismatch = true;
  const calls = mockApi(url => {
    if (url.pathname === "/market/signals" && mismatch) {
      const data = signalsResponse(url); data.points[0].daily_minimum = 99; return json(data);
    }
  });
  await mount(); await chooseMarket(); await chooseItem("101");
  await waitFor(() => document.querySelector('.signals-panel [role="alert"]'), "Mismatch visible");
  assert.match(document.querySelector(".signals-panel").textContent, /evidencia cambió/);
  assert.ok(document.querySelector(".chart-panel")); assert.equal(document.querySelector(".signal-card"), null);
  mismatch = false; await act(async () => document.querySelector(".signals-panel button").click());
  await waitFor(() => document.querySelector(".signal-card"), "Coherent reload");
  assert.equal(calls.filter(c => c.url.pathname === "/market/metrics").length, 2);
  assert.equal(calls.filter(c => c.url.pathname === "/market/signals").length, 2);
});

test("mounted App: source, variant, temporal basis, export and window stay identical across both endpoints", async () => {
  const basis = "2026-10-01T00:00:00Z", variant = "101:4";
  const base = series(1, variant).series[0];
  const accumulated = { ...base, context: { ...base.context, source_id: "source-a" } };
  const exported = [41, 42].map(export_id => ({ ...base, context: { ...base.context, source_id: "source-b", series_mode: "export", value_semantics: "export_projection", temporal_basis: basis, export_id } }));
  const calls = mockApi(url => {
    if (url.pathname === "/partial/items") return json([{ id: 1, item_key: variant, external_item_id: "101", key_kind: "gear_level" }]);
    if (url.pathname === "/market/series") return json({ series: [accumulated, ...exported], limit: 100, offset: 0, has_more: false });
  });
  await mount(); await chooseMarket(); await chooseItem(variant);
  await waitFor(() => document.querySelector(".signal-card"), "Accumulated signals");
  await act(async () => document.querySelector(".advanced-panel summary").click());
  await change(control("Fuente"), JSON.stringify(["source-b", "simulated"]));
  assert.equal(document.querySelector(".signals-panel"), null);
  await flush(240);
  assert.equal(calls.filter(c => c.url.pathname === "/market/signals").length, 1, "Export choice must be explicit");
  await change(control("Exportación"), "41");
  await waitFor(() => document.querySelector(".signal-card"), "Chosen export signals");
  assert.match(document.querySelector(".signal-footnote").textContent, /Exportación #41: un estado sellado/);
  await change(control("Exportación"), "42");
  await waitFor(() => document.querySelector(".signal-footnote")?.textContent.includes("Exportación #42:"), "Switch export");
  await change(control("Tipo"), "calendar_days");
  await waitFor(() => calls.some(c => c.url.pathname === "/market/signals" && c.url.searchParams.get("window_type") === "calendar_days"), "Calendar signals");
  await waitFor(() => document.querySelector(".signal-card"), "Calendar rendered");
  await change(control("Dataset"), "simulated");
  for (const s of calls.filter(c => c.url.pathname === "/market/signals")) {
    assert.equal(s.url.searchParams.get("item_key"), variant);
    assert.ok(calls.some(m => m.url.pathname === "/market/metrics" && m.url.search === s.url.search));
    assert.equal(s.url.searchParams.has("deviation_threshold_pct"), false, "Validated server defaults are used");
  }
  const last = calls.filter(c => c.url.pathname === "/market/signals").at(-1).url.searchParams;
  assert.equal(last.get("source_id"), "source-b"); assert.equal(last.get("temporal_basis"), basis);
  assert.equal(last.get("series_mode"), "export"); assert.equal(last.get("export_id"), "42"); assert.equal(last.get("days"), "30");
  assert.equal(document.querySelector('.signals-panel [role="alert"]'), null);
});

test("mounted App: invalid signals contract is a partial error; retry recovers without refetching metrics", async () => {
  let invalid = true;
  const calls = mockApi(url => {
    if (url.pathname === "/market/signals" && invalid) {
      const data = signalsResponse(url); data.price_deviation.deviation_pct.value = 0; return json(data);
    }
  });
  await mount(); await chooseMarket(); await chooseItem("101");
  await waitFor(() => document.querySelector('.signals-panel [role="alert"]'), "Contract error visible");
  assert.match(document.querySelector(".signals-panel").textContent, /contrato de la API/);
  assert.ok(document.querySelector(".chart-panel")); assert.ok(document.querySelector(".metrics-grid"));
  invalid = false; await act(async () => document.querySelector(".signals-panel button").click());
  await waitFor(() => document.querySelector(".signal-card"), "Contract retry recovers");
  assert.equal(calls.filter(c => c.url.pathname === "/market/metrics").length, 1);
});

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
    const labels = [...svg.querySelectorAll('.chart-grid')].map(line => line.parentElement.querySelector("text").textContent);
    assert.ok(labels.length >= 2);
    assert.equal(new Set(labels).size, labels.length);
  });
}
