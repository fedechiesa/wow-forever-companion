import type { SeriesDescriptor } from "../../api/generated";
import type { WindowInput } from "./query";

export const initialWindow: WindowInput = { type: "observed_buckets", size: "30", end: "" };
export function defaultIndexRange(descriptor?: SeriesDescriptor): WindowInput {
  const end = descriptor?.market_last_day ?? 0;
  const first = descriptor?.market_first_day ?? end;
  return { type: "index_range", start: String(Math.max(first, end - 365)), end: String(end) };
}
export function WindowControls({ descriptor, value, onChange }: { descriptor?: SeriesDescriptor; value: WindowInput; onChange: (window: WindowInput) => void }) {
  return <fieldset className="window-controls" disabled={!descriptor}><legend>Ventana de análisis</legend>
    <label>Tipo<select value={value.type} onChange={e => {
      const type = e.target.value;
      onChange(type === "index_range" ? defaultIndexRange(descriptor) : type === "calendar_days" ? { type, days: "30", end: "" } : initialWindow);
    }}><option value="observed_buckets">Buckets observados del mercado</option><option value="index_range">Rango de índices</option><option value="calendar_days" disabled={!descriptor || descriptor.context.temporal_basis === "unknown"}>Días calendario · base verificada</option></select></label>
    {value.type === "observed_buckets" && <label>Cantidad de buckets<input type="number" min="1" max="366" required value={value.size} onChange={e => onChange({ ...value, size: e.target.value })}/></label>}
    {value.type === "index_range" && <label>Índice inicial<input type="number" min="0" max="2147483647" required value={value.start} onChange={e => onChange({ ...value, start: e.target.value })}/></label>}
    {value.type === "calendar_days" && <label>Días<select value={value.days} onChange={e => onChange({ ...value, days: e.target.value })}>{[7,14,30].map(n => <option key={n} value={n}>{n} días</option>)}</select></label>}
    <label>Índice final {value.type !== "index_range" && <span className="optional">(opcional)</span>}<input type="number" min="0" max="2147483647" required={value.type === "index_range"} placeholder="Último bucket del mercado" value={value.end} onChange={e => onChange({ ...value, end: e.target.value })}/></label>
    <p className="context-note">Máximo 366 posiciones. {value.type === "observed_buckets" ? "30 buckets no equivalen necesariamente a 30 días. El mercado fija el eje, no el item." : value.type === "calendar_days" ? "Buckets nominales de 86400 segundos. El ancla es el mercado seleccionado, no hoy." : "Rango inclusivo; las posiciones sin evidencia permanecen vacías."}</p>
  </fieldset>;
}
