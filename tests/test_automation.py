"""cron-expression matcher for automation jobs."""
import datetime as dt

from c6u import automation


def test_parse_field_star():
    assert automation._parse_field("*", 0, 4) == {0, 1, 2, 3, 4}


def test_parse_field_ranges_steps():
    assert automation._parse_field("1-5", 0, 10) == {1, 2, 3, 4, 5}
    assert automation._parse_field("*/15", 0, 59) == {0, 15, 30, 45}
    assert automation._parse_field("0,30", 0, 59) == {0, 30}


def test_cron_match_minute():
    cron = automation._parse_cron("5 * * * *")
    assert automation._matches(cron, dt.datetime(2026, 1, 1, 12, 5))
    assert not automation._matches(cron, dt.datetime(2026, 1, 1, 12, 6))


def test_cron_match_dow():
    # Every Monday at 3am.
    cron = automation._parse_cron("0 3 * * 1")
    mon = dt.datetime(2026, 1, 5, 3, 0)  # Jan 5 2026 is a Monday
    tue = dt.datetime(2026, 1, 6, 3, 0)
    assert automation._matches(cron, mon)
    assert not automation._matches(cron, tue)
