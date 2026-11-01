# loglens

[![CI](https://github.com/midya8/loglens/actions/workflows/ci.yml/badge.svg)](https://github.com/midya8/loglens/actions/workflows/ci.yml)

Dependency-free access-log analysis for incident work. Point it at an nginx /
Apache combined log or structured JSON logs and get the numbers that matter in
the first five minutes of an incident: error rate, status distribution, hottest
paths, hottest failing paths, and the source IPs behind 5xxs. Standard library
only, Python 3.10+.

## Why

During an incident nobody wants to remember `awk` incantations. `loglens`
turns a log file into a one-screen summary, and its functions are importable
so the same analysis can run inside bigger tooling.

## Usage

CLI:

```bash
python -m loglens examples/access.log
python -m loglens - --format json < app.log
python -m loglens examples/access.log --timeline --bucket 60
python -m loglens examples/json.log --format json --latency
python -m loglens examples/access.log --since 2026-10-30 --until 2026-10-31
python -m loglens app.log --format json --json   # machine-readable summary for tooling
python -m loglens app.log --split-at 2026-10-31T22:00:00Z   # before/after comparison
python -m loglens app.log --report "Checkout 5xx spike"     # Markdown incident report
python -m loglens app.log --by-path                          # per-path volume/errors/p95
```

Library:

```python
from loglens.parse import parse_lines
from loglens.stats import error_rate, latency_summary, top_paths, top_error_ips, percentile

records = parse_lines(open("examples/access.log"))
print(f"5xx rate: {error_rate(records):.1%}")
print("hottest failing paths:", top_paths(records, errors_only=True))
print("ips behind 5xx:", top_error_ips(records))
```

## Design notes

- **Incident timeline.** `--timeline` buckets requests and 5xxs per minute
  (or any bucket size) so you can see exactly when an incident started, and
  flags spike buckets where the error rate and count both clear a threshold
  so a single error in a quiet minute never reads as a spike.
- **Latency view.** `--latency` reports p50/p95/p99 and the slowest requests
  from JSON logs carrying `duration_ms` or nginx-style `request_time`, and
  from combined-format logs with `$request_time` appended (a trailing
  fractional number is read as seconds); logs without durations simply
  skip the section.
- **Time windows.** `--since`/`--until` scope every statistic to an incident
  window; bounds accept ISO timestamps, combined-format timestamps, or a
  bare date (midnight UTC), and compare by instant across formats.
- **Composable output.** `--json` emits the whole summary (counts, rates,
  top-N, latency, timeline) as JSON so dashboards and scripts can consume
  it without scraping text.
- **Before/after comparison.** `--split-at` compares the windows on either
  side of a deploy or alert: error-rate delta, newly failing paths, and
  paths that recovered.
- **Incident reports.** `--report "Title"` renders the findings as a
  Markdown document - window, rates, failing paths, source IPs, a per-path
  breakdown table, latency, and the error peak - ready to paste into an
  incident doc or ticket.
- **Per-path breakdown.** `--by-path` ranks endpoints by error count with
  volume, error rate and p95 latency, so the path causing the pain leads.
- **Graceful degradation.** Unparseable lines are skipped, not fatal - real
  log files are mixed and partially corrupt.
- **Two formats, one record.** Combined-format and JSON parsers both emit the
  same `LogRecord`, so stats code never cares about the source format.
- **Tested statistics.** Status distribution, error rate, top-N and percentile
  behavior (including empty-input and boundary cases) are covered by unit tests.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Layout

```
loglens/
  parse.py     # combined-format and JSON parsers -> LogRecord
  stats.py     # error rate, distributions, top-N, latency percentiles
  timeline.py  # per-bucket request/error timeline, timestamp parsing
  filter.py    # time-window filtering
  compare.py   # before/after window comparison
  report.py    # Markdown incident report
  __main__.py  # CLI summary
tests/         # unittest suite, no external dependencies
examples/      # sample access log
```
