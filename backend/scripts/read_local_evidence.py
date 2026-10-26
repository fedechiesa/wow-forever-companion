"""Explicit, private, read-only CLI for sealed native v2 economic evidence."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _json(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported evidence value")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["markets", "states", "state", "facts", "receipts"])
    parser.add_argument("--database-url-env", required=True, help="Variable name, never a DSN argument")
    parser.add_argument("--market-id", type=int)
    parser.add_argument("--export-id", type=int)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.database_url_env.isidentifier():
        parser.error("--database-url-env must name an environment variable")
    if (args.action in ("states", "facts")) != (args.market_id is not None):
        parser.error("states/facts require --market-id; other actions do not accept it")
    if (args.action in ("state", "facts", "receipts")) != (args.export_id is not None):
        parser.error("state/facts/receipts require --export-id; other actions do not accept it")
    try:
        from app.db.trial import _open, _parameters
        from app.ingestion.local_readers import LocalEvidenceReader
        parameters = _parameters(os.environ.get(args.database_url_env))
        reader = LocalEvidenceReader(lambda: _open(parameters))  # read_only=True before any query
        page = dict(limit=args.limit, offset=args.offset)
        if args.action == "markets":
            rows = reader.markets(**page)
        elif args.action == "states":
            rows = reader.states(args.market_id, **page)
        elif args.action == "state":
            rows = reader.state(args.export_id)
        elif args.action == "facts":
            rows = reader.facts(args.export_id, args.market_id, **page)
        else:
            rows = reader.receipts(args.export_id, **page)
        print(json.dumps(dict(contract="local-evidence-reader-v2", analytics_enabled=False,
                              temporal_basis="unknown", result=rows), default=_json))
        return 0
    except Exception:
        print("Evidence read failed; verify selectors, prepared schema 006 and connection privately. Details withheld.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
