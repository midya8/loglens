"""CLI: ``python -m loglens <logfile>`` prints an incident-oriented summary."""

from __future__ import annotations

import argparse

from .filter import filter_records, parse_bound
from .parse import parse_lines
from .stats import (
    error_rate,
    latency_summary,
    slowest_requests,
    status_distribution,
    top_error_ips,
    top_paths,
)
from .timeline import bucket_records, format_timeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="loglens")
    parser.add_argument("logfile", help="'-' for stdin")
    parser.add_argument("--format", choices=("combined", "json"), default="combined")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--timeline", action="store_true", help="print per-bucket request/error counts")
    parser.add_argument("--bucket", type=int, default=60, help="timeline bucket size in seconds")
    parser.add_argument("--latency", action="store_true", help="print latency percentiles and slowest requests (JSON logs with durations)")
    parser.add_argument("--since", help="only include records at/after this timestamp")
    parser.add_argument("--until", help="only include records at/before this timestamp")
    args = parser.parse_args(argv)

    import sys

    lines = sys.stdin if args.logfile == "-" else open(args.logfile)
    records = parse_lines(lines, formats=(args.format,))
    if args.since or args.until:
        try:
            since = parse_bound(args.since) if args.since else None
            until = parse_bound(args.until) if args.until else None
        except ValueError as exc:
            parser.error(str(exc))
        records = filter_records(records, since=since, until=until)
    print(f"Parsed records: {len(records)}")
    print(f"Error rate (5xx): {error_rate(records):.1%}")
    print("Status distribution:", dict(sorted(status_distribution(records).items())))
    print(f"Top {args.top} paths:", top_paths(records, args.top))
    print(f"Top {args.top} error paths:", top_paths(records, args.top, errors_only=True))
    print(f"Top {args.top} error source IPs:", top_error_ips(records, args.top))
    if args.timeline:
        print("\nTimeline (UTC):")
        print(format_timeline(bucket_records(records, args.bucket)))
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


if __name__ == "__main__":
    raise SystemExit(main())
