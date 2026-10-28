import schemas from "./response-schemas.json";

export type Dataset = "real" | "simulated";
export interface PartialMarket {
  id: number;
  market_key: string;
  ruleset: "PvE" | "PvP" | "HC" | "RP";
  region: string;
  dataset: Dataset;
}
export interface PartialItem {
  id: number;
  item_key: string;
  external_item_id: string;
  key_kind: "item" | "gear_level" | "gear_suffix" | "pet";
}

interface Schema {
  $ref?: string;
  type?: string;
  const?: unknown;
  enum?: unknown[];
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean;
  items?: Schema;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minLength?: number;
  maxLength?: number;
  maxItems?: number;
  pattern?: string;
  format?: string;
}
const registry: Record<string, Schema> = schemas;
const string: Schema = { type: "string", minLength: 1 };
const id: Schema = { type: "integer", minimum: 1 };
// /partial has no OpenAPI response models. Fields come from api/partial.py,
// migration 003, and live responses; the API supplies neither names nor quality.
const partialSchemas: Record<string, Schema> = {
  markets: { type: "array", items: { type: "object", required: ["id", "market_key", "ruleset", "region", "dataset"], properties: {
    id, market_key: string, ruleset: { enum: ["PvE", "PvP", "HC", "RP"] }, region: string, dataset: { enum: ["real", "simulated"] },
  } } },
  items: { type: "array", items: { type: "object", required: ["id", "item_key", "external_item_id", "key_kind"], properties: {
    id, item_key: string, external_item_id: string, key_kind: { enum: ["item", "gear_level", "gear_suffix", "pet"] },
  } } },
};

export class ContractError extends Error {
  constructor(path: string) { super(`Respuesta incompatible con el contrato de la API (${path}).`); }
}

function validate(value: unknown, schema: Schema, path: string): void {
  const fail = (): never => { throw new ContractError(path); };
  if (schema.$ref) return validate(value, registry[schema.$ref.split("/").pop()!], path);
  if (schema.anyOf) {
    for (const option of schema.anyOf) {
      try { validate(value, option, path); return; } catch (error) { if (!(error instanceof ContractError)) throw error; }
    }
    fail();
  }
  if ("const" in schema && value !== schema.const) fail();
  if (schema.enum && !schema.enum.includes(value)) fail();
  if (schema.type === "null" && value !== null) fail();
  if (schema.type === "boolean" && typeof value !== "boolean") fail();
  if (schema.type === "string") {
    if (typeof value !== "string") fail();
    const text = value as string;
    if (text.length < (schema.minLength ?? 0) || text.length > (schema.maxLength ?? Infinity)) fail();
    if (schema.pattern && !new RegExp(schema.pattern).test(text)) fail();
    if (schema.format === "date-time" && (!/(Z|[+-]\d\d:\d\d)$/.test(text) || !Number.isFinite(Date.parse(text)))) fail();
  }
  if (schema.type === "integer" || schema.type === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) fail();
    const number = value as number;
    // Never silently round a PostgreSQL BIGINT identifier.
    if (schema.type === "integer" && !Number.isSafeInteger(number)) fail();
    if (number < (schema.minimum ?? -Infinity) || number > (schema.maximum ?? Infinity)) fail();
    if (schema.exclusiveMinimum !== undefined && number <= schema.exclusiveMinimum) fail();
  }
  if (schema.type === "array") {
    if (!Array.isArray(value)) fail();
    const array = value as unknown[];
    if (array.length > (schema.maxItems ?? Infinity)) fail();
    array.forEach((item, i) => validate(item, schema.items!, `${path}[${i}]`));
  }
  if (schema.type === "object") {
    if (value === null || typeof value !== "object" || Array.isArray(value)) fail();
    const record = value as Record<string, unknown>;
    for (const key of schema.required ?? []) if (!(key in record)) throw new ContractError(`${path}.${key}`);
    for (const [key, child] of Object.entries(record)) {
      const property = schema.properties?.[key];
      if (property) validate(child, property, `${path}.${key}`);
      else if (schema.additionalProperties === false) throw new ContractError(`${path}.${key}`);
    }
  }
}

export function assertResponse(value: unknown, name: "markets" | "items" | "SeriesDiscoveryResponse" | "MarketMetricsResponse" | "MarketSignalsResponse" | "EvidenceMarketsPage" | "EvidenceStatesPage" | "EvidenceFactsPage" | "EvidenceReceiptsPage" | "CatalogPage"): void {
  validate(value, partialSchemas[name] ?? registry[name], name);
}
