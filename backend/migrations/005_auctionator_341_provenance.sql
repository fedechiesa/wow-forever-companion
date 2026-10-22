-- Metadata-only extension. No row rewrites, backfill, new tables or sequences.
-- Run only against an explicitly verified destination; never auto-migrate at import.
ALTER TABLE partial_markets DROP CONSTRAINT partial_markets_dataset_check;
ALTER TABLE partial_markets ADD CONSTRAINT partial_markets_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test')) NOT VALID;
ALTER TABLE partial_markets VALIDATE CONSTRAINT partial_markets_dataset_check;

ALTER TABLE partial_import_runs DROP CONSTRAINT partial_import_runs_source_version_check;
ALTER TABLE partial_import_runs ADD CONSTRAINT partial_import_runs_source_version_check
    CHECK (source_version IN ('340','341')) NOT VALID;
ALTER TABLE partial_import_runs VALIDATE CONSTRAINT partial_import_runs_source_version_check;
ALTER TABLE partial_import_runs DROP CONSTRAINT partial_import_runs_dataset_check;
ALTER TABLE partial_import_runs ADD CONSTRAINT partial_import_runs_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test') AND (dataset <> 'stress_test' OR source_version='341')) NOT VALID;
ALTER TABLE partial_import_runs VALIDATE CONSTRAINT partial_import_runs_dataset_check;

ALTER TABLE partial_exports DROP CONSTRAINT partial_exports_source_version_check;
ALTER TABLE partial_exports ADD CONSTRAINT partial_exports_source_version_check
    CHECK (source_version IN ('340','341')) NOT VALID;
ALTER TABLE partial_exports VALIDATE CONSTRAINT partial_exports_source_version_check;
ALTER TABLE partial_exports DROP CONSTRAINT partial_exports_dataset_check;
ALTER TABLE partial_exports ADD CONSTRAINT partial_exports_dataset_check
    CHECK (dataset IN ('real','simulated','stress_test') AND (dataset <> 'stress_test' OR source_version='341')) NOT VALID;
ALTER TABLE partial_exports VALIDATE CONSTRAINT partial_exports_dataset_check;

ALTER TABLE partial_export_imports DROP CONSTRAINT partial_export_imports_input_format_check;
ALTER TABLE partial_export_imports ADD CONSTRAINT partial_export_imports_input_format_check
    CHECK (input_format IN ('lua_tables','libcbor','mixed','cbor_definite')) NOT VALID;
ALTER TABLE partial_export_imports VALIDATE CONSTRAINT partial_export_imports_input_format_check;
ALTER TABLE partial_export_imports DROP CONSTRAINT partial_export_imports_decoder_version_check;
ALTER TABLE partial_export_imports ADD CONSTRAINT partial_export_imports_decoder_version_check
    CHECK (decoder_version IN ('auctionator340-v1','auctionator-v8-v2')) NOT VALID;
ALTER TABLE partial_export_imports VALIDATE CONSTRAINT partial_export_imports_decoder_version_check;

-- Attestations live in the existing immutable manifest. Raw byte hashes remain
-- on receipts, preserving canonical reuse for equivalent input serializations.
CREATE FUNCTION partial_valid_capture_provenance(m JSONB, v TEXT, s TEXT, r TEXT, d TEXT)
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
             OR (d='real' AND m->'provenance'->>'capture_phase' IN ('launch','other')))
        AND m->'provenance'->'market_rulesets' = (
            SELECT jsonb_object_agg(x->>'market_key', x->>'ruleset')
            FROM jsonb_array_elements(m->'markets') x
        ), FALSE);
$$;

ALTER TABLE partial_exports ADD CONSTRAINT partial_exports_341_provenance_check
    CHECK (source_version='340' OR partial_valid_capture_provenance(
        structure_manifest,source_version,source_id,region,dataset)) NOT VALID;
ALTER TABLE partial_exports VALIDATE CONSTRAINT partial_exports_341_provenance_check;

-- Additional guard; all 004 immutability, sealing, context and deferred checks remain.
CREATE FUNCTION partial_guard_capture_transport() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE parent partial_exports%ROWTYPE;
BEGIN
    SELECT * INTO parent FROM partial_exports WHERE id=NEW.export_id;
    IF parent.source_version='341' OR NEW.decoder_version='auctionator-v8-v2' OR NEW.input_format='cbor_definite' THEN
        IF NEW.decoder_version <> 'auctionator-v8-v2' OR NOT partial_valid_capture_provenance(
            parent.structure_manifest,parent.source_version,parent.source_id,parent.region,parent.dataset) THEN
            RAISE EXCEPTION 'verified capture metadata and v8 decoder required' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER partial_capture_transport_guard BEFORE INSERT ON partial_export_imports
    FOR EACH ROW EXECUTE FUNCTION partial_guard_capture_transport();
