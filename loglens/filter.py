"""Time-window filtering for parsed log records.

Incidents are investigated inside a window: "what happened between the
first alert and the deploy?" `filter_records` keeps only records whose
timestamps fall inside [since, until] (inclusive bounds). Records with
unparseable timestamps are excluded when a window is given - guessing
their position would be worse than dropping them.
"""

from __future__ import annotations

from datetime import datetime

from .parse import LogRecord
from .timeline import parse_timestamp


def filter_records(
    records: list[LogRecord],
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[LogRecord]:
    """Keep records with timestamps inside [since, until], inclusive.

    Either bound may be None (open-ended). With no bounds the input is
    returned unchanged. Records whose timestamps do not parse are dropped
    when any bound is set.
    """
    if since is None and until is None:
        return records
    kept = []
    for record in records:
        ts = parse_timestamp(record.timestamp)
        if ts is None:
            continue
        if since is not None and ts < since:
            continue
        if until is not None and ts > until:
            continue
        kept.append(record)
    return kept


def parse_bound(value: str) -> datetime:
    """Parse a --since/--until CLI value; raises ValueError on bad input."""
    parsed = parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"unparseable timestamp: {value!r}")
    return parsed
