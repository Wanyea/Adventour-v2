import os
from datetime import datetime, timedelta

os.environ["ADVENTOUR_DEV_AUTH"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app as server_app
from adventour_backend.models import Friendship, LocalEvent, LocalEventInterest, User, db


def auth_headers(email):
    return {"Authorization": f"Bearer dev:{email}"}


def reset_db():
    with server_app.app.app_context():
        db.drop_all()
        db.create_all()


def seed_user(email):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"dev-{username}",
        email=email,
        username=username,
        display_name=username,
    )
    db.session.add(user)
    db.session.flush()
    return user


def seed_event(title="Neighborhood Market", **overrides):
    payload = {
        "title": title,
        "description": "Local makers and food pop-ups.",
        "city": "Test City",
        "latitude": 37.423,
        "longitude": -122.084,
        "starts_at": datetime.utcnow() + timedelta(days=2),
        "category": "market",
        "source_name": "Community board",
        "source_url": "https://example.com/market",
        "reservation_url": "https://example.com/market/rsvp",
        "authenticity_score": 0.9,
    }
    payload.update(overrides)
    event = LocalEvent(**payload)
    db.session.add(event)
    db.session.flush()
    return event


def test_local_event_interest_upsert_delete_and_recommendation_payload():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com")
        friend = seed_user("friend@example.com")
        event = seed_event()
        db.session.add_all([
            Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"),
            LocalEventInterest(event_id=event.id, user_id=friend.id, status="interested"),
        ])
        db.session.commit()
        viewer_id = viewer.id
        friend_id = friend.id
        event_id = event.id

    going_response = client.post(
        f"/api/local-events/{event_id}/interest",
        headers=auth_headers("viewer@example.com"),
        json={"status": "going"},
    )

    assert going_response.status_code == 200
    social = going_response.get_json()["social"]
    assert social["viewer_status"] == "going"
    assert social["going_count"] == 1
    assert social["interested_count"] == 1

    recommendations = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
            "member_ids": [friend_id],
        },
    )

    assert recommendations.status_code == 200
    event_payload = recommendations.get_json()["events"][0]
    assert event_payload["source"]["kind"] == "community"
    assert event_payload["source"]["badge"] == "Community post"
    assert event_payload["social"]["viewer_status"] == "going"
    assert event_payload["social"]["going_count"] == 1
    assert event_payload["social"]["interested_count"] == 1
    assert event_payload["social"]["friend_interested_count"] == 1
    assert event_payload["social"]["friend_preview"][0]["display_name"] == "friend"
    assert event_payload["social"]["friend_candidates"][0]["display_name"] == "friend"
    assert event_payload["social"]["friend_candidates"][0]["status"] == "interested"
    assert event_payload["social"]["social_next_action"].startswith("Coordinate with friend")
    assert event_payload["score_components"]["social_signal"] >= 0.42
    assert "A friend is interested" in event_payload["explanation"]
    assert event_payload["event_story"]["social_ready"] is True
    assert "friend" in event_payload["event_story"]["headline"]
    assert any(metric["id"] == "social" for metric in event_payload["event_story"]["metrics"])
    assert event_payload["event_readiness"]["status"] == "ready"
    assert event_payload["event_readiness"]["score"] >= 0.7
    assert event_payload["event_readiness"]["checks"][0]["name"] == "source"
    assert any(check["name"] == "social" and check["status"] == "pass" for check in event_payload["event_readiness"]["checks"])
    assert recommendations.get_json()["summary"]["going_count"] == 1
    assert recommendations.get_json()["summary"]["friend_interested_count"] == 1
    assert recommendations.get_json()["summary"]["ready_event_count"] == 1
    assert recommendations.get_json()["summary"]["social_anchor_count"] == 1
    social_readiness = recommendations.get_json()["summary"]["social_readiness"]
    assert social_readiness["status"] == "ready"
    assert social_readiness["meetup_ready"] is True
    assert social_readiness["friend_signal_count"] == 1
    checklist = {item["id"]: item for item in social_readiness["meetup_checklist"]}
    assert social_readiness["blocking_count"] == 0
    assert checklist["event_anchor"]["status"] == "ready"
    assert checklist["social_signal"]["status"] == "ready"
    assert checklist["reservation"]["status"] == "ready"
    assert social_readiness["top_social_event"]["title"] == event_payload["title"]
    assert "Coordinate" in social_readiness["next_action"]
    event_plan = recommendations.get_json()["event_plan"]
    assert event_plan["status"] == "ready"
    assert event_plan["items"][0]["id"] == "top_event"
    assert event_plan["items"][0]["readiness_status"] == "ready"
    assert any(item["id"] == "friend_signal" and item["status"] == "social" for item in event_plan["items"])

    delete_response = client.delete(
        f"/api/local-events/{event_id}/interest",
        headers=auth_headers("viewer@example.com"),
    )

    assert delete_response.status_code == 200
    assert delete_response.get_json()["social"]["viewer_status"] is None
    assert delete_response.get_json()["social"]["going_count"] == 0

    with server_app.app.app_context():
        assert LocalEventInterest.query.filter_by(user_id=viewer_id).count() == 0


def test_local_event_recommendations_name_selected_friends_to_ask_for_signal():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com")
        friend = seed_user("mara@example.com")
        friend.display_name = "Mara"
        friend.profile_picture = "profpic_fox"
        event = seed_event("Neighborhood Art Walk")
        db.session.add(Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"))
        db.session.commit()
        friend_id = friend.id
        event_id = event.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["art"],
            "member_ids": [friend_id],
        },
    )

    assert response.status_code == 200
    event_payload = response.get_json()["events"][0]
    social = event_payload["social"]

    assert event_payload["id"] == event_id
    assert social["friend_interested_count"] == 0
    assert social["friend_going_count"] == 0
    assert social["friend_preview"] == []
    assert social["friend_candidates"] == [{
        "user_id": friend_id,
        "display_name": "Mara",
        "profile_picture": "profpic_fox",
        "status": None,
    }]
    assert social["social_next_action"] == (
        "Ask Mara to mark Interested or Going if this should become a meetup anchor."
    )
    assert response.get_json()["summary"]["social_readiness"]["status"] == "needs_signal"


def test_local_event_interest_rejects_unknown_status():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        seed_user("viewer@example.com")
        event = seed_event()
        db.session.commit()
        event_id = event.id

    response = client.post(
        f"/api/local-events/{event_id}/interest",
        headers=auth_headers("viewer@example.com"),
        json={"status": "maybe"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "status must be interested or going"


def test_local_event_source_metadata_and_mix_are_returned():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        seed_user("viewer@example.com")
        official = seed_event(
            "Official Night Market",
            source_name="Official City Calendar",
            source_url="https://events.city.gov/night-market",
            reservation_url="https://events.city.gov/night-market/rsvp",
        )
        seed_event(
            "Unsourced Pop-up",
            source_name=None,
            source_url=None,
            reservation_url=None,
            authenticity_score=0.9,
        )
        db.session.commit()
        official_id = official.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["events"][0]["id"] == official_id
    assert payload["events"][0]["source"]["kind"] == "official"
    assert payload["events"][0]["source"]["badge"] == "Official source"
    assert payload["events"][0]["source"]["domain"] == "events.city.gov"
    assert payload["events"][0]["score_components"]["source_quality"] > 0.9
    assert payload["events"][0]["event_readiness"]["status"] == "ready"
    assert payload["events"][0]["event_readiness"]["headline"] == "Bookable local event with enough confidence to save."
    assert payload["summary"]["source_mix"]["official"] == 1
    assert payload["summary"]["source_mix"]["unsourced"] == 1
    assert payload["summary"]["source_summary"]["trusted_source_count"] == 1
    assert payload["summary"]["source_summary"]["unsourced_count"] == 1
    assert payload["summary"]["source_summary"]["reservation_ready_count"] == 1
    assert payload["summary"]["source_summary"]["source_badges"][0] == {
        "kind": "official",
        "badge": "Official source",
        "count": 1,
    }
    assert payload["summary"]["source_summary"]["message"] == "Local event picks include trusted sources and reservation links."
    assert payload["event_plan"]["headline"] == "Local event plan is ready to save or reserve."
    assert payload["event_plan"]["items"][0]["reservation_url"].endswith("/rsvp")
    source_links = payload["external_sources"]
    assert source_links[1]["label"] == "Local calendars"
    assert source_links[1]["url"].startswith("https://www.google.com/search?q=")
    assert "Test+City" in source_links[1]["url"]
    assert source_links[2]["source_type"] == "official_search"


def test_local_event_ranking_prefers_bookable_social_anchor_over_merely_close_listing():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com")
        friend = seed_user("friend@example.com")
        close_unsourced = seed_event(
            "Close Unsourced Pop-up",
            latitude=37.423,
            longitude=-122.084,
            source_name=None,
            source_url=None,
            reservation_url=None,
            authenticity_score=0.95,
        )
        anchor = seed_event(
            "Friend-Backed Night Market",
            latitude=37.468,
            longitude=-122.084,
            source_name="Official City Calendar",
            source_url="https://events.city.gov/night-market",
            reservation_url="https://events.city.gov/night-market/rsvp",
            authenticity_score=0.82,
        )
        db.session.add_all([
            Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"),
            LocalEventInterest(event_id=anchor.id, user_id=friend.id, status="interested"),
        ])
        db.session.commit()
        friend_id = friend.id
        anchor_id = anchor.id
        close_id = close_unsourced.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
            "member_ids": [friend_id],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["events"][0]["id"] == anchor_id
    assert payload["events"][1]["id"] == close_id
    assert payload["events"][0]["score_components"]["event_anchor_score"] > payload["events"][1]["score_components"]["event_anchor_score"]
    assert payload["events"][1]["score_components"]["baseline_score"] > payload["events"][0]["score_components"]["baseline_score"]
    assert payload["events"][0]["event_readiness"]["status"] == "ready"
    assert payload["events"][0]["event_story"]["social_ready"] is True
    assert payload["summary"]["social_readiness"]["status"] == "ready"
    assert payload["summary"]["social_readiness"]["friend_signal_count"] == 1


def test_local_blog_event_with_friend_signal_still_needs_freshness_confirmation():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com")
        friend = seed_user("friend@example.com")
        event = seed_event(
            "Blog-Loved Makers Crawl",
            source_name="Local Food Blog",
            source_url="https://localblog.example.com/makers-crawl",
            reservation_url=None,
            authenticity_score=0.9,
        )
        db.session.add_all([
            Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"),
            LocalEventInterest(event_id=event.id, user_id=friend.id, status="interested"),
        ])
        db.session.commit()
        friend_id = friend.id
        event_id = event.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
            "member_ids": [friend_id],
        },
    )

    assert response.status_code == 200
    event_payload = response.get_json()["events"][0]
    freshness_check = next(
        check for check in event_payload["event_readiness"]["checks"]
        if check["name"] == "freshness"
    )

    assert event_payload["id"] == event_id
    assert event_payload["source"]["kind"] == "local_blog"
    assert event_payload["score_components"]["source_freshness"] < 0.75
    assert event_payload["event_readiness"]["status"] == "needs_confirmation"
    assert freshness_check["status"] == "warn"
    assert event_payload["event_readiness"]["next_action"].startswith("Open the source and confirm the date")
    assert "Confirm the event date" in event_payload["event_story"]["cautions"][0]


def test_local_event_empty_results_still_return_actionable_external_sources():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        seed_user("viewer@example.com")
        db.session.commit()

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 40.7128, "longitude": -74.0060},
            "radius_meters": 8000,
            "destination_label": "New York, NY",
            "preference_tags": ["market", "music"],
            "date_window": {"start": "2026-07-03", "end": "2026-07-06"},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "empty"
    assert payload["events"] == []
    assert payload["event_plan"]["status"] == "needs_scouting"
    assert payload["event_plan"]["items"][0]["id"] == "recommended_external_source"
    assert payload["event_plan"]["items"][0]["source_type"] == "market_popup_search"
    assert payload["event_plan"]["items"][0]["source_url"].startswith("https://www.google.com/search?q=")
    assert any(
        item["id"] == "external_official_search" and item["source_url"].startswith("https://www.google.com/search?q=")
        for item in payload["event_plan"]["items"]
    )
    assert payload["summary"]["source_summary"]["actionable_external_source_count"] >= 4
    assert payload["summary"]["source_summary"]["message"] == (
        "No saved local events found yet, but Adventour has date-aware external sources to scout."
    )
    scouting_brief = payload["summary"]["source_summary"]["scouting_brief"]
    assert scouting_brief["status"] == "needs_event_anchor"
    assert scouting_brief["headline"] == "Scout a local event anchor."
    assert scouting_brief["recommended_source"]["source_type"] == "market_popup_search"
    assert scouting_brief["blocking_count"] == 2
    assert [gap["id"] for gap in scouting_brief["missing"]] == ["event_anchor", "source", "reservation"]
    assert payload["summary"]["social_readiness"]["status"] == "needs_scouting"
    assert payload["summary"]["social_readiness"]["meetup_ready"] is False
    empty_checklist = {item["id"]: item for item in payload["summary"]["social_readiness"]["meetup_checklist"]}
    assert payload["summary"]["social_readiness"]["blocking_count"] >= 2
    assert empty_checklist["event_anchor"]["blocking"] is True
    assert empty_checklist["social_signal"]["blocking"] is True
    assert payload["external_sources"][1]["url"].startswith("https://www.google.com/search?q=")
    assert "New+York%2C+NY" in payload["external_sources"][1]["url"]
    assert "market+music" in payload["external_sources"][1]["url"]
    assert payload["external_sources"][1]["query"].startswith("New York, NY local events")
    assert payload["external_sources"][2]["source_type"] == "official_search"
    assert payload["external_sources"][3]["source_type"] == "market_popup_search"
    assert payload["external_sources"][4]["reservation_hint"]


def test_local_event_readiness_marks_weak_lead_for_research():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        seed_user("viewer@example.com")
        weak = seed_event(
            "Unsourced Maybe Pop-up",
            source_name=None,
            source_url=None,
            reservation_url=None,
            authenticity_score=0.55,
        )
        db.session.commit()
        weak_id = weak.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    event_payload = payload["events"][0]
    assert event_payload["id"] == weak_id
    assert event_payload["event_readiness"]["status"] == "research"
    assert event_payload["event_readiness"]["next_action"].startswith("Find a stronger")
    assert any(check["name"] == "source" and check["status"] == "fail" for check in event_payload["event_readiness"]["checks"])
    assert payload["summary"]["ready_event_count"] == 0
    social_checklist = {item["id"]: item for item in payload["summary"]["social_readiness"]["meetup_checklist"]}
    assert payload["summary"]["social_readiness"]["status"] == "needs_signal"
    assert social_checklist["event_anchor"]["status"] == "ready"
    assert social_checklist["source"]["blocking"] is True
    assert social_checklist["social_signal"]["blocking"] is True
    assert payload["event_plan"]["status"] == "needs_scouting"
    assert payload["event_plan"]["items"][0]["readiness_status"] == "research"


def test_local_event_scouting_brief_prioritizes_reservation_research():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com")
        friend = seed_user("friend@example.com")
        event = seed_event(
            "Local Blog Night Market",
            source_name="Local Food Blog",
            source_url="https://localblog.example.com/night-market",
            reservation_url=None,
        )
        db.session.add_all([
            Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"),
            LocalEventInterest(event_id=event.id, user_id=friend.id, status="interested"),
        ])
        db.session.commit()
        friend_id = friend.id

    response = client.post(
        "/api/local-events/recommendations",
        headers=auth_headers("viewer@example.com"),
        json={
            "location": {"latitude": 37.423, "longitude": -122.084},
            "radius_meters": 8000,
            "preference_tags": ["market"],
            "member_ids": [friend_id],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    scouting_brief = payload["summary"]["source_summary"]["scouting_brief"]
    assert scouting_brief["status"] == "needs_booking_link"
    assert scouting_brief["headline"] == "Find RSVP or ticket details."
    assert scouting_brief["recommended_source"]["source_type"] == "event_platform_search"
    assert scouting_brief["goal"] == "find_bookable_event_anchor"
    assert any(gap["id"] == "reservation" and gap["blocking"] is True for gap in scouting_brief["missing"])
    assert "RSVP" in scouting_brief["next_action"]
