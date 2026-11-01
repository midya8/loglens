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
