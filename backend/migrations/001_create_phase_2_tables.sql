CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realms (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_realms_unique_name_region
ON realms (name, COALESCE(region, ''));

CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    external_item_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    quality TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_items_quality CHECK (
        quality IN (
            'poor',
            'common',
            'uncommon',
            'rare',
            'epic',
            'legendary',
            'artifact',
            'heirloom',
            'unknown'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_items_name ON items (name);
CREATE INDEX IF NOT EXISTS idx_items_quality ON items (quality);

CREATE TABLE IF NOT EXISTS auction_snapshots (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id),
    source_type TEXT NOT NULL,
    source_version TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_hash TEXT NOT NULL UNIQUE,
    raw_reference TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_auction_snapshots_identity UNIQUE (realm_id, source_type, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_auction_snapshots_realm_captured
ON auction_snapshots (realm_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_auction_snapshots_source
ON auction_snapshots (source_type, source_version);

CREATE TABLE IF NOT EXISTS auction_snapshot_items (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES auction_snapshots(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES items(id),
    min_buyout INTEGER NOT NULL,
    avg_buyout INTEGER NOT NULL,
    max_buyout INTEGER NOT NULL,
    quantity_total INTEGER NOT NULL,
    auction_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_auction_snapshot_items_snapshot_item UNIQUE (snapshot_id, item_id),
    CONSTRAINT chk_snapshot_items_min_buyout CHECK (min_buyout >= 0),
    CONSTRAINT chk_snapshot_items_avg_buyout CHECK (avg_buyout >= 0),
    CONSTRAINT chk_snapshot_items_max_buyout CHECK (max_buyout >= 0),
    CONSTRAINT chk_snapshot_items_quantity_total CHECK (quantity_total >= 0),
    CONSTRAINT chk_snapshot_items_auction_count CHECK (auction_count >= 0),
    CONSTRAINT chk_snapshot_items_price_order CHECK (
        min_buyout <= avg_buyout AND avg_buyout <= max_buyout
    )
);

CREATE INDEX IF NOT EXISTS idx_snapshot_items_item
ON auction_snapshot_items (item_id);

CREATE INDEX IF NOT EXISTS idx_snapshot_items_snapshot
ON auction_snapshot_items (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_snapshot_items_item_snapshot
ON auction_snapshot_items (item_id, snapshot_id);

CREATE TABLE IF NOT EXISTS import_runs (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_version TEXT NULL,
    raw_reference TEXT NULL,
    source_hash TEXT NULL,
    status TEXT NOT NULL,
    snapshot_id BIGINT NULL REFERENCES auction_snapshots(id),
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_imported INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    CONSTRAINT chk_import_runs_status CHECK (
        status IN ('started', 'completed', 'duplicate', 'failed')
    ),
    CONSTRAINT chk_import_runs_items_seen CHECK (items_seen >= 0),
    CONSTRAINT chk_import_runs_items_imported CHECK (items_imported >= 0)
);

CREATE INDEX IF NOT EXISTS idx_import_runs_started_at
ON import_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_import_runs_status
ON import_runs (status);
