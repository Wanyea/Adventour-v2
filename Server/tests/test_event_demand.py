from datetime import date

from adventour_backend.services.event_demand_service import work_key


def test_work_key_is_stable_for_coalescing():
    assert work_key('8928308280fffff', date(2026, 9, 9), 14) == \
        'events:8928308280fffff:2026-09-09:14'
