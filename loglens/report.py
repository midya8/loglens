"""Render a Markdown incident summary from parsed log records.

After the first pass over a log, the findings go somewhere people read:
an incident doc, a ticket, a chat. `render_incident_report` turns the
same statistics the CLI prints into a shareable Markdown section.
"""

from __future__ import annotations

from .compare import WindowComparison
from .parse import LogRecord
from .stats import (
    error_rate,
    latency_summary,
    path_breakdown,
    slowest_requests,
    status_distribution,
    top_error_ips,
    top_paths,
)
from .timeline import bucket_records, is_spike, parse_timestamp


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def render_incident_report(
    records: list[LogRecord],
    title: str = "Log analysis",
    bucket_seconds: int = 60,
    top: int = 5,
    comparison: WindowComparison | None = None,
) -> str:
    """Render records as a Markdown incident report.

    When *comparison* is given (from ``compare_windows``), a before/after
    section is included so the report stands alone as a deploy writeup.
    """
    lines = [f"# {title}", ""]
    if not records:
        lines.append("No parseable records in input.")
        return "\n".join(lines) + "\n"

    timestamps = [ts for ts in (parse_timestamp(r.timestamp) for r in records) if ts]
    lines.append(f"- **Records:** {len(records)}")
    if timestamps:
        lines.append(
            f"- **Window:** {min(timestamps).isoformat()} to {max(timestamps).isoformat()}"
        )
    lines.append(f"- **Error rate (5xx):** {error_rate(records):.1%}")
    distribution = ", ".join(
        f"{status}x{count}" for status, count in sorted(status_distribution(records).items())
    )
    lines.append(f"- **Status distribution:** {distribution}")
    lines.append("")

    if comparison is not None:
        sign = "+" if comparison.error_rate_delta >= 0 else ""
        lines.append(f"## Before/after {comparison.split_at.isoformat()}")
        lines.append("")
        lines.append(
            f"- **Requests:** {comparison.before_requests} before, "
            f"{comparison.after_requests} after"
        )
        lines.append(
            f"- **Error rate:** {comparison.before_error_rate:.1%} before, "
            f"{comparison.after_error_rate:.1%} after "
            f"({sign}{comparison.error_rate_delta:.1%})"
        )
        if comparison.new_error_paths:
            lines.append(
                "- **New failing paths:** "
                + ", ".join(f"`{p}`" for p in comparison.new_error_paths)
            )
        if comparison.resolved_error_paths:
            lines.append(
                "- **Recovered paths:** "
                + ", ".join(f"`{p}`" for p in comparison.resolved_error_paths)
            )
        if not comparison.new_error_paths and not comparison.resolved_error_paths:
            lines.append("- **Error paths:** no change")
        lines.append("")

    error_paths = top_paths(records, top, errors_only=True)
    if error_paths:
        lines.append("## Hottest failing paths")
        lines.append("")
        for path, count in error_paths:
            lines.append(f"- `{path}` - {_plural(count, 'error')}")
        lines.append("")

    error_ips = top_error_ips(records, top)
    if error_ips:
        lines.append("## Source IPs behind 5xxs")
        lines.append("")
        for ip, count in error_ips:
            lines.append(f"- {ip} - {_plural(count, 'error')}")
        lines.append("")

    breakdown = path_breakdown(records, top)
    if breakdown:
        lines.append("## Per-path breakdown")
        lines.append("")
        lines.append("| Path | Requests | Errors | Error rate | p95 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in breakdown:
            p95 = f"{row['p95_ms']:.0f} ms" if row["p95_ms"] is not None else "-"
            lines.append(
                f"| `{row['path']}` | {row['requests']} | {row['errors']} | "
                f"{row['error_rate']:.0%} | {p95} |"
            )
        lines.append("")

    latency = latency_summary(records)
    if latency is not None:
        lines.append("## Latency")
        lines.append("")
        lines.append(
            f"p50 {latency['p50']:.1f} ms, p95 {latency['p95']:.1f} ms, "
            f"p99 {latency['p99']:.1f} ms over {int(latency['count'])} timed requests."
        )
        lines.append("")
        lines.append("Slowest requests:")
        lines.append("")
        for r in slowest_requests(records, top):
            lines.append(f"- {r.duration_ms:.1f} ms - `{r.method} {r.path}` -> {r.status}")
        lines.append("")

    if timestamps:
        buckets = bucket_records(records, bucket_seconds)
        spikes = [b for b in buckets if is_spike(b)]
        peak = max(buckets, key=lambda b: b.errors, default=None)
        if spikes:
            lines.append("## Incident window")
            lines.append("")
            first, last = spikes[0], spikes[-1]
            lines.append(
                f"- **First spike:** {first.start.isoformat()} - "
                f"{_plural(first.errors, 'error')} in {_plural(first.requests, 'request')} "
                f"({first.error_rate:.0%})"
            )
            lines.append(
                f"- **Last spike:** {last.start.isoformat()} - "
                f"{_plural(last.errors, 'error')} in {_plural(last.requests, 'request')} "
                f"({last.error_rate:.0%})"
            )
            if peak and peak.errors:
                lines.append(
                    f"- **Peak:** {peak.start.isoformat()} - "
                    f"{_plural(peak.errors, 'error')} in {_plural(peak.requests, 'request')}"
                )
            lines.append("")
        elif peak and peak.errors:
            lines.append("## Peak")
            lines.append("")
            lines.append(
                f"Errors peak at {peak.start.isoformat()}: "
                f"{_plural(peak.errors, 'error')} in {_plural(peak.requests, 'request')}."
            )
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
