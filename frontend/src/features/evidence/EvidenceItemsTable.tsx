import { useMemo, useState } from "react";
import { MoneyValue } from "../../components/MoneyValue";
import type { EvidenceItem } from "./items";
import { filterEvidenceItems } from "./items";

const PAGE_SIZE = 25;
const money = (value: number | null, compact = false) => value === null ? <span className="muted">Sin dato</span> : <MoneyValue value={value} compact={compact}/>;

function ItemDetails({ item }: { item: EvidenceItem }) {
  const [open, setOpen] = useState(false);
  return <details className="evidence-item-details" open={open} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>Ver registros y detalles<span className="sr-only"> · {item.key}</span></summary>
    {open && <><p>Clave completa: <code>{item.key}</code>. Los índices ordenan los registros nativos; no son fechas de scan. El último mínimo guardado no tiene fecha nativa.</p>
    <ul className="evidence-native-records" aria-label={`Registros nativos de ${item.key}`}>
      {item.facts.map(row => <li key={row.scan_day ?? "undated"}>
        <strong>{row.scan_day === null ? "Sin fecha · último mínimo" : `Bucket nativo ${row.scan_day}`}</strong>
        <dl>
          <div><dt>l · mínimo</dt><dd>{money(row.native_l)}</dd></div>
          <div><dt>h · mayor mínimo</dt><dd>{money(row.native_h)}</dd></div>
          <div><dt>a · disponibilidad</dt><dd>{row.native_a === null ? "Sin dato" : `${row.native_a} unidades`}</dd></div>
          <div><dt>m · último mínimo</dt><dd>{money(row.native_m)}</dd></div>
          <div><dt>Origen del mínimo</dt><dd>{row.minimum_origin === "l" ? "l · nativo" : row.minimum_origin === "h_fallback" ? "h · fallback, l ausente" : "No corresponde"}</dd></div>
          <div><dt>Hechos</dt><dd>{row.native_fact_count}</dd></div>
        </dl>
      </li>)}
    </ul></>}
  </details>;
}

function ItemRow({ item }: { item: EvidenceItem }) {
  const single = item.history.length === 1 ? item.history[0] : undefined;
  const multiple = item.history.length > 1;
  const missing = [item.lastMinimum === null ? "último mínimo" : null,
    !item.history.length || item.history.some(row => row.minimum_copper === null) ? "mínimo histórico en algún registro" : null,
    !item.history.length || item.history.some(row => row.native_a === null) ? "disponibilidad en algún registro" : null].filter(Boolean);
  return <tr className="evidence-item-row" role="row">
      <th scope="row" data-label="Item / variante">{item.kind === "pet" ? "Especie" : "Item"} {item.externalId}
        {item.kind !== "item" && <small>{item.kind === "gear_level" ? `Nivel ${item.key.split(":")[2]}` : item.kind === "gear_suffix" ? `Sufijo ${item.key.split(":").slice(2).join(":")}` : "Mascota"}</small>}
      </th>
      <td data-label="Último mínimo guardado">{money(item.lastMinimum, true)}{item.lastMinimum !== null && <small className="evidence-cell-note">Sin fecha nativa</small>}</td>
      <td data-label="Mínimo histórico">{multiple ? <span>{item.history.length} registros separados</span> : money(single?.minimum_copper ?? null, true)}</td>
      <td data-label="Disponibilidad máxima">{multiple ? <span>Ver por registro</span> : single?.native_a == null ? <span className="muted">Sin dato</span> : `${single.native_a} unidades`}</td>
      <td data-label="Información" className="evidence-item-note">
        {multiple && <span>Varios registros; sin combinarlos.</span>}
        {missing.length > 0 && <span>Falta {missing.join(", ")}.</span>}
        <ItemDetails item={item}/>
      </td>
    </tr>;
}

export function EvidenceItemsTable({ items }: { items: EvidenceItem[] }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const filtered = useMemo(() => filterEvidenceItems(items, search), [items, search]);
  const offset = page * PAGE_SIZE;
  const visible = filtered.slice(offset, offset + PAGE_SIZE);
  return <div className="evidence-items">
    <div className="evidence-item-tools">
      <label>Buscar item<input type="search" value={search} placeholder="ID o variante completa…" onChange={e => { setSearch(e.target.value); setPage(0); }}/></label>
      <p role="status">{filtered.length} de {items.length} items con datos</p>
    </div>
    <p className="muted evidence-name-note">Sin catálogo verificado asociado: se muestran IDs.</p>
    {!filtered.length ? <p className="status-panel" role="status">Sin coincidencias. Probá otro ID o variante.</p> : <div className="evidence-table-scroll" role="region" tabIndex={0} aria-label="Items del estado seleccionado">
      <table className="evidence-table evidence-item-table" role="table"><caption className="sr-only">Un item o variante por fila; registros nativos separados en los detalles</caption>
        <thead><tr><th scope="col">Item / variante</th><th scope="col">Último mínimo guardado</th><th scope="col">Mínimo histórico</th><th scope="col">Disponibilidad máxima</th><th scope="col">Información</th></tr></thead>
        <tbody>{visible.map(item => <ItemRow key={item.key} item={item}/>)}</tbody>
      </table>
    </div>}
    {(filtered.length > PAGE_SIZE || page > 0) && <nav className="evidence-pages" aria-label="Páginas de items">
      <button disabled={!page} onClick={() => setPage(n => n-1)}>Anterior · items</button><span>Página {page+1}</span>
      <button disabled={offset+PAGE_SIZE >= filtered.length} onClick={() => setPage(n => n+1)}>Siguiente · items</button>
    </nav>}
  </div>;
}
