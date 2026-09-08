"""Isolated-Postgres contracts for owned regional event persistence."""

from datetime import datetime, timedelta, timezone
import os
import uuid
from zoneinfo import ZoneInfo

import pytest


def _backend():
    if os.getenv('ENV_FILE') != '.env.ingest-check':
        pytest.skip('Run only with ENV_FILE=.env.ingest-check')
    pytest.importorskip('h3')
    import app
    from sqlalchemy.engine import make_url
    assert make_url(app.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    from adventour_backend.services import local_event_service as events
    return app, events


def _config(name='Synthetic source'):
    return {'name': name, 'metro': 'test_metro', 'permission_url': 'https://example.test/terms',
            'timezone': 'America/New_York', 'parser_version': 'synthetic_v1', 'max_age_hours': 24}


def _record(source, occurrence, now, **change):
    import h3
    start = now+timedelta(hours=1)
    record = {**{'source_id': source, 'occurrence_id': occurrence, 'series_id': occurrence,
                 'title': 'Community  Run', 'starts_at': start, 'ends_at': start+timedelta(hours=1),
                 'timezone': 'America/New_York', 'metro': 'test_metro', 'category': 'wellness',
                 'source_url': 'https://example.test/event/'+occurrence,
                 'official_url': 'https://example.test/event/'+occurrence, 'access_note': 'Synthetic only',
                 'access_url': 'https://example.test/terms', 'venue_name': 'Test Park', 'entity_id': 'park-1',
                 'latitude': 28.5383, 'longitude': -81.3792,
                 'h3_r8': h3.latlng_to_cell(28.5383, -81.3792, 8),
                 'verified_at': now, 'expires_at': start+timedelta(hours=1)}, **change}
    if {'latitude', 'longitude'} & change.keys() and 'h3_r8' not in change:
        record['h3_r8'] = h3.latlng_to_cell(record['latitude'], record['longitude'], 8)
    return record


def test_replace_is_idempotent_and_records_config_provenance():
    backend, events = _backend()
    from sqlalchemy import text
    source, now = 'region-'+uuid.uuid4().hex, datetime.now(timezone.utc)
    report = {'window_start': now.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'window_days': 14}
    with backend.app.app_context():
        try:
            first = _config()
            first.pop('timezone')
            with pytest.raises(ValueError, match='time bounds'):
                events.replace_window(backend.db, source, first,
                                      [_record(source, 'future', now, verified_at=now+timedelta(seconds=1))], report, now)
            events.replace_window(backend.db, source, first, [_record(source, 'one', now)], report, now)
            renamed = _config('Renamed source')
            renamed.pop('timezone')
            events.replace_window(backend.db, source, renamed, [_record(source, 'one', now)], report, now)
            backend.db.session.commit()
            row = backend.db.session.execute(text('SELECT name,metro,report FROM event_source WHERE id=:id'), {'id': source}).mappings().one()
            assert row['name'] == 'Renamed source' and row['report']['source_config'] == {
                'parser_version': 'synthetic_v1', 'timezone': 'America/New_York'}
            assert backend.db.session.execute(text('SELECT count(*) FROM local_event WHERE source_id=:id'), {'id': source}).scalar_one() == 1
        finally:
            backend.db.session.rollback()
            backend.db.session.execute(text('DELETE FROM local_event WHERE source_id=:id'), {'id': source})
            backend.db.session.execute(text('DELETE FROM event_source WHERE id=:id'), {'id': source})
            backend.db.session.commit()


def test_listing_collapses_equivalent_sources_and_does_not_touch_http(monkeypatch):
    backend, events = _backend()
    from sqlalchemy import text
    left, right, third, now = ('region-'+uuid.uuid4().hex, 'region-'+uuid.uuid4().hex,
                               'region-'+uuid.uuid4().hex, datetime.now(timezone.utc))
    report = {'window_start': now.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'window_days': 14}
    with backend.app.app_context():
        try:
            events.replace_window(backend.db, left, _config('First'), [_record(left, 'one', now, entity_id=None)], report, now)
            events.replace_window(backend.db, right, _config('Second'), [_record(right, 'two', now, title=' Community Run ')], report, now)
            events.replace_window(backend.db, third, _config('Third'), [_record(third, 'three', now,
                                  latitude=28.53831, longitude=-81.37921)], report, now)
            backend.db.session.commit()
            monkeypatch.setattr(events, 'sources', lambda: (_ for _ in ()).throw(AssertionError('listing requested source input')))
            result = events.listing(backend.db, 28.5383, -81.3792, radius=1000, now=now)
            assert len(result['events']) == 1 and [s['name'] for s in result['events'][0]['sources']] == ['First', 'Second', 'Third']
            assert events.listing(backend.db, 0, 0, radius=1000, now=now)['events'] == []
        finally:
            backend.db.session.rollback()
            for source in (left, right, third):
                backend.db.session.execute(text('DELETE FROM local_event WHERE source_id=:id'), {'id': source})
                backend.db.session.execute(text('DELETE FROM event_source WHERE id=:id'), {'id': source})
            backend.db.session.commit()


def test_invalid_or_stale_batch_cannot_partially_replace_window():
    backend, events = _backend()
    from sqlalchemy import text
    source, now = 'region-'+uuid.uuid4().hex, datetime.now(timezone.utc)
    report = {'window_start': now.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'window_days': 14}
    with backend.app.app_context():
        try:
            good = _record(source, 'good', now)
            events.replace_window(backend.db, source, _config(), [good], report, now)
            backend.db.session.commit()
            with pytest.raises(ValueError, match='source_id'):
                events.replace_window(backend.db, source, _config(), [good, _record('other', 'bad', now)], report, now)
            with pytest.raises(ValueError, match='expired'):
                events.replace_window(backend.db, source, _config(), [_record(source, 'stale', now, expires_at=now)], report, now)
            assert backend.db.session.execute(text('SELECT occurrence_id FROM local_event WHERE source_id=:id'), {'id': source}).scalar_one() == 'good'
        finally:
            backend.db.session.rollback()
            backend.db.session.execute(text('DELETE FROM local_event WHERE source_id=:id'), {'id': source})
            backend.db.session.execute(text('DELETE FROM event_source WHERE id=:id'), {'id': source})
            backend.db.session.commit()
