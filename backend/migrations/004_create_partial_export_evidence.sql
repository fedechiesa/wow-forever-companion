-- Additive only. No legacy rows can reconstruct previously unrecorded exports.
CREATE TABLE partial_exports (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('auctionator', 'simulated')),
    source_id TEXT NOT NULL CHECK (source_id <> '' AND source_id = btrim(source_id)),
    source_version TEXT NOT NULL CHECK (source_version = '340'),
    database_version INTEGER NOT NULL CHECK (database_version = 8),
    dataset TEXT NOT NULL CHECK (dataset IN ('real', 'simulated')),
    region TEXT NOT NULL CHECK (region <> '' AND region = btrim(region)),
    temporal_basis TEXT NOT NULL,
    canonical_version INTEGER NOT NULL CHECK (canonical_version = 1),
    state_hash TEXT NOT NULL CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    structure_manifest JSONB NOT NULL CHECK (jsonb_typeof(structure_manifest) = 'object'),
    native_fact_count INTEGER NOT NULL CHECK (native_fact_count BETWEEN 1 AND 200000),
    first_import_id BIGINT NOT NULL REFERENCES partial_import_runs(id),
    sealed BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK ((source_type = 'simulated') = (dataset = 'simulated')),
    UNIQUE (canonical_version, state_hash)
);

CREATE TABLE partial_export_facts (
    id BIGSERIAL PRIMARY KEY,
    export_id BIGINT NOT NULL REFERENCES partial_exports(id),
    market_id BIGINT NOT NULL REFERENCES partial_markets(id),
    item_id BIGINT NOT NULL REFERENCES partial_items(id),
    -- Identity snapshots make evidence independent of later catalog edits.
    market_key TEXT NOT NULL,
    ruleset TEXT NOT NULL CHECK (ruleset IN ('PvE', 'PvP', 'HC', 'RP')),
    item_key TEXT NOT NULL,
    external_item_id TEXT NOT NULL CHECK (external_item_id ~ '^[1-9][0-9]{0,9}$'),
    key_kind TEXT NOT NULL CHECK (key_kind IN ('item', 'gear_level', 'gear_suffix', 'pet')),
    original_item_key TEXT NOT NULL,
    native_field TEXT NOT NULL CHECK (native_field IN ('l', 'h', 'a', 'm')),
    scan_day INTEGER CHECK (scan_day >= 0),
    original_day_key TEXT CHECK (original_day_key ~ '^[0-9]{1,10}$'),
    value INTEGER NOT NULL CHECK (value >= 0),
    CHECK (market_key NOT IN ('PvE', 'PvP', 'HC', 'RP') OR market_key = ruleset),
    CHECK ((native_field = 'm') = (scan_day IS NULL)),
    CHECK ((scan_day IS NULL) = (original_day_key IS NULL)),
    CHECK (scan_day IS NULL OR original_day_key::BIGINT = scan_day)
);
CREATE UNIQUE INDEX partial_export_fact_identity ON partial_export_facts
    (export_id, market_id, item_id, COALESCE(scan_day, -1), native_field);
CREATE INDEX partial_export_fact_history ON partial_export_facts
    (export_id, market_id, item_id, scan_day);

CREATE TABLE partial_export_imports (
    import_id BIGINT PRIMARY KEY REFERENCES partial_import_runs(id),
    export_id BIGINT NOT NULL REFERENCES partial_exports(id),
    input_format TEXT NOT NULL CHECK (input_format IN ('lua_tables', 'libcbor', 'mixed')),
    decoder_version TEXT NOT NULL CHECK (decoder_version = 'auctionator340-v1')
);
CREATE INDEX partial_export_import_export ON partial_export_imports(export_id, import_id);

-- Indispensable guards: CHECK/FK cannot prevent UPDATE/DELETE or insertion into
-- an already sealed parent. Transactions alone do not protect manual SQL.
CREATE FUNCTION partial_guard_export() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.sealed THEN
            RAISE EXCEPTION 'export must be constructed before sealing' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP <> 'UPDATE' THEN
        RAISE EXCEPTION 'export evidence cannot be deleted or truncated' USING ERRCODE = '23514';
    END IF;
    IF OLD.sealed OR NOT NEW.sealed OR
       (to_jsonb(NEW) - 'sealed') IS DISTINCT FROM (to_jsonb(OLD) - 'sealed') THEN
        RAISE EXCEPTION 'only sealing an unchanged export is allowed' USING ERRCODE = '23514';
    END IF;
    IF (SELECT count(*) FROM partial_export_facts WHERE export_id = NEW.id) <> NEW.native_fact_count THEN
        RAISE EXCEPTION 'export native fact count mismatch' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM partial_export_facts f
        LEFT JOIN partial_export_facts h ON h.export_id=f.export_id
          AND h.market_id=f.market_id AND h.item_id=f.item_id
          AND h.scan_day=f.scan_day AND h.native_field='h'
        WHERE f.export_id=NEW.id AND f.native_field IN ('l','a')
          AND (h.id IS NULL OR f.original_day_key <> h.original_day_key
               OR (f.native_field='l' AND f.value > h.value))
    ) THEN
        RAISE EXCEPTION 'incoherent native l/h/a evidence' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_export_guard BEFORE INSERT OR UPDATE OR DELETE ON partial_exports
    FOR EACH ROW EXECUTE FUNCTION partial_guard_export();
CREATE TRIGGER partial_export_truncate_guard BEFORE TRUNCATE ON partial_exports
    FOR EACH STATEMENT EXECUTE FUNCTION partial_guard_export();

CREATE FUNCTION partial_guard_export_child() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    parent partial_exports%ROWTYPE;
    run partial_import_runs%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'export facts and import links are append-only' USING ERRCODE = '23514';
    END IF;
    SELECT * INTO parent FROM partial_exports WHERE id=NEW.export_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'export parent not found' USING ERRCODE = '23503';
    END IF;
    IF TG_TABLE_NAME = 'partial_export_facts' THEN
        IF parent.sealed THEN
            RAISE EXCEPTION 'cannot append facts to sealed export' USING ERRCODE = '23514';
        END IF;
    ELSE
        IF NOT parent.sealed THEN
            RAISE EXCEPTION 'import link requires sealed export' USING ERRCODE = '23514';
        END IF;
        SELECT * INTO run FROM partial_import_runs WHERE id=NEW.import_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'import run not found' USING ERRCODE = '23503';
        END IF;
        IF run.status='failed' OR
           ROW(run.source_type,run.source_id,run.source_version,run.database_version,
               run.dataset,run.region,run.temporal_basis) IS DISTINCT FROM
           ROW(parent.source_type,parent.source_id,parent.source_version,parent.database_version,
               parent.dataset,parent.region,parent.temporal_basis) THEN
            RAISE EXCEPTION 'import/export context mismatch' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_export_fact_guard BEFORE INSERT OR UPDATE OR DELETE ON partial_export_facts
    FOR EACH ROW EXECUTE FUNCTION partial_guard_export_child();
CREATE TRIGGER partial_export_fact_truncate_guard BEFORE TRUNCATE ON partial_export_facts
    FOR EACH STATEMENT EXECUTE FUNCTION partial_guard_export_child();
CREATE TRIGGER partial_export_import_guard BEFORE INSERT OR UPDATE OR DELETE ON partial_export_imports
    FOR EACH ROW EXECUTE FUNCTION partial_guard_export_child();
CREATE TRIGGER partial_export_import_truncate_guard BEFORE TRUNCATE ON partial_export_imports
    FOR EACH STATEMENT EXECUTE FUNCTION partial_guard_export_child();

-- One deferred check per new header, not a trigger per fact at commit.
CREATE FUNCTION partial_require_sealed_export() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM partial_exports e JOIN partial_export_imports link
          ON link.export_id=e.id AND link.import_id=e.first_import_id
        WHERE e.id=NEW.id AND e.sealed
    ) THEN
        RAISE EXCEPTION 'export must be sealed and linked before commit' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER partial_export_requires_seal AFTER INSERT ON partial_exports
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION partial_require_sealed_export();
