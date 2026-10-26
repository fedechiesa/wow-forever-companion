import { ContractError } from "../../api/contracts";
import type { EvidenceFact, EvidenceFactsPage } from "../../api/generated";

// Existing parser/ingestion budget, not a new economic aggregation limit.
const MAX_NATIVE_FACTS = 200_000;
export interface EvidenceItem {
  key: string;
  externalId: string;
  kind: EvidenceFact["key_kind"];
  lastMinimum: number | null;
  history: EvidenceFact[];
  facts: EvidenceFact[];
}

export async function collectStateFacts(
  loadPage: (offset: number, signal: AbortSignal) => Promise<EvidenceFactsPage>,
  expectedNativeFacts: number, signal: AbortSignal,
): Promise<EvidenceFact[]> {
  if (!Number.isSafeInteger(expectedNativeFacts) || expectedNativeFacts < 0 || expectedNativeFacts > MAX_NATIVE_FACTS) throw new ContractError("evidence size");
  const rows: EvidenceFact[] = [];
  const seen = new Set<string>();
  let nativeCount = 0;
  for (let offset = 0; ; offset += 100) {
    signal.throwIfAborted();
    const page = await loadPage(offset, signal);
    signal.throwIfAborted();
    if (page.offset !== offset || page.limit !== 100 || page.items.length > 100 || (page.has_more && page.items.length !== 100)) throw new ContractError("evidence pagination");
    for (const row of page.items) {
      const identity = JSON.stringify([row.item_key, row.scan_day]);
      if (seen.has(identity)) throw new ContractError("repeated native item/bucket");
      seen.add(identity);
      nativeCount += row.native_fact_count;
      if (nativeCount > expectedNativeFacts || rows.length >= MAX_NATIVE_FACTS) throw new ContractError("evidence size");
      rows.push(row);
    }
    if (!page.has_more) break;
  }
  if (nativeCount !== expectedNativeFacts) throw new ContractError("incomplete evidence state");
  return rows;
}

export function groupEvidenceItems(rows: EvidenceFact[]): EvidenceItem[] {
  const items = new Map<string, EvidenceItem>();
  const seen = new Set<string>();
  for (const row of rows) {
    const identity = JSON.stringify([row.item_key, row.scan_day]);
    if (seen.has(identity)) throw new ContractError("repeated native item/bucket");
    seen.add(identity);
    if ((row.scan_day === null && (row.native_l !== null || row.native_h !== null || row.native_a !== null))
      || (row.scan_day !== null && row.native_m !== null)) throw new ContractError("incompatible native time");
    let item = items.get(row.item_key);
    if (!item) {
      item = { key: row.item_key, externalId: row.external_item_id, kind: row.key_kind, lastMinimum: null, history: [], facts: [] };
      items.set(row.item_key, item);
    }
    if (item.externalId !== row.external_item_id || item.kind !== row.key_kind) throw new ContractError("incompatible native item identity");
    item.facts.push(row);
    if (row.scan_day === null) item.lastMinimum = row.native_m;
    else item.history.push(row);
  }
  for (const item of items.values()) item.history.sort((a, b) => a.scan_day! - b.scan_day!);
  return [...items.values()];
}

export function filterEvidenceItems(items: EvidenceItem[], search: string): EvidenceItem[] {
  const terms = search.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => terms.every(term => `${item.externalId} ${item.key}`.toLocaleLowerCase().includes(term)));
}
