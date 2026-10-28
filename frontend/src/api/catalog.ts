import { createReadOnlyClient } from "./client";
import { ContractError } from "./contracts";
import type { CatalogItem, CatalogPage } from "./generated";

export function usableMetadata(item: CatalogItem, now = Date.now() / 1000): boolean {
  const host = item.provider === "ahledger" ? "ahledger.com" : item.provider === "foreverdb" ? "foreverdb.net" : "";
  const link = (value: string) => {
    try { const url = new URL(value); return url.protocol === "https:" && [host, `api.${host}`].includes(url.hostname) && !url.username && !url.password && !url.port; }
    catch { return false; }
  };
  return !!host && item.product === "forever" && item.entity_kind === "item"
    && Number.isSafeInteger(item.item_id) && item.item_id > 0
    && !!item.name.trim() && !/[\u0000-\u001f]/.test(item.name)
    && item.fetched_at <= now && now < item.expires_at && item.expires_at - item.fetched_at <= 300
    && link(item.source_url) && link(item.attribution_url);
}

export function authorizedIcon(item: CatalogItem): string | undefined {
  return item.icon_permission === "authorized" && item.icon_ref && /^\/assets\/catalog\/[a-zA-Z0-9_-]+\.(png|webp|jpg)$/.test(item.icon_ref) ? item.icon_ref : undefined;
}

export function createCatalogApi(baseUrl: string, fetcher: typeof fetch = fetch) {
  const get = createReadOnlyClient(baseUrl, fetcher);
  return async (signal: AbortSignal): Promise<CatalogItem[]> => {
    const page = await get<CatalogPage>("/catalog/items", "CatalogPage", signal);
    const seen = new Set<number>();
    for (const item of page.items) {
      if (!usableMetadata(item) || seen.has(item.item_id)) throw new ContractError("catalog metadata");
      seen.add(item.item_id);
    }
    return page.items;
  };
}
