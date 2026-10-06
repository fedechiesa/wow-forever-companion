UPDATE realms
SET region = NULLIF(regexp_replace(region, '^[[:space:]]+|[[:space:]]+$', '', 'g'), '')
WHERE region IS NOT NULL;

ALTER TABLE realms ADD CONSTRAINT chk_realms_normalized_region CHECK (
    region IS NULL OR (
        region <> ''
        AND region = regexp_replace(region, '^[[:space:]]+|[[:space:]]+$', '', 'g')
    )
);
