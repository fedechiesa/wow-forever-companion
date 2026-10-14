import { useEffect, useMemo, useState } from "react";
import { getItems, getMarkets, getMetrics, getSeries } from "./api/backend";
import type { Dataset } from "./api/contracts";
import { StatusPanel } from "./components/StatusPanel";
import { emptySelection, type ContextSelection } from "./features/market/ContextControls";
import { initialWindow } from "./features/market/WindowControls";
import { AdvancedOptions } from "./features/market/AdvancedOptions";
import { ContextChoice } from "./features/market/ContextChoice";
import { ItemList } from "./features/market/ItemList";
import { MarketResults } from "./features/market/MarketResults";
import { contextKey, type WindowInput } from "./features/market/query";
import { marketLabel, planAnalysis, resolveContext } from "./features/market/selection";
import { useResource } from "./features/market/useResource";

export function App() {
  const [retry, setRetry] = useState(0);
  const [dataset, setDataset] = useState<Dataset | "">("");
  const [marketId, setMarketId] = useState("");
  const [search, setSearch] = useState("");
  const [itemKey, setItemKey] = useState("");
  const [preference, setPreference] = useState<ContextSelection | null>(null);
  const [window, setWindow] = useState<WindowInput>(initialWindow);
  const [resetNotice, setResetNotice] = useState("");
  const [metricsRetry, setMetricsRetry] = useState(0);
  const markets = useResource(`markets:${retry}`, getMarkets);
  const marketList = markets.status === "success" ? markets.data : [];
  const market = marketList.find(m => String(m.id) === marketId && (!dataset || m.dataset === dataset));
  const items = useResource(market ? `items:${market.id}:${retry}` : null, signal => getItems(market!.id, signal));
  const chosenItem = items.status === "success" ? items.data.find(item => item.item_key === itemKey) : undefined;
  const series = useResource(market && chosenItem ? `series:${market.id}:${itemKey}:${retry}` : null, signal => getSeries(market!.id, itemKey, signal));
  const availableSeries = series.status === "success" ? series.data : undefined;
  const resolution = useMemo(() => availableSeries ? resolveContext(availableSeries, preference) : undefined, [availableSeries, preference]);
  const plan = useMemo(() => planAnalysis(resolution, window), [resolution, window]);
  const descriptor = resolution?.descriptor;
  const metrics = useResource(plan.params ? `${plan.params}:${metricsRetry}` : null, async signal => {
    const result = await getMetrics(plan.params!, signal);
    if (contextKey(result.context) !== contextKey(descriptor!.context)) throw new Error("La respuesta no coincide con el historial seleccionado.");
    return result;
  }, 200);

  // Resolve invalid preferences before effects query anything: plan already uses
  // the reconciled identity/window, so this update does not create a second query.
  useEffect(() => {
    if (!resolution) return;
    const notices = [...resolution.notices, ...plan.notices];
    if (!notices.length) return;
    setResetNotice(notices.join(" "));
    setPreference(resolution.retainedPreference);
    setWindow(plan.window);
  }, [resolution, plan]);

  useEffect(() => {
    if (items.status === "success" && itemKey && !items.data.some(item => item.item_key === itemKey)) {
      setItemKey("");
      setResetNotice("El item elegido no está disponible en este mercado. Elegí otro item del catálogo.");
    }
  }, [items, itemKey]);

  const changeMarket = (id: string) => {
    setMarketId(id);
    // Verify the item in the new catalog before discovery/metrics can run.
    if (!id) setItemKey("");
    setSearch("");
    setResetNotice("");
  };
  const changeDataset = (value: Dataset | "") => {
    setDataset(value);
    if (market && value && market.dataset !== value) {
      changeMarket("");
      setResetNotice("El mercado anterior no pertenece a este dataset. Elegí un mercado de la lista filtrada.");
    }
  };
  const changeContext = (value: ContextSelection) => { setPreference(value); setResetNotice(""); };
  const reload = () => setRetry(n => n + 1);
  const filtered = items.status === "success" ? items.data.filter(item => `${item.item_key} ${item.external_item_id} ${item.key_kind}`.toLowerCase().includes(search.trim().toLowerCase())) : [];

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="#main"><span className="brand-mark" aria-hidden="true">W<span>◇</span></span><span>WOW FOREVER<small>COMPANION</small></span></a>
      <span className="topbar-section">Market Intelligence</span>
      <span className={`connection ${markets.status === "success" ? "connected" : ""}`}><i/>{markets.status === "success" ? "Archivo conectado" : markets.status === "error" ? "Archivo no disponible" : "Conectando…"}</span>
    </header>
    <main id="main">
      <section className="hero"><div><p className="eyebrow"><span aria-hidden="true">◆</span> El archivo del mercado</p><h1>Cada mínimo cuenta.</h1><p>Elegí un mercado y un item.<br/>Su histórico y estadísticas aparecen automáticamente.</p></div><div className="hero-seal" aria-hidden="true"><span>◇</span><small>MARKET<br/>ARCHIVE</small></div></section>
      <div className="workspace">
        <aside className="catalog panel" aria-labelledby="catalog-title">
          <div className="panel-heading"><div><p className="eyebrow">01 · Explorar</p><h2 id="catalog-title">Mercado e items</h2></div></div>
          {markets.status === "loading" && <StatusPanel title="Cargando mercados" loading/>}
          {markets.status === "error" && <StatusPanel title="No pudimos cargar los mercados" error onRetry={reload}>{markets.error.message}</StatusPanel>}
          {markets.status === "success" && (!marketList.length ? <StatusPanel title="Todavía no hay mercados">No hay información almacenada para explorar.</StatusPanel> : <>
            <label>Mercado<select value={marketId} onChange={e => changeMarket(e.target.value)}>
              <option value="">Elegir mercado</option>{marketList.filter(m => !dataset || m.dataset === dataset).map(m => <option key={m.id} value={m.id}>{marketLabel(m)}</option>)}
            </select></label>
            {!marketList.some(m => !dataset || m.dataset === dataset) && <p className="muted">No hay mercados para el dataset elegido. Revisá Opciones avanzadas.</p>}
            {market && <div className="market-meta"><span>{market.region} · reglas {market.ruleset}</span><span className={`badge ${market.dataset === "simulated" ? "simulated" : "neutral"}`}>{market.dataset === "simulated" ? "SIMULATED" : "REAL"}</span></div>}
          </>)}
          <div className="catalog-divider"/>
          <label>Buscar item<input type="search" value={search} disabled={items.status !== "success"} placeholder="ID o variante completa…" onChange={e => setSearch(e.target.value)}/></label>
          <p className="catalog-caption">El catálogo disponible identifica los items por su clave; aún no incluye nombres.</p>
          {items.status === "idle" && <StatusPanel title="Elegí un mercado">Sus items disponibles aparecerán aquí.</StatusPanel>}
          {items.status === "loading" && <StatusPanel title="Cargando items" loading/>}
          {items.status === "error" && <StatusPanel title="No pudimos cargar los items" error onRetry={reload}>{items.error.message}</StatusPanel>}
          {items.status === "success" && <>
            <div className="catalog-count">{filtered.length} de {items.data.length} items</div>
            {!filtered.length ? <StatusPanel title={items.data.length ? "Sin coincidencias" : "Sin items disponibles"}>{items.data.length ? "Probá otra clave o variante." : "Este mercado no tiene información de items en el catálogo."}</StatusPanel> : <ItemList items={filtered} selectedKey={itemKey} onSelect={key => { setItemKey(key); setResetNotice(""); }}/>}
          </>}
        </aside>
        <div className="analysis-column">
          <AdvancedOptions datasets={[...new Set(marketList.map(m => m.dataset))]} dataset={dataset} onDatasetChange={changeDataset}
            series={availableSeries ?? []} selection={resolution?.selection ?? emptySelection} onContextChange={changeContext}
            descriptor={descriptor} window={plan.window} onWindowChange={value => { setWindow(value); setResetNotice(""); }}/>
          {resetNotice && <p className="selection-notice" role="status">{resetNotice}</p>}
          {!chosenItem && <section className="analysis-placeholder"><span aria-hidden="true">✧</span><h2>Mercado. Item. Histórico.</h2><p>Elegí un item para ver sus mínimos guardados.<br/>La disponibilidad describe unidades disponibles, sin inferir ventas.</p></section>}
          {series.status === "loading" && <section className="panel analysis-state"><StatusPanel title="Buscando el histórico del item" loading/></section>}
          {series.status === "error" && <section className="panel analysis-state"><StatusPanel title="No pudimos encontrar el histórico" error onRetry={reload}>{series.error.message}</StatusPanel></section>}
          {resolution?.status === "empty" && <section className="panel analysis-state"><StatusPanel title="Sin históricos disponibles">Este item no tiene una serie compatible para analizar.</StatusPanel></section>}
          {resolution && (resolution.status === "ambiguous" || resolution.status === "export_required") && <ContextChoice resolution={resolution} onChange={changeContext}/>}
          {descriptor && <div className="reading-summary"><span>{descriptor.context.series_mode === "accumulated" ? "Historial acumulado" : `Exportación #${descriptor.context.export_id}`} · {plan.window.type === "observed_buckets" ? `${plan.window.size} registros de mercado solicitados` : plan.window.type === "calendar_days" ? `${plan.window.days} días nominales` : `Índices ${plan.window.start} → ${plan.window.end}`}</span><small>Fuente: {descriptor.context.source_id} · {descriptor.context.temporal_basis === "unknown" ? "Índices sin fechas verificadas" : `Base temporal: ${descriptor.context.temporal_basis}`}</small></div>}
          {plan.error && <p className="form-error" role="alert">{plan.error} Revisá Opciones avanzadas.</p>}
          {metrics.status === "loading" && <section className="panel analysis-state"><StatusPanel title="Cargando gráfico y estadísticas" loading>Consultando el historial de este item.</StatusPanel></section>}
          {metrics.status === "error" && <section className="panel analysis-state"><StatusPanel title="No pudimos cargar el análisis" error onRetry={() => setMetricsRetry(n => n + 1)}>{metrics.error.message}</StatusPanel></section>}
          {metrics.status === "success" && <MarketResults data={metrics.data}/>}
        </div>
      </div>
    </main>
    <footer><span>WoW Forever Companion <i>·</i> Market Intelligence</span><span>Evidencia descriptiva · lectura de datos</span></footer>
  </div>;
}

