import { assertResponse, ContractError, type PartialItem, type PartialMarket } from "./contracts";
import type { MarketMetricsResponse, SeriesDescriptor, SeriesDiscoveryResponse } from "./generated";
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}
export function createMarketApi(baseUrl: string, fetcher: typeof fetch = fetch) {
  const apiBaseUrl = baseUrl.replace(/\/+$/, "");
  async function get<T>(path: string, schema: Parameters<typeof assertResponse>[1], signal: AbortSignal): Promise<T> {
    const timeout = new AbortController();
    const abort = () => timeout.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const timer = setTimeout(abort, 15000);
    try {
      const response = await fetcher(`${apiBaseUrl}${path}`, { signal: timeout.signal });
      if (!response.ok) {
        const messages: Record<number, string> = {
          404: "El contexto seleccionado ya no está disponible.",
          409: "La evidencia del contexto es incoherente. No se puede analizar.",
          422: "Contexto o ventana inválidos. Revisá los filtros y la base temporal.",
          503: "FastAPI no puede acceder a PostgreSQL.",
        };
        throw new ApiError(messages[response.status] ?? `La API devolvió un error HTTP ${response.status}.`, response.status);
      }
      const data: unknown = await response.json();
      assertResponse(data, schema);
      return data as T;
    } catch (error) {
      if (signal.aborted) throw error;
      if (error instanceof SyntaxError) throw new ContractError("JSON");
      if (error instanceof TypeError || (error instanceof DOMException && error.name === "AbortError")) {
        throw new ApiError("No se pudo conectar con FastAPI. Comprobá la URL, CORS y que el backend esté iniciado.", 0);
      }
      throw error;
    } finally { clearTimeout(timer); signal.removeEventListener("abort", abort); }
  }
  function getMarkets(signal: AbortSignal): Promise<PartialMarket[]> { return get("/partial/markets", "markets", signal); }
  async function getItems(marketId: number, signal: AbortSignal): Promise<PartialItem[]> {
    const items: PartialItem[] = [];
    for (let offset = 0; ; offset += 100) {
      const page = await get<PartialItem[]>(`/partial/items?market_id=${marketId}&limit=100&offset=${offset}`, "items", signal);
      items.push(...page);
      if (page.length < 100) return items;
    }
  }
  async function getSeries(marketId: number, itemKey: string, signal: AbortSignal): Promise<SeriesDescriptor[]> {
    const series: SeriesDescriptor[] = [];
    for (let offset = 0; ; offset += 100) {
      const params = new URLSearchParams({ market_id: String(marketId), item_key: itemKey, limit: "100", offset: String(offset) });
      const page = await get<SeriesDiscoveryResponse>(`/market/series?${params}`, "SeriesDiscoveryResponse", signal);
      series.push(...page.series);
      if (!page.has_more) return series;
      if (!page.series.length) throw new Error("La paginación de contextos no avanzó.");
    }
  }
  function getMetrics(params: string, signal: AbortSignal): Promise<MarketMetricsResponse> { return get(`/market/metrics?${params}`, "MarketMetricsResponse", signal); }
  return { getMarkets, getItems, getSeries, getMetrics };
}
