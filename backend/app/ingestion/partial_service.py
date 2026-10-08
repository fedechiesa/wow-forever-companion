import re
import time

import psycopg
from psycopg.types.json import Jsonb

from app.db.connection import connect
from app.ingestion.adapters.auctionator import PartialAdapterResult
from app.ingestion.partial_contracts import PartialImportResult
from app.ingestion.native_exports import NativeExportEvidence


class PartialIngestionService:
    deadlock_attempts = 3

    def import_batch(self, result: PartialAdapterResult) -> PartialImportResult:
        if not re.fullmatch(r"[0-9a-f]{64}", result.source_hash):
            raise ValueError("source_hash must be SHA-256")
        if result.native is not None:
            native = NativeExportEvidence.model_validate(result.native.model_dump())
            def identities(observations):
                return sorted((o.market_key, o.ruleset, o.item_key, o.external_item_id, o.key_kind,
                               -1 if o.scan_day is None else o.scan_day, o.statistic, o.value)
                              for o in observations)
            if identities(native.projected_observations()) != identities(result.batch.observations):
                raise ValueError("native evidence and normalized batch disagree")
        for attempt in range(self.deadlock_attempts):
            try:
                return self._import_batch(result)
            except psycopg.Error as error:
                if error.sqlstate == "40P01" and attempt + 1 < self.deadlock_attempts:
                    # Entire transaction (including the run) has rolled back.
                    time.sleep(0.01 * (2 ** attempt))
                    continue
                self._record_failure(result, error)
                raise

    def _record_failure(self, result, error):
        # Data and the attempted completed run have already rolled back.
        try:
            with connect() as connection:
                self._create_run(connection, result, "failed", str(error))
        except psycopg.Error:
            pass

    @staticmethod
    def _basis(batch):
        return batch.scan_day_zero.isoformat() if batch.scan_day_zero else "unknown"

    def _create_run(self, connection, result, status, error=None):
        b = result.batch
        row = connection.execute(
            """INSERT INTO partial_import_runs
               (source_type, source_id, source_version, database_version, dataset,
                region, temporal_basis, source_hash, raw_reference, status,
                observations_seen, observations_changed, error_message)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s) RETURNING id""",
            (b.source_type, b.source_id, b.source_version, b.database_version, b.dataset,
             b.region, self._basis(b), result.source_hash, result.raw_reference, status,
             len(b.observations), error),
        ).fetchone()
        return row["id"]

    def _import_batch(self, result):
        b = result.batch
        with connect() as connection:
            with connection.transaction():
                run_id = self._create_run(connection, result, "completed")
                # Global phases: items, markets, native export, observations, link.
                # Market-dependent item order can invert locks between batches.
                items = {}
                item_entries = {o.item_key: o for o in b.observations}
                market_entries = {o.market_key: o for o in b.observations}
                if result.native is not None:
                    for market in result.native.markets:
                        market_entries[market.market_key] = market
                        for item in market.items:
                            item_entries[item.item_key] = item
                for key, o in sorted(item_entries.items()):
                    items[key] = self._lock_item(connection, o)
                markets = {}
                for key, o in sorted(market_entries.items()):
                    markets[key] = self._lock_market(connection, b, o)
                export_id, export_created = self._persist_export(connection, result, markets, items, run_id)
                changed = 0
                evidence_hash = result.evidence_hash
                # Stable ordering also reduces deadlocks across overlapping imports.
                observations = sorted(b.observations, key=lambda o: (
                    o.market_key, o.item_key, -1 if o.scan_day is None else o.scan_day, o.statistic,
                ))
                for o in observations:
                    changed += self._persist_observation(
                        connection, result, o, markets[o.market_key], items[o.item_key], run_id, evidence_hash,
                    )
                self._validate_daily_coherence(connection, b, markets, items)
                status = "completed" if changed or export_created else "duplicate"
                connection.execute(
                    "UPDATE partial_import_runs SET status=%s, observations_changed=%s WHERE id=%s",
                    (status, changed, run_id),
                )
                if export_id is not None:
                    connection.execute(
                        """INSERT INTO partial_export_imports(import_id,export_id,input_format,decoder_version)
                           VALUES (%s,%s,%s,%s)""",
                        (run_id, export_id, result.native.input_format, result.native.decoder_version),
                    )
                return PartialImportResult(import_id=run_id, status=status,
                                           observations_seen=len(observations), observations_changed=changed,
                                           export_id=export_id,
                                           evidence_status="created" if export_created else "reused" if export_id else "unavailable",
                                           native_facts_seen=len(result.native.facts) if result.native else 0)

    def _persist_export(self, connection, result, markets, items, run_id):
        native, b = result.native, result.batch
        if native is None:
            return None, False
        state_hash = native.state_hash(b)
        manifest = native.manifest()
        inserted = connection.execute(
            """INSERT INTO partial_exports
               (source_type,source_id,source_version,database_version,dataset,region,temporal_basis,
                canonical_version,state_hash,structure_manifest,native_fact_count,first_import_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (canonical_version,state_hash) DO NOTHING RETURNING id""",
            (b.source_type,b.source_id,b.source_version,b.database_version,b.dataset,b.region,self._basis(b),
             native.canonical_version,state_hash,Jsonb(manifest),len(native.facts),run_id),
        ).fetchone()
        columns = ("market_key", "ruleset", "item_key", "external_item_id", "key_kind",
                   "original_item_key", "native_field", "scan_day", "original_day_key", "value")
        facts = sorted(native.facts, key=lambda f: (f.market_key,f.item_key,
                       -1 if f.scan_day is None else f.scan_day,f.native_field))
        if inserted is None:
            header = connection.execute(
                "SELECT * FROM partial_exports WHERE canonical_version=%s AND state_hash=%s FOR UPDATE",
                (native.canonical_version,state_hash),
            ).fetchone()
            stored = connection.execute(
                """SELECT market_key,ruleset,item_key,external_item_id,key_kind,original_item_key,
                          native_field,scan_day,original_day_key,value FROM partial_export_facts
                   WHERE export_id=%s ORDER BY market_key COLLATE "C",item_key COLLATE "C",
                   scan_day NULLS FIRST,native_field""",
                (header["id"],),
            ).fetchall()
            expected = [{key: getattr(f,key) for key in columns} for f in facts]
            context = (b.source_type,b.source_id,b.source_version,b.database_version,b.dataset,b.region,self._basis(b))
            stored_context = tuple(header[key] for key in ("source_type","source_id","source_version",
                                   "database_version","dataset","region","temporal_basis"))
            if (not header["sealed"] or header["structure_manifest"] != manifest or stored != expected
                    or header["native_fact_count"] != len(facts) or stored_context != context):
                raise psycopg.errors.CheckViolation("canonical export identity collision or corrupt evidence")
            return header["id"], False
        export_id = inserted["id"]
        for f in facts:
            connection.execute(
                """INSERT INTO partial_export_facts
                   (export_id,market_id,item_id,market_key,ruleset,item_key,external_item_id,key_kind,
                    original_item_key,native_field,scan_day,original_day_key,value)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (export_id,markets[f.market_key],items[f.item_key],*(getattr(f,key) for key in columns)),
            )
        connection.execute("UPDATE partial_exports SET sealed=TRUE WHERE id=%s", (export_id,))
        return export_id, True

    def _lock_item(self, connection, o):
        connection.execute(
            """INSERT INTO partial_items(item_key,external_item_id,key_kind)
               VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
            (o.item_key, o.external_item_id, o.key_kind),
        )
        return connection.execute(
            "SELECT id FROM partial_items WHERE item_key=%s FOR UPDATE", (o.item_key,),
        ).fetchone()["id"]

    def _lock_market(self, connection, batch, o):
        connection.execute(
            """INSERT INTO partial_markets(market_key,ruleset,region,dataset)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (o.market_key, o.ruleset, batch.region, batch.dataset),
        )
        row = connection.execute(
            """SELECT id,ruleset FROM partial_markets
               WHERE market_key=%s AND region=%s AND dataset=%s FOR UPDATE""",
            (o.market_key, batch.region, batch.dataset),
        ).fetchone()
        if row["ruleset"] != o.ruleset:
            raise psycopg.IntegrityError("Market ruleset conflicts with previously imported evidence")
        return row["id"]

    def _validate_daily_coherence(self, connection, batch, markets, items):
        # Catalog item locks are held until commit, including when one statistic
        # did not exist yet. Row locks on observations alone cannot cover that gap.
        pairs = {(o.market_key, o.item_key, o.scan_day) for o in batch.observations if o.scan_day is not None}
        for market, item, day in sorted(pairs):
            values = dict((row["statistic"], row["value"]) for row in connection.execute(
                """SELECT statistic,value FROM partial_observations
                   WHERE market_id=%s AND item_id=%s AND source_id=%s AND source_type=%s
                     AND temporal_basis=%s AND scan_day=%s AND evidence_key='daily'""",
                (markets[market], items[item], batch.source_id, batch.source_type, self._basis(batch), day),
            ).fetchall())
            low, high = values.get("daily_minimum"), values.get("daily_highest_minimum")
            if low is not None and high is not None and low > high:
                raise psycopg.errors.CheckViolation("daily_minimum exceeds persisted daily_highest_minimum")

    def _persist_observation(self, connection, result, o, market_id, item_id, run_id, evidence_hash):
        b = result.batch
        # These are extrema across imported evidence, not GetPriceHistory of the
        # latest export. Native export evidence is persisted independently.
        # Never assign m to the most recent historical day.
        row = connection.execute(
            """INSERT INTO partial_observations
               (market_id,item_id,source_id,source_type,temporal_basis,scan_day,statistic,
                value,evidence_key,first_import_id,last_import_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (market_id,item_id,source_id,source_type,temporal_basis,
                            (COALESCE(scan_day,-1)),statistic,evidence_key)
               DO UPDATE SET value = CASE
                   WHEN EXCLUDED.statistic='daily_minimum'
                   THEN LEAST(partial_observations.value,EXCLUDED.value)
                   ELSE GREATEST(partial_observations.value,EXCLUDED.value) END,
                   last_import_id=EXCLUDED.last_import_id
               WHERE (EXCLUDED.statistic='daily_minimum' AND EXCLUDED.value<partial_observations.value)
                  OR (EXCLUDED.statistic<>'daily_minimum' AND EXCLUDED.value>partial_observations.value)
               RETURNING id""",
            (market_id, item_id, b.source_id, b.source_type, self._basis(b), o.scan_day,
             o.statistic, o.value, evidence_hash if o.scan_day is None else "daily", run_id, run_id),
        ).fetchone()
        return int(row is not None)
