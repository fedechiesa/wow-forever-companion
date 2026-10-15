"""Fail-closed, session-bound target selection for the Auctionator trial CLI."""
from contextlib import contextmanager
from dataclasses import dataclass
import os
import re

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row


class TrialSafetyError(ValueError):
    """Only fixed, credential-free messages may cross the CLI boundary."""


@dataclass(frozen=True)
class DatabaseIdentity:
    system_identifier: str
    database_oid: int
    database: str

    @property
    def effective_key(self):
        return self.system_identifier, self.database_oid


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ALLOWED = {
    "host", "hostaddr", "port", "dbname", "user", "password", "passfile",
    "sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl", "sslcrldir",
    "channel_binding",
}
_ROUTING_ENV = (
    "PGSERVICE", "PGSERVICEFILE", "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE",
    "PGUSER", "PGOPTIONS", "PGTARGETSESSIONATTRS", "PGLOADBALANCEHOSTS",
)


def _parameters(dsn):
    if not isinstance(dsn, str) or not dsn.strip():
        raise TrialSafetyError("Both database connections must be explicitly configured.")
    try:
        params = conninfo_to_dict(dsn)
    except Exception:
        raise TrialSafetyError("Invalid database connection configuration.") from None
    if (set(params) - _ALLOWED or any(not params.get(k) for k in ("host", "port", "dbname", "user"))
            or not _NAME.fullmatch(params["dbname"])
            or not params["port"].isdigit() or not 1 <= int(params["port"]) <= 65535
            or any("," in params.get(k, "") for k in ("host", "hostaddr", "port"))
            or any(c.isspace() or ord(c) < 32 for c in params["host"])):
        raise TrialSafetyError("Use explicit single-host host/port/dbname/user connections without service or options.")
    if any(os.environ.get(k) for k in _ROUTING_ENV):
        raise TrialSafetyError("Conflicting PostgreSQL routing/session environment; use a clean shell.")
    return params


def _open(params):
    # Fixed session settings, never inherited from PGOPTIONS or a DSN search_path.
    c = None
    try:
        c = psycopg.connect(
            **params, connect_timeout=3, application_name="auctionator-trial",
            options="-c search_path=public -c statement_timeout=15000 -c lock_timeout=5000",
            row_factory=dict_row,
        )
        c.read_only = True
        return c
    except Exception:
        if c is not None:
            c.close()
        raise TrialSafetyError("Cannot establish a verified database connection.") from None


def _identity(c):
    try:
        with c.transaction():
            row = c.execute("""SELECT pg_catalog.current_database() AS database,
                d.oid::bigint AS database_oid, s.system_identifier::text AS system_identifier,
                pg_catalog.pg_is_in_recovery() AS recovery
                FROM pg_catalog.pg_database d CROSS JOIN pg_catalog.pg_control_system() s
                WHERE d.datname=pg_catalog.current_database()""").fetchone()
        if (not row or not _NAME.fullmatch(row["database"])
                or not re.fullmatch(r"[1-9][0-9]*", row["system_identifier"])
                or type(row["database_oid"]) is not int or row["database_oid"] <= 0
                or type(row["recovery"]) is not bool):
            raise ValueError("unverifiable identity")
        return DatabaseIdentity(row["system_identifier"], row["database_oid"], row["database"]), row["recovery"]
    except Exception:
        raise TrialSafetyError("Cannot verify PostgreSQL cluster/database identity with read-only queries.") from None


class TrialDatabase:
    """Direct, stable PostgreSQL only; verify both identities before each writer."""

    def __init__(self, target_dsn, protected_dsn, expected_database):
        if (not isinstance(expected_database, str) or not _NAME.fullmatch(expected_database)
                or not expected_database.endswith("_test")):
            raise TrialSafetyError("An explicit expected database name ending in _test is required.")
        self._target = _parameters(target_dsn)
        self._protected = _parameters(protected_dsn)
        if self._target["dbname"] != expected_database:
            raise TrialSafetyError("Selected connection does not name the expected trial database.")
        self.expected_database = expected_database
        self.identity = None
        self._protected_identity = None
        self._protected_recovery = None
        self._protected_connection = None
        self._first = None

    def __enter__(self):
        try:
            self._protected_connection = _open(self._protected)
            self._protected_identity, self._protected_recovery = _identity(self._protected_connection)
            if self._protected_identity.database != self._protected["dbname"]:
                raise TrialSafetyError("Protected database connection resolved unexpectedly.")
            self._first = _open(self._target)
            self.identity = self._verify(self._first)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        for c in (self._first, self._protected_connection):
            if c is not None:
                c.close()
        self._first = self._protected_connection = None

    def _verify(self, c):
        identity, recovery = _identity(c)
        if identity.effective_key == self._protected_identity.effective_key:
            raise TrialSafetyError("Trial target is the effective DATABASE_URL database; refusing writes.")
        if identity.database != self.expected_database or recovery:
            raise TrialSafetyError("Unexpected or read-only trial target; refusing writes.")
        if self.identity is not None and identity != self.identity:
            raise TrialSafetyError("Trial target identity changed; refusing writes.")
        return identity

    def _verify_protected(self):
        c = self._protected_connection
        if (c is None or c.closed or c.info.transaction_status != TransactionStatus.IDLE
                or c.read_only is not True):
            raise TrialSafetyError("Protected database session is unavailable or unsafe; refusing writes.")
        identity, recovery = _identity(c)
        if identity != self._protected_identity or recovery != self._protected_recovery:
            raise TrialSafetyError("Protected database identity or recovery state changed; refusing writes.")

    @contextmanager
    def connection(self):
        if self._protected_connection is None or self._protected_connection.closed:
            raise TrialSafetyError("Trial validation context is not active.")
        c, self._first = self._first, None
        if c is None:
            c = _open(self._target)
        try:
            if c.closed or c.info.transaction_status != TransactionStatus.IDLE:
                raise TrialSafetyError("Trial session is not idle; refusing writes.")
            c.read_only = False
            with c:
                with c.transaction():
                    # No protected reconnect/fallback: loss or change aborts the run.
                    # Only direct, stable connections are supported, not routing proxies.
                    self._verify_protected()
                    # Target check shares the transaction with all subsequent writes.
                    self._verify(c)
                    yield c
        finally:
            c.close()
