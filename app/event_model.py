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
    # True when a scraper has deliberately set `location` to an approximate
    # spot (e.g. presidio.py, whose actual event locations vary across a
    # large park) rather than a real venue address — bypasses Google Places
    # and is always reported as location_type "inexact" downstream, instead
    # of letting Places resolve it to a misleadingly precise address.
    location_inexact: bool = field(default=False)
    # Scraper-supplied notes about the event's provenance (e.g. sf_bar_guide's
    # "parsed from" line and verification disclaimer) that render below the
    # calendar body's ―――――――――― separator rather than in the description.
    # These lines used to be appended to `description` (joined with "\n\n"),
    # so unique_key folds them back in exactly that way — keeping keys
    # identical to the old layout, so moving them didn't re-push any events.
    footer_lines: list[str] = field(default_factory=list)

    @property
    def _key_description(self) -> str:
        if not self.footer_lines:
            return self.description or ""
        parts = ([self.description] if self.description else []) + self.footer_lines
        return "\n\n".join(parts)

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
            self._key_description,
            self.location or "",
        ])
        return hashlib.sha256(raw.encode()).hexdigest()
