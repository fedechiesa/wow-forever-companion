-- Additive metadata/identity extension. No monetary widening, legacy backfill,
-- evidence rewrite or interpretation of existing region/realm/source labels.
ALTER TABLE partial_markets ADD COLUMN economic_identity JSONB;

CREATE FUNCTION partial_valid_economic_identity(i JSONB, d TEXT, r TEXT)
RETURNS BOOLEAN LANGUAGE SQL IMMUTABLE AS $$
    SELECT COALESCE(jsonb_typeof(i)='object'
        AND i - ARRAY['version','dataset','region','economy','auction_house_scope','faction']::text[] = '{}'::jsonb
        AND i->'version'='1'::jsonb AND i->>'dataset'=d AND i->>'region'=r
        AND d IN ('simulated','stress_test','launch')
        AND jsonb_typeof(i->'economy')='string' AND length(i->>'economy') BETWEEN 1 AND 100
        AND i->>'economy'=btrim(i->>'economy') AND i->>'economy' !~ '[[:cntrl:]]'
        AND ((i->>'auction_house_scope'='shared' AND i->'faction'='null'::jsonb)
             OR (i->>'auction_house_scope'='faction' AND jsonb_typeof(i->'faction')='string'
                 AND length(i->>'faction') BETWEEN 1 AND 100
                 AND i->>'faction'=btrim(i->>'faction') AND i->>'faction' !~ '[[:cntrl:]]')), FALSE);
$$;
ALTER TABLE partial_markets ADD CONSTRAINT partial_market_economic_identity_check
    CHECK (economic_identity IS NULL OR partial_valid_economic_identity(economic_identity,dataset,region));
ALTER TABLE partial_markets DROP CONSTRAINT partial_markets_region_market_key_dataset_key;
CREATE UNIQUE INDEX partial_legacy_market_identity ON partial_markets(region,market_key,dataset)
    WHERE economic_identity IS NULL;
-- Full JSONB equality, not a truncated digest. Observer/native label are absent.
CREATE UNIQUE INDEX partial_verified_market_identity ON partial_markets(economic_identity)
    WHERE economic_identity IS NOT NULL;

ALTER TABLE partial_markets DROP CONSTRAINT partial_markets_dataset_check;
ALTER TABLE partial_markets ADD CONSTRAINT partial_markets_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test','launch')) NOT VALID;
ALTER TABLE partial_markets VALIDATE CONSTRAINT partial_markets_dataset_check;
ALTER TABLE partial_markets ADD CONSTRAINT partial_launch_market_identity_check
    CHECK (dataset <> 'launch' OR economic_identity IS NOT NULL);

ALTER TABLE partial_import_runs DROP CONSTRAINT partial_import_runs_dataset_check;
ALTER TABLE partial_import_runs ADD CONSTRAINT partial_import_runs_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test','launch')
           AND (dataset NOT IN ('stress_test','launch') OR source_version='341')) NOT VALID;
ALTER TABLE partial_import_runs VALIDATE CONSTRAINT partial_import_runs_dataset_check;
ALTER TABLE partial_exports DROP CONSTRAINT partial_exports_dataset_check;
ALTER TABLE partial_exports ADD CONSTRAINT partial_exports_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test','launch')
           AND (dataset NOT IN ('stress_test','launch') OR source_version='341')) NOT VALID;
ALTER TABLE partial_exports VALIDATE CONSTRAINT partial_exports_dataset_check;
ALTER TABLE partial_exports DROP CONSTRAINT partial_exports_canonical_version_check;
ALTER TABLE partial_exports ADD CONSTRAINT partial_exports_canonical_version_check
    CHECK (canonical_version IN (1,2)) NOT VALID;
ALTER TABLE partial_exports VALIDATE CONSTRAINT partial_exports_canonical_version_check;
ALTER TABLE partial_exports ADD CONSTRAINT partial_local_export_manifest_check CHECK (
    (canonical_version=1 AND dataset <> 'launch') OR
    (canonical_version=2 AND source_version='341' AND temporal_basis='unknown'
     AND COALESCE(jsonb_typeof(structure_manifest->'market_identities')='object', FALSE)));

-- Extend only the lifecycle alternatives of the existing 005 predicate.
CREATE OR REPLACE FUNCTION partial_valid_capture_provenance(m JSONB, v TEXT, s TEXT, r TEXT, d TEXT)
RETURNS BOOLEAN LANGUAGE SQL IMMUTABLE AS $$
    SELECT COALESCE(
        jsonb_typeof(m->'provenance')='object'
        AND m->'provenance'->>'version'='1'
        AND m->'provenance'->>'format_version'=v
        AND m->'provenance'->>'source_id'=s
        AND m->'provenance'->>'region'=r
        AND m->'provenance'->>'dataset'=d
        AND length(btrim(m->'provenance'->>'region_evidence_ref')) > 0
        AND length(btrim(m->'provenance'->>'market_evidence_ref')) > 0
        AND length(btrim(m->'provenance'->>'origin_evidence_ref')) > 0
        AND ((d='stress_test' AND m->'provenance'->>'capture_phase'='stress_test')
             OR (d='simulated' AND m->'provenance'->>'capture_phase'='simulated')
             OR (d='launch' AND m->'provenance'->>'capture_phase'='launch')
             OR (d='real' AND m->'provenance'->>'capture_phase' IN ('launch','other')))
        AND m->'provenance'->'market_rulesets' = (
            SELECT jsonb_object_agg(x->>'market_key', x->>'ruleset')
            FROM jsonb_array_elements(m->'markets') x
        ), FALSE);
$$;

CREATE TABLE partial_capture_receipts (
    import_id BIGINT PRIMARY KEY REFERENCES partial_import_runs(id),
    export_id BIGINT NOT NULL REFERENCES partial_exports(id),
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    market_sha256 TEXT NOT NULL CHECK (market_sha256 ~ '^[0-9a-f]{64}$'),
    acquired_at TIMESTAMPTZ NOT NULL,
    archive_metadata JSONB NOT NULL CHECK (jsonb_typeof(archive_metadata)='object'),
    capture_context JSONB NOT NULL CHECK (jsonb_typeof(capture_context)='object')
);
CREATE INDEX partial_capture_receipt_file ON partial_capture_receipts(source_sha256,import_id);
CREATE INDEX partial_capture_receipt_export ON partial_capture_receipts(export_id,import_id);

CREATE FUNCTION partial_guard_capture_receipt() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE parent partial_exports%ROWTYPE; run partial_import_runs%ROWTYPE; p JSONB; identities JSONB;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'local capture receipts are append-only' USING ERRCODE='23514';
    END IF;
    SELECT * INTO parent FROM partial_exports WHERE id=NEW.export_id FOR UPDATE;
    -- Serialize receipt validation with any concurrent change of its run.
    SELECT * INTO run FROM partial_import_runs WHERE id=NEW.import_id FOR UPDATE;
    p := NEW.capture_context->'provenance';
    SELECT jsonb_object_agg(key,jsonb_build_object(
        'version',1,'dataset',run.dataset,'region',run.region,'economy',value->'economy'->>'value',
        'auction_house_scope',value->>'auction_house_scope','faction',value->'faction'->>'value'))
        INTO identities FROM jsonb_each(NEW.capture_context->'market_identities');
    IF NOT COALESCE(parent.sealed AND parent.canonical_version=2 AND run.status <> 'failed'
        AND ROW(run.source_type,run.source_version,run.database_version,run.dataset,run.region,run.temporal_basis)
            IS NOT DISTINCT FROM
            ROW(parent.source_type,parent.source_version,parent.database_version,parent.dataset,parent.region,parent.temporal_basis)
        AND NEW.source_sha256=run.source_hash
        AND NEW.archive_metadata->>'source_sha256'=NEW.source_sha256
        AND NEW.archive_metadata->>'capture_id'=NEW.source_sha256
        AND NEW.archive_metadata->>'market_sha256'=NEW.market_sha256
        AND NEW.archive_metadata->>'captured_at' ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
        AND (NEW.archive_metadata->>'captured_at')::timestamptz=NEW.acquired_at
        AND NEW.archive_metadata->'native_scan_timestamp'='null'::jsonb
        AND NEW.capture_context->'serialized_codec'=NEW.archive_metadata->'selected_serialized_codec'
        AND NEW.capture_context->>'contract'='verified-local-capture-v1'
        AND p->>'source_sha256'=run.source_hash AND p->>'source_id'=run.source_id
        AND partial_valid_capture_provenance(
            jsonb_build_object('provenance',p,'markets',parent.structure_manifest->'markets'),
            run.source_version,run.source_id,run.region,run.dataset)
        AND identities=parent.structure_manifest->'market_identities', FALSE) THEN
        RAISE EXCEPTION 'local capture receipt identity/context mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_capture_receipt_guard BEFORE INSERT OR UPDATE OR DELETE ON partial_capture_receipts
    FOR EACH ROW EXECUTE FUNCTION partial_guard_capture_receipt();
CREATE TRIGGER partial_capture_receipt_truncate_guard BEFORE TRUNCATE ON partial_capture_receipts
    FOR EACH STATEMENT EXECUTE FUNCTION partial_guard_capture_receipt();

CREATE FUNCTION partial_require_capture_link() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM partial_export_imports l
                   WHERE l.import_id=NEW.import_id AND l.export_id=NEW.export_id) THEN
        RAISE EXCEPTION 'local receipt requires matching export reception' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER partial_capture_requires_link AFTER INSERT ON partial_capture_receipts
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION partial_require_capture_link();

-- Preserve every 004 child protection. Only v2 reception source_id may differ
-- from the first observer: its own immutable receipt must already validate it.
CREATE OR REPLACE FUNCTION partial_guard_export_child() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE parent partial_exports%ROWTYPE; run partial_import_runs%ROWTYPE; identity JSONB;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'export facts and import links are append-only' USING ERRCODE='23514';
    END IF;
    SELECT * INTO parent FROM partial_exports WHERE id=NEW.export_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'export parent not found' USING ERRCODE='23503';
    END IF;
    IF TG_TABLE_NAME='partial_export_facts' THEN
        IF parent.sealed THEN
            RAISE EXCEPTION 'cannot append facts to sealed export' USING ERRCODE='23514';
        END IF;
        IF parent.canonical_version=2 THEN
            SELECT economic_identity INTO identity FROM partial_markets WHERE id=NEW.market_id;
            IF identity IS NULL OR identity IS DISTINCT FROM parent.structure_manifest->'market_identities'->NEW.market_key THEN
                RAISE EXCEPTION 'native fact market disagrees with verified economy' USING ERRCODE='23514';
            END IF;
        END IF;
    ELSE
        IF NOT parent.sealed THEN
            RAISE EXCEPTION 'import link requires sealed export' USING ERRCODE='23514';
        END IF;
        SELECT * INTO run FROM partial_import_runs WHERE id=NEW.import_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'import run not found' USING ERRCODE='23503';
        END IF;
        IF parent.canonical_version=1 THEN
            IF run.status='failed' OR
               ROW(run.source_type,run.source_id,run.source_version,run.database_version,run.dataset,run.region,run.temporal_basis)
                 IS DISTINCT FROM
               ROW(parent.source_type,parent.source_id,parent.source_version,parent.database_version,parent.dataset,parent.region,parent.temporal_basis) THEN
                RAISE EXCEPTION 'import/export context mismatch' USING ERRCODE='23514';
            END IF;
        ELSIF run.status='failed' OR NOT EXISTS (
            SELECT 1 FROM partial_capture_receipts r WHERE r.import_id=NEW.import_id AND r.export_id=NEW.export_id
              AND r.archive_metadata->>'input_format'=NEW.input_format
              AND NEW.decoder_version='auctionator-v8-v2'
        ) THEN
            RAISE EXCEPTION 'verified local receipt required for shared export reception' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION partial_guard_verified_market() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.economic_identity IS NOT NULL OR
       (TG_OP='UPDATE' AND NEW.economic_identity IS NOT NULL) THEN
        RAISE EXCEPTION 'verified market identity is immutable; legacy identity cannot be reinterpreted'
            USING ERRCODE='23514';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_verified_market_guard BEFORE UPDATE OR DELETE ON partial_markets
    FOR EACH ROW EXECUTE FUNCTION partial_guard_verified_market();

-- An immutable receipt must not acquire different provenance through a mutable
-- parent run. Keep the service's completed/duplicate finalization (zero 003
-- changes) while freezing identity, hashes, timestamps and counters. Legacy
-- runs without a local receipt keep their existing behavior.
CREATE FUNCTION partial_guard_capture_run() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM partial_capture_receipts WHERE import_id=OLD.id) THEN
        IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'local capture run lineage is immutable' USING ERRCODE='23514';
        END IF;
        IF (to_jsonb(NEW) - ARRAY['status','observations_changed']::text[]) IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['status','observations_changed']::text[])
           OR NEW.status NOT IN ('completed','duplicate') OR NEW.observations_changed <> 0 THEN
            RAISE EXCEPTION 'local capture run lineage is immutable' USING ERRCODE='23514';
        END IF;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_capture_run_guard BEFORE UPDATE OR DELETE ON partial_import_runs
    FOR EACH ROW EXECUTE FUNCTION partial_guard_capture_run();
