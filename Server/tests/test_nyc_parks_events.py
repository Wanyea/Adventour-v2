"""NYC publication age, access exclusions and recheck source dispatch."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from adventour_backend.services.local_event_service import sources
from data_pipeline import nyc_parks_events as nyc
from data_pipeline.event_adapters import adapter

NOW = datetime(2026, 9, 6, 20, tzinfo=timezone.utc)
PUBLISHED = NOW-timedelta(hours=8)
SOURCE = sources()['nyc_parks']


def occurrence():
    return {'guid': '123', 'title': 'Synthetic park concert', 'starttime': '2026-09-08 18:00:00',
        'endtime': '2026-09-08 19:00:00', 'link': {'url': 'https://www.nycgovparks.org/events/synthetic'},
        'coordinates': '40.7534, -73.9827', 'parkids': 'M008', 'parknames': 'Bryant Park',
        'location': 'Upper Terrace (in Bryant Park)', 'categories': 'Concerts',
        'description': 'Do not persist this prose', 'registration_description': 'Registration not required.',
        'image': {'url': 'https://example.com/image'}, 'contact_phone': 'test'}


def test_city_event_keeps_facts_and_publication_age_only():
    row, reason = nyc.normalize(occurrence(), SOURCE, PUBLISHED, NOW)
    assert reason is None and row['category'] == 'entertainment'
    assert row['verified_at'] == PUBLISHED and row['expires_at'] == PUBLISHED+timedelta(hours=24)
    assert row['starts_at'].utcoffset() == timedelta(hours=-4)
    assert row['entity_id'] is None and row['latitude'] == 40.7534
    assert not {'description', 'registration_description', 'image', 'contact_phone'} & row.keys()
    # A later fetch of the same version cannot extend its lifetime.
    later = nyc.normalize(occurrence(), SOURCE, PUBLISHED, NOW+timedelta(hours=2))[0]
    assert later['expires_at'] == row['expires_at']
    assert 'No registration required' in row['access_note']


@pytest.mark.parametrize('change', [
    {'title': 'CANCELED: Park concert'}, {'registration_description': 'Registration is closed.'},
    {'description': 'This is a private event'}, {'categories': 'Best for Kids'},
    {'coordinates': '28.6, -81.2'}, {'coordinates': 'nan, -74'}, {'parkids': 'M008 | M009'},
    {'endtime': '2026-09-08 05:00:00'},
])
def test_ineligible_city_event_is_excluded(change):
    assert nyc.normalize({**occurrence(), **change}, SOURCE, PUBLISHED, NOW)[0] is None


def test_stale_publication_or_truncated_feed_does_not_renew_freshness():
    def response(value):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)
    session = SimpleNamespace(get=lambda *a, **kw: response({'rowsUpdatedAt': (NOW-timedelta(hours=24)).timestamp()}))
    with pytest.raises(ValueError, match='stale'):
        nyc.publication(session, NOW)
    session.get = lambda *a, **kw: response([{}]*5000)
    with pytest.raises(ValueError, match='truncated'):
        nyc.read_rows(session)
    with pytest.raises(ValueError, match='schema'):
        nyc.normalize({}, SOURCE, PUBLISHED, NOW)


def test_recheck_uses_city_source_and_removes_missing_or_cancelled(monkeypatch):
    assert adapter(SOURCE) is nyc
    session = object()
    monkeypatch.setattr(nyc, 'session_for_source', lambda: session)
    monkeypatch.setattr(nyc, 'publication', lambda s, now: now)
    def read(s, **params):
        assert s is session and params == {'guid': '123'}
        return []
    monkeypatch.setattr(nyc, 'read_rows', read)
    assert nyc.recheck(None, SOURCE, {'occurrence_id': '123'}) is None
    monkeypatch.setattr(nyc, 'read_rows', lambda *a, **kw: [{**occurrence(), 'title': 'CANCELED: concert'}])
    assert nyc.recheck(None, SOURCE, {'occurrence_id': '123'}) is None
    with pytest.raises(ValueError, match='identity'):
        nyc.recheck(None, SOURCE, {'occurrence_id': '123 OR 1=1'})
