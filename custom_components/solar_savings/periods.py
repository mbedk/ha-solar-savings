"""Pure-Python calendar-period tracking for a single running total.

No Home Assistant imports here, same reasoning as ledger.py: this is a unit
of accounting logic (calendar rollover + baseline bookkeeping), not
integration glue, so it should be testable on its own.

Given a timezone-aware "now" and a running total's current value, tracks a
baseline per period (daily/weekly/monthly/yearly) and reports how much the
total has moved since that period started - "how much of the running total
happened today / this week / this month / this year."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

PERIODS = ("daily", "weekly", "monthly", "yearly")


def _period_key(period: str, now: datetime) -> str:
    if period == "daily":
        return now.strftime("%Y-%m-%d")
    if period == "weekly":
        iso_year, iso_week, _ = now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if period == "monthly":
        return now.strftime("%Y-%m")
    if period == "yearly":
        return now.strftime("%Y")
    raise ValueError(f"unknown period: {period!r}")


@dataclass
class PeriodTracker:
    """Tracks daily/weekly/monthly/yearly deltas of one running total.

    Rollover is calendar-based (local time, ISO week for "weekly"), not a
    fixed duration - a period's value is "how much has this total moved
    since the current day/week/month/year started," and can legitimately go
    negative if the underlying total decreases within the period.
    """

    _period_keys: dict[str, str] = field(default_factory=dict)
    _baselines: dict[str, float] = field(default_factory=dict)
    _values: dict[str, float] = field(default_factory=lambda: {p: 0.0 for p in PERIODS})

    def update(self, now: datetime, current_total: float) -> None:
        """Roll over any period whose key has changed, then refresh every
        period's reported value. Call this on every tick with the latest
        cumulative total - value() reflects whatever was passed at the last
        update() call, not the current wall-clock time.
        """
        for period in PERIODS:
            key = _period_key(period, now)
            if self._period_keys.get(period) != key:
                # First time this period has ever been seen, or it just
                # rolled over: start counting from the current total.
                self._period_keys[period] = key
                self._baselines[period] = current_total
            self._values[period] = current_total - self._baselines[period]

    def value(self, period: str) -> float:
        return self._values[period]

    def to_dict(self) -> dict:
        return {
            "period_keys": dict(self._period_keys),
            "baselines": dict(self._baselines),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PeriodTracker":
        tracker = cls()
        tracker._period_keys = dict(data.get("period_keys", {}))
        tracker._baselines = dict(data.get("baselines", {}))
        return tracker
