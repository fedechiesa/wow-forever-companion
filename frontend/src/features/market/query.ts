import type { SeriesContext } from "../../api/generated";

export type WindowInput =
  | { type: "observed_buckets"; size: string; end: string }
  | { type: "index_range"; start: string; end: string }
  | { type: "calendar_days"; days: string; end: string };

function integer(value: string, min: number, max: number, label: string): number {
  if (!/^\d+$/.test(value) || Number(value) < min || Number(value) > max) throw new Error(`${label}: ingresá un entero entre ${min} y ${max}.`);
  return Number(value);
}
export function metricsParams(context: SeriesContext, window: WindowInput): URLSearchParams {
  const params = new URLSearchParams({ market_id: String(context.market_id), item_key: context.item_key,
    source_id: context.source_id, source_type: context.source_type, temporal_basis: context.temporal_basis,
    series_mode: context.series_mode, window_type: window.type });
  if (context.series_mode === "export") {
    if (!context.export_id) throw new Error("Elegí una exportación explícita.");
    params.set("export_id", String(context.export_id));
  }
  if (window.end !== "") params.set("end_day", String(integer(window.end, 0, 2147483647, "Índice final")));
  if (window.type === "observed_buckets") params.set("size", String(integer(window.size, 1, 366, "Buckets")));
  if (window.type === "index_range") {
    const start = integer(window.start, 0, 2147483647, "Índice inicial");
    const end = integer(window.end, 0, 2147483647, "Índice final");
    if (end < start || end - start + 1 > 366) throw new Error("El rango debe contener entre 1 y 366 índices, en orden ascendente.");
    params.set("start_day", String(start));
  }
  if (window.type === "calendar_days") {
    if (context.temporal_basis === "unknown") throw new Error("El calendario requiere una base temporal verificada.");
    const days = integer(window.days, 7, 30, "Días");
    if (![7, 14, 30].includes(days)) throw new Error("Elegí 7, 14 o 30 días.");
    params.set("days", String(days));
  }
  return params;
}
export function contextKey(context: SeriesContext): string {
  return JSON.stringify([context.market_id, context.item_key, context.source_id, context.source_type, context.temporal_basis, context.series_mode, context.export_id ?? null]);
}
export function sourceKey(context: SeriesContext): string { return JSON.stringify([context.source_id, context.source_type]); }
