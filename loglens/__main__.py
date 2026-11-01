"""CLI: ``python -m loglens <logfile>`` prints an incident-oriented summary."""

from __future__ import annotations

import argparse

from .parse import parse_lines
from .stats import error_rate, status_distribution, top_error_ips, top_paths
from .timeline import bucket_records, format_timeline


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="loglens")
    parser.add_argument("logfile", help="'-' for stdin")
    parser.add_argument("--format", choices=("combined", "json"), default="combined")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--timeline", action="store_true", help="print per-bucket request/error counts")
    parser.add_argument("--bucket", type=int, default=60, help="timeline bucket size in seconds")
    args = parser.parse_args(argv)

    import sys

    lines = sys.stdin if args.logfile == "-" else open(args.logfile)
    records = parse_lines(lines, formats=(args.format,))
    print(f"Parsed records: {len(records)}")
    print(f"Error rate (5xx): {error_rate(records):.1%}")
    print("Status distribution:", dict(sorted(status_distribution(records).items())))
    print(f"Top {args.top} paths:", top_paths(records, args.top))
    print(f"Top {args.top} error paths:", top_paths(records, args.top, errors_only=True))
    print(f"Top {args.top} error source IPs:", top_error_ips(records, args.top))
    if args.timeline:
        print("\nTimeline (UTC):")
        print(format_timeline(bucket_records(records, args.bucket)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
