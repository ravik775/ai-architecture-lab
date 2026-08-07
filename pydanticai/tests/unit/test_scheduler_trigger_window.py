from __future__ import annotations

from datetime import datetime

from app.scheduler.jobs import EndOfDayTriggerState


def test_triggers_within_window_once_per_day():
    state = EndOfDayTriggerState()
    now = datetime(2024, 1, 1, 23, 5)

    assert state.should_trigger("Asia/Kolkata", now, window_minutes=15) is True
    state.mark_triggered("Asia/Kolkata", now.date())

    # Same day, still in window - must not re-trigger.
    later_same_window = datetime(2024, 1, 1, 23, 10)
    assert state.should_trigger("Asia/Kolkata", later_same_window, window_minutes=15) is False


def test_does_not_trigger_outside_window():
    state = EndOfDayTriggerState()
    assert state.should_trigger("Asia/Kolkata", datetime(2024, 1, 1, 22, 59), window_minutes=15) is False
    assert state.should_trigger("Asia/Kolkata", datetime(2024, 1, 1, 23, 20), window_minutes=15) is False


def test_triggers_again_next_day():
    state = EndOfDayTriggerState()
    day1 = datetime(2024, 1, 1, 23, 5)
    state.mark_triggered("Asia/Kolkata", day1.date())

    day2 = datetime(2024, 1, 2, 23, 5)
    assert state.should_trigger("Asia/Kolkata", day2, window_minutes=15) is True


def test_timezones_tracked_independently():
    state = EndOfDayTriggerState()
    now = datetime(2024, 1, 1, 23, 5)
    state.mark_triggered("Asia/Kolkata", now.date())

    assert state.should_trigger("America/Chicago", now, window_minutes=15) is True
