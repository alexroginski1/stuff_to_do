from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from config.settings import PUSH_HISTORY_FILE

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 30

History = dict[str, dict[str, str]]  # {calendar_name: {unique_key: iso_timestamp}}


def load() -> History:
    from app.gcp import is_cloud

    if is_cloud():
        from app.gcp import load_push_history_gcs
        return load_push_history_gcs()

    if not os.path.exists(PUSH_HISTORY_FILE):
        return {}
    try:
        with open(PUSH_HISTORY_FILE) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"Could not read push history: {exc}")
        return {}


def save(history: History) -> None:
    from app.gcp import is_cloud

    if is_cloud():
        from app.gcp import save_push_history_gcs
        save_push_history_gcs(history)
        return

    try:
        with open(PUSH_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as exc:
        logger.warning(f"Could not save push history: {exc}")


def prune(history: History) -> History:
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=_RETENTION_DAYS)).isoformat()
    return {
        cal: {k: v for k, v in keys.items() if v >= cutoff}
        for cal, keys in history.items()
    }


def was_pushed(history: History, calendar_name: str, unique_key: str) -> bool:
    return unique_key in history.get(calendar_name, {})


def record(history: History, calendar_name: str, unique_key: str) -> None:
    history.setdefault(calendar_name, {})[unique_key] = datetime.now(tz=timezone.utc).isoformat()


def remove(history: History, calendar_name: str, unique_key: str) -> None:
    history.get(calendar_name, {}).pop(unique_key, None)
