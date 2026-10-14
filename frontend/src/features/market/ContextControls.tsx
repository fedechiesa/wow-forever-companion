import type { SeriesDescriptor } from "../../api/generated";
import { contextKey, sourceKey } from "./query";

export interface ContextSelection { source: string; mode: string; basis: string; exportId: string }
export const emptySelection: ContextSelection = { source: "", mode: "", basis: "", exportId: "" };
export function selectedDescriptor(series: SeriesDescriptor[], value: ContextSelection): SeriesDescriptor | undefined {
  return series.find(({ context: c }) => sourceKey(c) === value.source && c.series_mode === value.mode && c.temporal_basis === value.basis && (c.series_mode !== "export" || String(c.export_id) === value.exportId));
}
export function ContextControls({ series, value, onChange }: { series: SeriesDescriptor[]; value: ContextSelection; onChange: (value: ContextSelection) => void }) {
  const sources = Array.from(new Map(series.map(({ context: c }) => [sourceKey(c), c])).values());
  const modes = [...new Set(series.filter(({ context: c }) => sourceKey(c) === value.source).map(({ context: c }) => c.series_mode))];
  const bases = [...new Set(series.filter(({ context: c }) => sourceKey(c) === value.source && c.series_mode === value.mode).map(({ context: c }) => c.temporal_basis))];
  const exports = series.filter(({ context: c }) => sourceKey(c) === value.source && c.series_mode === "export" && c.temporal_basis === value.basis);
  return <div className="context-grid">
    <label>Fuente · quién aportó el historial<select value={value.source} onChange={e => onChange({ ...emptySelection, source: e.target.value })}><option value="">Elegir fuente</option>{sources.map(c => <option value={sourceKey(c)} key={sourceKey(c)}>{c.source_id} · {c.source_type}</option>)}</select></label>
    <label>Modo · tipo de evidencia<select disabled={!value.source} value={value.mode} onChange={e => onChange({ ...value, mode: e.target.value, basis: "", exportId: "" })}><option value="">Elegir modo</option>{modes.map(mode => <option key={mode} value={mode}>{mode === "accumulated" ? "accumulated · historial acumulado" : "export · un estado guardado"}</option>)}</select></label>
    <label>Base temporal · reloj del historial<select disabled={!value.mode} value={value.basis} onChange={e => onChange({ ...value, basis: e.target.value, exportId: "" })}><option value="">Elegir base temporal</option>{bases.map(basis => <option key={basis} value={basis}>{basis === "unknown" ? "unknown · sólo índices" : basis}</option>)}</select></label>
    {value.mode === "export" && <label>Exportación<select disabled={!value.basis} value={value.exportId} onChange={e => onChange({ ...value, exportId: e.target.value })}><option value="">Elegir export_id</option>{exports.map(({ context: c }) => <option key={contextKey(c)} value={String(c.export_id)}>Export #{c.export_id}</option>)}</select></label>}
    <p className="context-note">{value.mode === "export" ? "Elegí un export por su identidad. El ID y la recepción no establecen cronología del mercado." : "accumulated conserva extremos entre imports. No representa el último estado del addon."}</p>
  </div>;
}
