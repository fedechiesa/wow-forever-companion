import type { MetricValue } from "../api/generated";
import { compactExact, copperToCoins, decimalText } from "../features/market/format";

const statuses = { no_data: "Sin datos", insufficient_data: "Muestra insuficiente", undefined: "No definido", ok: "Disponible" };
export function ExactValue({ value, unit }: { value: string; unit: string }) {
  const short = compactExact(value);
  const money = unit === "copper" || unit === "copper/scan_index";
  const suffix = unit === "percent" ? "%" : unit === "copper/scan_index" ? "c / índice" : unit === "copper" ? "c" : unit === "units" ? "unidades" : "";
  return <div className="exact-value">
    <span className="metric-number" title={`${decimalText(value)} ${suffix}`}>{short.text} <small>{suffix}</small></span>
    {money && !short.shortened && <span className="coins">{copperToCoins(value)}{unit === "copper/scan_index" ? " / índice" : ""}</span>}
    {short.shortened && <details><summary>Ver valor exacto · sin redondeo</summary>
      <p>{decimalText(value)} {suffix}</p>{money && <p>{copperToCoins(value)}{unit === "copper/scan_index" ? " / índice" : ""}</p>}
    </details>}
  </div>;
}

export function MetricCard({ label, metric, hint, accent = false }: { label: string; metric: MetricValue; hint?: string; accent?: boolean }) {
  return <article className={`metric-card ${accent ? "accent-card" : ""}`}>
    <p className="metric-label">{label}</p>
    {metric.value !== null && metric.status === "ok" ? <ExactValue value={metric.value} unit={metric.unit} /> : <>
      <strong className="unavailable">{statuses[metric.status]}</strong><p className="muted">Motivo: {metric.reason ?? "sin motivo informado"}</p>
    </>}
    <p className="metric-hint">{hint ?? `${metric.observation_count} buckets con dato`}</p>
    {metric.first_day != null && metric.last_day != null && <p className="metric-endpoints">Índices observados {metric.first_day} → {metric.last_day}</p>}
  </article>;
}
