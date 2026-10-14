import type { PartialMarket } from "../../api/contracts";
import type { SeriesContext, SeriesDescriptor } from "../../api/generated";
import { emptySelection, type ContextSelection } from "./ContextControls";
import { initialWindow } from "./WindowControls";
import { contextKey, metricsParams, sourceKey, type WindowInput } from "./query";

export function selectionFromContext(context: SeriesContext): ContextSelection {
  return { source: sourceKey(context), mode: context.series_mode, basis: context.temporal_basis,
    exportId: context.series_mode === "export" ? String(context.export_id) : "" };
}

export interface ContextResolution {
  status: "ready" | "ambiguous" | "export_required" | "empty";
  selection: ContextSelection;
  descriptor?: SeriesDescriptor;
  candidates: SeriesDescriptor[];
  notices: string[];
  retainedPreference: ContextSelection | null;
}

// Only an explicit user preference may break an ambiguity. Discovery order,
// export ID, receipt time, coverage and sample count are never ranking criteria.
export function resolveContext(series: SeriesDescriptor[], preference: ContextSelection | null): ContextResolution {
  const all = [...new Map(series.map(s => [contextKey(s.context), s])).values()];
  let selection = { ...(preference ?? emptySelection) };
  let retainedPreference = preference ? { ...preference } : null;
  const notices: string[] = [];
  if (!all.length) {
    if (preference?.source) notices.push("El historial elegido no está disponible para este item. Se restablecieron las opciones de contexto.");
    return { status: "empty", selection: { ...emptySelection }, candidates: [], notices, retainedPreference: null };
  }
  if (selection.source && !all.some(s => sourceKey(s.context) === selection.source)) {
    selection = { ...emptySelection };
    retainedPreference = null;
    notices.push("La fuente elegida no está disponible para esta selección. Se restableció el contexto; solo se usa un historial predeterminado si es único.");
  }
  let pool = all.filter(s => !selection.source || sourceKey(s.context) === selection.source);
  if (selection.mode && !pool.some(s => s.context.series_mode === selection.mode)) {
    selection = { ...selection, mode: "", basis: "", exportId: "" };
    if (retainedPreference) retainedPreference = { ...retainedPreference, mode: "", basis: "", exportId: "" };
    notices.push("El modo elegido no está disponible. Se restablecieron el modo, la base temporal y la exportación.");
  }
  if (!selection.mode) selection.mode = pool.some(s => s.context.series_mode === "accumulated") ? "accumulated" : "export";
  pool = pool.filter(s => s.context.series_mode === selection.mode);
  const sources = [...new Set(pool.map(s => sourceKey(s.context)))];
  if (!selection.source && sources.length === 1) selection.source = sources[0];
  pool = pool.filter(s => !selection.source || sourceKey(s.context) === selection.source);
  if (selection.basis && !pool.some(s => s.context.temporal_basis === selection.basis)) {
    selection = { ...selection, basis: "", exportId: "" };
    if (retainedPreference) retainedPreference = { ...retainedPreference, basis: "", exportId: "" };
    notices.push("La base temporal elegida no está disponible. Se restablecieron la base y la exportación.");
  }
  const bases = [...new Set(pool.map(s => s.context.temporal_basis))];
  if (!selection.basis && selection.source && bases.length === 1) selection.basis = bases[0];
  pool = pool.filter(s => !selection.basis || s.context.temporal_basis === selection.basis);
  if (selection.mode === "export") {
    if (selection.exportId && !pool.some(s => String(s.context.export_id) === selection.exportId)) {
      selection.exportId = "";
      if (retainedPreference) retainedPreference = { ...retainedPreference, exportId: "" };
      notices.push("La exportación elegida no contiene este contexto. Elegí otra exportación explícitamente.");
    }
    if (!selection.exportId) return { status: "export_required", selection, candidates: pool, notices, retainedPreference };
    pool = pool.filter(s => String(s.context.export_id) === selection.exportId);
  } else selection.exportId = "";
  if (pool.length !== 1) return { status: "ambiguous", selection, candidates: pool, notices, retainedPreference };
  return { status: "ready", selection: selectionFromContext(pool[0].context), descriptor: pool[0], candidates: pool, notices, retainedPreference };
}

export interface AnalysisPlan { window: WindowInput; params: string | null; error: string | null; notices: string[] }
export function planAnalysis(resolution: ContextResolution | undefined, input: WindowInput): AnalysisPlan {
  const descriptor = resolution?.descriptor;
  const notices: string[] = [];
  let window = input;
  if (descriptor && input.type === "calendar_days" && descriptor.context.temporal_basis === "unknown") {
    window = { ...initialWindow };
    notices.push("Este historial no tiene fechas verificadas. La ventana pasó a 30 registros observados del mercado.");
  }
  if (!descriptor) return { window, params: null, error: null, notices };
  try {
    return { window, params: metricsParams(descriptor.context, window).toString(), error: null, notices };
  } catch (error) {
    return { window, params: null, error: (error as Error).message, notices };
  }
}

export function marketLabel(market: PartialMarket): string {
  const rules = market.market_key === market.ruleset ? "" : ` · reglas ${market.ruleset}`;
  return `${market.market_key} · ${market.region}${rules} · ${market.dataset === "simulated" ? "SIMULATED" : "REAL"}`;
}
