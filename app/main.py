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
        "--delete_events",
        action="store_true",
        default=False,
        help="Delete all existing Google Calendar events found during sync",
    )
    args = parser.parse_args()

    setup_logging()
    run_sync(num_events_per_source=args.num_events_per_source, delete_events=args.delete_events)


if __name__ == "__main__":
    main()
