import type { MarketMetricsResponse, MarketSignalsResponse, SignalEvidence } from "../../api/generated";
import { ExactValue, MetricCard } from "../../components/MetricCard";
import { StatusPanel } from "../../components/StatusPanel";
import type { Resource } from "./resource";
import { deviationLabels, trendLabels, reasonLabels, signalWarnings, signalsMatchAnalysis } from "./signals";

function Evidence({ evidence: e }: { evidence: SignalEvidence }) {
  return <div className="signal-evidence">
    <p className="muted">{e.status === "sufficient" ? "Evidencia suficiente para esta regla" : "Evidencia insuficiente para esta regla"} · {e.usable_observation_count} mínimos guardados · {e.historical_observation_count} anteriores al último. No es un nivel de confianza.</p>
    {e.reasons.length > 0 && <ul className="signal-reasons">{e.reasons.map(reason => <li key={reason.code}>{reasonLabels[reason.code]} <small>{reason.code}</small></li>)}</ul>}
    <details className="signal-detail"><summary>Revisar calidad de evidencia</summary>
      <div className="signal-values">
        <MetricCard label="Cobertura de la ventana solicitada" metric={e.requested_price_ratio}/>
        <MetricCard label="Cobertura del intervalo de índices" metric={e.index_span_price_ratio}/>
      </div>
      <p className="muted">Distancia del último precio al ancla: {e.latest_price_lag ?? "sin dato"} índices. No mide antigüedad respecto de hoy.</p>
      <p className="muted">Origen: l {e.minimum_l_count} · h_fallback {e.minimum_h_fallback_count} · desconocido {e.minimum_unknown_origin_count}. El fallback h puede omitir mínimos; el acumulado no distingue l de h.</p>
    </details>
  </div>;
}

export function MarketSignals({ analysis, resource, onRetry, onReload }: {
  analysis: MarketMetricsResponse; resource: Resource<MarketSignalsResponse>; onRetry: () => void; onReload: () => void;
}) {
  const data = resource.status === "success" ? resource.data : undefined;
  const mismatch = data && !signalsMatchAnalysis(analysis, data);
  const d = data?.price_deviation, t = data?.historical_trend;
  return <section className="panel signals-panel" aria-labelledby="signals-title" aria-busy={resource.status === "loading"}>
    <div className="panel-heading"><div><p className="eyebrow">Lectura automática</p><h2 id="signals-title">Señales del histórico</h2></div><span className="badge neutral">Mínimos guardados</span></div>
    <p className="muted">Comparaciones sobre esta selección. Una bajada no confirma una oportunidad de compra; estos valores no indican oferta disponible ahora.</p>
    {(resource.status === "loading" || resource.status === "idle") && <StatusPanel title="Calculando señales del item" loading/>}
    {resource.status === "error" && <StatusPanel title="No pudimos cargar las señales" error onRetry={onRetry}>{resource.error.message} El gráfico y las métricas siguen disponibles.</StatusPanel>}
    {mismatch && <StatusPanel title="La evidencia cambió entre consultas" error onRetry={onReload}>Las señales recibidas no corresponden exactamente al análisis visible. Reintentá para actualizar ambas lecturas.</StatusPanel>}
    {data && !mismatch && d && t && <>
      {data.context.dataset === "simulated" && <p className="signal-notice">SIMULATED · Señales calculadas con datos sintéticos; pendientes de validar con archivos auténticos de Forever.</p>}
      {data.coverage.price_observation_count === 0 && <StatusPanel title="Sin mínimos guardados en esta ventana">Las dos reglas carecen de datos para clasificar. Los motivos aparecen debajo.</StatusPanel>}
      <div className="signals-grid">
        <article className="signal-card" aria-labelledby="deviation-title" data-direction={d.direction}>
          <p className="eyebrow">Desviación histórica</p><h3 id="deviation-title">{deviationLabels[d.direction]}</h3>
          <p className="metric-label">Desvío porcentual del último mínimo</p>
          {d.deviation_pct.value !== null ? <ExactValue value={d.deviation_pct.value} unit={d.deviation_pct.unit}/> : <p className="unavailable">Porcentaje no definido</p>}
          <p className="signal-explanation">{d.direction === "insufficient_evidence" ? "No alcanza la evidencia para clasificar el desvío. Los valores disponibles son descriptivos." : d.direction === "no_significant_deviation" ? "El desvío no alcanza el umbral de la regla, o ambos precios son cero." : `El último mínimo guardado está ${d.direction === "below_reference" ? "por debajo" : "por encima"} de la mediana de precios anteriores y alcanza el umbral de la regla.`}</p>
          <Evidence evidence={d.evidence}/>
          <details className="signal-detail"><summary>Ver precios y magnitud del desvío</summary><div className="signal-values">
            <MetricCard label="Último mínimo guardado" metric={d.observed_price_copper} moneyKind="observed"/>
            <MetricCard label="Referencia: mediana sin el último" metric={d.reference_price_copper}/>
            <MetricCard label="Diferencia con signo" metric={d.signed_deviation_copper}/>
            <MetricCard label="Magnitud absoluta" metric={d.absolute_deviation_copper}/>
          </div><p className="muted" lang="en">Explicación original del motor: {d.explanation}</p></details>
        </article>
        <article className="signal-card" aria-labelledby="trend-title" data-direction={t.direction}>
          <p className="eyebrow">Tendencia histórica</p><h3 id="trend-title">{trendLabels[t.direction]}</h3>
          <p className="metric-label">Cambio entre el primer y último mínimo</p>
          {t.price_change_pct.value !== null ? <ExactValue value={t.price_change_pct.value} unit={t.price_change_pct.unit}/> : <p className="unavailable">Porcentaje no definido</p>}
          <p className="signal-explanation">{t.direction === "insufficient_evidence" ? "No alcanza la evidencia para clasificar la tendencia. Los valores disponibles son descriptivos." : t.direction === "no_significant_trend" ? "La pendiente y el cambio entre extremos no cumplen juntos las condiciones de dirección y magnitud. Esto no prueba estabilidad de los precios." : `La pendiente y el cambio entre extremos son ${t.direction === "ascending" ? "positivos" : "negativos"} y cumplen los umbrales de la regla.`}</p>
          <Evidence evidence={t.evidence}/>
          <details className="signal-detail"><summary>Ver pendiente y magnitud del cambio</summary><div className="signal-values">
            <MetricCard label="Pendiente descriptiva" metric={t.slope_copper_per_scan_index} hint="Copper por índice; no es una tasa diaria ni un pronóstico"/>
            <MetricCard label="Cambio con signo" metric={t.price_change_copper}/>
            <MetricCard label="Primer mínimo" metric={t.first_price_copper} moneyKind="observed"/>
            <MetricCard label="Último mínimo" metric={t.last_price_copper} moneyKind="observed"/>
          </div><p className="muted" lang="en">Explicación original del motor: {t.explanation}</p></details>
        </article>
      </div>
      <p className="signal-footnote">{data.context.series_mode === "accumulated" ? signalWarnings.accumulated_extremes : `Exportación #${data.context.export_id}: un estado sellado del addon seleccionado; sus mínimos pueden incluir fallback h. No representa todo el mercado ni oferta actual.`} {data.context.temporal_basis === "unknown" ? "Índices sin fechas verificadas: no se infieren días transcurridos." : "La pendiente sigue expresada por índice, aun con base temporal conocida."}</p>
      <details className="signal-detail"><summary>Reglas, parámetros y límites</summary>
        <p className="muted">“Significativa” significa alcanzar el umbral configurado; no es significancia estadística. La regresión es sensible a extremos y los mínimos guardados pueden estar sujetos a poda.</p>
        <ul className="signal-reasons">{data.warnings.map(w => <li key={w.code}>{signalWarnings[w.code] ?? w.message} <small>{w.code}</small></li>)}</ul>
        <p className="muted">Motor {data.analysis_version} · métricas {data.metrics_analysis_version} · precisión Decimal {data.decimal_precision}. Parámetros efectivos devueltos por la API:</p>
        <dl className="signal-parameters">{Object.entries(data.parameters).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>
      </details>
    </>}
  </section>;
}
