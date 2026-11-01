"""Time-bucketed request and error counts over parsed log records.

During an incident the first question is "when did it start?" A timeline
of per-bucket request and 5xx counts answers it at a glance. Records
whose timestamps cannot be parsed are skipped, not fatal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .parse import LogRecord

_FORMATS = (
    "%d/%b/%Y:%H:%M:%S %z",  # nginx/Apache combined: 30/Oct/2026:14:05:01 +0000
    "%Y-%m-%dT%H:%M:%S%z",   # ISO 8601 with offset
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",     # ISO 8601, assumed UTC
    "%Y-%m-%d %H:%M:%S",
)


def parse_timestamp(value: str) -> datetime | None:
    """Parse a log timestamp into an aware datetime, or None.

    Naive timestamps are assumed UTC - a documented convention, since log
    lines without zone info cannot be interpreted any other honest way.
    """
    for fmt in _FORMATS:
        try:
            parsed = datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


@dataclass(frozen=True)
class Bucket:
    """One time bucket's counts."""

    start: datetime
    requests: int
    errors: int

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0


def bucket_records(
    records: list[LogRecord],
    bucket_seconds: int = 60,
    error_threshold: int = 500,
) -> list[Bucket]:
    """Aggregate records into chronological time buckets.

    Raises ValueError for a non-positive bucket size. Records with
    unparseable timestamps are skipped.
    """
    if bucket_seconds <= 0:
        raise ValueError(f"bucket_seconds must be positive, got {bucket_seconds!r}")
    counts: dict[int, list[int]] = {}
    for record in records:
        moment = parse_timestamp(record.timestamp)
        if moment is None:
            continue
        slot = int(moment.timestamp()) // bucket_seconds
        requests, errors = counts.get(slot, [0, 0])
        requests += 1
        if record.status >= error_threshold:
            errors += 1
        counts[slot] = [requests, errors]
    return [
        Bucket(
            start=datetime.fromtimestamp(slot * bucket_seconds, tz=timezone.utc),
            requests=req,
            errors=err,
        )
        for slot, (req, err) in sorted(counts.items())
    ]


def format_timeline(buckets: list[Bucket]) -> str:
    """Render buckets as a plain-text table with a simple error bar."""
    lines = []
    for bucket in buckets:
        bar = "#" * bucket.errors
        lines.append(
            f"{bucket.start:%H:%M}  {bucket.requests:>5} req  "
            f"{bucket.errors:>3} err  {bucket.error_rate:>5.0%}  {bar}"
        )
    return "\n".join(lines)
