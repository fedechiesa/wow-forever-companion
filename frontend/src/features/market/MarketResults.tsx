import type { ReactNode } from "react";
import type { MarketMetricsResponse } from "../../api/generated";
import { MetricCard } from "../../components/MetricCard";
import { MoneyValue } from "../../components/MoneyValue";
import { PriceChart } from "./PriceChart";
import { DataQuality } from "./DataQuality";
import { bucketLabel, trendLabel } from "./format";

export function MarketResults({ data, signals }: { data: MarketMetricsResponse; signals?: ReactNode }) {
  const m = data.metrics;
  return <div className="results">
    <div className="result-heading"><div><p className="eyebrow">Análisis del item</p><h2>Item {data.context.item_key}</h2><p className="muted">{data.context.market_key} · {data.context.region} · {data.context.source_id} · {data.context.series_mode}{data.context.export_id != null && ` · export #${data.context.export_id}`}</p></div>{data.context.dataset === "simulated" && <span className="badge simulated">SIMULATED</span>}</div>
    <div className="metrics-grid">
      <MetricCard label="Promedio de mínimos" metric={m.mean_daily_minimum_copper} accent/>
      <MetricCard label="Mediana de mínimos" metric={m.median_daily_minimum_copper}/>
      <MetricCard label="Variación de precio" metric={m.price_change_pct} hint="Entre el primer y último mínimo observado"/>
      <MetricCard label="Pendiente de mínimos" metric={m.trend_copper_per_scan_index} hint={trendLabel(m.trend_copper_per_scan_index)}/>
    </div>
    <PriceChart key={JSON.stringify(data.window)} data={data}/>
    {signals}
    <div className="metrics-grid secondary-metrics">
      <MetricCard label="Mínimo de la ventana" metric={m.minimum_copper} moneyKind="observed"/>
      <MetricCard label="Último mínimo observado" metric={m.last_minimum_copper} moneyKind="observed" hint="Evidencia guardada; no precio actual"/>
      <MetricCard label="Variación absoluta" metric={m.price_change_copper}/>
      <MetricCard label="Última disponibilidad máxima" metric={m.last_max_available} hint="Unidades disponibles en su último bucket observado; no ventas"/>
    </div>
    <section className="panel"><details className="additional-metrics"><summary>Dispersión y cambios de disponibilidad</summary>
      <p className="muted">La dispersión describe diferencias entre mínimos guardados, no volatilidad de retornos. La disponibilidad no indica ventas.</p>
      <div className="metrics-grid">
        <MetricCard label="Desviación muestral de mínimos" metric={m.minimum_stddev_copper}/>
        <MetricCard label="Dispersión relativa (CV)" metric={m.minimum_cv_pct}/>
        <MetricCard label="Cambio de disponibilidad" metric={m.availability_change_units}/>
        <MetricCard label="Cambio porcentual de disponibilidad" metric={m.availability_change_pct}/>
      </div>
    </details></section>
    <DataQuality data={data}/>
    <section className="panel"><details className="evidence-table"><summary>Inspeccionar los {data.points.length} buckets y sus referencias</summary>
      <div className="table-scroll"><table><caption>Null indica ausencia de dato. Los ceros explícitos se conservan.</caption><thead><tr><th>Bucket</th><th>Mínimo guardado</th><th>Disponibilidad máxima</th><th>Origen</th><th>Referencia precio / disponibilidad</th></tr></thead>
        <tbody>{data.points.map(p => <tr key={p.scan_day}><th scope="row">{bucketLabel(p, data.context.temporal_basis)}{!p.market_observed && <small>Sin evidencia de mercado</small>}</th><td>{p.daily_minimum == null ? "Sin dato" : <MoneyValue value={p.daily_minimum}/>}</td><td>{p.daily_max_available ?? "Sin dato"}</td><td>{p.minimum_origin ?? "—"}</td><td>{p.minimum_evidence ? `${p.minimum_evidence.table} #${p.minimum_evidence.row_id}` : "—"} / {p.availability_evidence ? `#${p.availability_evidence.row_id}` : "—"}</td></tr>)}</tbody>
      </table></div>
    </details></section>
  </div>;
}
