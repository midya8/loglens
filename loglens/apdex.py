"""Apdex (Application Performance Index) scoring over request durations.

Apdex is a standard open metric for user-perceived responsiveness: pick a
threshold T (in seconds), then each timed request is *satisfied* when it
completes within T, *tolerating* within 4T, and *frustrated* beyond 4T.
The score is (satisfied + tolerating / 2) / samples, from 0 to 1 - the
fraction of the user experience that is not frustrated.
"""

from .parse import LogRecord


def _buckets(duration_s: float, threshold_s: float) -> str:
    if duration_s <= threshold_s:
        return "satisfied"
    if duration_s <= 4 * threshold_s:
        return "tolerating"
    return "frustrated"


def _score(counts: dict[str, int], samples: int) -> dict:
    return {
        "samples": samples,
        "satisfied": counts["satisfied"],
        "tolerating": counts["tolerating"],
        "frustrated": counts["frustrated"],
        "score": (counts["satisfied"] + counts["tolerating"] / 2) / samples,
    }


def apdex_score(records: list[LogRecord], threshold_s: float) -> dict | None:
    """Overall Apdex score for *threshold_s* (T, seconds).

    Returns None when no record carries a duration, so callers can omit the
    section instead of printing a misleading perfect-or-zero score.
    """
    if threshold_s <= 0:
        raise ValueError("apdex threshold must be positive")
    counts = {"satisfied": 0, "tolerating": 0, "frustrated": 0}
    samples = 0
    for r in records:
        if r.duration_ms is None:
            continue
        counts[_buckets(r.duration_ms / 1000.0, threshold_s)] += 1
        samples += 1
    if not samples:
        return None
    result = _score(counts, samples)
    result["threshold_s"] = threshold_s
    return result


def apdex_by_path(records: list[LogRecord], threshold_s: float,
                  limit: int = 10) -> list[dict]:
    """Per-path Apdex rows, worst score first (ties: most samples first).

    Only paths with at least one timed request appear.
    """
    if threshold_s <= 0:
        raise ValueError("apdex threshold must be positive")
    per_path: dict[str, dict[str, int]] = {}
    for r in records:
        if r.duration_ms is None:
            continue
        counts = per_path.setdefault(
            r.path, {"satisfied": 0, "tolerating": 0, "frustrated": 0})
        counts[_buckets(r.duration_ms / 1000.0, threshold_s)] += 1
    rows = []
    for path, counts in per_path.items():
        samples = sum(counts.values())
        row = _score(counts, samples)
        row["path"] = path
        rows.append(row)
    rows.sort(key=lambda row: (row["score"], -row["samples"], row["path"]))
    return rows[:limit]
