import { createReadOnlyClient } from "./client";
import { ContractError } from "./contracts";
import type { EvidenceMarketsPage, EvidenceStatesPage, EvidenceFactsPage, EvidenceReceiptsPage, EvidenceMarket } from "./generated";

export type EvidenceDataset = EvidenceMarket["dataset"];
export function createEvidenceApi(baseUrl: string, fetcher: typeof fetch = fetch) {
  const get = createReadOnlyClient(baseUrl, fetcher);
  const id = (value: string) => {
    if (!/^[1-9][0-9]{0,18}$/.test(value) || BigInt(value) > 9223372036854775807n) throw new ContractError("evidence ID");
    return value;
  };
  function query(dataset: EvidenceDataset, offset: number, limit: number) {
    if (!["simulated", "stress_test", "launch"].includes(dataset) || !Number.isInteger(offset) || offset < 0 || offset > 2147483647) throw new ContractError("evidence selection");
    return new URLSearchParams({ dataset, limit: String(limit), offset: String(offset) });
  }
  function context<T extends { dataset: EvidenceDataset; market_id?: string; export_id?: string }>(page: T, dataset: EvidenceDataset, market?: string, state?: string): T {
    if (page.dataset !== dataset || page.market_id !== market || page.export_id !== state) throw new ContractError("evidence context");
    return page;
  }
  return {
    async markets(dataset: EvidenceDataset, offset: number, signal: AbortSignal) {
      const page = context(await get<EvidenceMarketsPage>(`/evidence/v2/markets?${query(dataset, offset, 50)}`, "EvidenceMarketsPage", signal), dataset);
      if (page.items.some(m => m.dataset !== dataset)) throw new ContractError("evidence dataset");
      return page;
    },
    async states(dataset: EvidenceDataset, market: string, offset: number, signal: AbortSignal) {
      return context(await get<EvidenceStatesPage>(`/evidence/v2/markets/${id(market)}/states?${query(dataset, offset, 50)}`, "EvidenceStatesPage", signal), dataset, market);
    },
    async facts(dataset: EvidenceDataset, market: string, state: string, offset: number, signal: AbortSignal) {
      return context(await get<EvidenceFactsPage>(`/evidence/v2/markets/${id(market)}/states/${id(state)}/facts?${query(dataset, offset, 100)}`, "EvidenceFactsPage", signal), dataset, market, state);
    },
    async receipts(dataset: EvidenceDataset, market: string, state: string, offset: number, signal: AbortSignal) {
      return context(await get<EvidenceReceiptsPage>(`/evidence/v2/markets/${id(market)}/states/${id(state)}/receipts?${query(dataset, offset, 20)}`, "EvidenceReceiptsPage", signal), dataset, market, state);
    },
  };
}
