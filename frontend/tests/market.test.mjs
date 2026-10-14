import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const built = name => require(join(process.env.TEST_BUILD_DIR, name));
const { copperToCoins, compactExact, trendLabel, bucketLabel } = built("features/market/format.js");
const { chartGeometry, nearestChartDot } = built("features/market/chart.js");
const { metricsParams, sourceKey } = built("features/market/query.js");
const { assertResponse, ContractError } = built("api/contracts.js");
const { createMarketApi, ApiError } = built("api/client.js");
const { selectedDescriptor, ContextControls, emptySelection } = built("features/market/ContextControls.js");
const { WindowControls, defaultIndexRange } = built("features/market/WindowControls.js");
const { StatusPanel } = built("components/StatusPanel.js");
const { MetricCard } = built("components/MetricCard.js");
const { resolveContext, planAnalysis, selectionFromContext, marketLabel } = built("features/market/selection.js");
const { startResourceRequest, visibleResource } = built("features/market/resource.js");
const { AdvancedOptions } = built("features/market/AdvancedOptions.js");
const { ContextChoice } = built("features/market/ContextChoice.js");
const { ItemList } = built("features/market/ItemList.js");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));

// Synthetic fixtures exclusively for tests; never imported by the application.
const context = { market_id: 1, item_key: "123:4", source_id: "test-source", source_type: "simulated", temporal_basis: "unknown", series_mode: "accumulated", export_id: null, market_key: "PvE", ruleset: "PvE", region: "simulation", dataset: "simulated", external_item_id: "123", key_kind: "gear_level", value_semantics: "accumulated_extreme" };
const descriptor = { context, item_first_day: 100, item_last_day: 129, market_first_day: 100, market_last_day: 129, excluded_undated_count: 1, availability_field_presence: "unknown" };
const metric = (value, unit = "copper", status = "ok") => ({ value, unit, status, observation_count: 30, reason: status === "ok" ? null : "zero_baseline" });
const point = (scan_day, daily_minimum) => ({ scan_day, daily_minimum, market_observed: true, bucket_start: null });

test("coins preserve fractional copper and values beyond Number precision", () => {
  assert.equal(copperToCoins("12345.50000000000000000001"), "1 oro · 23 plata · 45,50000000000000000001 cobre");
  assert.equal(copperToCoins("9007199254740993"), "900719925474 oro · 9 plata · 93 cobre");
  assert.equal(copperToCoins("-10000.5"), "−1 oro · 0 plata · 0,5 cobre");
  assert.equal(copperToCoins(0), "0 cobre");
  assert.throws(() => copperToCoins("1e9"));
  assert.throws(() => copperToCoins(Number.MAX_SAFE_INTEGER + 1));
  assert.throws(() => copperToCoins(0.5));
});
test("compact decimals indicate truncation without rounding", () => {
  assert.deepEqual(compactExact("69.99999"), { text: "69,99…", shortened: true });
  assert.deepEqual(compactExact("-0.009"), { text: "−0,00…", shortened: true });
  const markup = render(MetricCard, { label: "Promedio", metric: metric("69.99999") });
  assert.match(markup, /Ver valor exacto/);
  assert.match(markup, /69,99999 cobre/);
});
test("trend sign uses exact decimal, including tiny slopes and explicit zero", () => {
  assert.equal(trendLabel(metric("-0.000000000000000000000000001")), "Tendencia descendente");
  assert.equal(trendLabel(metric("0.000000000000000000000000001")), "Tendencia ascendente");
  assert.equal(trendLabel(metric("0.000")), "Pendiente nula");
  assert.equal(trendLabel(metric(null, "copper", "undefined")), "Sin tendencia calculable");
});
test("unknown indices never become dates; verified dates use UTC", () => {
  assert.equal(bucketLabel({ ...point(2500, 0), bucket_start: "2026-10-01T00:00:00Z" }, "unknown"), "Índice 2500");
  assert.match(bucketLabel({ ...point(1, 0), bucket_start: "2026-10-01T00:00:00Z" }, "2026-09-30T00:00:00Z"), /01.*oct.*2026 UTC · índice 1/);
});
test("chart preserves zeros, breaks nulls and index gaps, uses original index spacing", () => {
  const geometry = chartGeometry([point(1, 0), point(2, 10), point(3, null), point(4, 8), point(8, 12)]);
  assert.equal(geometry.segments.length, 3);
  assert.notEqual(geometry.dots[0].y, null);
  assert.equal(geometry.dots[2].y, null);
  assert.ok(geometry.dots[4].x - geometry.dots[3].x > geometry.dots[1].x - geometry.dots[0].x);
  assert.equal(chartGeometry([point(1, null)]).hasPrices, false);
  assert.ok(Number.isFinite(chartGeometry([point(4, 0)]).dots[0].y));
});
test("query encodes complete item/source and verified time basis", () => {
  const params = metricsParams({ ...context, temporal_basis: "2026-01-01T00:00:00+00:00", source_id: "a + b" }, { type: "calendar_days", days: "14", end: "129" });
  assert.equal(params.get("item_key"), "123:4");
  assert.match(params.toString(), /%2B/);
  assert.equal(params.get("days"), "14");
  assert.equal(params.get("end_day"), "129");
  assert.equal(params.has("size"), false);
});
test("window restrictions mirror backend: 366, ordered inclusive range, verified calendar", () => {
  for (const size of ["0", "367", "1.5", ""]) assert.throws(() => metricsParams(context, { type: "observed_buckets", size, end: "" }));
  assert.equal(metricsParams(context, { type: "observed_buckets", size: "30", end: "" }).get("size"), "30");
  assert.throws(() => metricsParams(context, { type: "calendar_days", days: "30", end: "" }), /verificada/);
  for (const [start, end] of [["4", "3"], ["0", "366"], ["0", ""], ["0", "2147483648"]]) assert.throws(() => metricsParams(context, { type: "index_range", start, end }));
  assert.equal(metricsParams(context, { type: "index_range", start: "0", end: "365" }).get("end_day"), "365");
});
test("export selection is explicit and independent of receipt time", () => {
  const exported = { ...descriptor, context: { ...context, series_mode: "export", export_id: 8, value_semantics: "export_projection" }, first_received_at: "2026-10-14T00:00:00Z" };
  const selection = { source: sourceKey(context), mode: "export", basis: "unknown", exportId: "" };
  assert.equal(selectedDescriptor([exported], selection), undefined);
  assert.equal(selectedDescriptor([exported], { ...selection, exportId: "8" }), exported);
  assert.equal(metricsParams(exported.context, { type: "observed_buckets", size: "30", end: "" }).get("export_id"), "8");
  assert.throws(() => metricsParams({ ...exported.context, export_id: null }, { type: "observed_buckets", size: "30", end: "" }));
  assert.match(render(ContextControls, { series: [exported], value: selection, onChange() {} }), /Elegir export_id/);
  assert.equal(selectedDescriptor([descriptor], emptySelection), undefined);
});
test("calendar option disabled for unknown basis and unavailable metrics keep reason", () => {
  assert.match(render(WindowControls, { descriptor, value: { type: "observed_buckets", size: "30", end: "" }, onChange() {} }), /value="calendar_days" disabled/);
  assert.match(render(MetricCard, { label: "Variación", metric: metric(null, "percent", "undefined") }), /No definido/);
  assert.match(render(MetricCard, { label: "Variación", metric: metric(null, "percent", "undefined") }), /zero_baseline/);
});
test("runtime contracts reject numeric Decimals, unsafe IDs and missing fields", () => {
  assert.throws(() => assertResponse([{ id: Number.MAX_SAFE_INTEGER + 1, market_key: "PvE", ruleset: "PvE", region: "s", dataset: "simulated" }], "markets"), ContractError);
  assert.throws(() => assertResponse([{ id: 1, item_key: "123" }], "items"), ContractError);
  assertResponse({ series: [descriptor], limit: 100, offset: 0, has_more: false }, "SeriesDiscoveryResponse");
});
test("all catalog pages are fetched, not only the first 100", async () => {
  const calls = [];
  const api = createMarketApi("http://test.invalid/", async url => {
    calls.push(url);
    const offset = Number(new URL(url).searchParams.get("offset"));
    return new Response(JSON.stringify(Array.from({ length: offset === 0 ? 100 : 1 }, (_, i) => ({ id: offset + i + 1, item_key: String(offset + i + 1), external_item_id: String(offset + i + 1), key_kind: "item" }))));
  });
  assert.equal((await api.getItems(1, new AbortController().signal)).length, 101);
  assert.equal(calls.length, 2);
  assert.match(calls[1], /offset=100/);
});
test("discovery follows has_more without choosing a context", async () => {
  let count = 0;
  const api = createMarketApi("http://test.invalid", async () => new Response(JSON.stringify({ series: [descriptor], limit: 100, offset: count * 100, has_more: ++count === 1 })));
  assert.equal((await api.getSeries(1, "123:4", new AbortController().signal)).length, 2);
  assert.equal(count, 2);
});
test("HTTP invalid context, database and network errors are distinct", async () => {
  for (const status of [404,409,422,503,500]) {
    const api = createMarketApi("http://test.invalid", async () => new Response("{}", { status }));
    await assert.rejects(api.getMarkets(new AbortController().signal), error => error instanceof ApiError && error.status === status);
  }
  const api = createMarketApi("http://test.invalid", async () => { throw new TypeError("offline"); });
  await assert.rejects(api.getMarkets(new AbortController().signal), /conectar con FastAPI/);
});
test("request cancellation propagates to the fetcher", async () => {
  const controller = new AbortController();
  let forwarded;
  const api = createMarketApi("http://test.invalid", async (_url, options) => {
    forwarded = options.signal;
    controller.abort();
    throw new DOMException("Aborted", "AbortError");
  });
  await assert.rejects(api.getMarkets(controller.signal), /Aborted/);
  assert.equal(forwarded.aborted, true);
});
test("loading, connection errors and empty messages have accessible roles", () => {
  assert.match(render(StatusPanel, { title: "Cargando", loading: true }), /role="status"/);
  assert.match(render(StatusPanel, { title: "Error de conexión", error: true, onRetry() {} }), /role="alert"/);
  assert.match(render(StatusPanel, { title: "Sin items" }), /Sin items/);
});

const history = overrides => ({ ...descriptor, context: { ...context, ...overrides } });
const observed30 = { type: "observed_buckets", size: "30", end: "" };
const nextTick = () => new Promise(resolve => setImmediate(resolve));

test("safe default prioritizes the only accumulated context, independent of export receipt/order", () => {
  const exported = history({ series_mode: "export", export_id: 999, value_semantics: "export_projection" });
  for (const series of [[exported, descriptor], [descriptor, exported]]) {
    const result = resolveContext(series, null);
    assert.equal(result.status, "ready");
    assert.equal(result.descriptor, descriptor);
    assert.equal(result.selection.exportId, "");
    assert.equal(result.retainedPreference, null);
    const plan = planAnalysis(result, observed30);
    assert.equal(new URLSearchParams(plan.params).get("size"), "30");
    assert.equal(new URLSearchParams(plan.params).has("export_id"), false);
  }
});
test("multiple accumulated sources or bases require an explicit choice", () => {
  for (const other of [history({ source_id: "another-source" }), history({ temporal_basis: "2026-01-01T00:00:00+00:00" })]) {
    const result = resolveContext([descriptor, other], null);
    assert.equal(result.status, "ambiguous");
    assert.equal(result.descriptor, undefined);
    assert.equal(planAnalysis(result, observed30).params, null);
    assert.match(render(ContextChoice, { resolution: result, onChange() {} }), /Hay más de un historial/);
  }
});
test("export-only discovery never selects even a single export automatically", () => {
  const exported = history({ series_mode: "export", export_id: 8, value_semantics: "export_projection" });
  const result = resolveContext([exported], null);
  assert.equal(result.status, "export_required");
  assert.equal(result.selection.exportId, "");
  assert.equal(planAnalysis(result, observed30).params, null);
  const chosen = resolveContext([exported], selectionFromContext(exported.context));
  assert.equal(chosen.status, "ready");
  assert.equal(new URLSearchParams(planAnalysis(chosen, observed30).params).get("export_id"), "8");
});
test("compatible explicit source/mode/basis and windows survive item changes", () => {
  const nextItem = history({ item_key: "456:4", external_item_id: "456" });
  const other = history({ item_key: "456:4", external_item_id: "456", source_id: "another-source" });
  const result = resolveContext([other, nextItem], selectionFromContext(context));
  assert.equal(result.status, "ready");
  assert.equal(result.descriptor, nextItem);
  const range = { type: "index_range", start: "103", end: "109" };
  const plan = planAnalysis(result, range);
  assert.equal(plan.window, range);
  assert.equal(new URLSearchParams(plan.params).get("item_key"), "456:4");
  assert.equal(new URLSearchParams(plan.params).get("start_day"), "103");
  assert.deepEqual(result.notices, []);
});
test("an automatic default is not promoted to an explicit preference for later ambiguous items", () => {
  const first = resolveContext([descriptor], null);
  const next = resolveContext([history({ item_key: "456:4" }), history({ item_key: "456:4", source_id: "b" })], first.retainedPreference);
  assert.equal(next.status, "ambiguous");
});
test("invalid source on a new market resets safely and reports the change", () => {
  const next = history({ market_id: 2, market_key: "PvP", ruleset: "PvP", source_id: "new-source" });
  const result = resolveContext([next], selectionFromContext(context));
  assert.equal(result.status, "ready");
  assert.match(result.notices.join(" "), /fuente elegida no está disponible/);
  assert.equal(result.retainedPreference, null);
  assert.equal(new URLSearchParams(planAnalysis(result, observed30).params).get("market_id"), "2");
  const ambiguous = resolveContext([next, history({ ...next.context, source_id: "another" })], selectionFromContext(context));
  assert.equal(ambiguous.status, "ambiguous");
});
test("invalid calendar resets to observed buckets with a visible reason; valid calendar is retained", () => {
  const calendar = { type: "calendar_days", days: "14", end: "129" };
  const fallback = planAnalysis(resolveContext([descriptor], null), calendar);
  assert.deepEqual(fallback.window, observed30);
  assert.match(fallback.notices.join(" "), /no tiene fechas verificadas/);
  const known = history({ temporal_basis: "2026-01-01T00:00:00+00:00" });
  const retained = planAnalysis(resolveContext([known], null), calendar);
  assert.equal(retained.window, calendar);
  assert.equal(new URLSearchParams(retained.params).get("days"), "14");
});
test("invalid export on another item is cleared, never replaced by a newer export", () => {
  const old = history({ series_mode: "export", export_id: 8, value_semantics: "export_projection" });
  const available = history({ item_key: "456:4", series_mode: "export", export_id: 999, value_semantics: "export_projection" });
  const result = resolveContext([available], selectionFromContext(old.context));
  assert.equal(result.status, "export_required");
  assert.equal(result.selection.exportId, "");
  assert.equal(result.retainedPreference.exportId, "");
  assert.match(result.notices.join(" "), /no contiene este contexto/);
  assert.equal(planAnalysis(result, observed30).params, null);
});
test("advanced options are initially collapsed and keep every technical control", () => {
  const markup = render(AdvancedOptions, { datasets: ["simulated", "real"], dataset: "", onDatasetChange() {}, series: [descriptor], selection: selectionFromContext(context), onContextChange() {}, descriptor, window: observed30, onWindowChange() {} });
  assert.match(markup, /<details><summary>Opciones avanzadas/);
  assert.doesNotMatch(markup, /<details[^>]*\bopen/);
  for (const label of ["Dataset", "Fuente", "Modo", "Base temporal", "Tipo", "Cantidad de buckets", "Índice final"]) assert.ok(markup.includes(label));
  assert.doesNotMatch(markup, /Consultar histórico/);
});
test("market labels distinguish actual key, region, ruleset and SIMULATED", () => {
  const market = { id: 1, market_key: "Everlook Alliance", ruleset: "PvE", region: "simulation", dataset: "simulated" };
  assert.equal(marketLabel(market), "Everlook Alliance · simulation · reglas PvE · SIMULATED");
  const markup = render(ItemList, { items: [{ id: 1, item_key: "123:4", external_item_id: "123", key_kind: "gear_level" }], selectedKey: "123:4", onSelect() {} });
  assert.match(markup, /Item 123:4/);
  assert.match(markup, /aria-pressed="true"/);
});
test("automatic analysis starts from a valid plan without a submit event", async () => {
  const plan = planAnalysis(resolveContext([descriptor], null), observed30);
  let calls = 0;
  const state = await new Promise(resolve => {
    startResourceRequest(async () => { calls++; return { query: plan.params }; }, resolve);
  });
  assert.equal(calls, 1);
  assert.equal(state.status, "success");
  assert.equal(new URLSearchParams(state.data.query).get("size"), "30");
  assert.equal(planAnalysis(resolveContext([], null), observed30).params, null);
  assert.equal(planAnalysis(resolveContext([descriptor], null), { ...observed30, size: "367" }).params, null);
});
test("rapid market/item changes cancel old requests and never publish stale successes or errors", async () => {
  for (const rejectOld of [false, true]) {
    let settleOld;
    let oldSignal;
    const published = [];
    const cancel = startResourceRequest(signal => {
      oldSignal = signal;
      return new Promise((resolve, reject) => { settleOld = rejectOld ? reject : resolve; });
    }, state => published.push(state));
    await nextTick();
    cancel();
    startResourceRequest(async () => "new-item-new-market", state => published.push(state));
    await nextTick();
    settleOld(rejectOld ? new Error("old error") : "old item");
    await nextTick();
    assert.equal(oldSignal.aborted, true);
    assert.deepEqual(published, [{ status: "success", data: "new-item-new-market" }]);
  }
});
test("request scheduling suppresses StrictMode replay and debounced intermediate edits", async () => {
  let calls = 0;
  const load = async () => ++calls;
  const results = [];
  startResourceRequest(load, state => results.push(state))();
  startResourceRequest(load, state => results.push(state));
  await nextTick();
  assert.equal(calls, 1);
  const cancelled = startResourceRequest(load, state => results.push(state), 15);
  cancelled();
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.equal(calls, 1);
  assert.equal(results.length, 1);
});
test("key gating hides prior metrics immediately, and failures become explicit errors", async () => {
  const previous = { key: "old-item", result: { status: "success", data: "old metrics" } };
  assert.deepEqual(visibleResource(previous, "new-item"), { status: "loading" });
  assert.deepEqual(visibleResource(previous, null), { status: "idle" });
  assert.equal(visibleResource(previous, "old-item").data, "old metrics");
  const error = await new Promise(resolve => startResourceRequest(async () => { throw new Error("connection failed"); }, resolve));
  assert.equal(error.status, "error");
  assert.equal(error.error.message, "connection failed");
});

for (const count of [1, 30, 366, 501]) {
  test(`default inclusive range for ${count} indices ends at the last index and fits 366 positions`, () => {
    const first = 2500, end = first + count - 1;
    const sample = { ...descriptor, market_first_day: first, market_last_day: end };
    const range = defaultIndexRange(sample);
    assert.deepEqual(range, { type: "index_range", start: String(Math.max(first, end - 365)), end: String(end) });
    assert.equal(Number(range.end) - Number(range.start) + 1, Math.min(count, 366));
    assert.doesNotThrow(() => metricsParams(context, range));
    let selected;
    const controls = WindowControls({ descriptor: sample, value: observed30, onChange: v => selected = v });
    const label = controls.props.children.find(child => child?.type === "label");
    label.props.children[1].props.onChange({ target: { value: "index_range" } });
    assert.deepEqual(selected, range);
  });
}
test("non-consecutive market indices use a bounded index span; explicit historical ranges are never truncated", () => {
  // Only indices 10 and 1000 may have observations; a range counts all positions.
  assert.deepEqual(defaultIndexRange({ ...descriptor, market_first_day: 10, market_last_day: 1000 }), { type: "index_range", start: "635", end: "1000" });
  const explicit = { type: "index_range", start: "0", end: "500" };
  const invalid = planAnalysis(resolveContext([descriptor], null), explicit);
  assert.equal(invalid.window, explicit);
  assert.equal(invalid.params, null);
  assert.match(invalid.error, /366/);
  assert.equal(metricsParams(context, { type: "index_range", start: "10", end: "39" }).get("start_day"), "10");
});
for (const count of [30, 366]) {
  test(`nearest-point selection ignores drawing order for ${count} repeated/nearby prices`, () => {
    const points = Array.from({ length: count }, (_, i) => point(i, 100 + i % 2));
    const { dots } = chartGeometry(points);
    for (const dot of dots) {
      assert.equal(nearestChartDot(dots, dot.x, dot.y).point.scan_day, dot.point.scan_day);
      assert.equal(nearestChartDot([...dots].reverse(), dot.x + .01, dot.y).point.scan_day, dot.point.scan_day);
    }
    const flat = chartGeometry(points.map(p => ({ ...p, daily_minimum: 100 }))).dots;
    assert.equal(nearestChartDot(flat, flat[0].x, flat[0].y).point.scan_day, 0);
    assert.equal(nearestChartDot(flat, flat[5].x, flat[5].y).point.scan_day, 5);
  });
}
test("nearest-point ties and gaps are deterministic, with no null-to-zero conversion", () => {
  const candidates = [{ point: point(8, 0), x: 10, y: 10 }, { point: point(3, 0), x: 12, y: 10 }];
  assert.equal(nearestChartDot(candidates, 11, 10).point.scan_day, 3);
  assert.equal(nearestChartDot([...candidates].reverse(), 11, 10).point.scan_day, 3);
  const gap = chartGeometry([point(0, 0), point(1, null), point(2, 0)]);
  assert.notEqual(nearestChartDot(gap.dots, gap.dots[1].x, 230).point.daily_minimum, null);
  assert.equal(nearestChartDot(chartGeometry([point(0, null)]).dots, 0, 0), undefined);
  const close = chartGeometry([point(0, 0), point(1, 0), point(2147483647, 0)]).dots;
  assert.equal(nearestChartDot(close, close[0].x, close[0].y).point.scan_day, 0);
});
for (const prices of [[0, 0], [100, 100], [0, 1], [100, 101], [2147483647, 2147483647]]) {
  test(`axis labels remain distinct and integral for prices ${prices.join("/")}`, () => {
    const points = prices.map((price, i) => point(i, price));
    const { yTicks, dots } = chartGeometry(points);
    assert.ok(yTicks.length >= 2);
    assert.equal(new Set(yTicks.map(t => t.value)).size, yTicks.length);
    assert.ok(yTicks.every(t => Number.isSafeInteger(t.value) && Number.isFinite(t.y) && t.y >= 15 && t.y <= 230));
    assert.deepEqual(dots.map(dot => dot.point.daily_minimum), prices);
    if (prices[0] === prices[1]) assert.equal(dots[0].y, dots[1].y);
  });
}
