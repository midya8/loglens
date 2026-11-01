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
  (or any bucket size) so you can see exactly when an incident started.
- **Latency view.** `--latency` reports p50/p95/p99 and the slowest requests
  from JSON logs carrying `duration_ms` or nginx-style `request_time`;
  logs without durations simply skip the section.
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
  timeline.py  # per-bucket request/error timeline
  __main__.py  # CLI summary
tests/         # unittest suite, no external dependencies
examples/      # sample access log
```
