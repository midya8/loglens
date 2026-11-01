"""Before/after comparison of log windows split at a moment in time.

"Did the deploy make things worse?" is answered by comparing the window
before a timestamp with the window after it: error-rate delta, which
error paths are new, and which stopped. Records with unparseable
timestamps are excluded from both sides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .parse import LogRecord
from .stats import error_rate, top_paths
from .timeline import parse_timestamp


@dataclass(frozen=True)
class WindowComparison:
    """Stats for the windows before and after a split timestamp."""

    split_at: datetime
    before_requests: int
    after_requests: int
    before_error_rate: float
    after_error_rate: float
    new_error_paths: tuple[str, ...]
    resolved_error_paths: tuple[str, ...]

    @property
    def error_rate_delta(self) -> float:
        """Change in error rate across the split (positive means worse)."""
        return self.after_error_rate - self.before_error_rate


def compare_windows(
    records: list[LogRecord],
    split_at: datetime,
    error_threshold: int = 500,
) -> WindowComparison:
    """Split records at *split_at* and compare the two windows."""
    before, after = [], []
    for record in records:
        ts = parse_timestamp(record.timestamp)
        if ts is None:
            continue
        (before if ts < split_at else after).append(record)
    before_paths = {p for p, _ in top_paths(before, limit=len(before) or 1, errors_only=True)}
    after_paths = {p for p, _ in top_paths(after, limit=len(after) or 1, errors_only=True)}
    return WindowComparison(
        split_at=split_at,
        before_requests=len(before),
        after_requests=len(after),
        before_error_rate=error_rate(before, error_threshold),
        after_error_rate=error_rate(after, error_threshold),
        new_error_paths=tuple(sorted(after_paths - before_paths)),
        resolved_error_paths=tuple(sorted(before_paths - after_paths)),
    )


def format_comparison(comp: WindowComparison) -> str:
    """Render a comparison as a plain-text block."""
    sign = "+" if comp.error_rate_delta >= 0 else ""
    lines = [
        f"Comparison across {comp.split_at.isoformat()}",
        f"  Before: {comp.before_requests} requests, error rate {comp.before_error_rate:.1%}",
        f"  After:  {comp.after_requests} requests, error rate {comp.after_error_rate:.1%} "
        f"({sign}{comp.error_rate_delta:.1%})",
    ]
    if comp.new_error_paths:
        lines.append("  New error paths: " + ", ".join(comp.new_error_paths))
    if comp.resolved_error_paths:
        lines.append("  Resolved error paths: " + ", ".join(comp.resolved_error_paths))
    if not comp.new_error_paths and not comp.resolved_error_paths:
        lines.append("  No change in error paths.")
    return "\n".join(lines)


@dataclass(frozen=True)
class LogsComparison:
    """Two whole logs side by side: baseline vs current.

    The release-over-release question: did errors move, which error
    paths are new or gone, which existing paths regressed most, and how
    did latency shift. Latency fields are None when either side lacks
    durations.
    """

    baseline_requests: int
    current_requests: int
    baseline_error_rate: float
    current_error_rate: float
    new_error_paths: tuple[str, ...]
    resolved_error_paths: tuple[str, ...]
    regressions: tuple[dict, ...]
    baseline_p50_ms: float | None
    current_p50_ms: float | None
    baseline_p95_ms: float | None
    current_p95_ms: float | None

    @property
    def error_rate_delta(self) -> float:
        """Change in error rate from baseline to current (positive = worse)."""
        return self.current_error_rate - self.baseline_error_rate


def compare_logs(
    baseline: list[LogRecord],
    current: list[LogRecord],
    error_threshold: int = 500,
    regression_limit: int = 5,
) -> LogsComparison:
    """Compare two parsed logs: error movement, path regressions, latency."""
    from .stats import latency_summary

    def error_counts(records: list[LogRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in records:
            if r.status >= error_threshold:
                counts[r.path] = counts.get(r.path, 0) + 1
        return counts

    before_counts = error_counts(baseline)
    after_counts = error_counts(current)
    regressions = [
        {"path": path, "baseline_errors": before_counts.get(path, 0),
         "current_errors": after_errors,
         "delta": after_errors - before_counts.get(path, 0)}
        for path, after_errors in after_counts.items()
        if after_errors > before_counts.get(path, 0)
    ]
    regressions.sort(key=lambda r: (-r["delta"], r["path"]))
    before_latency = latency_summary(baseline)
    after_latency = latency_summary(current)
    return LogsComparison(
        baseline_requests=len(baseline),
        current_requests=len(current),
        baseline_error_rate=error_rate(baseline, error_threshold),
        current_error_rate=error_rate(current, error_threshold),
        new_error_paths=tuple(sorted(set(after_counts) - set(before_counts))),
        resolved_error_paths=tuple(sorted(set(before_counts) - set(after_counts))),
        regressions=tuple(regressions[:regression_limit]),
        baseline_p50_ms=before_latency["p50"] if before_latency else None,
        current_p50_ms=after_latency["p50"] if after_latency else None,
        baseline_p95_ms=before_latency["p95"] if before_latency else None,
        current_p95_ms=after_latency["p95"] if after_latency else None,
    )


def format_log_comparison(comp: LogsComparison) -> str:
    """Render a two-log comparison as a plain-text block."""
    sign = "+" if comp.error_rate_delta >= 0 else ""
    lines = [
        "Comparison vs baseline:",
        f"  Baseline: {comp.baseline_requests} requests, error rate {comp.baseline_error_rate:.1%}",
        f"  Current:  {comp.current_requests} requests, error rate {comp.current_error_rate:.1%} "
        f"({sign}{comp.error_rate_delta:.1%})",
    ]
    if comp.new_error_paths:
        lines.append("  New error paths: " + ", ".join(comp.new_error_paths))
    if comp.resolved_error_paths:
        lines.append("  Resolved error paths: " + ", ".join(comp.resolved_error_paths))
    if not comp.new_error_paths and not comp.resolved_error_paths:
        lines.append("  No change in error paths.")
    if comp.regressions:
        lines.append("  Biggest regressions:")
        for r in comp.regressions:
            lines.append(f"    {r['path']}: {r['baseline_errors']} -> {r['current_errors']} "
                         f"errors (+{r['delta']})")
    if comp.baseline_p95_ms is not None and comp.current_p95_ms is not None:
        delta = comp.current_p95_ms - comp.baseline_p95_ms
        sign_ms = "+" if delta >= 0 else ""
        lines.append(f"  Latency p50: {comp.baseline_p50_ms:.0f} -> {comp.current_p50_ms:.0f} ms; "
                     f"p95: {comp.baseline_p95_ms:.0f} -> {comp.current_p95_ms:.0f} ms "
                     f"({sign_ms}{delta:.0f})")
    return "\n".join(lines)
