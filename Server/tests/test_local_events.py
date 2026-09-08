"""Focused event freshness and cancellation contracts, using synthetic occurrences."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import uuid

import pytest
from sqlalchemy import text

from adventour_backend.services import local_event_service as events
from data_pipeline.ucf_events import normalize


def test_event_normalization_does_not_infer_public_admission_or_keep_description():
    now = datetime(2026,9,6,tzinfo=timezone.utc)
    source = events.sources()['ucf_main']
    venues = {'UCF Art Gallery': {'entity_id':'synthetic','lat':28.6027,'lon':-81.2038,'access':'Public'}}
    raw = {'eventinstance_id':'synthetic', 'title':'Test exhibition','starts':'Thu, 10 Sep 2026 17:00:00 -0400',
           'ends':'Thu, 10 Sep 2026 19:00:00 -0400','url':'https://events.ucf.edu/event/synthetic/',
           'location':'UCF Art Gallery','category':'Arts Exhibit','description':'Do not retain this text'}
    record, reason = normalize(raw, source, venues, now)
    assert reason is None and record['starts_at'].hour == 17
    assert record['expires_at'] == now+timedelta(hours=24)
    assert not {'description','contact_email','location_url'} & record.keys()
    for changes in ({'location':'Private studio'}, {'description':'Students only'},
                    {'title':'CANCELLED: Test exhibition'}, {'ends':raw['starts']}):
        assert normalize({**raw,**changes},source,venues,now)[0] is None
    assert normalize(raw,source,venues,now+timedelta(days=5))[0] is None


def test_event_expiry_failed_refresh_and_atomic_cancellation(monkeypatch):
    if os.getenv('ENV_FILE') != '.env.ingest-check':
        pytest.skip('Isolated database only')
    import app as backend
    from sqlalchemy.engine import make_url
    assert make_url(backend.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    source_id='test-'+uuid.uuid4().hex
    config={**events.sources()['ucf_main'],'source_id':source_id,'name':'Synthetic calendar'}
    now=datetime.now(timezone.utc)
    record={'source_id':source_id,'occurrence_id':'one','series_id':'series','title':'Synthetic event',
            'starts_at':now-timedelta(minutes=5),'ends_at':now+timedelta(hours=2),'timezone':'America/New_York',
            'metro':'orlando','category':'arts_culture','source_url':'https://events.ucf.edu/event/synthetic/',
            'official_url':'https://events.ucf.edu/event/synthetic/','access_note':'Test only','access_url':config['access_url'],
            'venue_name':'Synthetic venue','entity_id':None,'latitude':28.6027,'longitude':-81.2038,
            'h3_r8':__import__('h3').latlng_to_cell(28.6027,-81.2038,8),
            'verified_at':now,'expires_at':now+timedelta(hours=2)}
    local_day=now.astimezone(ZoneInfo('America/New_York')).date()
    report={'window_start':local_day.isoformat(),'window_days':14}
    with backend.app.app_context():
        try:
            events.replace_window(backend.db,source_id,config,[record],report,now)
            backend.db.session.commit()
            nearby = events.listing(backend.db,28.6027,-81.2038,now=now)['events']
            assert len([event for event in nearby if event['source_id'] == source_id]) == 1
            for latitude, longitude in ((29.5844,-81.2079), (40.7128,-74.006)):
                assert not [event for event in events.listing(backend.db, latitude, longitude, now=now)['events']
                            if event['source_id'] == source_id]
            assert not [event for event in events.listing(backend.db,28.6027,-81.2038,now=now+timedelta(hours=2))['events']
                        if event['source_id'] == source_id]
            # Longer occurrence expires at 24h even if it hasn't ended.
            extended={**record,'ends_at':now+timedelta(days=2),'expires_at':now+timedelta(hours=24)}
            events.replace_window(backend.db,source_id,config,[extended],report,now)
            backend.db.session.commit()
            assert not [event for event in events.listing(backend.db,28.6027,-81.2038,now=now+timedelta(hours=24))['events']
                        if event['source_id'] == source_id]
            from data_pipeline.refresh_events import refresh
            from data_pipeline import refresh_events
            monkeypatch.setattr(events,'sources',lambda:{source_id:config})
            monkeypatch.setattr(refresh_events, '_collect', lambda *_args: (_ for _ in ()).throw(TimeoutError()))
            monkeypatch.setattr('requests.sessions.Session.request',
                                lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('network forbidden')))
            before = backend.db.session.execute(text('SELECT verified_at,expires_at FROM local_event WHERE source_id=:s'),
                                                {'s':source_id}).one()
            source_before = backend.db.session.execute(text('SELECT last_success,last_attempt FROM event_source WHERE id=:s'),
                                                       {'s':source_id}).one()
            failed = refresh(backend,local_day,14)[source_id]
            assert failed == {'error': 'TimeoutError', 'freshness_renewed': False}
            after = backend.db.session.execute(text('SELECT verified_at,expires_at FROM local_event WHERE source_id=:s'),
                                               {'s':source_id}).one()
            source_after = backend.db.session.execute(text('SELECT last_success,last_attempt FROM event_source WHERE id=:s'),
                                                      {'s':source_id}).one()
            assert after == before and source_after.last_success == source_before.last_success
            assert source_after.last_attempt > source_before.last_attempt
            # Complete successful snapshot without occurrence removes it immediately.
            events.replace_window(backend.db,source_id,config,[],report,now)
            backend.db.session.commit()
            assert not [event for event in events.listing(backend.db,28.6027,-81.2038,now=now)['events']
                        if event['source_id'] == source_id]
        finally:
            backend.db.session.rollback()
            backend.db.session.execute(text('DELETE FROM local_event WHERE source_id=:s'),{'s':source_id})
            backend.db.session.execute(text('DELETE FROM event_source WHERE id=:s'),{'s':source_id})
            backend.db.session.commit()
