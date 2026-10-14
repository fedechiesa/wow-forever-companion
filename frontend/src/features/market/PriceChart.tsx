import { useState, type PointerEvent } from "react";
import type { MarketMetricsResponse } from "../../api/generated";
import { bucketLabel, copperToCoins } from "./format";
import { chartGeometry, nearestChartDot } from "./chart";

export function PriceChart({ data }: { data: MarketMetricsResponse }) {
  const [active, setActive] = useState<number | null>(null);
  const { dots, segments, yTicks, hasPrices } = chartGeometry(data.points);
  const point = data.points.find(p => p.scan_day === active);
  const ticks = Array.from(new Set([0, Math.floor((dots.length - 1) / 2), dots.length - 1])).filter(i => i >= 0);
  const inspectNearest = (event: PointerEvent<SVGSVGElement>) => {
    // Screen CTM accounts for scaling, scrolling and viewBox letterboxing.
    const inverse = event.currentTarget.getScreenCTM()?.inverse();
    if (!inverse) return;
    const x = inverse.a * event.clientX + inverse.c * event.clientY + inverse.e;
    const y = inverse.b * event.clientX + inverse.d * event.clientY + inverse.f;
    const closest = nearestChartDot(dots, x, y);
    if (closest) setActive(closest.point.scan_day);
  };
  return <section className="panel chart-panel" aria-labelledby="chart-title">
    <div className="panel-heading"><div><p className="eyebrow">Evidencia histórica</p><h2 id="chart-title">Mínimos guardados</h2></div><span className="chart-legend"><i /> Mínimo por bucket</span></div>
    <p className="muted">{data.context.temporal_basis === "unknown" ? "Índices del addon · sin fechas verificadas" : "Buckets nominales · fecha UTC e índice del addon"}. Eje vertical en copper.</p>
    {hasPrices ? <div className="chart-scroll" tabIndex={0} aria-label="Gráfico con desplazamiento horizontal en pantallas pequeñas"><svg className="price-chart" viewBox="0 0 900 270" role="group" aria-label="Histórico de mínimos guardados; cada punto permite ver su evidencia" onPointerMove={inspectNearest} onPointerDown={inspectNearest}>
      <defs><linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#cba563" stopOpacity=".18"/><stop offset="100%" stopColor="#cba563" stopOpacity="0"/></linearGradient></defs>
      {yTicks.map(tick => <g key={tick.value}><line x1="82" x2="872" y1={tick.y} y2={tick.y} className="chart-grid"/><text x="70" y={tick.y + 4} textAnchor="end">{tick.value} c</text></g>)}
      {segments.map((segment, i) => {
        const line = segment.map((dot, n) => `${n ? "L" : "M"}${dot.x},${dot.y}`).join(" ");
        return <g key={i}><path d={`${line} L${segment[segment.length - 1].x},230 L${segment[0].x},230 Z`} fill="url(#price-fill)"/><path d={line} className="chart-line"/></g>;
      })}
      {dots.map(dot => dot.y === null ? <line key={dot.point.scan_day} x1={dot.x} x2={dot.x} y1="222" y2="230" className="missing-marker"/> : <g key={dot.point.scan_day}>
        <circle cx={dot.x} cy={dot.y} r={active === dot.point.scan_day ? 5 : 3} className="chart-dot" pointerEvents="none"/>
        <circle cx={dot.x} cy={dot.y} r="5" className="chart-hit" pointerEvents="none" tabIndex={0} role="button"
          aria-label={`${bucketLabel(dot.point, data.context.temporal_basis)}: ${copperToCoins(dot.point.daily_minimum!)}`}
          onFocus={() => setActive(dot.point.scan_day)} onClick={event => { if (event.detail === 0) setActive(dot.point.scan_day); }}
          onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setActive(dot.point.scan_day); } }}>
          <title>{`${bucketLabel(dot.point, data.context.temporal_basis)} · ${copperToCoins(dot.point.daily_minimum!)}`}</title>
        </circle>
      </g>)}
      {ticks.map(index => <text key={index} x={dots[index].x} y="260" textAnchor={index === 0 ? "start" : index === dots.length - 1 ? "end" : "middle"}>{dots[index].point.scan_day}</text>)}
    </svg></div> : <div className="chart-empty" role="status">No hay mínimos guardados en esta ventana.</div>}
    <div className="chart-detail" aria-live="polite">{point ? <><strong>{bucketLabel(point, data.context.temporal_basis)}</strong><span>{copperToCoins(point.daily_minimum!)} · origen {point.minimum_origin}</span><span>Disponibilidad máxima: {point.daily_max_available ?? "desconocida"}</span></> : <span>Pasá por un punto, tocá el gráfico o usá Tab para inspeccionar un bucket.</span>}</div>
    <p className="chart-footnote">Los huecos cortan la línea. No se interpolan ausencias; estos valores no representan precios actuales.</p>
  </section>;
}
