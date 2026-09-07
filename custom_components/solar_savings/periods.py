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

# Daily history grows one entry per day forever; the other three periods grow
# slowly enough (<=366/year for weekly, 12/year for monthly, 1/year for
# yearly) that no cap is needed. This bounds the entity attribute (and the
# recorder writes it) to a reasonable size - old daily figures are still
# fully recoverable from the underlying sensor's own recorder history, this
# is just a convenience window, not the only copy of the data.
MAX_DAILY_HISTORY = 60


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
    _history: dict[str, dict[str, float]] = field(default_factory=dict)

    def update(self, now: datetime, current_total: float) -> None:
        """Roll over any period whose key has changed, then refresh every
        period's reported value. Call this on every tick with the latest
        cumulative total - value() reflects whatever was passed at the last
        update() call, not the current wall-clock time.
        """
        for period in PERIODS:
            key = _period_key(period, now)
            old_key = self._period_keys.get(period)
            if old_key != key:
                if old_key is not None:
                    # A real rollover, not first-ever initialization: archive
                    # the just-closed period's final total under its own key.
                    # self._values[period] is still whatever the last update()
                    # call computed for the OLD period, so this doesn't pick
                    # up any of the new period's accrual - it's exactly the
                    # value the sensor showed the instant before it reset,
                    # never a fabricated or interpolated number.
                    history = self._history.setdefault(period, {})
                    history[old_key] = self._values[period]
                    if period == "daily" and len(history) > MAX_DAILY_HISTORY:
                        for stale_key in sorted(history)[: len(history) - MAX_DAILY_HISTORY]:
                            del history[stale_key]
                self._period_keys[period] = key
                self._baselines[period] = current_total
            self._values[period] = current_total - self._baselines[period]

    def value(self, period: str) -> float:
        return self._values[period]

    def history(self, period: str) -> dict[str, float]:
        """Closed-out totals for previous periods, keyed by their period key
        (e.g. "2025" for yearly, "2026-03" for monthly) - only ever populated
        by an actual rollover witnessed in update(), never backfilled or
        guessed at for periods this tracker didn't live through.
        """
        return dict(self._history.get(period, {}))

    def to_dict(self) -> dict:
        return {
            "period_keys": dict(self._period_keys),
            "baselines": dict(self._baselines),
            "history": {period: dict(values) for period, values in self._history.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PeriodTracker":
        tracker = cls()
        tracker._period_keys = dict(data.get("period_keys", {}))
        tracker._baselines = dict(data.get("baselines", {}))
        tracker._history = {
            period: dict(values) for period, values in data.get("history", {}).items()
        }
        return tracker
