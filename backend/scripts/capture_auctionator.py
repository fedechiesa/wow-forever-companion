"""One explicit local capture; no settings, database, network or watcher startup."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.local_capture import CaptureError, capture_file


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate and archive local Auctionator evidence (offline)")
    parser.add_argument("file", type=Path)
    parser.add_argument("--destination", type=Path, help="Private directory outside this project")
    parser.add_argument("--origin-id", help="Optional opaque local alias; never a path/account name")
    parser.add_argument("--source-version", choices=["340", "341"], help="Operator-selected version, not detected")
    parser.add_argument("--serialized-codec", choices=["cbor-definite"], help="Explicit bounded CBOR profile")
    # Avoid logging arbitrary market mappings/paths or loading another private file.
    parser.add_argument("--market-rule", action="append", default=[], metavar="KEY=RULESET",
                        help="Explicit external-key mapping to PvE/PvP/HC/RP; repeatable")
    args = parser.parse_args(argv)
    try:
        mapping = {}
        for rule in args.market_rule:
            key, separator, value = rule.rpartition("=")
            if not separator or not key or value not in ("PvE", "PvP", "HC", "RP") or key in mapping:
                raise CaptureError("invalid_options")
            mapping[key] = value
        result = capture_file(args.file, args.destination, origin_id=args.origin_id,
                              source_version=args.source_version, serialized_codec=args.serialized_codec,
                              market_mapping=mapping)
        # Full metadata is private on disk. Console output has only opaque hashes,
        # counts and statuses: no source/destination paths or market/account names.
        m = result.metadata
        print(json.dumps({"status": result.status, "capture_id": m.capture_id,
                          "market_sha256": m.market_sha256, "market_status": result.comparison.status,
                          "new_market_states": len(result.comparison.new_market_states),
                          "native_fact_count": m.native_fact_count,
                          "projected_statistic_count": m.projected_statistic_count}))
        return 0
    except CaptureError as error:
        print(json.dumps({"error": error.code}), file=sys.stderr)
        return 1
    except Exception:
        print('{"error":"capture_failed"}', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
