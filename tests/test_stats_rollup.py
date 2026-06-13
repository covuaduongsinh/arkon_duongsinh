"""
Unit tests for the self-healing rollup logic in app/services/stats_aggregator.py.

These exercise the pure date-gap planner (`_missing_rollup_dates`) only — no DB,
Redis, or rollup execution required.
"""

from datetime import date, timedelta

from app.services.stats_aggregator import BACKFILL_DAYS, _missing_rollup_dates

TODAY = date(2026, 6, 12)


def test_empty_table_backfills_trailing_window():
    """No rollups yet -> compute the trailing backfill window ending today."""
    got = _missing_rollup_dates(None, TODAY, backfill_days=14)
    assert got[0] == TODAY - timedelta(days=13)
    assert got[-1] == TODAY
    assert len(got) == 14
    # Strictly ascending, daily, no gaps/dupes.
    assert got == sorted(got)
    assert all((b - a).days == 1 for a, b in zip(got, got[1:]))


def test_already_fresh_is_noop():
    """latest == today -> nothing to do."""
    assert _missing_rollup_dates(TODAY, TODAY, backfill_days=14) == []


def test_future_latest_is_noop():
    """Defensive: a latest date ahead of today still yields no work."""
    assert _missing_rollup_dates(TODAY + timedelta(days=1), TODAY, backfill_days=14) == []


def test_small_gap_fills_only_missing_days():
    """latest a few days back -> [latest+1 .. today], inclusive."""
    latest = TODAY - timedelta(days=3)
    got = _missing_rollup_dates(latest, TODAY, backfill_days=14)
    assert got == [
        TODAY - timedelta(days=2),
        TODAY - timedelta(days=1),
        TODAY,
    ]


def test_one_day_stale_fills_today_only():
    """The normal cron-was-down-overnight case: latest == yesterday -> just today."""
    got = _missing_rollup_dates(TODAY - timedelta(days=1), TODAY, backfill_days=14)
    assert got == [TODAY]


def test_large_gap_is_capped_to_backfill_window():
    """A very old latest date must not trigger an unbounded backfill."""
    latest = TODAY - timedelta(days=400)
    got = _missing_rollup_dates(latest, TODAY, backfill_days=14)
    assert len(got) == 14
    assert got[0] == TODAY - timedelta(days=13)
    assert got[-1] == TODAY


def test_default_backfill_days_constant():
    """Calling with the module default matches BACKFILL_DAYS."""
    got = _missing_rollup_dates(None, TODAY, backfill_days=BACKFILL_DAYS)
    assert len(got) == BACKFILL_DAYS
