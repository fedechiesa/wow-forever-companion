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

export interface EvidenceReason {
  code: "insufficient_observations" | "insufficient_history" | "insufficient_price_coverage" | "insufficient_index_coverage" | "latest_price_missing_or_stale" | "native_l_required" | "known_temporal_basis_required" | "zero_reference" | "zero_baseline" | "unavailable_trend";
  message: string;
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
