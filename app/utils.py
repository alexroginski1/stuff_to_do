from __future__ import annotations

import logging
from typing import Optional

import requests
from dateutil import parser as dtparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def fetch_html(url: str, headers: Optional[dict] = None, timeout: int = 20) -> str:
    merged = {**_DEFAULT_HEADERS, **(headers or {})}
    resp = _session.get(url, headers=merged, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_iso_datetime(s: str):
    """Parse an ISO 8601 datetime string into a timezone-aware datetime."""
    return dtparser.parse(s)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
