import type { MarketMetricsResponse, MarketSignalsResponse } from "../../api/generated";

// Both endpoints read independently. Never combine even a matching selection
// if an import changed the resolved window or evidence between those reads.
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => `${JSON.stringify(key)}:${canonical(child)}`).join(",")}}`;
  return JSON.stringify(value);
}
export function signalsMatchAnalysis(metrics: MarketMetricsResponse, signals: MarketSignalsResponse): boolean {
  return (["context", "window", "points", "coverage", "quality", "provenance"] as const)
    .every(key => canonical(metrics[key]) === canonical(signals[key]));
}

export const deviationLabels = {
  below_reference: "Por debajo de la referencia",
  above_reference: "Por encima de la referencia",
  no_significant_deviation: "Sin desviación significativa",
  insufficient_evidence: "Evidencia insuficiente",
};
export const trendLabels = {
  ascending: "Tendencia ascendente",
  descending: "Tendencia descendente",
  no_significant_trend: "Sin tendencia significativa",
  insufficient_evidence: "Evidencia insuficiente",
};
export const reasonLabels = {
  insufficient_observations: "Hay pocos mínimos guardados para evaluar esta regla.",
  insufficient_history: "Faltan precios anteriores al último mínimo para construir la referencia.",
  insufficient_price_coverage: "Hay precios para una parte demasiado pequeña de la ventana solicitada.",
  insufficient_index_coverage: "Los precios están demasiado dispersos en el intervalo de índices.",
  latest_price_missing_or_stale: "No hay un precio suficientemente cercano al índice de cierre de la ventana.",
  native_l_required: "La regla requiere mínimos de origen l en todas las observaciones.",
  known_temporal_basis_required: "La regla requiere una base temporal verificada.",
  zero_reference: "La referencia es cero: no se puede calcular un porcentaje de desviación.",
  zero_baseline: "El primer precio es cero: no se puede calcular un cambio porcentual.",
  unavailable_trend: "No hay una pendiente calculable para esta muestra o sus índices.",
};
export const signalWarnings: Record<string, string> = {
  statistical_rules_only: "Los umbrales son reglas descriptivas; no expresan confianza probabilística, pronóstico ni una oportunidad de compra confirmada.",
  availability_not_sales: "La disponibilidad no demuestra ventas, demanda, liquidez o rentabilidad y no interviene en estas señales.",
  accumulated_extremes: "El acumulado reúne extremos de imports compatibles; puede cambiar con imports posteriores. No es un estado único del addon ni una reconstrucción histórica inmutable.",
  trend_direction_disagreement: "La pendiente y el cambio entre extremos tienen signos opuestos; no se clasifica una tendencia direccional.",
};
