from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_cloud() -> bool:
    """True when running in Cloud Run (Job or Service), detected via GCP-injected env vars."""
    return bool(
        os.environ.get("CLOUD_RUN_JOB")
        or os.environ.get("K_SERVICE")
        or os.environ.get("GCS_BUCKET")
    )


def _project() -> str:
    return os.environ["GOOGLE_CLOUD_PROJECT"]


def _gcs_bucket() -> str:
    return os.environ["GCS_BUCKET"]


def read_secret(secret_name: str) -> str:
    from google.cloud import secretmanager  # type: ignore

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{_project()}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def write_secret(secret_name: str, data: str) -> None:
    from google.cloud import secretmanager  # type: ignore

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{_project()}/secrets/{secret_name}"
    client.add_secret_version(
        request={"parent": parent, "payload": {"data": data.encode("utf-8")}}
    )
    logger.info(f"Updated secret '{secret_name}'")


def load_push_history_gcs() -> dict[str, Any]:
    from google.cloud import storage  # type: ignore

    client = storage.Client()
    blob = client.bucket(_gcs_bucket()).blob("push_history.json")
    try:
        return json.loads(blob.download_as_text())
    except Exception as exc:
        logger.warning(f"Could not read push history from GCS: {exc}")
        return {}


def save_push_history_gcs(history: dict[str, Any]) -> None:
    from google.cloud import storage  # type: ignore

    client = storage.Client()
    blob = client.bucket(_gcs_bucket()).blob("push_history.json")
    blob.upload_from_string(
        json.dumps(history, indent=2), content_type="application/json"
    )
    logger.info("Saved push history to GCS")
