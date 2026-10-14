import type { Dataset } from "../../api/contracts";
import type { SeriesDescriptor } from "../../api/generated";
import { ContextControls, type ContextSelection } from "./ContextControls";
import { WindowControls } from "./WindowControls";
import type { WindowInput } from "./query";

export function AdvancedOptions({ datasets, dataset, onDatasetChange, series, selection, onContextChange, descriptor, window, onWindowChange }: {
  datasets: Dataset[]; dataset: Dataset | ""; onDatasetChange: (dataset: Dataset | "") => void;
  series: SeriesDescriptor[]; selection: ContextSelection; onContextChange: (selection: ContextSelection) => void;
  descriptor?: SeriesDescriptor; window: WindowInput; onWindowChange: (window: WindowInput) => void;
}) {
  return <section className="panel advanced-panel"><details>
    <summary>Opciones avanzadas<span>Fuente, datos y período de análisis</span></summary>
    <div className="advanced-content">
      <p className="muted">Los cambios válidos actualizan el análisis automáticamente. Cada historial corresponde a una fuente, un mercado y una base temporal.</p>
      <label className="dataset-filter">Dataset · origen de los datos<select value={dataset} onChange={e => onDatasetChange(e.target.value as Dataset | "")}>
        <option value="">Todos los disponibles</option>{datasets.map(d => <option key={d} value={d}>{d === "simulated" ? "simulated · SIMULATED" : "real · datos importados"}</option>)}
      </select></label>
      <fieldset className="advanced-context" disabled={!series.length}><legend>Identidad del historial</legend>
        <ContextControls series={series} value={selection} onChange={onContextChange}/>
      </fieldset>
      <WindowControls descriptor={descriptor} value={window} onChange={onWindowChange}/>
    </div>
  </details></section>;
}
