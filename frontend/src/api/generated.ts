// Generated from FastAPI OpenAPI. Run scripts/generate-api-contracts.py; do not edit.
export interface BucketPoint {
  scan_day: number;
  bucket_start?: string | null;
  market_observed: boolean;
  daily_minimum?: number | null;
  daily_highest_minimum?: number | null;
  daily_max_available?: number | null;
  minimum_origin?: "l" | "h_fallback" | "unknown" | null;
  minimum_evidence?: EvidenceReference | null;
  highest_minimum_evidence?: EvidenceReference | null;
  availability_evidence?: EvidenceReference | null;
}

export interface CatalogItem {
  product?: "forever";
  entity_kind?: "item";
  item_id: number;
  name: string;
  language?: string | null;
  quality?: string | null;
  category?: string | null;
  subclass?: string | null;
  build?: string | null;
  compatibility?: "provider_product_only";
  icon_ref?: string | null;
  icon_permission?: "unverified" | "authorized";
  provider: "ahledger" | "foreverdb";
  source_url: string;
  attribution_url: string;
  fetched_at: number;
  expires_at: number;
}

export interface CatalogPage {
  contract?: "5d2-v1";
  items: Array<CatalogItem>;
}

export interface CoverageSummary {
  selected_position_count: number;
  observed_market_bucket_count: number;
  price_observation_count: number;
  availability_observation_count: number;
  missing_price_position_count: number;
  missing_availability_position_count: number;
  index_span_position_count: number;
  unobserved_market_position_count: number;
  price_ratio: MetricValue;
  availability_ratio: MetricValue;
}

export interface EvidenceFact {
  item_key: string;
  external_item_id: string;
  key_kind: "item" | "gear_level" | "gear_suffix" | "pet";
  scan_day: number | null;
  native_l: number | null;
  native_h: number | null;
  native_a: number | null;
  native_m: number | null;
  minimum_copper: number | null;
  minimum_origin: "l" | "h_fallback" | null;
  native_fact_count: number;
}

export interface EvidenceFactsPage {
  contract?: "5c1-v1";
  dataset: "simulated" | "stress_test" | "launch";
  limit: number;
  offset: number;
  has_more: boolean;
  market_id: string;
  export_id: string;
  items: Array<EvidenceFact>;
}

export interface EvidenceMarket {
  id: string;
  dataset: "simulated" | "stress_test" | "launch";
  economy: string;
  region: string;
  native_label: string;
  ruleset: "PvE" | "PvP" | "HC" | "RP";
  auction_house_scope: "shared" | "faction";
  faction: string | null;
}

export interface EvidenceMarketsPage {
  contract?: "5c1-v1";
  dataset: "simulated" | "stress_test" | "launch";
  limit: number;
  offset: number;
  has_more: boolean;
  items: Array<EvidenceMarket>;
}

export interface EvidenceReason {
  code: "insufficient_observations" | "insufficient_history" | "insufficient_price_coverage" | "insufficient_index_coverage" | "latest_price_missing_or_stale" | "native_l_required" | "known_temporal_basis_required" | "zero_reference" | "zero_baseline" | "unavailable_trend";
  message: string;
}

export interface EvidenceReceipt {
  id: string;
  acquired_at: string;
  received_at: string;
  status: "completed" | "duplicate";
  source_sha256: string;
  input_format: "lua_tables" | "cbor_definite" | "mixed";
  codec_producer: "unverified" | "C_EncodingUtil" | "LibCBOR";
  capture_build_known: boolean;
}

export interface EvidenceReceiptsPage {
  contract?: "5c1-v1";
  dataset: "simulated" | "stress_test" | "launch";
  limit: number;
  offset: number;
  has_more: boolean;
  market_id: string;
  export_id: string;
  items: Array<EvidenceReceipt>;
}

export interface EvidenceReference {
  table: "partial_observations" | "partial_export_facts";
  row_id: number;
  first_import_id?: number | null;
  last_import_id?: number | null;
  native_field?: "l" | "h" | "a" | null;
  original_item_key?: string | null;
  original_day_key?: string | null;
}

export interface EvidenceState {
  id: string;
  state_hash: string;
  native_label: string;
  item_count: number;
  native_fact_count: number;
  receipt_count: number;
  first_acquired_at: string | null;
  last_acquired_at: string | null;
}

export interface EvidenceStatesPage {
  contract?: "5c1-v1";
  dataset: "simulated" | "stress_test" | "launch";
  limit: number;
  offset: number;
  has_more: boolean;
  market_id: string;
  items: Array<EvidenceState>;
}

export interface HistoricalDeviationSignal {
  signal_type?: "historical_price_deviation";
  direction: "below_reference" | "above_reference" | "no_significant_deviation" | "insufficient_evidence";
  observed_price_copper: MetricValue;
  reference_price_copper: MetricValue;
  reference_method?: "median_excluding_latest";
  signed_deviation_copper: MetricValue;
  absolute_deviation_copper: MetricValue;
  deviation_pct: MetricValue;
  evidence: SignalEvidence;
  explanation: string;
}

export interface HistoricalTrendSignal {
  signal_type?: "historical_price_trend";
  direction: "ascending" | "descending" | "no_significant_trend" | "insufficient_evidence";
  first_price_copper: MetricValue;
  last_price_copper: MetricValue;
  slope_copper_per_scan_index: MetricValue;
  price_change_copper: MetricValue;
  price_change_pct: MetricValue;
  evidence: SignalEvidence;
  explanation: string;
}

export interface MarketMetrics {
  minimum_copper: MetricValue;
  mean_daily_minimum_copper: MetricValue;
  median_daily_minimum_copper: MetricValue;
  first_minimum_copper: MetricValue;
  last_minimum_copper: MetricValue;
  price_change_copper: MetricValue;
  price_change_pct: MetricValue;
  minimum_stddev_copper: MetricValue;
  minimum_cv_pct: MetricValue;
  trend_copper_per_scan_index: MetricValue;
  first_max_available: MetricValue;
  last_max_available: MetricValue;
  availability_change_units: MetricValue;
  availability_change_pct: MetricValue;
}

export interface MarketMetricsResponse {
  analysis_version?: "3a-v1";
  decimal_precision?: 40;
  context: SeriesContext;
  window: ResolvedWindow;
  points: Array<BucketPoint>;
  metrics: MarketMetrics;
  coverage: CoverageSummary;
  quality: QualitySummary;
  provenance: ProvenanceSummary;
}

export interface MarketSignalsResponse {
  analysis_version?: "3b1-v1";
  metrics_analysis_version?: "3a-v1";
  decimal_precision?: 40;
  parameters: SignalParameters;
  context: SeriesContext;
  window: ResolvedWindow;
  points: Array<BucketPoint>;
  coverage: CoverageSummary;
  quality: QualitySummary;
  provenance: ProvenanceSummary;
  warnings: Array<QualityWarning>;
  price_deviation: HistoricalDeviationSignal;
  historical_trend: HistoricalTrendSignal;
}

export interface MetricValue {
  value: string | null;
  unit: string;
  status: "ok" | "no_data" | "insufficient_data" | "undefined";
  reason?: string | null;
  observation_count: number;
  first_day?: number | null;
  last_day?: number | null;
}

export interface ProvenanceSummary {
  selected_daily_row_count: number;
  excluded_undated_count: number;
  undated_count_scope?: "selected_item_context_all_indices";
  referenced_import_ids: Array<number>;
  export_state_hash?: string | null;
  first_received_at?: string | null;
}

export interface QualitySummary {
  warnings: Array<QualityWarning>;
  minimum_l_count: number;
  minimum_h_fallback_count: number;
  minimum_unknown_origin_count: number;
  availability_field_presence: "present" | "absent" | "unknown";
  sample_warning_threshold?: 7;
}

export interface QualityWarning {
  code: string;
  message: string;
}

export interface ResolvedWindow {
  spec: WindowSpec;
  anchor_day: number | null;
  market_first_day: number | null;
  market_last_day: number | null;
  start_day: number | null;
  end_day: number | null;
  positions: Array<number>;
  requested_position_count: number;
  calendar_start?: string | null;
  calendar_end_exclusive?: string | null;
}

export interface SeriesContext {
  market_id: number;
  item_key: string;
  source_id: string;
  source_type: "auctionator" | "simulated";
  temporal_basis: string;
  series_mode: "accumulated" | "export";
  export_id?: number | null;
  market_key: string;
  ruleset: "PvE" | "PvP" | "HC" | "RP";
  region: string;
  dataset: "real" | "simulated";
  external_item_id: string;
  key_kind: "item" | "gear_level" | "gear_suffix" | "pet";
  source_version?: "340";
  database_version?: 8;
  value_semantics: "accumulated_extreme" | "export_projection";
}

export interface SeriesDescriptor {
  context: SeriesContext;
  item_first_day: number | null;
  item_last_day: number | null;
  market_first_day: number | null;
  market_last_day: number | null;
  excluded_undated_count: number;
  availability_field_presence: "present" | "absent" | "unknown";
  first_received_at?: string | null;
}

export interface SeriesDiscoveryResponse {
  series: Array<SeriesDescriptor>;
  limit: number;
  offset: number;
  has_more: boolean;
  ordering?: "mode_source_basis_export_id; not observation chronology";
}

export interface SignalEvidence {
  status: "sufficient" | "insufficient";
  reasons: Array<EvidenceReason>;
  usable_observation_count: number;
  historical_observation_count: number;
  requested_price_ratio: MetricValue;
  index_span_price_ratio: MetricValue;
  latest_price_lag?: number | null;
  minimum_l_count: number;
  minimum_h_fallback_count: number;
  minimum_unknown_origin_count: number;
}

export interface SignalParameters {
  min_history_observations?: number;
  min_trend_observations?: number;
  min_price_coverage?: string;
  min_index_coverage?: string;
  deviation_threshold_pct?: string;
  trend_threshold_pct?: string;
  min_trend_slope_copper_per_scan_index?: string;
  max_latest_price_lag?: number;
  require_native_l?: boolean;
  require_known_temporal_basis?: boolean;
}

export interface WindowSpec {
  window_type: "observed_buckets" | "index_range" | "calendar_days";
  size?: number | null;
  start_day?: number | null;
  end_day?: number | null;
  days?: 7 | 14 | 30 | null;
}
