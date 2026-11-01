"""Aggregate statistics over parsed log records."""

from __future__ import annotations

from collections import Counter

from .parse import LogRecord
from .timeline import parse_timestamp


def status_distribution(records: list[LogRecord]) -> dict[int, int]:
    """Count records per exact status code."""
    return dict(Counter(r.status for r in records))


def status_classes(records: list[LogRecord]) -> dict[str, int]:
    """Roll statuses up into 2xx/3xx/4xx/5xx classes (plus other).

    The at-a-glance split between client trouble (4xx) and server trouble
    (5xx) - the first triage question in an incident. All five keys are
    always present so JSON consumers can index directly.
    """
    classes = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0}
    for record in records:
        klass = f"{record.status // 100}xx" if 200 <= record.status < 600 else "other"
        classes[klass] += 1
    return classes


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


def top_user_agents(
    records: list[LogRecord], limit: int = 10, errors_only: bool = False
) -> list[tuple[str, int]]:
    """Most frequent user agents, optionally only among 5xx responses.

    Answers "is this spike a bot or real users?" - one scripted agent
    behind every 5xx reads very differently from a mix of browsers.
    Records without a user agent are skipped.
    """
    pool = (
        r for r in records
        if r.user_agent and (not errors_only or r.status >= 500)
    )
    return Counter(r.user_agent for r in pool).most_common(limit)


def top_referers(
    records: list[LogRecord], limit: int = 10, errors_only: bool = False
) -> list[tuple[str, int]]:
    """Most frequent referers, optionally only among 5xx responses.

    Answers "which page were users on when it broke?" - a checkout 5xx
    storm referred by /cart reads differently from one with no referer.
    Records without a referer (nginx logs "-") are skipped.
    """
    pool = (
        r for r in records
        if r.referer and (not errors_only or r.status >= 500)
    )
    return Counter(r.referer for r in pool).most_common(limit)


def top_methods(records: list[LogRecord], limit: int = 10, errors_only: bool = False) -> list[tuple[str, int]]:
    """HTTP methods ranked by volume, optionally restricted to 5xx responses.

    The write-vs-read question in an incident: a 5xx spike on POSTs is a
    different emergency than one on GETs. Empty methods are skipped.
    """
    pool = (r for r in records if r.method and (not errors_only or r.status >= 500))
    return Counter(r.method for r in pool).most_common(limit)


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


def ip_breakdown(records: list[LogRecord], limit: int = 10, sort: str = "errors") -> list[dict]:
    """Per-source-IP volume, error rate and latency, worst offenders first.

    The client-side mirror of ``path_breakdown``: answers "is one client
    retry-storming us?" with the same shape and ``sort`` semantics
    (``errors``, ``requests`` or ``p95``). Records without a source IP are
    skipped.
    """
    if sort not in ("errors", "requests", "p95"):
        raise ValueError(f"unknown sort: {sort!r} (want errors, requests or p95)")
    by_ip: dict[str, list[LogRecord]] = {}
    for record in records:
        if record.source_ip:
            by_ip.setdefault(record.source_ip, []).append(record)
    rows = []
    for ip, group in by_ip.items():
        errors = sum(1 for r in group if r.status >= 500)
        durations = [r.duration_ms for r in group if r.duration_ms is not None]
        rows.append({
            "ip": ip,
            "requests": len(group),
            "errors": errors,
            "error_rate": errors / len(group),
            "p95_ms": percentile(durations, 95) if durations else None,
        })
    if sort == "p95":
        rows.sort(key=lambda row: (row["p95_ms"] is None,
                                   -(row["p95_ms"] or 0), -row["requests"], row["ip"]))
    elif sort == "requests":
        rows.sort(key=lambda row: (-row["requests"], -row["errors"], row["ip"]))
    else:
        rows.sort(key=lambda row: (-row["errors"], -row["requests"], row["ip"]))
    return rows[:limit]


def path_breakdown(records: list[LogRecord], limit: int = 10, sort: str = "errors") -> list[dict]:
    """Per-path volume, error rate and latency, worst offenders first.

    ``sort`` picks what "worst" means: ``errors`` (error count, then
    volume - the path causing the pain leads), ``requests`` (busiest
    first), or ``p95`` (slowest first, untimed paths last). Latency is p95
    over the path's timed requests (None when the path has none).
    """
    if sort not in ("errors", "requests", "p95"):
        raise ValueError(f"unknown sort: {sort!r} (want errors, requests or p95)")
    by_path: dict[str, list[LogRecord]] = {}
    for record in records:
        by_path.setdefault(record.path, []).append(record)
    rows = []
    for path, group in by_path.items():
        errors = sum(1 for r in group if r.status >= 500)
        durations = [r.duration_ms for r in group if r.duration_ms is not None]
        rows.append({
            "path": path,
            "requests": len(group),
            "errors": errors,
            "error_rate": errors / len(group),
            "p95_ms": percentile(durations, 95) if durations else None,
        })
    if sort == "p95":
        rows.sort(key=lambda row: (row["p95_ms"] is None,
                                   -(row["p95_ms"] or 0), -row["requests"], row["path"]))
    elif sort == "requests":
        rows.sort(key=lambda row: (-row["requests"], -row["errors"], row["path"]))
    else:
        rows.sort(key=lambda row: (-row["errors"], -row["requests"], row["path"]))
    return rows[:limit]


def path_status_breakdown(records: list[LogRecord], limit: int = 10,
                          threshold: int = 400) -> list[dict]:
    """Per-path status-code counts behind the failures, worst paths first.

    ``--by-path`` ranks endpoints but hides which codes are failing; this
    pivot answers "are the /api/checkout 5xxs actually 502s from the
    upstream?". Only paths with at least one response at or above
    ``threshold`` appear, ranked by failing-request count (ties: total
    volume, then path). Each row carries the failing total plus the
    per-code counts, sorted by code.
    """
    by_path: dict[str, dict[int, int]] = {}
    volumes: dict[str, int] = {}
    for record in records:
        volumes[record.path] = volumes.get(record.path, 0) + 1
        if record.status >= threshold:
            by_path.setdefault(record.path, {})[record.status] = (
                by_path.setdefault(record.path, {}).get(record.status, 0) + 1)
    rows = []
    for path, codes in by_path.items():
        rows.append({
            "path": path,
            "requests": volumes[path],
            "failing": sum(codes.values()),
            "statuses": dict(sorted(codes.items())),
        })
    rows.sort(key=lambda row: (-row["failing"], -row["requests"], row["path"]))
    return rows[:limit]


def hourly_breakdown(records: list[LogRecord]) -> list[dict]:
    """Per-hour-of-day volume, error rate and latency (UTC).

    Complements the chronological timeline: every request is bucketed
    into its UTC hour of day (0-23), so a daily pattern - the nightly
    batch job, the lunch peak - stands out even in a multi-day log.
    Records with unparseable timestamps are skipped, the same convention
    as the timeline. Rows cover only hours present in the data, sorted
    by hour.
    """
    by_hour: dict[int, list[LogRecord]] = {}
    for record in records:
        ts = parse_timestamp(record.timestamp)
        if ts is None:
            continue
        by_hour.setdefault(ts.hour, []).append(record)
    rows = []
    for hour in sorted(by_hour):
        group = by_hour[hour]
        errors = sum(1 for r in group if r.status >= 500)
        durations = [r.duration_ms for r in group if r.duration_ms is not None]
        rows.append({
            "hour": hour,
            "requests": len(group),
            "errors": errors,
            "error_rate": errors / len(group),
            "p95_ms": percentile(durations, 95) if durations else None,
        })
    return rows


_LATENCY_BUCKETS_MS = (50.0, 100.0, 250.0, 500.0, 1000.0)


def latency_histogram(records: list[LogRecord]) -> list[dict]:
    """Latency distribution over fixed millisecond buckets.

    Percentiles compress the shape away; the histogram shows it - a p95
    of 400ms reads differently when the mass sits at 250-500ms versus a
    long tail past 1s. Untimed records are skipped. Buckets are labelled
    by their upper bound ("<=50ms", ..., ">1000ms") and always returned
    in order, empty buckets included, so charts and text line up.
    """
    counts = [0] * (len(_LATENCY_BUCKETS_MS) + 1)
    for record in records:
        if record.duration_ms is None:
            continue
        for i, bound in enumerate(_LATENCY_BUCKETS_MS):
            if record.duration_ms <= bound:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    labels = [f"<={b:g}ms" for b in _LATENCY_BUCKETS_MS] + [f">{_LATENCY_BUCKETS_MS[-1]:g}ms"]
    return [{"bucket": label, "count": count} for label, count in zip(labels, counts)]


def human_bytes(n: float) -> str:
    """Format a byte count compactly: 950 B, 12.4 KB, 3.1 MB."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def size_summary(records: list[LogRecord]) -> dict | None:
    """Aggregate response sizes: total, mean, max over records that carry one.

    Returns None when no record has a size (e.g. logs without a bytes
    field), so callers can skip the section instead of printing zeros.
    """
    sizes = [r.size_bytes for r in records if r.size_bytes is not None]
    if not sizes:
        return None
    return {
        "count": len(sizes),
        "total_bytes": sum(sizes),
        "mean_bytes": sum(sizes) / len(sizes),
        "max_bytes": max(sizes),
    }


def top_paths_by_bytes(records: list[LogRecord], limit: int = 10) -> list[dict]:
    """Per-path bytes served, largest first, with share of the total.

    Bandwidth concentrates differently than request volume - the path
    hammered most is not always the one moving the megabytes. This
    ranking finds the heavy responses.
    """
    per_path: dict[str, dict] = {}
    for r in records:
        if r.size_bytes is None:
            continue
        entry = per_path.setdefault(r.path, {"path": r.path, "bytes": 0, "requests": 0})
        entry["bytes"] += r.size_bytes
        entry["requests"] += 1
    total = sum(e["bytes"] for e in per_path.values())
    ranked = sorted(per_path.values(), key=lambda e: (-e["bytes"], e["path"]))
    for entry in ranked:
        entry["share"] = entry["bytes"] / total if total else 0.0
    return ranked[:limit]
