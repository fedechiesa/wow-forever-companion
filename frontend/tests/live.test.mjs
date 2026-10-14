// Read-only integration: no imports, migrations, POSTs or writes to PostgreSQL.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { join } from "node:path";
const require = createRequire(import.meta.url);
const built = name => require(join(process.env.TEST_BUILD_DIR, name));
const { createMarketApi } = built("api/client.js");
const { assertResponse } = built("api/contracts.js");
const { metricsParams } = built("features/market/query.js");
const { resolveContext, planAnalysis } = built("features/market/selection.js");
const { initialWindow } = built("features/market/WindowControls.js");
const { startResourceRequest } = built("features/market/resource.js");
const { MarketResults } = built("features/market/MarketResults.js");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const url = process.env.TEST_API_BASE_URL ?? "http://127.0.0.1:8000";
const api = createMarketApi(url);
const signal = new AbortController().signal;
let context;

test("real API: market → item → safe default → automatic 30-bucket analysis → React output", async () => {
  const markets = await api.getMarkets(signal);
  const market = markets.find(m => m.ruleset === "PvE" && m.dataset === "simulated");
  assert.ok(market, "Existing simulated PvE market required; test never imports data");
  const items = await api.getItems(market.id, signal);
  assert.ok(items.length);
  const series = await api.getSeries(market.id, items[0].item_key, signal);
  const resolved = resolveContext(series, null);
  assert.equal(resolved.status, "ready", "A unique accumulated context is required; never choose arbitrary contexts for the test");
  context = resolved.descriptor.context;
  const plan = planAnalysis(resolved, initialWindow);
  assert.ok(plan.params);
  // Same request scheduler as useResource: query starts without a submit action.
  const data = await new Promise((resolve, reject) => {
    startResourceRequest(signal => api.getMetrics(plan.params, signal), state => {
      if (state.status === "success") resolve(state.data);
      else if (state.status === "error") reject(state.error);
    });
  });
  assert.equal(data.points.length, 30);
  assert.equal(data.window.requested_position_count, 30);
  assert.equal(typeof data.metrics.mean_daily_minimum_copper.value, "string");
  const markup = renderToStaticMarkup(React.createElement(MarketResults, { data }));
  assert.match(markup, /SIMULATED/);
  assert.match(markup, /Mínimos guardados/);
  assert.match(markup, /Cobertura y calidad/);
  if (context.temporal_basis === "unknown") assert.match(markup, /sin fechas verificadas/);
  assert.match(markup, /<svg/);
  const broken = structuredClone(data);
  broken.metrics.mean_daily_minimum_copper.value = 12.4;
  assert.throws(() => assertResponse(broken, "MarketMetricsResponse"));
  console.log(JSON.stringify({ market: market.market_key, item: context.item_key, source: context.source_id, buckets: data.points.length, mean: data.metrics.mean_daily_minimum_copper.value, median: data.metrics.median_daily_minimum_copper.value, coverage: data.coverage.price_observation_count }));
});
test("real API: empty range renders no price data, not zeros", async () => {
  assert.ok(context);
  const data = await api.getMetrics(metricsParams(context, { type: "index_range", start: "0", end: "2" }).toString(), signal);
  assert.equal(data.coverage.price_observation_count, 0);
  assert.ok(data.points.every(p => p.daily_minimum === null));
  assert.equal(data.metrics.mean_daily_minimum_copper.status, "no_data");
  const markup = renderToStaticMarkup(React.createElement(MarketResults, { data }));
  assert.match(markup, /No hay mínimos guardados/);
  assert.match(markup, /Sin datos/);
});
test("real API: changing market with the same available item resolves and queries only that market", async () => {
  assert.ok(context);
  const markets = await api.getMarkets(signal);
  const market = markets.find(m => m.dataset === context.dataset && m.id !== context.market_id);
  assert.ok(market, "A second existing simulated market is required");
  const items = await api.getItems(market.id, signal);
  assert.ok(items.some(item => item.item_key === context.item_key));
  const histories = await api.getSeries(market.id, context.item_key, signal);
  const result = resolveContext(histories, null);
  assert.equal(result.status, "ready");
  const plan = planAnalysis(result, initialWindow);
  const data = await api.getMetrics(plan.params, signal);
  assert.equal(data.context.market_id, market.id);
  assert.equal(data.context.item_key, context.item_key);
  assert.notEqual(data.context.market_id, context.market_id);
  assert.equal(data.window.spec.size, 30);
});

test("real API: invalid and missing contexts return 422 and 404", async () => {
  assert.ok(context);
  const params = metricsParams(context, { type: "observed_buckets", size: "30", end: "" });
  params.set("size", "367");
  await assert.rejects(api.getMetrics(params.toString(), signal), error => error.status === 422);
  params.set("size", "30"); params.set("source_id", "nonexistent-readonly-audit-context");
  await assert.rejects(api.getMetrics(params.toString(), signal), error => error.status === 404);
});
