from __future__ import annotations

from pathlib import Path
from typing import List

from app.event_model import Event
from app.utils import fetch_mobilize_org_events

_SOURCE = Path(__file__).stem
_ORG_SLUG = "civicjoyfund"
# "Community Service" tag on Mobilize — narrows the org's feed to
# neighborhood cleanups etc., matching the volunteering calendar's scope.
_TAG_IDS = ["546"]


def fetch_events() -> List[Event]:
    return fetch_mobilize_org_events(_ORG_SLUG, _SOURCE, tag_ids=_TAG_IDS)
