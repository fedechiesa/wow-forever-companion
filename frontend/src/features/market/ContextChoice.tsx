import { contextKey } from "./query";
import { selectionFromContext, type ContextResolution } from "./selection";
import type { ContextSelection } from "./ContextControls";

export function ContextChoice({ resolution, onChange }: { resolution: ContextResolution; onChange: (selection: ContextSelection) => void }) {
  const exported = resolution.status === "export_required";
  return <section className="panel context-choice" aria-labelledby="history-choice-title">
    <h2 id="history-choice-title">{exported ? "Elegí una exportación para investigar" : "Hay más de un historial disponible"}</h2>
    <p className="muted">{exported ? "Las exportaciones son estados guardados. Su recepción y su ID no indican cuál fue la última observación del mercado." : "Cada historial conserva su fuente y su reloj. Elegí cuál querés ver; no mezclamos sus datos."}</p>
    <label>Historial a consultar<select value="" onChange={e => {
      const selected = resolution.candidates.find(s => contextKey(s.context) === e.target.value);
      if (selected) onChange(selectionFromContext(selected.context));
    }}><option value="">Elegir historial</option>{resolution.candidates.map(({ context: c }) => <option value={contextKey(c)} key={contextKey(c)}>
      {c.source_id} · {c.source_type} · {c.temporal_basis === "unknown" ? "sin fechas verificadas" : `base ${c.temporal_basis}`} · {c.series_mode === "export" ? `export #${c.export_id}` : "historial acumulado"}
    </option>)}</select></label>
  </section>;
}
