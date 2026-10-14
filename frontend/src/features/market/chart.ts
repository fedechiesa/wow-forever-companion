import type { BucketPoint } from "../../api/generated";

export interface ChartDot { point: BucketPoint; x: number; y: number | null }
export interface PriceTick { value: number; y: number }

// Integral copper scale labels stay distinct even for constant/zero prices.
export function priceTicks(low: number, high: number, height = 270): PriceTick[] {
  const rawStep = Math.max(1, (high - low) / 3);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 5, 10].find(factor => factor * magnitude >= rawStep)! * magnitude;
  const ticks: PriceTick[] = [];
  for (let value = Math.ceil(low / step) * step; value <= high; value += step) {
    ticks.push({ value, y: 15 + (high - value) / (high - low) * (height - 55) });
  }
  return ticks;
}

// Ties use the lower original index, independently of SVG drawing order.
export function nearestChartDot(dots: ChartDot[], x: number, y: number): ChartDot | undefined {
  let nearest: ChartDot | undefined;
  let distance = Infinity;
  for (const dot of dots) {
    if (dot.y === null) continue;
    const candidate = (dot.x - x) ** 2 + (dot.y - y) ** 2;
    if (candidate < distance || (candidate === distance && (!nearest || dot.point.scan_day < nearest.point.scan_day))) {
      nearest = dot;
      distance = candidate;
    }
  }
  return nearest;
}
export function chartGeometry(points: BucketPoint[], width = 900, height = 270) {
  const prices = points.flatMap(p => p.daily_minimum === null || p.daily_minimum === undefined ? [] : [p.daily_minimum]);
  const min = prices.length ? Math.min(...prices) : 0;
  const max = prices.length ? Math.max(...prices) : 0;
  const low = Math.max(0, min - Math.max(1, (max - min) * .15));
  const high = max + Math.max(1, (max - min) * .15);
  const first = points[0]?.scan_day ?? 0;
  const last = points[points.length - 1]?.scan_day ?? first;
  const dots: ChartDot[] = points.map(point => ({ point,
    x: last === first ? width / 2 : 82 + (point.scan_day - first) / (last - first) * (width - 110),
    y: point.daily_minimum == null ? null : 15 + (high - point.daily_minimum) / (high - low) * (height - 55),
  }));
  const segments: ChartDot[][] = [];
  let current: ChartDot[] = [];
  for (const dot of dots) {
    if (dot.y === null || (current.length && dot.point.scan_day !== current[current.length - 1].point.scan_day + 1)) {
      if (current.length) segments.push(current);
      current = [];
    }
    if (dot.y !== null) current.push(dot);
  }
  if (current.length) segments.push(current);
  return { dots, segments, low, high, yTicks: priceTicks(low, high, height), hasPrices: prices.length > 0 };
}
