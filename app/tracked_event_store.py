"""Persistent memory of events seen on Partiful/Luma "explore" pages.

Those pages are a rotating featured list, not a complete feed: an event can
be featured on one run and gone from the list the next while still very much
happening. Instead of mirroring whatever is featured right now, the explore
scrapers (scrapers/partiful.py, scrapers/luma.py) run their featured events
through `collect_explore_events`, which remembers every event ever seen and
keeps emitting it on later runs until it ends, or until a re-check finds it
deleted/cancelled at the source.

One Firestore document per (source, event id). `raw` holds the scraper's own
normalized event dict, so a tracked event can still be emitted from its
last-known data if re-checking it hits a transient network error.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.utils import parse_iso_datetime

logger = logging.getLogger(__name__)

_COLLECTION = "tracked_explore_events"
_BATCH_LIMIT = 400  # Firestore caps a batch at 500 writes
# Partiful explore events often have no end time; treat those as over this
# long after they start.
_DEFAULT_DURATION = timedelta(hours=3)
_client: firestore.Client | None = None


class EventGone(Exception):
    """Raised by a re-check when the source confirms the event no longer
    exists (404, cancelled, unpublished) — as opposed to any other exception,
    which is treated as transient."""


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def _doc_id(source: str, event_id: str) -> str:
    # Partiful ids are alphanumeric and Luma's are "evt-..." — neither ever
    # contains "/", the only character Firestore forbids in a document id.
    return f"{source}__{event_id}"


def load_tracked(source: str) -> Optional[Dict[str, dict]]:
    """Return {event_id: raw} for every event currently tracked for `source`.

    Returns None (not {}) if Firestore is unreachable, so callers can tell
    "nothing tracked" apart from "couldn't check" and fall back to just the
    currently-featured events without dropping anything from the store.
    """
    try:
        docs = (
            _get_client()
            .collection(_COLLECTION)
            .where(filter=FieldFilter("source", "==", source))
            .stream()
        )
        tracked: Dict[str, dict] = {}
        for doc in docs:
            data = doc.to_dict() or {}
            event_id, raw = data.get("event_id"), data.get("raw")
            if event_id and isinstance(raw, dict):
                tracked[event_id] = raw
        return tracked
    except Exception as exc:
        logger.error(f"[{source}] failed to load tracked explore events: {exc}")
        return None


def save_tracked(source: str, raws: Dict[str, dict], remove_ids: Iterable[str]) -> None:
    """Upsert `raws` ({event_id: raw}) and delete `remove_ids` for `source`."""
    ops: list[tuple[str, Optional[dict]]] = [(eid, raw) for eid, raw in raws.items()]
    ops += [(eid, None) for eid in remove_ids]
    try:
        client = _get_client()
        collection = client.collection(_COLLECTION)
        for i in range(0, len(ops), _BATCH_LIMIT):
            batch = client.batch()
            for event_id, raw in ops[i:i + _BATCH_LIMIT]:
                ref = collection.document(_doc_id(source, event_id))
                if raw is None:
                    batch.delete(ref)
                else:
                    batch.set(ref, {
                        "source": source,
                        "event_id": event_id,
                        "raw": raw,
                        "last_checked_at": firestore.SERVER_TIMESTAMP,
                    })
            batch.commit()
    except Exception as exc:
        logger.error(f"[{source}] failed to save tracked explore events: {exc}")


def _start(raw: dict) -> Optional[datetime]:
    try:
        return parse_iso_datetime(raw["start"]) if raw.get("start") else None
    except (ValueError, OverflowError):
        return None


def _has_ended(raw: dict, now: datetime) -> bool:
    start = _start(raw)
    if start is None:
        return True
    try:
        end = parse_iso_datetime(raw["end"]) if raw.get("end") else start + _DEFAULT_DURATION
    except (ValueError, OverflowError):
        end = start + _DEFAULT_DURATION
    return end < now


def collect_explore_events(
    source: str,
    featured: Dict[str, dict],
    recheck: Callable[[str], dict],
    horizon_days: int,
) -> List[dict]:
    """Merge the currently-featured events with every previously-seen one.

    `featured` and the return value are {event_id: raw} / [raw] using the
    caller's raw schema, which must include ISO-8601 "start" and optional
    "end". `recheck(event_id)` refetches one tracked-but-no-longer-featured
    event and returns its fresh raw dict, or raises EventGone if the source
    says it's been deleted/cancelled (any other exception = transient, so
    the stored copy is used instead).

    Tracked events starting past `horizon_days` aren't re-checked or emitted
    yet (the sync engine wouldn't push them anyway) — they just stay tracked.
    Events are dropped from the store once they've ended or are gone.
    """
    tracked = load_tracked(source)
    if tracked is None:
        logger.warning(f"[{source}] tracker unavailable — using featured events only this run")
        return list(featured.values())

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=horizon_days)
    keep: Dict[str, dict] = {}
    remove: List[str] = []
    rechecked = gone = stale = 0

    for event_id, raw in featured.items():
        if _has_ended(raw, now):
            if event_id in tracked:
                remove.append(event_id)
        else:
            keep[event_id] = raw

    for event_id, stored in tracked.items():
        if event_id in featured:
            continue
        if _has_ended(stored, now):
            remove.append(event_id)
            continue
        start = _start(stored)
        if start and start > horizon:
            continue  # stays tracked untouched; not in the push window yet
        try:
            fresh = recheck(event_id)
            rechecked += 1
        except EventGone:
            gone += 1
            remove.append(event_id)
            continue
        except Exception as exc:
            logger.warning(f"[{source}] re-check of tracked event {event_id} failed, using stored copy: {exc}")
            stale += 1
            fresh = stored
        if _has_ended(fresh, now):
            remove.append(event_id)
        else:
            keep[event_id] = fresh

    save_tracked(source, keep, remove)
    logger.info(
        f"[{source}] featured={len(featured)} tracked={len(tracked)} rechecked={rechecked} "
        f"gone={gone} stale={stale} removed={len(remove)} emitting={len(keep)}"
    )
    # Tracked-but-beyond-horizon events aren't in `keep`, but weren't
    # removed either, so they're still in the store for a later run.
    return list(keep.values())
