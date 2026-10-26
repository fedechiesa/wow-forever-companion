"""Read-only native v2 evidence, independent of 003 and Market Intelligence.

States are selected explicitly. Receipt order describes database reception only;
facts never join receipts, and no state is advertised as the latest scan.
"""
from contextlib import contextmanager


class EvidenceSchemaUnavailable(ValueError):
    pass


def _integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("invalid evidence selector or pagination")
    return value


def _id(value):
    return _integer(value, 1, 2**63 - 1)


def _page(limit, offset):
    return _integer(limit, 1, 1000), _integer(offset, 0, 2**31 - 1)


class LocalEvidenceReader:
    def __init__(self, connection_factory):
        self._connect = connection_factory

    @contextmanager
    def _snapshot(self):
        with self._connect() as connection:
            connection.read_only = True
            with connection.transaction():
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                ready = connection.execute(
                    "SELECT 1 FROM public.schema_migrations WHERE id='006_verified_local_lineage.sql'"
                ).fetchone()
                if not ready:
                    raise EvidenceSchemaUnavailable("verified local lineage schema 006 required")
                yield connection

    @staticmethod
    def _market(c, market_id):
        row = c.execute("SELECT id FROM public.partial_markets WHERE id=%s AND economic_identity IS NOT NULL",
                        (_id(market_id),)).fetchone()
        if row is None:
            raise ValueError("verified economic market not found")

    @staticmethod
    def _state(c, export_id):
        row = c.execute("""SELECT id,canonical_version,state_hash,source_version,database_version,
            dataset,region,temporal_basis,source_id AS first_observer_source_id,
            structure_manifest,native_fact_count,first_import_id
            FROM public.partial_exports WHERE id=%s AND canonical_version=2 AND sealed""",
                        (_id(export_id),)).fetchone()
        if row is None:
            raise ValueError("sealed v2 state not found")
        return row

    @staticmethod
    def _membership(c, export_id, market_id):
        LocalEvidenceReader._market(c, market_id)
        if c.execute("""SELECT 1 FROM public.partial_exports e
            JOIN public.partial_markets m ON m.id=%s
            WHERE e.id=%s AND EXISTS (SELECT 1 FROM jsonb_each(e.structure_manifest->'market_identities') i
                                     WHERE i.value=m.economic_identity)""",
                     (market_id, export_id)).fetchone() is None:
            raise ValueError("state does not contain selected economic market")

    def markets(self, *, limit=100, offset=0):
        page = _page(limit, offset)
        with self._snapshot() as c:
            return c.execute("""SELECT id,market_key AS first_native_label,ruleset,region,dataset,economic_identity
                FROM public.partial_markets WHERE economic_identity IS NOT NULL
                ORDER BY id LIMIT %s OFFSET %s""", page).fetchall()

    def states(self, market_id, *, limit=100, offset=0):
        _id(market_id)
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._market(c, market_id)
            # Manifest membership also discovers states of completely empty
            # markets, which have no fact rows to join against.
            return c.execute("""SELECT e.id,e.state_hash,e.canonical_version,e.source_version,e.dataset,e.region,
                e.temporal_basis,e.native_fact_count,
                (SELECT count(*) FROM public.partial_capture_receipts r WHERE r.export_id=e.id) AS receipt_count
                FROM public.partial_exports e JOIN public.partial_markets m ON m.id=%s
                WHERE e.canonical_version=2 AND e.sealed
                  AND EXISTS (SELECT 1 FROM jsonb_each(e.structure_manifest->'market_identities') i
                              WHERE i.value=m.economic_identity)
                ORDER BY e.id LIMIT %s OFFSET %s""", (market_id, *page)).fetchall()

    def state(self, export_id):
        _id(export_id)
        with self._snapshot() as c:
            return self._state(c, export_id)

    def facts(self, export_id, market_id, *, limit=1000, offset=0):
        _id(export_id)
        _id(market_id)
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._state(c, export_id)
            self._membership(c, export_id, market_id)
            return c.execute("""SELECT market_id,market_key,ruleset,item_key,external_item_id,key_kind,
                original_item_key,native_field,scan_day,original_day_key,value
                FROM public.partial_export_facts WHERE export_id=%s AND market_id=%s
                ORDER BY item_key COLLATE "C",scan_day NULLS LAST,native_field
                LIMIT %s OFFSET %s""", (export_id, market_id, *page)).fetchall()

    def receipts(self, export_id, *, limit=100, offset=0):
        _id(export_id)
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._state(c, export_id)
            return c.execute("""SELECT r.import_id,r.export_id,r.source_sha256,r.market_sha256,
                r.acquired_at,i.imported_at AS received_at,i.source_id AS observer_source_id,i.status,
                r.archive_metadata,r.capture_context,l.input_format,l.decoder_version
                FROM public.partial_capture_receipts r
                JOIN public.partial_import_runs i ON i.id=r.import_id
                JOIN public.partial_export_imports l ON l.import_id=r.import_id AND l.export_id=r.export_id
                WHERE r.export_id=%s ORDER BY r.import_id LIMIT %s OFFSET %s""",
                             (export_id, *page)).fetchall()

    # Web projections deliberately select an allowlist. The private CLI methods
    # above keep their complete lineage contract. Every page uses the same
    # read-only snapshot/006 guard, with no joins multiplying facts by receipts.
    @staticmethod
    def _web_market(c, market_id, dataset):
        row = c.execute("""SELECT id FROM public.partial_markets WHERE id=%s
            AND dataset=%s AND economic_identity IS NOT NULL""", (_id(market_id), dataset)).fetchone()
        if row is None:
            raise ValueError("verified economic market not found")

    def web_markets(self, dataset, *, limit=50, offset=0):
        page = _page(limit, offset)
        with self._snapshot() as c:
            return c.execute("""SELECT id,market_key AS native_label,ruleset,region,dataset,
                economic_identity->>'economy' AS economy,
                economic_identity->>'auction_house_scope' AS auction_house_scope,
                economic_identity->>'faction' AS faction
                FROM public.partial_markets WHERE economic_identity IS NOT NULL AND dataset=%s
                ORDER BY id LIMIT %s OFFSET %s""", (dataset, *page)).fetchall()

    def web_states(self, market_id, dataset, *, limit=50, offset=0):
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._web_market(c, market_id, dataset)
            return c.execute("""SELECT e.id,e.state_hash,i.key AS native_label,
                (SELECT count(*) FROM public.partial_export_facts f
                 WHERE f.export_id=e.id AND f.market_id=m.id) AS native_fact_count,
                jsonb_array_length((SELECT x->'items'
                    FROM jsonb_array_elements(e.structure_manifest->'markets') x
                    WHERE x->>'market_key'=i.key)) AS item_count,
                (SELECT count(*) FROM public.partial_capture_receipts r WHERE r.export_id=e.id) AS receipt_count,
                (SELECT min(acquired_at) FROM public.partial_capture_receipts r WHERE r.export_id=e.id) AS first_acquired_at,
                (SELECT max(acquired_at) FROM public.partial_capture_receipts r WHERE r.export_id=e.id) AS last_acquired_at
                FROM public.partial_exports e JOIN public.partial_markets m ON m.id=%s
                CROSS JOIN LATERAL jsonb_each(e.structure_manifest->'market_identities') i
                WHERE e.canonical_version=2 AND e.sealed AND e.dataset=%s AND i.value=m.economic_identity
                ORDER BY e.id LIMIT %s OFFSET %s""", (market_id, dataset, *page)).fetchall()

    def web_facts(self, export_id, market_id, dataset, *, limit=100, offset=0):
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._web_market(c, market_id, dataset)
            self._state(c, export_id)
            self._membership(c, export_id, market_id)
            # One complete native item/bucket per row, so page boundaries cannot
            # lose l and incorrectly label h as a fallback. m stays undated.
            return c.execute("""SELECT item_key,external_item_id,key_kind,scan_day,
                max(value) FILTER (WHERE native_field='l') AS native_l,
                max(value) FILTER (WHERE native_field='h') AS native_h,
                max(value) FILTER (WHERE native_field='a') AS native_a,
                max(value) FILTER (WHERE native_field='m') AS native_m,
                count(*) AS native_fact_count
                FROM public.partial_export_facts WHERE export_id=%s AND market_id=%s
                GROUP BY item_key,external_item_id,key_kind,scan_day
                ORDER BY item_key COLLATE "C",scan_day NULLS LAST LIMIT %s OFFSET %s""",
                             (export_id, market_id, *page)).fetchall()

    def web_receipts(self, export_id, market_id, dataset, *, limit=20, offset=0):
        page = _page(limit, offset)
        with self._snapshot() as c:
            self._web_market(c, market_id, dataset)
            self._state(c, export_id)
            self._membership(c, export_id, market_id)
            return c.execute("""SELECT r.import_id AS id,r.acquired_at,i.imported_at AS received_at,
                i.status,r.source_sha256,l.input_format,
                r.capture_context->'provenance'->>'codec_producer' AS codec_producer,
                (r.capture_context->'provenance'->'capture_client_build' IS NOT NULL
                 AND r.capture_context->'provenance'->'capture_client_build'<>'null'::jsonb) AS capture_build_known
                FROM public.partial_capture_receipts r
                JOIN public.partial_import_runs i ON i.id=r.import_id
                JOIN public.partial_export_imports l ON l.import_id=r.import_id AND l.export_id=r.export_id
                WHERE r.export_id=%s ORDER BY r.import_id LIMIT %s OFFSET %s""",
                             (export_id, *page)).fetchall()
