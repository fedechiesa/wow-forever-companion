import { createMarketApi } from "./client";
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
export const { getMarkets, getItems, getSeries, getMetrics } = createMarketApi(apiBaseUrl);
