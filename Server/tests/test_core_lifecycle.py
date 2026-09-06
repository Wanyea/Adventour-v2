"""Real Postgres/API contract for the agreed core loop; isolated dev identity only."""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url


def test_served_snapshot_owned_stop_and_trip_lifecycle(monkeypatch):
    if os.getenv("ENV_FILE") != ".env.ingest-check":
        pytest.skip("Run with ENV_FILE=.env.ingest-check against the isolated ingestion database")
    import app as backend
    assert make_url(backend.app.config["SQLALCHEMY_DATABASE_URI"]).database.startswith("adventour_ingest_check_")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-must-never-be-called")
    def forbidden(*args, **kwargs):
        raise AssertionError("A provider request occurred while building an owned deck")
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    client = backend.app.test_client()
    email = f"core-test-{uuid.uuid4().hex[:8]}@adventour.local"
    headers = {"Authorization": f"Bearer dev:{email}"}
    assert client.get('/user/' + 'dev-' + email.split('@')[0]).status_code == 401
    assert client.get('/user/someone-else', headers=headers).status_code == 403
    assert client.put('/user/profile', headers=headers, json={'date_of_birth': '2020-01-01'}).status_code == 400
    assert client.post('/onboarding', headers=headers, json={'initial_tags': ['coffee_sweets', 'outdoors']}).status_code == 200
    assert client.post('/onboarding', headers=headers, json={'initial_tags': [{}]}).status_code == 400
    request = {"location": {"latitude": 29.895, "longitude": -81.313},
               "constraints": {"limit": 20, "avoid_chains": True}}
    result = client.post("/api/recommendations", headers=headers, json=request)
    assert result.status_code == 200
    place = result.json["recommendations"][0]
    event = {"place_id": place["place_id"], "decision_id": place["decision_id"], "event_type": "impression"}
    other = {"Authorization": f"Bearer dev:other-{uuid.uuid4().hex[:8]}@adventour.local"}
    assert client.post("/api/events", headers=other, json=event).status_code == 400
    with backend.app.app_context():
        old_score = backend.db.session.execute(text("SELECT authenticity FROM places WHERE id=:id"),
                                               {"id": place["provider_place_id"]}).scalar_one()
        backend.db.session.execute(text("UPDATE places SET authenticity=.321 WHERE id=:id"),
                                   {"id": place["provider_place_id"]})
        backend.db.session.commit()
    try:
        for _ in range(2):
            recorded = client.post("/api/events", headers=headers, json=event)
            assert recorded.status_code == 201
            assert recorded.json["event"]["score_snapshot"] == place["score"]
        session = client.post("/api/adventours", headers=headers, json={"title": "Synthetic core verification"}).json["adventour"]
        stop_result = client.post(f"/api/adventours/{session['id']}/stops", headers=headers, json={
            "place_id": place["place_id"], "decision_id": place["decision_id"],
            "provider": "google", "display": {"name": "UNTRUSTED DISPLAY SENTINEL", "rating": 5},
        })
        assert stop_result.status_code == 201
        replay = client.post(f"/api/adventours/{session['id']}/stops", headers=headers, json={
            "place_id": place["place_id"], "decision_id": place["decision_id"]})
        assert replay.status_code == 200 and replay.json["stop"]["id"] == stop_result.json["stop"]["id"]
        stop = stop_result.json["stop"]
        assert stop["display"]["name"] == place["name"]
        assert stop["display"]["rating"] is None
        path = f"/api/adventours/{session['id']}/stops/{stop['id']}"
        assert client.post(path + "/complete", headers=headers, json={"rating": 4}).status_code == 409
        assert client.post(path + "/navigate", headers=headers).status_code == 200
        assert client.post(path + "/arrive", headers=headers).status_code == 200
        rated = client.post(path + "/complete", headers=headers, json={"rating": 4, "notes": "Synthetic review; not preference ground truth"})
        assert rated.status_code == 200
        assert rated.json["stop"]["notes"].startswith("Synthetic")
        completed = client.post(f"/api/adventours/{session['id']}/complete", headers=headers)
        assert completed.status_code == 200 and completed.json["adventour"]["summary"]["stop_count"] == 1
        history = client.get('/api/profile/history', headers=headers)
        assert history.status_code == 200
        assert history.json['places'][0]['own_review'] == 'Synthetic review; not preference ground truth'
        assert history.json['places'][0]['score'] == place['score']
        assert client.post("/api/events", headers=headers, json={**event, "event_type": "reject"}).status_code == 400
        with backend.app.app_context():
            rows = backend.db.session.execute(text("""SELECT event_type,score_snapshot,test_activity
                FROM place_event WHERE decision_id=:id"""), {"id": place["decision_id"]}).all()
            assert {r[0] for r in rows} == {"impression", "accept", "save", "navigate", "arrival", "rate"}
            assert len(rows) == 6 and all(r[1] == place["score"] and r[2] for r in rows)
            review = backend.PlaceRating.query.filter_by(place_id=place["place_id"], rating=4).filter(
                backend.PlaceRating.review == "Synthetic review; not preference ground truth").first()
            assert review is not None
    finally:
        with backend.app.app_context():
            backend.db.session.execute(text("UPDATE places SET authenticity=:score WHERE id=:id"),
                                       {"score": old_score, "id": place["provider_place_id"]})
            backend.db.session.commit()


def test_provider_accept_gate_quota_and_id_only_suppression(monkeypatch):
    if os.getenv("ENV_FILE") != ".env.ingest-check":
        pytest.skip("Isolated database only")
    import app as backend
    assert make_url(backend.app.config["SQLALCHEMY_DATABASE_URI"]).database.startswith("adventour_ingest_check_")
    client = backend.app.test_client()
    headers = {"Authorization": f"Bearer dev:provider-test-{uuid.uuid4().hex[:8]}@adventour.local"}
    request = {"location": {"latitude": 29.895, "longitude": -81.313}, "constraints": {"avoid_chains": True}}
    places = client.post('/api/recommendations', headers=headers, json=request).json['recommendations']
    place, other = places[:2]
    url = '/api/places/details?place_id=' + place['place_id']
    assert client.get(url, headers=headers).status_code == 400
    for selected in (place, other):
        assert client.post('/api/events', headers=headers, json={"place_id": selected['place_id'],
            "decision_id": selected['decision_id'], "event_type": "accept"}).status_code == 201
    monkeypatch.setenv('GOOGLE_API_KEY', 'test-key')
    monkeypatch.setenv('GOOGLE_DAILY_CALL_LIMIT', '2')
    google_id = 'synthetic-' + uuid.uuid4().hex
    calls = []
    class Response:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload
    def provider(method, url, **kwargs):
        calls.append(method)
        if method == 'POST':
            return Response({'places': [{'id': google_id}]})
        return Response({'id': google_id, 'displayName': {'text': place['name']},
            'location': {'latitude': place['latitude'], 'longitude': place['longitude']},
            'businessStatus': 'CLOSED_PERMANENTLY', 'formattedAddress': 'PROVIDER CONTENT SENTINEL'})
    monkeypatch.setattr('requests.request', provider)
    try:
        checked = client.get(url, headers=headers)
        assert checked.status_code == 200 and checked.json['verification'] == 'suppressed'
        assert set(checked.json) == {'place_id', 'google_place_id', 'verification'}
        assert checked.headers['Cache-Control'] == 'no-store'
        assert calls == ['POST', 'GET']
        denied = client.get('/api/places/details?place_id=' + other['place_id'], headers=headers)
        assert denied.json['verification'] == 'unavailable' and len(calls) == 2
        next_deck = client.post('/api/recommendations', headers=headers, json=request).json['recommendations']
        assert place['place_id'] not in {p['place_id'] for p in next_deck}
        with backend.app.app_context():
            columns = backend.db.session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='suppressed_place'")).scalars().all()
            assert set(columns) == {'google_place_id', 'suppressed_at'}
    finally:
        # Remove only this test's synthetic provider IDs; keep test events for audit.
        with backend.app.app_context():
            backend.db.session.execute(text('DELETE FROM suppressed_place WHERE google_place_id=:id'), {'id': google_id})
            backend.db.session.execute(text('DELETE FROM place_provider_ref WHERE google_place_id=:id'), {'id': google_id})
            backend.db.session.commit()
