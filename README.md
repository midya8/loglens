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
python -m loglens - < app.log                                       # format is auto-detected per line
python -m loglens - --format json < app.log                          # or force one format
python -m loglens examples/access.log --timeline --bucket 60
python -m loglens examples/json.log --format json --latency
python -m loglens examples/access.log --since 2026-10-30 --until 2026-10-31
python -m loglens examples/access.log --status 5xx            # errors only
python -m loglens app.log --status 5xx --path-prefix /api     # API errors only
python -m loglens app.log --max-error-rate 0.05               # exit 1 above 5% 5xxs
python -m loglens app.log --format json --json   # machine-readable summary for tooling
python -m loglens app.log --split-at 2026-10-31T22:00:00Z   # before/after comparison
python -m loglens app.log --report "Checkout 5xx spike"     # Markdown incident report
python -m loglens app.log --by-path                          # per-path volume/errors/p95
python -m loglens app.log --by-ip                            # per-client volume/errors/p95
python -m loglens app.log --by-hour                          # hour-of-day pattern (UTC)
python -m loglens app.log --spikes                           # flare-up windows from spike buckets
python -m loglens app.log --errors                           # list the 5xx requests themselves
python -m loglens app.log --methods                          # top HTTP methods, incl. behind 5xxs
python -m loglens app.log --agents                           # top user agents, incl. behind 5xxs
python -m loglens app.log --referers                         # top referers, incl. behind 5xxs
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
  `--status 5xx,404` scopes everything to exact codes and/or Nxx classes,
  and `--path-prefix /api,/health` scopes to a service's surface - "show me
  only the API errors" is `--status 5xx --path-prefix /api`.
- **Pipeline gate.** `--max-error-rate 0.05` exits 1 when the 5xx rate
  breaches the threshold - drop loglens into CI or a cron health check
  against a fresh log slice. Works in text, JSON and report modes.
- **Composable output.** `--json` emits the whole summary (counts, rates,
  top-N, latency, timeline) as JSON so dashboards and scripts can consume
  it without scraping text.
- **Before/after comparison.** `--split-at` compares the windows on either
  side of a deploy or alert: error-rate delta, newly failing paths, and
  paths that recovered.
- **Incident reports.** `--report "Title"` renders the findings as a
  Markdown document - window, rates, failing paths, source IPs, the methods
  behind the 5xxs, a per-path breakdown table, latency, and the incident
  window (first and last spike bucket plus the error peak); with
  `--split-at` it also opens a before/after comparison across the deploy.
  Outside the report, `--spikes` groups consecutive spike buckets into
  flare-up windows (start, end, requests, errors, rate) in the text and
  JSON output.
  Ready to paste into an incident doc or ticket.
- **Per-path and per-client breakdowns.** `--by-path` ranks endpoints by
  error count - or by volume or p95 latency with `--sort requests|p95` -
  with volume, error rate and p95 latency, so the path causing the pain
  leads. `--by-ip` gives the same table per source IP, answering "is one
  client retry-storming us?". `--by-hour` buckets the whole window by
  UTC hour of day, so a daily pattern - the nightly batch job, the lunch
  peak - stands out in a multi-day log.
- **Methods, user agents and referers.** `--methods` answers "is the spike
  on writes or reads?" with method counts overall and behind 5xxs.
  `--agents` ranks user agents overall and
  behind 5xxs - the fast answer to "is this spike a bot or real users?" -
  and `--referers` does the same for referers, answering "which page were
  users on when it broke?" Combined-format referer/agent fields and JSON
  `user_agent`/`agent`/`referer`/`referrer` keys are picked up
  automatically, and incident reports list all three behind 5xxs when the
  log carries them. `--errors` lists the failing requests themselves
  (timestamp, client, method, path, status, duration), capped by `--top`
  with a "+N more" note - the fastest way from "the rate spiked" to the
  exact requests that failed.
- **Graceful degradation.** Unparseable lines are skipped, not fatal - real
  log files are mixed and partially corrupt. Format detection is per line
  (`--format auto`, the default), so a file that switches between combined
  and JSON lines parses both; force one parser with `--format`.
- **Two formats, one record.** Combined-format and JSON parsers both emit the
  same `LogRecord`, so stats code never cares about the source format.
- **Tested statistics.** Status distribution with a 2xx/3xx/4xx/5xx class
  roll-up (the instant client-vs-server split), error rate, top-N and percentile
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
