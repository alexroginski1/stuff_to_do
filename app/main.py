from __future__ import annotations

from app.sync_engine import run_sync
from app.utils import setup_logging


def main() -> None:
    setup_logging()
    run_sync()


if __name__ == "__main__":
    main()
