from __future__ import annotations

import argparse

from app.sync_engine import run_sync
from app.utils import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync events to Google Calendar")
    parser.add_argument(
        "--num_events_per_source",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of events to process per scraper source",
    )
    parser.add_argument(
        "--delete_parser_events",
        action="store_true",
        default=False,
        help="Delete all parser-created Google Calendar events from today onwards",
    )
    parser.add_argument(
        "--delete_all_events",
        action="store_true",
        default=False,
        help="Delete ALL Google Calendar events from today onwards, including manually created ones",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        metavar="SOURCE",
        help="Limit deletions to a specific source (e.g. luma_tiat). Only applies with --delete_parser_events or --delete_all_events",
    )
    args = parser.parse_args()

    setup_logging()
    run_sync(
        num_events_per_source=args.num_events_per_source,
        delete_parser_events=args.delete_parser_events,
        delete_all_events_flag=args.delete_all_events,
        source=args.source,
    )


if __name__ == "__main__":
    main()
