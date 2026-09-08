"""UCF ICS parser and factual-normalization contracts."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from adventour_backend.services.local_event_service import sources
from data_pipeline import ucf_ics_events as ucf
from data_pipeline.event_adapters import adapter


SOURCE = {**sources()['ucf_main'], 'method': 'documented_ics_feed',
          'source_id': 'ucf_main', 'timezone': 'America/New_York'}
NOW = datetime(2026, 9, 6, 20, tzinfo=timezone.utc)
UID = 'https://events.ucf.edu/event/4200001/synthetic-exhibition/'


def calendar(event):
    return '\n'.join(['BEGIN:VCALENDAR', 'VERSION:2.0', 'BEGIN:VTIMEZONE',
        'TZID:America/New_York', 'END:VTIMEZONE', 'BEGIN:VEVENT', *event, 'END:VEVENT', 'END:VCALENDAR'])


def event(**changes):
    values = {
        'UID': UID, 'DTSTART': '20260910T170000', 'DTEND': '20260910T190000',
        'LOCATION': 'UCF Art Gallery', 'SUMMARY': 'Synthetic exhibition', 'URL': UID,
        'DESCRIPTION': 'Do not retain this prose',
    }
    values.update(changes)
    return [f'{key}:{value}' for key, value in values.items()]


def venues():
    return {'UCF Art Gallery': {'entity_id': 'synthetic', 'lat': 28.6027, 'lon': -81.2038,
                                'access': 'Public admission'}}


def test_documented_ics_occurrence_keeps_only_facts_and_stable_uid():
    raw = ucf.parse_calendar(calendar(event()), SOURCE)[0]
    raw['category'] = 'Arts Exhibit'
    record, reason = ucf.normalize(raw, SOURCE, venues(), NOW)
    assert reason is None
    assert record['occurrence_id'] == '4200001' and record['series_id'] == '4200001'
    assert record['starts_at'].utcoffset() == timedelta(hours=-4)
    assert record['category'] == 'arts_culture'
    assert record['expires_at'] == NOW + timedelta(hours=24)
    assert not {'description', 'contact_email', 'location_url'} & record.keys()


@pytest.mark.parametrize('change', [
    {'SUMMARY': 'CANCELED: Synthetic exhibition'}, {'DESCRIPTION': 'Students only'},
    {'STATUS': 'CANCELLED'},
    {'LOCATION': 'Private studio'}, {'DTEND': '20260910T170000'},
    {'URL': 'https://example.test/event/4200001/synthetic/'},
])
def test_ics_excludes_cancelled_restricted_or_invalid_occurrences(change):
    raw = ucf.parse_calendar(calendar(event(**change)), SOURCE)[0]
    raw['category'] = 'Arts Exhibit'
    assert ucf.normalize(raw, SOURCE, venues(), NOW)[0] is None


@pytest.mark.parametrize('lines, message', [
    (event(RRULE='FREQ=WEEKLY'), 'recurrence'),
    (event(DTSTART='20260910'), 'time format'),
    ([line for line in event() if not line.startswith('DTSTART:')] + ['DTSTART;TZID=America/Chicago:20260910T170000'], 'timezone'),
])
def test_ics_rejects_recurrence_and_unsupported_time_formats(lines, message):
    with pytest.raises(ValueError, match=message):
        ucf.parse_calendar(calendar(lines), SOURCE)


def test_collect_uses_documented_daily_ics_and_injected_bounded_session(monkeypatch):
    body = calendar(event())
    calls = []
    def get(url, timeout):
        calls.append((url, timeout))
        if url.endswith('.json'):
            return SimpleNamespace(json=lambda: [{'eventinstance_id': '4200001', 'category': 'Arts Exhibit'}],
                raise_for_status=lambda: None)
        if url.endswith('ticketing/'):
            return SimpleNamespace(text='The gallery is free and open to the public', raise_for_status=lambda: None)
        return SimpleNamespace(headers={'content-type': 'text/calendar'}, text=body, raise_for_status=lambda: None)
    session = SimpleNamespace(get=get)
    monkeypatch.setattr(ucf, '_locations', lambda db, source: venues())
    records, report = ucf.collect(None, SOURCE, date(2026, 9, 10), 1, session=session)
    assert calls == [('https://cah.ucf.edu/events/ticketing/', 20),
        ('https://events.ucf.edu/2026/9/10/feed.ics', 20), (UID+'feed.json', 20)]
    assert [row['occurrence_id'] for row in records] == ['4200001']
    assert report['counts'] == {'source_occurrences': 1, 'eligible': 1}
    assert adapter(SOURCE) is ucf
