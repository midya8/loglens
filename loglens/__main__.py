"""CLI: ``python -m loglens <logfile>`` prints an incident-oriented summary."""

from __future__ import annotations

import argparse
import json

from .compare import compare_windows, format_comparison
from .filter import filter_by_status, filter_records, parse_bound, parse_status_spec
from .parse import parse_lines
from .report import render_incident_report
from .stats import (
    error_rate,
    latency_summary,
    path_breakdown,
    slowest_requests,
    status_classes,
    status_distribution,
    top_error_ips,
    top_paths,
    top_referers,
    top_user_agents,
)
from .timeline import bucket_records, format_timeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="loglens")
    parser.add_argument("logfile", help="'-' for stdin")
    parser.add_argument("--format", choices=("auto", "combined", "json"), default="auto",
                        help="log format; auto (default) detects each line independently, "
                             "so mixed files parse")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--timeline", action="store_true", help="print per-bucket request/error counts")
    parser.add_argument("--bucket", type=int, default=60, help="timeline bucket size in seconds")
    parser.add_argument("--latency", action="store_true", help="print latency percentiles and slowest requests (JSON logs with durations)")
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON instead of text")
    parser.add_argument("--since", help="only include records at/after this timestamp")
    parser.add_argument("--until", help="only include records at/before this timestamp")
    parser.add_argument("--split-at", help="compare stats before/after this timestamp")
    parser.add_argument("--status",
                        help="only include these statuses: exact codes and/or Nxx classes, comma-separated (e.g. 5xx,404)")
    parser.add_argument("--report", metavar="TITLE", nargs="?", const="Log analysis",
                        help="emit a Markdown incident report instead of the text summary")
    parser.add_argument("--sort", choices=("errors", "requests", "p95"), default="errors",
                        help="ordering for --by-path: errors (default), requests, or p95 latency")
    parser.add_argument("--by-path", action="store_true",
                        help="per-path breakdown: volume, error rate, p95 latency, worst first")
    parser.add_argument("--agents", action="store_true",
                        help="top user agents overall and behind 5xxs (bot vs real users)")
    parser.add_argument("--referers", action="store_true",
                        help="top referers overall and behind 5xxs (which page broke)")
    args = parser.parse_args(argv)

    import sys

    lines = sys.stdin if args.logfile == "-" else open(args.logfile)
    formats = ("combined", "json") if args.format == "auto" else (args.format,)
    records = parse_lines(lines, formats=formats)
    if args.since or args.until:
        try:
            since = parse_bound(args.since) if args.since else None
            until = parse_bound(args.until) if args.until else None
        except ValueError as exc:
            parser.error(str(exc))
        records = filter_records(records, since=since, until=until)
    if args.status:
        try:
            codes, classes = parse_status_spec(args.status)
        except ValueError as exc:
            parser.error(str(exc))
        records = filter_by_status(records, codes, classes)
    if args.split_at:
        try:
            split_at = parse_bound(args.split_at)
        except ValueError as exc:
            parser.error(str(exc))
        comparison = compare_windows(records, split_at)
    else:
        comparison = None
    if args.json:
        print(json.dumps(_summary(records, args, comparison), indent=2))
        return 0
    if args.report is not None:
        print(render_incident_report(records, title=args.report, bucket_seconds=args.bucket, top=args.top, comparison=comparison), end="")
        return 0
    print(f"Parsed records: {len(records)}")
    print(f"Error rate (5xx): {error_rate(records):.1%}")
    print("Status distribution:", dict(sorted(status_distribution(records).items())))
    classes = status_classes(records)
    print("Status classes:", {k: v for k, v in classes.items() if v})
    print(f"Top {args.top} paths:", top_paths(records, args.top))
    print(f"Top {args.top} error paths:", top_paths(records, args.top, errors_only=True))
    print(f"Top {args.top} error source IPs:", top_error_ips(records, args.top))
    if args.timeline:
        print("\nTimeline (UTC):")
        print(format_timeline(bucket_records(records, args.bucket)))
    if comparison is not None:
        print()
        print(format_comparison(comparison))
    if args.by_path:
        print(f"\nPer-path breakdown (top {args.top}):")
        print(f"  {'path':40s} {'req':>6} {'err':>4} {'rate':>6} {'p95':>9}")
        for row in path_breakdown(records, args.top, sort=args.sort):
            p95 = f"{row['p95_ms']:.0f} ms" if row['p95_ms'] is not None else "-"
            print(f"  {row['path']:40s} {row['requests']:>6} {row['errors']:>4} "
                  f"{row['error_rate']:>6.0%} {p95:>9}")
    if args.agents:
        print(f"Top {args.top} user agents:", top_user_agents(records, args.top))
        print(f"Top {args.top} error user agents:", top_user_agents(records, args.top, errors_only=True))
    if args.referers:
        print(f"Top {args.top} referers:", top_referers(records, args.top))
        print(f"Top {args.top} error referers:", top_referers(records, args.top, errors_only=True))
    if args.latency:
        summary = latency_summary(records)
        if summary is None:
            print("\nLatency: no durations in log (needs JSON lines with duration_ms or request_time)")
        else:
            print(f"\nLatency (ms): p50={summary['p50']:.1f} p95={summary['p95']:.1f} p99={summary['p99']:.1f}")
            print(f"Slowest {args.top} requests:")
            for r in slowest_requests(records, args.top):
                print(f"  {r.duration_ms:8.1f} ms  {r.method} {r.path} -> {r.status}")
    return 0


def _summary(records, args, comparison=None) -> dict:
    """Build the machine-readable summary for --json."""
    summary = {
        "parsed_records": len(records),
        "error_rate_5xx": error_rate(records),
        "status_distribution": {str(k): v for k, v in sorted(status_distribution(records).items())},
        "status_classes": status_classes(records),
        "top_paths": [
            {"path": path, "count": count}
            for path, count in top_paths(records, args.top)
        ],
        "top_error_paths": [
            {"path": path, "count": count}
            for path, count in top_paths(records, args.top, errors_only=True)
        ],
        "top_error_ips": [
            {"ip": ip, "count": count}
            for ip, count in top_error_ips(records, args.top)
        ],
    }
    latency = latency_summary(records)
    if latency is not None:
        summary["latency_ms"] = {k: (int(v) if k == "count" else v) for k, v in latency.items()}
        summary["slowest_requests"] = [
            {"method": r.method, "path": r.path, "status": r.status,
             "duration_ms": r.duration_ms}
            for r in slowest_requests(records, args.top)
        ]
    if args.timeline:
        summary["timeline"] = [
            {"start": b.start.isoformat(), "requests": b.requests,
             "errors": b.errors, "error_rate": b.error_rate}
            for b in bucket_records(records, args.bucket)
        ]
    if getattr(args, "by_path", False):
        summary["path_breakdown"] = path_breakdown(records, args.top, sort=args.sort)
    if getattr(args, "agents", False):
        summary["top_user_agents"] = [
            {"user_agent": agent, "count": count}
            for agent, count in top_user_agents(records, args.top)
        ]
        summary["top_error_user_agents"] = [
            {"user_agent": agent, "count": count}
            for agent, count in top_user_agents(records, args.top, errors_only=True)
        ]
    if getattr(args, "referers", False):
        summary["top_referers"] = [
            {"referer": referer, "count": count}
            for referer, count in top_referers(records, args.top)
        ]
        summary["top_error_referers"] = [
            {"referer": referer, "count": count}
            for referer, count in top_referers(records, args.top, errors_only=True)
        ]
    if comparison is not None:
        summary["comparison"] = {
            "split_at": comparison.split_at.isoformat(),
            "before_requests": comparison.before_requests,
            "after_requests": comparison.after_requests,
            "before_error_rate": comparison.before_error_rate,
            "after_error_rate": comparison.after_error_rate,
            "error_rate_delta": comparison.error_rate_delta,
            "new_error_paths": list(comparison.new_error_paths),
            "resolved_error_paths": list(comparison.resolved_error_paths),
        }
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
