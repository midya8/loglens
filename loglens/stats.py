"""Aggregate statistics over parsed log records."""

from __future__ import annotations

from collections import Counter

from .parse import LogRecord


def status_distribution(records: list[LogRecord]) -> dict[int, int]:
    """Count records per exact status code."""
    return dict(Counter(r.status for r in records))


def error_rate(records: list[LogRecord], threshold: int = 500) -> float:
    """Share of records with status >= threshold. 0.0 on empty input."""
    if not records:
        return 0.0
    errors = sum(1 for r in records if r.status >= threshold)
    return errors / len(records)


def top_paths(records: list[LogRecord], limit: int = 10, errors_only: bool = False) -> list[tuple[str, int]]:
    """Most requested paths, optionally restricted to 5xx responses."""
    pool = (r for r in records if not errors_only or r.status >= 500)
    return Counter(r.path for r in pool).most_common(limit)


def top_error_ips(records: list[LogRecord], limit: int = 10) -> list[tuple[str, int]]:
    """Source IPs ranked by 5xx responses - where the pain concentrates."""
    return Counter(r.source_ip for r in records if r.status >= 500 and r.source_ip).most_common(limit)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile of a numeric sample.

    Raises ValueError on empty input or a percentile outside (0, 100].
    """
    if not values:
        raise ValueError("percentile of empty sample")
    if not 0 < pct <= 100:
        raise ValueError(f"pct must be in (0, 100], got {pct!r}")
    ordered = sorted(values)
    rank = max(1, round(len(ordered) * pct / 100))
    return ordered[min(rank, len(ordered)) - 1]


def latency_summary(records: list[LogRecord]) -> dict[str, float] | None:
    """p50/p95/p99 latency in milliseconds over records that carry durations.

    Returns None when no record has a duration, so callers can omit the
    section instead of printing misleading zeros.
    """
    durations = [r.duration_ms for r in records if r.duration_ms is not None]
    if not durations:
        return None
    return {
        "count": float(len(durations)),
        "p50": percentile(durations, 50),
        "p95": percentile(durations, 95),
        "p99": percentile(durations, 99),
    }


def slowest_requests(records: list[LogRecord], limit: int = 5) -> list[LogRecord]:
    """The slowest requests with known durations, slowest first."""
    with_duration = [r for r in records if r.duration_ms is not None]
    return sorted(with_duration, key=lambda r: r.duration_ms, reverse=True)[:limit]
