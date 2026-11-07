"""Pure aggregation of Grainit loads (no Home Assistant imports, easy to test)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .api import Load
from .const import FERTILIZER_YEAR_START_MONTH, RECENT_LOADS

_DANISH = str.maketrans({"æ": "ae", "ø": "oe", "å": "aa", "é": "e", "ü": "u", "ö": "oe", "ä": "ae"})


def slug(text: str) -> str:
    out = []
    for ch in text.lower().translate(_DANISH):
        out.append(ch if ch.isascii() and ch.isalnum() else "_")
    return "_".join(p for p in "".join(out).split("_") if p)


def stream_key(product: str, direction: str) -> str:
    return f"{slug(product)}_{direction}"


def fertilizer_year_start(today: date) -> date:
    year = today.year if today.month >= FERTILIZER_YEAR_START_MONTH else today.year - 1
    return date(year, FERTILIZER_YEAR_START_MONTH, 1)


@dataclass
class Stream:
    """Totals for one product in one direction (e.g. Rågylle Kvæg, ud)."""

    product: str
    direction: str
    today_t: float = 0.0
    today_count: int = 0
    week_t: float = 0.0
    month_t: float = 0.0
    month_count: int = 0
    year_t: float = 0.0
    year_count: int = 0
    last_time: datetime | None = None


@dataclass
class Summary:
    streams: dict[str, Stream] = field(default_factory=dict)
    today_count: int = 0
    month_count: int = 0
    last_load: Load | None = None
    recent: list[Load] = field(default_factory=list)  # newest first


def summarize(loads: list[Load], now: datetime) -> Summary:
    """Summarise loads relative to `now` (naive local time)."""
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = fertilizer_year_start(today)

    s = Summary()
    for load in loads:
        d = load.time.date()
        if d < year_start or load.time > now + timedelta(minutes=5):
            continue
        key = stream_key(load.product, load.direction)
        st = s.streams.setdefault(key, Stream(load.product, load.direction))
        t = load.tonnes
        st.year_t += t
        st.year_count += 1
        if d >= month_start:
            st.month_t += t
            st.month_count += 1
            s.month_count += 1
        if d >= week_start:
            st.week_t += t
        if d == today:
            st.today_t += t
            st.today_count += 1
            s.today_count += 1
        if st.last_time is None or load.time > st.last_time:
            st.last_time = load.time

    in_year = [l for l in loads if l.time.date() >= year_start]
    if in_year:
        s.last_load = in_year[-1]
        s.recent = list(reversed(in_year[-RECENT_LOADS:]))
    return s


def hourly_cumulative(loads: list[Load]) -> dict[str, list[tuple[datetime, float]]]:
    """Per stream: [(hour start, cumulative tonnes up to and including that hour)].

    Used for long-term statistics so Home Assistant graphs show the full
    history (per day/week/month bars) right after installation.
    """
    per_stream: dict[str, dict[datetime, float]] = {}
    for load in loads:
        hour = load.time.replace(minute=0, second=0, microsecond=0)
        bucket = per_stream.setdefault(stream_key(load.product, load.direction), {})
        bucket[hour] = bucket.get(hour, 0.0) + load.tonnes

    result: dict[str, list[tuple[datetime, float]]] = {}
    for key, buckets in per_stream.items():
        total = 0.0
        rows = []
        for hour in sorted(buckets):
            total += buckets[hour]
            rows.append((hour, round(total, 3)))
        result[key] = rows
    return result
