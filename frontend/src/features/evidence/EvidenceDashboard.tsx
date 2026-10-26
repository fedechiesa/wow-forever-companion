import { useState } from "react";
import { apiBaseUrl } from "../../api/backend";
import { createEvidenceApi, type EvidenceDataset } from "../../api/evidence";
import { StatusPanel } from "../../components/StatusPanel";
import { useResource, type Resource } from "../market/useResource";
import { collectStateFacts, groupEvidenceItems } from "./items";
import { EvidenceItemsTable } from "./EvidenceItemsTable";

const api = createEvidenceApi(apiBaseUrl);
const date = (value: string | null) => value ? new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) + " UTC" : "Sin adquisición registrada";

function Progress({ resource, onRetry }: { resource: Resource<unknown>; onRetry: () => void }) {
  return resource.status === "loading" ? <StatusPanel title="Cargando evidencia" loading/> : resource.status === "error" ? <StatusPanel title="No pudimos cargar la evidencia" error onRetry={onRetry}>{resource.error.message}</StatusPanel> : null;
}
function Pages({ offset, limit, more, label, onChange }: { offset: number; limit: number; more: boolean; label: string; onChange: (offset: number) => void }) {
  if (!offset && !more) return null;
  return <nav className="evidence-pages" aria-label={`Páginas de ${label}`}>
    <button disabled={!offset} onClick={() => onChange(Math.max(0, offset-limit))}>Anterior<span className="sr-only"> · {label}</span></button>
    <span>Página {Math.floor(offset/limit)+1}</span>
    <button disabled={!more} onClick={() => onChange(offset+limit)}>Siguiente<span className="sr-only"> · {label}</span></button>
  </nav>;
}

export function EvidenceDashboard() {
  const [dataset, setDataset] = useState<EvidenceDataset | "">("");
  const [marketId, setMarketId] = useState("");
  const [stateId, setStateId] = useState("");
  const [marketsOffset, setMarketsOffset] = useState(0);
  const [statesOffset, setStatesOffset] = useState(0);
  const [receiptsOffset, setReceiptsOffset] = useState(0);
  const [showReceipts, setShowReceipts] = useState(false);
  const [retry, setRetry] = useState(0);
  const reload = () => setRetry(n => n+1);
  const markets = useResource(dataset ? `evidence:markets:${dataset}:${marketsOffset}:${retry}` : null, signal => api.markets(dataset as EvidenceDataset, marketsOffset, signal));
  const market = markets.status === "success" ? markets.data.items.find(m => m.id === marketId) : undefined;
  const states = useResource(market ? `evidence:states:${dataset}:${marketId}:${statesOffset}:${retry}` : null, signal => api.states(dataset as EvidenceDataset, marketId, statesOffset, signal));
  const state = states.status === "success" ? states.data.items.find(s => s.id === stateId) : undefined;
  const facts = useResource(state ? `evidence:items:${dataset}:${marketId}:${stateId}:${retry}` : null, async signal => {
    const rows = await collectStateFacts((offset, requestSignal) => api.facts(dataset as EvidenceDataset, marketId, stateId, offset, requestSignal), state!.native_fact_count, signal);
    return groupEvidenceItems(rows);
  });
  const receipts = useResource(state && showReceipts ? `evidence:receipts:${dataset}:${marketId}:${stateId}:${receiptsOffset}:${retry}` : null, signal => api.receipts(dataset as EvidenceDataset, marketId, stateId, receiptsOffset, signal));
  function resetState() { setStateId(""); setReceiptsOffset(0); setShowReceipts(false); }
  function resetMarket() { setMarketId(""); setStatesOffset(0); resetState(); }

  return <div className="app-shell evidence-shell">
    <header className="topbar"><a className="brand" href="#evidence-main"><span className="brand-mark" aria-hidden="true">W<span>◇</span></span><span>WOW FOREVER<small>COMPANION</small></span></a><span className="topbar-section">Evidencia de mercado</span><span className="badge neutral">Sólo lectura</span></header>
    <main id="evidence-main">
      <section className="hero evidence-hero"><div><p className="eyebrow">El archivo del mercado</p><h1>Evidencia de mercado.</h1><p>Mínimos guardados y disponibilidad observada.<br/>No representan la oferta disponible ahora.</p></div></section>
      <section className="panel evidence-selection" aria-labelledby="evidence-selection-title">
        <div className="panel-heading"><h2 id="evidence-selection-title">Elegí qué evidencia explorar</h2></div>
        <div className="evidence-controls">
          <label>Dataset de evidencia<select value={dataset} onChange={e => { setDataset(e.target.value as EvidenceDataset | ""); setMarketsOffset(0); resetMarket(); }}><option value="">Elegir dataset</option><option value="simulated">Simulado · simulated</option><option value="stress_test">Prueba de estrés · stress_test</option><option value="launch">Lanzamiento · launch</option></select></label>
          <label>Economía / mercado<select value={marketId} disabled={markets.status !== "success"} onChange={e => { setMarketId(e.target.value); setStatesOffset(0); resetState(); }}><option value="">Elegir economía</option>{markets.status === "success" && markets.data.items.map(m => <option key={m.id} value={m.id}>{m.economy} · {m.region} · {m.faction ?? "AH compartido"}</option>)}</select></label>
          <label>Estado económico<select value={stateId} disabled={states.status !== "success"} onChange={e => { resetState(); setStateId(e.target.value); }}><option value="">Elegir estado</option>{states.status === "success" && states.data.items.map(s => <option key={s.id} value={s.id}>#{s.id} · adquirido {date(s.first_acquired_at)}</option>)}</select></label>
        </div>
        {!dataset && <StatusPanel title="Elegí un dataset">Los datos simulados, de estrés y de lanzamiento se consultan por separado.</StatusPanel>}
        <Progress resource={markets} onRetry={reload}/><Progress resource={states} onRetry={reload}/>
        {markets.status === "success" && <><Pages {...{ offset: marketsOffset, limit: 50, more: markets.data.has_more, label: "economías" }} onChange={n => { setMarketsOffset(n); resetMarket(); }}/>{!markets.data.items.length && <StatusPanel title="Sin economías disponibles">No hay evidencia v2 para este dataset. Las importaciones se realizan manualmente fuera del dashboard.</StatusPanel>}</>}
        {states.status === "success" && <><Pages {...{ offset: statesOffset, limit: 50, more: states.data.has_more, label: "estados" }} onChange={n => { setStatesOffset(n); resetState(); }}/>{!states.data.items.length && <StatusPanel title="Sin estados disponibles">Esta economía todavía no tiene estados v2 consultables.</StatusPanel>}</>}
      </section>
      {market && <section className="evidence-identity" aria-label="Identidad económica"><strong>{market.economy}</strong><span>{market.region} · {market.faction ?? "AH compartido"}</span><span className={`badge ${dataset === "simulated" ? "simulated" : "neutral"}`}>{dataset}</span></section>}
      {state && <>
        <section className="panel evidence-state" aria-labelledby="evidence-state-title">
          <div className="panel-heading"><div><p className="eyebrow">Items del estado seleccionado</p><h2 id="evidence-state-title">Estado #{state.id}</h2></div><span>{state.item_count} items registrados</span></div>
          <p>Adquisición: <time dateTime={state.first_acquired_at ?? undefined}>{date(state.first_acquired_at)}</time>. Es la hora de copia, no la fecha de cada precio.</p>
          <p className="evidence-warning" role="note">{dataset === "simulated" ? "Datos sintéticos. " : dataset === "stress_test" ? "Datos de estrés; no representan el lanzamiento. " : "Dataset de lanzamiento declarado. "}Precios guardados, sin oferta en vivo. La disponibilidad no indica ventas.</p>
          <Progress resource={facts} onRetry={reload}/>
          {facts.status === "success" && (!facts.data.length ? <StatusPanel title="Sin items con datos">El mercado puede estar vacío dentro de un estado que contiene otros mercados.</StatusPanel> : <EvidenceItemsTable key={`${dataset}:${marketId}:${stateId}`} items={facts.data}/>)}
        </section>
        <details className="panel evidence-provenance" open={showReceipts} onToggle={e => setShowReceipts(e.currentTarget.open)}><summary>Procedencia y recepciones · información avanzada</summary>
          <p>{state.item_count} estructuras de item · {state.native_fact_count} hechos · {state.receipt_count} recepciones. Reglas {market!.ruleset} · etiqueta nativa {state.native_label}.</p>
          <p className="muted">Etiqueta representativa de la economía: {market!.native_label}. Los buckets son índices sin fecha civil verificada; varios estados del mismo bucket no crean días nuevos.</p>
          <p>Hash del estado: <code>{state.state_hash}</code></p>
          <p>Procedencia declarada por el operador y hashes comprobados al importar. Estas declaraciones no autentican el cliente ni el reloj. La recepción SQL tampoco fecha los precios.</p>
          <p className="muted">Última adquisición registrada: {date(state.last_acquired_at)}. El orden de los estados no establece el orden de los scans.</p>
          <Progress resource={receipts} onRetry={reload}/>
          {receipts.status === "success" && <>{!receipts.data.items.length && <p>No hay recepciones en esta página.</p>}<ul className="evidence-receipts">{receipts.data.items.map(r => <li key={r.id}><strong>Recepción #{r.id} · {r.status === "duplicate" ? "estado reutilizado" : "estado creado"}</strong><span>Adquisición: <time dateTime={r.acquired_at}>{date(r.acquired_at)}</time></span><span>Recepción SQL: <time dateTime={r.received_at}>{date(r.received_at)}</time></span><small>Formato {r.input_format} · productor {r.codec_producer === "unverified" ? "no confirmado" : r.codec_producer} · build al capturar {r.capture_build_known ? "declarado con evidencia" : "no confirmado"}</small><code>SHA-256: {r.source_sha256}</code></li>)}</ul><Pages offset={receiptsOffset} limit={20} more={receipts.data.has_more} label="recepciones" onChange={setReceiptsOffset}/></>}
        </details>
      </>}
    </main>
    <footer><span>WoW Forever Companion · Evidencia de mercado</span><span>Sin sincronización, predicciones ni oferta en vivo</span></footer>
  </div>;
}
