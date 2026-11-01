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


def parse_status_spec(value: str) -> tuple[frozenset[int], frozenset[int]]:
    """Parse a --status value like '5xx,404' into (exact codes, classes).

    Classes are the hundreds digit (5 for 5xx). Raises ValueError on
    anything that is not a three-digit code or an Nxx class pattern.
    """
    codes: set[int] = set()
    classes: set[int] = set()
    for part in value.split(","):
        part = part.strip().lower()
        if len(part) == 3 and part[0].isdigit() and part[1:] == "xx":
            classes.add(int(part[0]))
        elif part.isdigit() and len(part) == 3:
            codes.add(int(part))
        else:
            raise ValueError(f"unparseable status spec: {part!r} (want e.g. 5xx, 404)")
    if not codes and not classes:
        raise ValueError("empty status spec")
    return frozenset(codes), frozenset(classes)


def filter_by_status(
    records: list[LogRecord],
    codes: frozenset[int],
    classes: frozenset[int],
) -> list[LogRecord]:
    """Keep records whose status is an exact match or inside a listed class."""
    return [
        r for r in records
        if r.status in codes or r.status // 100 in classes
    ]


def parse_prefix_spec(value: str) -> tuple[str, ...]:
    """Parse a --path-prefix value like '/api,/health' into prefixes.

    Raises ValueError on empty input or empty segments.
    """
    prefixes = tuple(part.strip() for part in value.split(","))
    if not all(prefixes):
        raise ValueError(f"unparseable path prefix spec: {value!r} (want e.g. /api,/health)")
    return prefixes


def filter_by_path_prefix(records: list[LogRecord], prefixes: tuple[str, ...]) -> list[LogRecord]:
    """Keep records whose path starts with any listed prefix."""
    return [r for r in records if r.path.startswith(prefixes)]


def parse_bound(value: str) -> datetime:
    """Parse a --since/--until CLI value; raises ValueError on bad input."""
    parsed = parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"unparseable timestamp: {value!r}")
    return parsed
