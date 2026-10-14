import type { PartialItem } from "../../api/contracts";

export function ItemList({ items, selectedKey, onSelect, getLabel = item => `Item ${item.item_key}` }: {
  items: PartialItem[]; selectedKey: string; onSelect: (itemKey: string) => void;
  // Future catalog enrichment can supply a verified label without changing
  // selection identity or fabricating a name in today's partial API contract.
  getLabel?: (item: PartialItem) => string;
}) {
  return <ul className="item-list" aria-label="Items disponibles">{items.map(item => <li key={item.item_key}>
    <button className={`item-button ${selectedKey === item.item_key ? "selected" : ""}`} aria-pressed={selectedKey === item.item_key} onClick={() => onSelect(item.item_key)}>
      <span className="item-glyph" aria-hidden="true">◇</span>
      <span><strong>{getLabel(item)}</strong><small>{item.key_kind} · ID {item.external_item_id}</small></span>
      <span className="item-arrow" aria-hidden="true">›</span>
    </button>
  </li>)}</ul>;
}
