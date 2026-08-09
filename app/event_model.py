from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    name: str
    start_time: datetime
    end_time: Optional[datetime]
    location: Optional[str]
    description: Optional[str]
    source_url: str
    source: str
    # True when a scraper has hardcoded `location` to a known-correct full
    # address (e.g. luma_the_commons.py), bypassing Google Places entirely —
    # lets downstream location resolution skip a pointless API call/cache
    # write for a value that's already exact.
    location_verified: bool = field(default=False)

    @property
    def unique_key(self) -> str:
        """Identity of this event: title + start datetime + description + location.

        If any of these change, this hashes to a different key, so the sync
        engine treats it as a new event (and the old one gets deleted as no
        longer present) rather than updating in place.
        """
        raw = "|".join([
            self.name,
            self.start_time.isoformat(),
            self.description or "",
            self.location or "",
        ])
        return hashlib.sha256(raw.encode()).hexdigest()
