import type { BucketPoint, MetricValue } from "../../api/generated";
import { splitCopper } from "./currency";

const DECIMAL = /^[+-]?\d+(?:\.\d+)?$/;
function parts(value: string) {
  if (!DECIMAL.test(value)) throw new Error("Decimal inválido");
  const negative = value.startsWith("-");
  const [integer, fraction = ""] = value.replace(/^[+-]/, "").split(".");
  return { negative, integer: BigInt(integer), fraction };
}

// Keep all fractional copper exactly as FastAPI serialized it.
export function copperToCoins(value: string | number): string {
  const { negative, gold, silver, copper, fraction } = splitCopper(value);
  const coins = [];
  if (gold) coins.push(`${gold} oro`);
  if (silver || gold) coins.push(`${silver} plata`);
  coins.push(`${copper}${fraction ? `,${fraction}` : ""} cobre`);
  return `${negative ? "−" : ""}${coins.join(" · ")}`;
}

export function decimalText(value: string): string {
  parts(value);
  return value.replace(/^-/, "−").replace(".", ",");
}
export function compactExact(value: string, places = 2): { text: string; shortened: boolean } {
  parts(value);
  const [integer, fraction = ""] = value.split(".");
  const shortened = fraction.length > places;
  return { text: decimalText(`${integer}${fraction ? `.${fraction.slice(0, places)}` : ""}`) + (shortened ? "…" : ""), shortened };
}
export function trendLabel(metric: MetricValue): string {
  if (metric.value === null || metric.status !== "ok") return "Sin tendencia calculable";
  const { negative, integer, fraction } = parts(metric.value);
  if (integer === 0n && !/[1-9]/.test(fraction)) return "Pendiente nula";
  return negative ? "Tendencia descendente" : "Tendencia ascendente";
}
export function bucketLabel(point: BucketPoint, basis: string): string {
  if (basis === "unknown" || !point.bucket_start) return `Índice ${point.scan_day}`;
  return `${new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(point.bucket_start))} UTC · índice ${point.scan_day}`;
}
