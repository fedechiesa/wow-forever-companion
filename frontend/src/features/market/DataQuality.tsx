import type { MarketMetricsResponse } from "../../api/generated";

const warnings: Record<string, string> = {
  stored_minima_only: "Son mínimos guardados; no se garantizan mínimos de todas las subastas o scans.",
  session_bucket_assignment: "El addon fija el índice del bucket nominal durante la sesión.",
  simulated_dataset: "Precios, disponibilidad e identidades sintéticos. No validan datos reales de Forever.",
  unknown_calendar: "Los índices no tienen fechas calendario verificadas.",
  calendar_out_of_range: "Algunos índices exceden el calendario representable; se muestran como índices.",
  small_sample: "Menos de 7 buckets con precio. Alcanzar 7 tampoco garantiza confianza estadística.",
  incomplete_window: "Hay menos buckets de mercado disponibles que los solicitados.",
  missing_prices: "Las posiciones sin precio se excluyen de las métricas de precio.",
  missing_availability: "La disponibilidad ausente es desconocida, no cero.",
  market_axis_gaps: "Hay índices en el intervalo sin evidencia almacenada del mercado/contexto.",
  no_price_data: "No hay buckets con precio en esta selección.",
  price_endpoints_inset: "La variación de precio usa sus extremos observados dentro de la ventana.",
  availability_endpoints_inset: "La disponibilidad utiliza sus propios extremos observados.",
  explicit_zero_price: "Se conservan ceros explícitos. Los porcentajes con base cero no están definidos.",
  unknown_minimum_origin: "El acumulado no permite conocer si el mínimo proviene de l o de h_fallback.",
  h_fallback: "Hay mínimos proyectados desde h por falta de l; pueden faltar mínimos anteriores.",
  undated_evidence_excluded: "Los mínimos sin fecha (m) quedan fuera del gráfico y de las métricas temporales.",
};
export function DataQuality({ data }: { data: MarketMetricsResponse }) {
  const { coverage: c, quality: q, provenance: p } = data;
  return <section className="panel quality-panel" aria-labelledby="quality-title">
    <div className="panel-heading"><div><p className="eyebrow">Límites de la evidencia</p><h2 id="quality-title">Cobertura y calidad</h2></div><span className="badge neutral">{q.warnings.length} avisos</span></div>
    <div className="coverage-grid">
      <article><span>Precio</span><strong>{c.price_observation_count} / {c.selected_position_count}</strong><small>buckets con dato / posiciones seleccionadas</small></article>
      <article><span>Disponibilidad</span><strong>{c.availability_observation_count} / {c.selected_position_count}</strong><small>buckets con dato / posiciones seleccionadas</small></article>
      <article><span>Eje de mercado</span><strong>{c.observed_market_bucket_count} / {c.index_span_position_count}</strong><small>observados / índices en el intervalo</small></article>
    </div>
    <p className="muted">Sin precio: {c.missing_price_position_count} · sin disponibilidad: {c.missing_availability_position_count} · índices sin evidencia de mercado: {c.unobserved_market_position_count}. Cobertura de evidencia guardada, sin score de confianza.</p>
    <ul className="warning-list">{q.warnings.map(w => <li key={w.code}><span aria-hidden="true">◇</span><div>{warnings[w.code] ?? w.message}<small>{w.code}</small></div></li>)}</ul>
    <details className="provenance"><summary>Procedencia y trazabilidad</summary>
      <dl><div><dt>Semántica</dt><dd>{data.context.value_semantics}</dd></div><div><dt>Origen del mínimo</dt><dd>l: {q.minimum_l_count} · h_fallback: {q.minimum_h_fallback_count} · unknown: {q.minimum_unknown_origin_count}</dd></div>
        <div><dt>Campo de disponibilidad</dt><dd>{q.availability_field_presence}</dd></div><div><dt>Evidencias sin fecha excluidas</dt><dd>{p.excluded_undated_count} (item/contexto en todos los índices)</dd></div>
        <div><dt>Filas diarias referenciadas</dt><dd>{p.selected_daily_row_count}</dd></div><div><dt>Import IDs</dt><dd>{p.referenced_import_ids.join(", ") || "Ninguno"}</dd></div>
        <div><dt>Versión de análisis</dt><dd>{data.analysis_version} · precisión Decimal {data.decimal_precision}</dd></div>
        {p.export_state_hash && <div><dt>Hash del estado exportado</dt><dd>{p.export_state_hash}</dd></div>}
        {p.first_received_at && <div><dt>Primera recepción (no observación)</dt><dd>{p.first_received_at}</dd></div>}
      </dl>
    </details>
  </section>;
}
