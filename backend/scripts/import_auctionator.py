import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ingestion.adapters.auctionator import AuctionatorAdapter
from app.ingestion.partial_service import PartialIngestionService


def main():
    parser = argparse.ArgumentParser(description="Import literal Auctionator 340 SavedVariables")
    parser.add_argument("file", type=Path)
    parser.add_argument("--source-id", required=True, help="Stable account/export identity and clock context")
    parser.add_argument("--region", required=True, help="Explicit source region; not present in SavedVariables")
    parser.add_argument("--dataset", choices=["real", "simulated"], required=True)
    parser.add_argument("--market-map", type=Path, help="JSON mapping raw market keys to PvE/PvP/HC/RP")
    parser.add_argument("--scan-day-zero", help="Verified ISO timestamp of client SCAN_DAY_0; otherwise unknown")
    parser.add_argument("--allow-libcbor", action="store_true", help="Explicitly select inspected LibCBOR encoding")
    args = parser.parse_args()
    mapping = json.loads(args.market_map.read_text(encoding="utf-8")) if args.market_map else None
    result = AuctionatorAdapter().load(args.file, source_id=args.source_id, region=args.region,
                                     dataset=args.dataset, market_mapping=mapping,
                                     scan_day_zero=args.scan_day_zero, allow_libcbor=args.allow_libcbor)
    print(PartialIngestionService().import_batch(result).model_dump_json())


if __name__ == "__main__":
    main()
