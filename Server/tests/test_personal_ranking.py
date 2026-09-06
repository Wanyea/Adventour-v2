"""Behavior contracts, not manufactured recommendation-quality labels."""

from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest
from adventour_backend.services import personal_ranking_service as ranking


def test_feedback_is_one_vote_per_entity_and_repeat_windows_expire():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    def event(entity, kind, days, value=None):
        return {'entity_id': entity, 'event_type': kind, 'event_value': value,
                'occurred_at': now-timedelta(days=days), 'tag_groups': ['coffee_sweets']}
    history = ranking.from_history(['coffee_sweets'], [
        event('a', 'rate', 1, 5), event('a', 'accept', 2), event('a', 'impression', 2),
        event('b', 'reject', 29), event('c', 'reject', 30), event('d', 'accept', 7),
        event('e', 'impression', .5), event('f', 'impression', 1)], now)
    assert history['hidden'] == {'a', 'b'}
    assert history['impressed'] == {'e'}
    assert history['counts']['coffee_sweets'] == 4
    assert history['feedback']['coffee_sweets'] == pytest.approx(-.5 / 7)
    place = ranking.score({'place_id': 'e', 'tag_groups': ['coffee_sweets'],
                           'distance_meters': 500}, history, 1000, 'regional')
    assert place['ranking_components']['interests'] == .5
    assert place['ranking_components']['repeat'] == -.1
    assert place['score'] == round(sum(place['ranking_components'].values()), 6)
    assert place['availability'] == 'unknown'


def test_case_variants_do_not_make_a_selected_region_ambiguous():
    from types import SimpleNamespace
    from adventour_backend.services import launch_service
    rows=[{'label':name,'region':'FL','lat':28.53,'lon':-81.37}
          for name in ('orlando','Orlando','ORLANDO')]
    result=SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:rows))
    db=SimpleNamespace(session=SimpleNamespace(execute=lambda *args,**kwargs:result))
    assert len(launch_service.suggestions(db,'Orlando')) == 1
    assert launch_service.resolve(db,'Orlando, FL')['latitude'] == 28.53


def test_personal_api_repeats_are_private_and_snapshot_survives(monkeypatch):
    if os.getenv('ENV_FILE') != '.env.ingest-check':
        pytest.skip('Isolated ingestion database only')
    import app as backend
    from sqlalchemy.engine import make_url
    assert make_url(backend.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    def forbidden(*args, **kwargs):
        raise AssertionError('Personal ranking made a provider call')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    client = backend.app.test_client()
    def identity(): return {'Authorization': f'Bearer dev:fit-{uuid.uuid4().hex[:8]}@adventour.local'}
    coffee, blank = identity(), identity()
    client.post('/onboarding', headers=coffee, json={'initial_tags': ['coffee_sweets']})
    request = {'location': {'latitude': 29.895, 'longitude': -81.313},
               'radius_meters': 3200, 'constraints': {'avoid_chains': True, 'limit': 50}}
    deck = client.post('/api/recommendations', headers=coffee, json=request).json['recommendations']
    assert deck and 'coffee_sweets' in deck[0]['tag_groups']
    place = deck[0]
    result = client.post('/api/events', headers=coffee, json={'place_id': place['place_id'],
        'decision_id': place['decision_id'], 'event_type': 'accept'})
    assert result.status_code == 201
    again = client.post('/api/recommendations', headers=coffee, json=request).json['recommendations']
    assert place['place_id'] not in {p['place_id'] for p in again}
    other = client.post('/api/recommendations', headers=blank, json=request).json['recommendations']
    assert place['place_id'] in {p['place_id'] for p in other}
    assert all(p['ranking_components']['interests'] == p['ranking_components']['feedback'] == 0 for p in other)
    saved = client.get('/api/profile/history', headers=coffee).json['places'][0]
    assert saved['ranking_components'] == place['ranking_components']
    assert saved['structural_score'] == place['structural_score']
    assert saved['model'] == ranking.MODEL
