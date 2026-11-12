# loglens

[![CI](https://github.com/midya8/loglens/actions/workflows/ci.yml/badge.svg)](https://github.com/midya8/loglens/actions/workflows/ci.yml)

Standard-library access-log analysis for nginx / Apache combined logs and
structured JSON logs. Reports include recorded error rates, status counts,
paths, latency and source IPs behind 5xx responses. Python 3.10+.

## Choose a view

| Question | Flags |
| --- | --- |
| Which requests failed? | `--errors`, `--path-status`, `--by-path` |
| When did recorded error rates rise? | `--timeline`, `--spikes`, `--bucket` |
| How do two recorded windows differ? | `--split-at`, `--vs` |
| What durations and response sizes are present? | `--latency`, `--latency-dist`, `--apdex`, `--by-size` |
| Which recorded clients and metadata recur? | `--by-ip`, `--methods`, `--agents`, `--referers` |

Statistics describe parsed log records, not the cause of an incident. Malformed
lines are skipped; missing records or duration fields can change the picture.
Client IPs and user-agent strings do not identify a person or establish bot
activity. Compare windows with their traffic mix and coverage in mind.

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
python -m loglens app.log --format json --apdex 0.5         # Apdex score at T=0.5s, per path
python -m loglens app.log --format json --apdex 0.5 --min-apdex 0.94   # exit 1 below 0.94
python -m loglens app.log --format json --json   # machine-readable summary for tooling
python -m loglens app.log --split-at 2026-10-31T22:00:00Z   # before/after comparison
python -m loglens app.log --vs examples/access-baseline.log   # vs a baseline log
python -m loglens app.log --report "Checkout 5xx spike"     # Markdown incident report
python -m loglens app.log --by-path                          # per-path volume/errors/p95
python -m loglens app.log --path-status                     # failing paths x their status codes
python -m loglens app.log --by-ip                            # per-client volume/errors/p95
python -m loglens app.log --by-hour                          # hour-of-day pattern (UTC)
python -m loglens app.log --by-size                          # bandwidth: total bytes, heaviest paths
python -m loglens app.log --spikes                           # flare-up windows from spike buckets
python -m loglens app.log --throughput                       # mean/peak per-bucket throughput
python -m loglens app.log --latency-dist                     # latency shape over fixed ms buckets
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
  (or any bucket size) to locate elevated error rates in the supplied records, and
  flags spike buckets where the error rate and count both clear a threshold
  so a low-count bucket can be excluded by the configured count threshold.
- **Latency view.** `--latency` reports p50/p95/p99 and the slowest requests
  from JSON logs carrying `duration_ms` or nginx-style `request_time`, and
  from combined-format logs with `$request_time` appended (a trailing
  fractional number is read as seconds); logs without durations simply
  skip the section.
- **Apdex scoring.** `--apdex SECONDS` computes the Apdex user-satisfaction
  score at threshold T: requests within T are satisfied, within 4T
  tolerating, beyond 4T frustrated, and the score is
  (satisfied + tolerating/2) / samples - one number for "how responsive
  did this log feel", plus a per-path table worst-first so the endpoint
  dragging the score down leads. `--min-apdex 0.94` turns it into a
  pipeline gate (exit 1 below the threshold, and a log with no durations
  fails the gate rather than passing unmeasured), and the incident report
  gains an Apdex section when `--apdex` is set. Also in `--json` as an
  `apdex` block with per-path rows.
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
  JSON output, and the report's incident window section lists those same
  windows with a peak-bucket line. `--throughput` summarizes the
  timeline into mean and peak per-bucket throughput, and `--latency-dist`
  shows the latency shape over fixed millisecond buckets - a p95 of
  400ms reads differently when the mass sits at 250-500ms versus a long
  tail past 1s.
  Ready to paste into an incident doc or ticket.
- **Failing-path status pivot.** `--path-status` answers "are the
  /api/checkout 5xxs actually 502s from the upstream?": the failing
  endpoints (4xx+5xx) ranked worst-first, each with its per-status-code
  counts and total volume. Compose it with `--status 5xx` to pivot on
  server errors only. Also in `--json` as `path_status` rows.
- **Per-path and per-client breakdowns.** `--by-path` ranks endpoints by
  error count - or by volume or p95 latency with `--sort requests|p95` -
  with volume, error rate and p95 latency. `--by-ip` gives the same table per
  source IP; it does not establish which client process sent a request.
  `--by-hour` buckets the whole window by
  UTC hour of day, so a daily pattern - the nightly batch job, the lunch
  peak - stands out in a multi-day log.
- **Baseline comparison.** `--vs baseline.log` compares recorded outcomes
  across two whole logs without attributing the change to a release:
  error-rate delta, new and resolved error paths, the paths with the biggest error-count increases
  (ranked regressions), and p50/p95 latency shifts when both sides carry
  durations. Also available in `--json` as a `comparison` block.
- **Response sizes.** `--by-size` turns the bytes column into bandwidth
  answers: total bytes served, mean and largest response, and the paths
  ranked by bytes moved (with share of total) - because the most
  requested path is not always the one moving the megabytes. Combined
  logs' size field and JSON `size_bytes`/`body_bytes_sent`/`bytes`/`size`
  keys are picked up automatically; logs without sizes print a note
  instead of zeros.
- **Methods, user agents and referers.** `--methods` answers "is the spike
  on writes or reads?" with method counts overall and behind 5xxs.
  `--agents` ranks user agents overall and
  behind 5xxs - a view of the recorded agent strings, not a bot classifier -
  and `--referers` does the same for recorded referer values.
  Combined-format referer/agent fields and JSON
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

241 tests cover parsing (both formats, mixed files, corrupt lines),
statistics, timeline bucketing and spike windows, latency and Apdex
scoring, filters, before/after and baseline comparisons, report rendering,
and every CLI flag including the exit-code gates.

## Layout

```
loglens/
  parse.py     # combined-format and JSON parsers -> LogRecord
  stats.py     # error rate, distributions, top-N, latency percentiles
  timeline.py  # per-bucket request/error timeline, timestamp parsing
  filter.py    # time-window filtering
  compare.py   # before/after window comparison
  apdex.py     # Apdex user-satisfaction scoring (overall and per path)
  report.py    # Markdown incident report
  __main__.py  # CLI summary
tests/         # unittest suite, no external dependencies
examples/      # sample access log
```
