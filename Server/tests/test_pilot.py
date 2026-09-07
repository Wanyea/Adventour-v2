"""Real isolated Postgres: study boundaries, exact joins, retries and replay."""
from datetime import datetime, timezone
import os
import uuid
import pytest
from sqlalchemy import text


@pytest.fixture
def setup(monkeypatch):
    if os.getenv('ENV_FILE') != '.env.ingest-check':
        pytest.skip('Isolated ingestion database only')
    import app as backend
    from sqlalchemy.engine import make_url
    assert make_url(backend.app.config['SQLALCHEMY_DATABASE_URI']).database.startswith('adventour_ingest_check_')
    def forbidden(*args, **kwargs):
        raise AssertionError('Pilot deck made a provider call')
    monkeypatch.setattr('requests.sessions.Session.request', forbidden)
    client = backend.app.test_client()
    token = f'Bearer dev:pilot-{uuid.uuid4().hex[:8]}@adventour.local'
    normal = {'Authorization': token}
    study = 'test-' + uuid.uuid4().hex
    client.post('/onboarding', headers=normal, json={'initial_tags': ['coffee_sweets']})
    with backend.app.app_context():
        user_id = backend.db.session.execute(text('SELECT id FROM "user" WHERE firebase_uid=:uid'),
            {'uid': 'dev-' + token.split('dev:')[1].split('@')[0]}).scalar()
        backend.db.session.execute(text("INSERT INTO pilot_enrollment(pilot_id,user_id,participant_id,consent_version) VALUES(:p,:u,:id,'synthetic_test')"),
            {'p': study, 'u': user_id, 'id': str(uuid.uuid4())})
        backend.db.session.execute(text("INSERT INTO pilot_build(pilot_id,build_id) VALUES(:p,'test-build')"), {'p': study})
        backend.db.session.commit()
    headers = {**normal, 'X-Adventour-Pilot': study, 'X-Adventour-Build': 'test-build',
               'X-Adventour-Session': str(uuid.uuid4()), 'X-Adventour-Timezone': 'America/New_York'}
    body = {'location': {'latitude': 29.895, 'longitude': -81.313}, 'radius_meters': 3200,
            'constraints': {'limit': 3, 'avoid_chains': True}}
    yield backend, client, headers, normal, body, user_id
    with backend.app.app_context():
        backend.db.session.execute(text('DELETE FROM pilot_enrollment WHERE pilot_id=:p'), {'p': study})
        backend.db.session.execute(text('DELETE FROM pilot_build WHERE pilot_id=:p'), {'p': study})
        backend.db.session.commit()


def deck(client, headers, body):
    result = client.post('/api/recommendations', headers=headers, json=body)
    assert result.status_code == 200, result.json
    assert result.json['recommendations']
    return result.json['recommendations']


def test_standard_and_unapproved_build_do_not_capture(setup):
    backend, client, headers, normal, body, user = setup
    for h in (normal, {**headers, 'X-Adventour-Build': 'unknown'}):
        assert all('pilot_decision_id' not in p for p in deck(client, h, body))
    with backend.app.app_context():
        assert backend.db.session.execute(text('SELECT count(*) FROM pilot_request WHERE user_id=:u'), {'u': user}).scalar() == 0
    result = deck(client, headers, body)
    assert result[0]['pilot_decision_id']
    with backend.app.app_context():
        backend.db.session.execute(text('UPDATE pilot_enrollment SET active=false WHERE user_id=:u'), {'u': user})
        backend.db.session.commit()
    assert 'pilot_decision_id' not in deck(client, headers, body)[0]
    assert client.post(f"/api/pilot/decisions/{result[0]['pilot_decision_id']}/invite", headers=headers, json={}).status_code == 403


def test_answer_retry_correction_export_and_owned_replay(setup):
    from data_pipeline.pilot_admin import export, replay
    backend, client, headers, normal, body, user = setup
    item = deck(client, headers, body)[0]
    path = f"/api/pilot/decisions/{item['pilot_decision_id']}"
    assert client.post(path+'/invite', headers=normal, json={}).status_code == 403
    inv = client.post(path+'/invite', headers=headers, json={}).json['invitation']
    answer = {'id': str(uuid.uuid4()), 'invitation_id': inv['id'], 'answer_kind': 'rated',
              'value': 0, 'reason': 'timing', 'note': 'Coffee appeals; wrong day.',
              'duration_ms': 1500, 'occurred_at': datetime.now(timezone.utc).isoformat()}
    for _ in range(2):
        result = client.post(path+'/feedback', headers=headers, json=answer)
        assert result.status_code == 200, result.json
    assert client.post(path+'/feedback', headers=headers, json={**answer, 'value': 4}).status_code == 400
    correction = {**answer, 'id': str(uuid.uuid4()), 'supersedes': answer['id'], 'value': 3}
    assert client.post(path+'/feedback', headers=headers, json=correction).status_code == 200
    with backend.app.app_context():
        report = export(backend.db, headers['X-Adventour-Pilot'])
        assert len(report['requests']) == 1
        assert 'user_id' not in report['requests'][0]
        assert replay(report['requests'][0]['trace'])['matches']
        saved = next(d for d in report['decisions'] if d['id'] == item['pilot_decision_id'])
        assert [f['value'] for f in saved['feedback']] == [0, 3]
        assert saved['payload']['ranking_components'] == item['ranking_components']
        assert saved['core_decision_id'] == item['decision_id']


def test_sampling_skip_unknown_and_duplicate_exposure(setup, monkeypatch):
    from adventour_backend.services import pilot_feedback_service as feedback
    monkeypatch.setattr(feedback.secrets, 'randbelow', lambda _: 0)
    backend, client, headers, normal, body, user = setup
    items = deck(client, headers, body)
    path = f"/api/pilot/decisions/{items[0]['pilot_decision_id']}"
    signal = {'id': str(uuid.uuid4()), 'kind': 'view', 'duration_ms': 1000,
              'occurred_at': datetime.now(timezone.utc).isoformat()}
    assert client.post(path+'/signals', headers=headers, json={**signal, 'duration_ms': 500}).status_code == 400
    first = client.post(path+'/signals', headers=headers, json=signal)
    assert first.status_code == 200, first.json
    inv = first.json['invitation']
    assert inv and inv['source'] == 'sampled'
    assert client.post(path+'/signals', headers=headers, json=signal).json['invitation']['id'] == inv['id']
    next_path = f"/api/pilot/decisions/{items[1]['pilot_decision_id']}"
    assert client.post(next_path+'/signals', headers=headers, json={**signal, 'id': str(uuid.uuid4())}).json['invitation'] is None
    assert client.post(path+'/skip', headers=headers, json={'invitation_id': inv['id']}).status_code == 200
    unknown = {'id': str(uuid.uuid4()), 'invitation_id': inv['id'], 'answer_kind': 'unknown',
               'value': None, 'duration_ms': 500, 'occurred_at': signal['occurred_at']}
    assert client.post(path+'/feedback', headers=headers, json=unknown).status_code == 400
    voluntary = client.post(path+'/invite', headers=headers, json={}).json['invitation']
    unknown['invitation_id'] = voluntary['id']
    assert client.post(path+'/feedback', headers=headers, json=unknown).status_code == 200


def test_other_user_cannot_join_feedback_to_known_decision(setup):
    backend, client, headers, normal, body, user = setup
    ident = deck(client, headers, body)[0]['pilot_decision_id']
    other = {**headers, 'Authorization': f'Bearer dev:other-{uuid.uuid4().hex[:8]}@adventour.local'}
    client.post('/onboarding', headers=other, json={'initial_tags': []})
    with backend.app.app_context():
        other_id = backend.db.session.execute(text('SELECT id FROM "user" WHERE firebase_uid=:u'),
            {'u': 'dev-' + other['Authorization'].split('dev:')[1].split('@')[0]}).scalar()
        backend.db.session.execute(text("INSERT INTO pilot_enrollment(pilot_id,user_id,participant_id,consent_version) VALUES(:p,:u,:id,'synthetic_test')"),
            {'p': headers['X-Adventour-Pilot'], 'u': other_id, 'id': str(uuid.uuid4())})
        backend.db.session.commit()
    assert client.post(f'/api/pilot/decisions/{ident}/invite', headers=other, json={}).status_code == 403


def test_event_snapshot_is_not_replaced_by_later_listing(setup, monkeypatch):
    backend, client, headers, normal, body, user = setup
    from adventour_backend.services import local_event_service
    event = {'source_id': 'synthetic', 'occurrence_id': 'test', 'title': 'Test only',
             'starts_at': '2026-09-20T12:00:00-04:00', 'ends_at': '2026-09-20T13:00:00-04:00'}
    monkeypatch.setattr(local_event_service, 'listing', lambda *a, **k: {'events': [dict(event)], 'checked_at': datetime.now(timezone.utc).isoformat()})
    path = '/api/local-events?latitude=40.7&longitude=-74&radius_meters=1000'
    assert 'pilot_decision_id' not in client.get(path, headers=normal).json['events'][0]
    original = client.get(path, headers=headers).json['events'][0]
    event['title'] = 'Changed after serving'
    assert client.get(path, headers=headers).json['events'][0]['title'] != original['title']
    with backend.app.app_context():
        saved = backend.db.session.execute(text('SELECT payload FROM pilot_decision WHERE id=:id'), {'id': original['pilot_decision_id']}).scalar()
        assert saved['title'] == 'Test only'
