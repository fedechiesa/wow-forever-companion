import type { MetricValue } from "../api/generated";
import { compactExact, decimalText } from "../features/market/format";
import { MoneyValue } from "./MoneyValue";
import type { MoneyKind } from "../features/market/currency";

const statuses = { no_data: "Sin datos", insufficient_data: "Muestra insuficiente", undefined: "No definido", ok: "Disponible" };
export function ExactValue({ value, unit, moneyKind = "derived" }: { value: string; unit: string; moneyKind?: MoneyKind }) {
  if (unit === "copper") return <MoneyValue value={value} kind={moneyKind}/>;
  // A rate is not a purse of coins: keep every decimal digit, including tiny
  // nonzero slopes, and preserve the original API string in the technical detail.
  if (unit === "copper/scan_index") return <div className="exact-value technical-rate">
    <span className="metric-number">{decimalText(value)} <small>copper / índice</small></span>
    <details><summary>Ver valor exacto · sin redondeo</summary><p>Original: <span className="raw-copper">{value}</span> copper / índice</p></details>
  </div>;
  const short = compactExact(value);
  const suffix = unit === "percent" ? "%" : unit === "units" ? "unidades" : "";
  return <div className="exact-value">
    <span className="metric-number" title={`${decimalText(value)} ${suffix}`}>{short.text} <small>{suffix}</small></span>
    {short.shortened && <details><summary>Ver valor exacto · sin redondeo</summary>
      <p>{decimalText(value)} {suffix}</p>
    </details>}
  </div>;
}

export function MetricCard({ label, metric, hint, accent = false, moneyKind = "derived" }: { label: string; metric: MetricValue; hint?: string; accent?: boolean; moneyKind?: MoneyKind }) {
  return <article className={`metric-card ${accent ? "accent-card" : ""}`}>
    <p className="metric-label">{label}</p>
    {metric.value !== null && metric.status === "ok" ? <ExactValue value={metric.value} unit={metric.unit} moneyKind={moneyKind} /> : <>
      <strong className="unavailable">{statuses[metric.status]}</strong><p className="muted">Motivo: {metric.reason ?? "sin motivo informado"}</p>
    </>}
    <p className="metric-hint">{hint ?? `${metric.observation_count} buckets con dato`}</p>
    {metric.first_day != null && metric.last_day != null && <p className="metric-endpoints">Índices observados {metric.first_day} → {metric.last_day}</p>}
  </article>;
}
