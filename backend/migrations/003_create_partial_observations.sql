-- Additive Phase 2.5 schema; full snapshots and their catalog stay untouched.
CREATE TABLE partial_markets (
    id BIGSERIAL PRIMARY KEY,
    market_key TEXT NOT NULL CHECK (market_key <> '' AND market_key = btrim(market_key)),
    ruleset TEXT NOT NULL CHECK (ruleset IN ('PvE', 'PvP', 'HC', 'RP')),
    region TEXT NOT NULL CHECK (region <> '' AND region = btrim(region)),
    dataset TEXT NOT NULL CHECK (dataset IN ('real', 'simulated')),
    UNIQUE(region, market_key, dataset)
);

CREATE TABLE partial_items (
    id BIGSERIAL PRIMARY KEY,
    item_key TEXT NOT NULL UNIQUE,
    external_item_id TEXT NOT NULL CHECK (external_item_id ~ '^[1-9][0-9]{0,9}$'),
    key_kind TEXT NOT NULL CHECK (key_kind IN ('item', 'gear_level', 'gear_suffix', 'pet'))
    -- No name or quality is manufactured from a price database.
);

CREATE TABLE partial_import_runs (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('auctionator', 'simulated')),
    source_id TEXT NOT NULL,
    source_version TEXT NOT NULL CHECK (source_version = '340'),
    database_version INTEGER NOT NULL CHECK (database_version = 8),
    dataset TEXT NOT NULL CHECK (dataset IN ('real', 'simulated')),
    region TEXT NOT NULL,
    temporal_basis TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
    raw_reference TEXT,
    status TEXT NOT NULL CHECK (status IN ('completed', 'duplicate', 'failed')),
    observations_seen INTEGER NOT NULL CHECK (observations_seen > 0),
    observations_changed INTEGER NOT NULL CHECK (observations_changed >= 0),
    error_message TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((source_type = 'simulated') = (dataset = 'simulated'))
);

CREATE TABLE partial_observations (
    id BIGSERIAL PRIMARY KEY,
    market_id BIGINT NOT NULL REFERENCES partial_markets(id),
    item_id BIGINT NOT NULL REFERENCES partial_items(id),
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('auctionator', 'simulated')),
    temporal_basis TEXT NOT NULL,
    scan_day INTEGER CHECK (scan_day >= 0),
    statistic TEXT NOT NULL CHECK (statistic IN (
        'daily_minimum', 'daily_highest_minimum', 'daily_max_available', 'last_minimum'
    )),
    value INTEGER NOT NULL CHECK (value >= 0),
    evidence_key TEXT NOT NULL,
    first_import_id BIGINT NOT NULL REFERENCES partial_import_runs(id),
    last_import_id BIGINT NOT NULL REFERENCES partial_import_runs(id),
    CHECK ((statistic = 'last_minimum') = (scan_day IS NULL)),
    CHECK ((statistic = 'last_minimum' AND evidence_key ~ '^[0-9a-f]{64}$')
        OR (statistic <> 'last_minimum' AND evidence_key = 'daily'))
);
CREATE UNIQUE INDEX partial_observation_identity ON partial_observations
    (market_id, item_id, source_id, source_type, temporal_basis,
     COALESCE(scan_day, -1), statistic, evidence_key);
CREATE INDEX partial_history ON partial_observations(market_id, item_id, scan_day);
CREATE INDEX partial_imports_time ON partial_import_runs(imported_at DESC, id DESC);
