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
    unique_key: str

    @staticmethod
    def build_unique_key(name: str, start_time: datetime) -> str:
        raw = name + start_time.isoformat()
        return hashlib.sha256(raw.encode()).hexdigest()

    def content_hash(self) -> str:
        raw = "|".join([
            self.name,
            self.start_time.isoformat(),
            self.end_time.isoformat() if self.end_time else "",
            self.location or "",
            self.description or "",
        ])
        return hashlib.sha256(raw.encode()).hexdigest()
