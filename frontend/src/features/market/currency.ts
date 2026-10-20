export type Denomination = "gold" | "silver" | "copper";
export interface CopperAmount {
  original: string;
  negative: boolean;
  gold: bigint;
  silver: bigint;
  copper: bigint;
  fraction: string;
}
export interface CoinToken { denomination: Denomination; value: string }
export type MoneyKind = "observed" | "derived";
export const coinLabels = { gold: "oro", silver: "plata", copper: "cobre" };
export const coinSuffixes = { gold: "g", silver: "s", copper: "c" };

// Numbers are accepted only for native integer prices/ticks already validated by
// the API contract. Derived Decimal values always enter as their original string.
export function splitCopper(value: string | number): CopperAmount {
  if (typeof value === "number" && !Number.isSafeInteger(value)) throw new Error("Copper numérico fuera del rango entero seguro");
  if (typeof value !== "string" && typeof value !== "number") throw new Error("Monto de copper inválido");
  const original = String(value);
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(original)) throw new Error("Decimal de copper inválido");
  const [whole, fraction = ""] = original.replace(/^[+-]/, "").split(".");
  const integer = BigInt(whole);
  return { original, negative: original.startsWith("-"), gold: integer / 10000n,
    silver: integer % 10000n / 100n, copper: integer % 100n, fraction };
}

export function presentCopper(value: string | number, kind: MoneyKind = "observed") {
  const amount = splitCopper(value);
  const rounded = /[1-9]/.test(amount.fraction);
  if (kind === "observed" && rounded) throw new Error("Precio observado inválido: se requiere copper entero.");
  // Display-only ROUND_HALF_UP: round the absolute Decimal using its digits,
  // then restore its sign. No float conversion, Decimal mutation or economic calculation.
  const magnitude = amount.gold * 10000n + amount.silver * 100n + amount.copper
    + (rounded && amount.fraction[0] >= "5" ? 1n : 0n);
  const gold = magnitude / 10000n, silver = magnitude % 10000n / 100n, copper = magnitude % 100n;
  const tokens: CoinToken[] = [];
  if (gold) tokens.push({ denomination: "gold", value: String(gold) });
  if (silver) tokens.push({ denomination: "silver", value: String(silver) });
  if (copper || !tokens.length) tokens.push({ denomination: "copper", value: String(copper) });
  const sign = amount.negative ? "−" : "";
  return { ...amount, tokens, rounded,
    text: (rounded ? "≈ " : "") + sign + tokens.map(token => `${token.value}${coinSuffixes[token.denomination]}`).join(" "),
    label: (rounded ? "aproximadamente " : "") + (amount.negative ? "menos " : "") + tokens.map(token => `${token.value} ${coinLabels[token.denomination]}`).join(", "),
  };
}

export function formatCopper(value: string | number, kind: MoneyKind = "observed"): string { return presentCopper(value, kind).text; }

// Keep whole denominations on the axis too. Very long labels use integer copper
// to fit the existing SVG margin, preserving distinct ticks without rounding.
export function formatCopperAxis(value: number): string {
  const exact = formatCopper(value);
  return exact.length > 14 ? `${value}c` : exact;
}
