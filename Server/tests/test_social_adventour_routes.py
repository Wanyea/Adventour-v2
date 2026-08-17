import json
import os
from datetime import datetime

os.environ["ADVENTOUR_DEV_AUTH"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app as server_app
from adventour_backend.models import AdventourSession, AdventourStop, Friendship, Place, User, db


def auth_headers(email):
    return {"Authorization": f"Bearer dev:{email}"}


def reset_db():
    with server_app.app.app_context():
        db.drop_all()
        db.create_all()


def test_friend_adventour_payload_and_take_preserve_planned_summary():
    reset_db()
    client = server_app.app.test_client()

    planned_summary = {
        "source": "planned_itinerary",
        "destination": "Test City",
        "route_readiness": {"label": "Strong route", "score": 0.91},
        "destination_scout": {
            "source": "destination_compare",
            "selected_destination": {
                "id": "test-city",
                "label": "Test City",
                "location": {"latitude": 37.422, "longitude": -122.084},
            },
            "scoring_profile": "authenticity_forward",
            "rank": {
                "trip_readiness_score": 0.93,
                "authenticity_score": 0.88,
            },
            "explanation": {
                "headline": "Best friend-ready local weekend.",
            },
        },
        "local_events": {
            "status": "ready",
            "events": [{"title": "Block Market", "reservation_url": "https://example.com/rsvp"}],
        },
        "booking_plan": {"summary": {"readiness_score": 0.88}},
        "trip_packet": {
            "status": "ready",
            "booking_links": [
                {
                    "label": "RSVP: Block Market",
                    "url": "https://example.com/rsvp",
                    "reservation_type": "event",
                },
            ],
            "save_prompts": [
                {
                    "label": "RSVP: Block Market",
                    "reservation_type": "event",
                },
            ],
        },
        "scenario_readiness": {
            "mode": "planned_itinerary",
            "status": "ready",
            "friend_readiness": {
                "status": "ready",
                "covered_members": 2,
                "total_members": 2,
            },
        },
        "launch_checklist": {
            "can_start": True,
            "headline": "Ready to launch.",
            "items": [{"id": "route_stops", "label": "Route stops", "status": "ready"}],
        },
    }

    with server_app.app.app_context():
        owner = User(firebase_uid="dev-owner", email="owner@example.com", username="owner", display_name="Owner")
        friend = User(firebase_uid="dev-friend", email="friend@example.com", username="friend", display_name="Friend")
        place = Place(canonical_name="Shared Stop", normalized_name="shared stop")
        db.session.add_all([owner, friend, place])
        db.session.flush()
        db.session.add(Friendship(user_id=owner.id, friend_id=friend.id, status="accepted"))
        source = AdventourSession(
            user_id=owner.id,
            title="Owner's Planned Route",
            status="completed",
            ended_at=datetime.utcnow(),
            summary_json=json.dumps(planned_summary),
        )
        db.session.add(source)
        db.session.flush()
        source_stop_metadata = {
            "source": "planned_itinerary",
            "display": {"name": "Shared Stop"},
            "slot_id": "morning_anchor",
            "why_this_stop": {
                "headline": "A friend-tested local favorite.",
                "reasons": ["Owner rated it highly", "Hidden-gem signal"],
            },
            "local_event_matches": [
                {
                    "title": "Block Market",
                    "reservation_url": "https://example.com/rsvp",
                },
            ],
            "alternatives": [
                {
                    "name": "Backup Market Cafe",
                    "provider": "mock",
                    "provider_place_id": "backup-market-cafe",
                    "swap_impact": {
                        "route_score_delta": 0.03,
                        "swap_decision": {"headline": "Easy friend-safe swap."},
                    },
                },
            ],
            "authenticity_evidence": {"label": "Hidden gem"},
            "diversity_groups": ["shops_markets", "food_drink"],
        }
        db.session.add(AdventourStop(
            session_id=source.id,
            place_id=place.id,
            order_index=0,
            status="completed",
            metadata_json=json.dumps(source_stop_metadata),
        ))
        db.session.commit()
        source_id = source.id
        source_stop_id = source.stops.first().id

    list_response = client.get(
        "/api/friends/adventours",
        headers=auth_headers("friend@example.com"),
    )
    assert list_response.status_code == 200
    listed = list_response.get_json()["adventours"][0]
    assert listed["summary"]["route_readiness"]["label"] == "Strong route"
    assert listed["summary"]["destination_scout"]["selected_destination"]["label"] == "Test City"
    assert listed["summary"]["destination_scout"]["rank"]["trip_readiness_score"] == 0.93
    assert listed["summary"]["launch_checklist"]["can_start"] is True
    assert listed["summary"]["local_events"]["events"][0]["title"] == "Block Market"
    assert listed["summary"]["trip_packet"]["booking_links"][0]["reservation_type"] == "event"
    assert listed["summary"]["scenario_readiness"]["friend_readiness"]["covered_members"] == 2
    assert listed["stops"][0]["metadata"]["why_this_stop"]["headline"] == "A friend-tested local favorite."
    assert listed["stops"][0]["metadata"]["alternatives"][0]["name"] == "Backup Market Cafe"

    take_response = client.post(
        f"/api/friends/adventours/{source_id}/take",
        headers=auth_headers("friend@example.com"),
    )
    assert take_response.status_code == 201
    taken = take_response.get_json()["adventour"]
    assert taken["summary"]["route_readiness"]["score"] == 0.91
    assert taken["summary"]["destination_scout"]["source"] == "destination_compare"
    assert taken["summary"]["destination_scout"]["selected_destination"]["label"] == "Test City"
    assert taken["summary"]["destination_scout"]["explanation"]["headline"] == "Best friend-ready local weekend."
    assert taken["summary"]["launch_checklist"]["headline"] == "Ready to launch."
    assert taken["summary"]["source_friend_adventour_id"] == source_id
    assert taken["summary"]["local_events"]["events"][0]["reservation_url"].endswith("/rsvp")
    assert taken["summary"]["trip_packet"]["save_prompts"][0]["label"] == "RSVP: Block Market"
    assert taken["summary"]["scenario_readiness"]["status"] == "ready"

    with server_app.app.app_context():
        copied_stop = AdventourStop.query.filter_by(session_id=taken["id"]).first()
        copied_metadata = json.loads(copied_stop.metadata_json)
        assert copied_metadata["why_this_stop"]["headline"] == "A friend-tested local favorite."
        assert copied_metadata["local_event_matches"][0]["title"] == "Block Market"
        assert copied_metadata["alternatives"][0]["swap_impact"]["route_score_delta"] == 0.03
        assert copied_metadata["authenticity_evidence"]["label"] == "Hidden gem"
        assert copied_metadata["source_friend_adventour_id"] == source_id
        assert copied_metadata["source_friend_stop_id"] == source_stop_id
        assert copied_metadata["source_friend_user_id"] == listed["owner"]["id"]
