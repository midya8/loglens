"""Parsers for common log line formats.

Each parser returns a LogRecord or None for lines it cannot parse, so a
mixed or partially corrupt file degrades gracefully instead of failing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) (?P<size>\S+)(?: "[^"]*" "(?P<agent>[^"]*)")?'
)

# nginx configs that append $request_time log it as a fractional number of
# seconds at end of line (e.g. `... 200 1234 0.042`). Integer-only trailing
# tokens are treated as the response size, not a duration.
_TRAILING_REQUEST_TIME = re.compile(r"\s(?P<rt>\d+\.\d+)\s*$")


@dataclass(frozen=True)
class LogRecord:
    """One parsed log event."""

    timestamp: str
    method: str
    path: str
    status: int
    source_ip: str = ""
    duration_ms: float | None = None
    user_agent: str = ""


def parse_combined(line: str) -> LogRecord | None:
    """Parse one nginx/Apache combined-format line.

    The referer and user-agent fields are optional; the user agent is
    captured when present. A trailing fractional number is treated as
    nginx $request_time in seconds and exposed as duration_ms.
    """
    match = _COMBINED.match(line.strip())
    if not match:
        return None
    duration_ms = None
    rt = _TRAILING_REQUEST_TIME.search(line)
    if rt:
        duration_ms = float(rt.group("rt")) * 1000.0
    return LogRecord(
        timestamp=match.group("time"),
        method=match.group("method"),
        path=match.group("path"),
        status=int(match.group("status")),
        source_ip=match.group("ip"),
        duration_ms=duration_ms,
        user_agent=match.group("agent") or "",
    )


def parse_json_line(line: str) -> LogRecord | None:
    """Parse one structured JSON log line.

    Expects keys named like ``time``/``timestamp``, ``method``, ``path``
    and ``status``; returns None when any are missing or the line is not
    valid JSON. A numeric ``duration_ms`` key is used as-is; a numeric
    ``request_time`` key (nginx-style seconds) is converted to
    milliseconds. Both are optional.
    """
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    timestamp = data.get("time") or data.get("timestamp")
    method, path, status = data.get("method"), data.get("path"), data.get("status")
    if not (timestamp and method and path) or not isinstance(status, int):
        return None
    duration_ms = data.get("duration_ms")
    if duration_ms is None and isinstance(data.get("request_time"), (int, float)):
        duration_ms = float(data["request_time"]) * 1000.0
    if duration_ms is not None and not isinstance(duration_ms, (int, float)):
        duration_ms = None
    return LogRecord(
        timestamp=str(timestamp),
        method=str(method),
        path=str(path),
        status=status,
        duration_ms=None if duration_ms is None else float(duration_ms),
        source_ip=str(data.get("ip", "")),
        user_agent=str(data.get("user_agent") or data.get("agent") or ""),
    )


def parse_lines(lines, formats=("combined", "json")) -> list[LogRecord]:
    """Parse lines with the given formats, skipping unparseable ones."""
    parsers = {"combined": parse_combined, "json": parse_json_line}
    records = []
    for line in lines:
        if not line.strip():
            continue
        record = None
        for fmt in formats:
            record = parsers[fmt](line)
            if record:
                break
        if record:
            records.append(record)
    return records
