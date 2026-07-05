from __future__ import annotations

import hashlib
from dataclasses import dataclass
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
