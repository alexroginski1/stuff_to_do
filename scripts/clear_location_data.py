"""Delete all documents from the `event_snapshot` Firestore collection,
which backs the "Raw Location" / "Clean Location" table at the stats API
root.

`location_cache` (the persistent Places-resolution cache checked by
resolve_location() before calling Places) is intentionally left alone.

Run from the repo root:
    python -m scripts.clear_location_data
"""

from __future__ import annotations

import logging

from google.cloud import firestore

logging.basicConfig(level=logging.INFO, format="%(message)s")

_COLLECTIONS = ["event_snapshot"]
_BATCH_SIZE = 500


def _delete_collection(client: firestore.Client, name: str) -> None:
    collection = client.collection(name)
    deleted = 0
    while True:
        docs = list(collection.limit(_BATCH_SIZE).stream())
        if not docs:
            break
        batch = client.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()
        deleted += len(docs)
    logging.info(f"[{name}] deleted {deleted} documents")


def main() -> None:
    client = firestore.Client()
    for name in _COLLECTIONS:
        _delete_collection(client, name)


if __name__ == "__main__":
    main()
