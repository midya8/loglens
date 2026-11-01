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
    "%Y-%m-%d",              # date only, midnight UTC
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


def is_spike(bucket: Bucket, min_error_rate: float = 0.25, min_errors: int = 2) -> bool:
    """Whether a bucket's error rate is anomalous enough to flag.

    Both conditions must hold so a single error in a quiet minute does not
    read as a spike: at least *min_errors* errors AND an error rate of at
    least *min_error_rate*.
    """
    if not 0 < min_error_rate <= 1:
        raise ValueError(f"min_error_rate must be in (0, 1], got {min_error_rate!r}")
    if min_errors < 1:
        raise ValueError(f"min_errors must be >= 1, got {min_errors!r}")
    return bucket.errors >= min_errors and bucket.error_rate >= min_error_rate


def format_timeline(
    buckets: list[Bucket],
    spike_min_error_rate: float = 0.25,
    spike_min_errors: int = 2,
) -> str:
    """Render buckets as a plain-text table with a simple error bar.

    Buckets flagged as spikes by `is_spike` are marked with `<-- spike`.
    """
    lines = []
    for bucket in buckets:
        bar = "#" * bucket.errors
        marker = "  <-- spike" if is_spike(bucket, spike_min_error_rate, spike_min_errors) else ""
        lines.append(
            f"{bucket.start:%H:%M}  {bucket.requests:>5} req  "
            f"{bucket.errors:>3} err  {bucket.error_rate:>5.0%}  {bar}{marker}"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class SpikeWindow:
    """One run of consecutive spike buckets: a single flare-up.

    ``end`` is exclusive (last spike bucket start + bucket size), so
    ``end - start`` is the window's duration.
    """

    start: datetime
    end: datetime
    requests: int
    errors: int

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 0.0


def spike_windows(
    buckets: list[Bucket],
    bucket_seconds: int = 60,
    min_error_rate: float = 0.25,
    min_errors: int = 2,
) -> list[SpikeWindow]:
    """Group consecutive spike buckets into windows.

    A single spike bucket is noise; a run of them is the incident. Two
    spike buckets belong to the same window when their starts are exactly
    ``bucket_seconds`` apart - a gap (empty or quiet buckets) splits
    windows. Only the spike buckets' own counts are aggregated, so the
    window's error rate reflects the flare-up, not the lull around it.
    Thresholds are ``is_spike``'s.
    """
    if bucket_seconds <= 0:
        raise ValueError(f"bucket_seconds must be positive, got {bucket_seconds!r}")
    runs: list[list[Bucket]] = []
    run: list[Bucket] = []
    for bucket in buckets:
        if not is_spike(bucket, min_error_rate, min_errors):
            continue
        if run and (bucket.start - run[-1].start).total_seconds() != bucket_seconds:
            runs.append(run)
            run = []
        run.append(bucket)
    if run:
        runs.append(run)
    return [
        SpikeWindow(
            start=r[0].start,
            end=datetime.fromtimestamp(r[-1].start.timestamp() + bucket_seconds,
                                       tz=timezone.utc),
            requests=sum(b.requests for b in r),
            errors=sum(b.errors for b in r),
        )
        for r in runs
    ]


def throughput_summary(buckets: list[Bucket]) -> dict | None:
    """Mean and peak per-bucket throughput over a timeline.

    Answers "how busy was it, and how bad did the busiest minute get?"
    without scanning the whole table. Returns None for an empty
    timeline; ``peak`` names the single busiest bucket by requests
    (earliest on ties).
    """
    if not buckets:
        return None
    peak = max(buckets, key=lambda b: b.requests)
    total_requests = sum(b.requests for b in buckets)
    return {
        "buckets": len(buckets),
        "total_requests": total_requests,
        "mean_requests_per_bucket": total_requests / len(buckets),
        "peak_start": peak.start.isoformat(),
        "peak_requests": peak.requests,
        "peak_errors": peak.errors,
    }
