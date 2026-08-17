import json
import os

os.environ["ADVENTOUR_DEV_AUTH"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app as server_app
from adventour_backend.models import AdventourSession, AdventourStop, Place, PlaceProviderRef, TravelReservation, User, UserPlaceEvent, db


def auth_headers(email):
    return {"Authorization": f"Bearer dev:{email}"}


def reset_db():
    with server_app.app.app_context():
        db.drop_all()
        db.create_all()


def create_user_with_session(email="booker@example.com", title="Reservation Route"):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"dev-{username}",
        email=email,
        username=username,
        display_name=username,
    )
    db.session.add(user)
    db.session.flush()
    session = AdventourSession(user_id=user.id, title=title)
    db.session.add(session)
    db.session.commit()
    return user, session


def test_reservation_crud_and_adventour_history_payload():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        _, session = create_user_with_session()
        session.summary_json = json.dumps({
            "price_breakdown": {"party_size": 2},
            "booking_plan": {
                "components": [
                    {
                        "id": "stay",
                        "type": "stay",
                        "label": "Stay",
                        "status": "manual",
                        "stores_reservation": True,
                    },
                    {
                        "id": "event",
                        "type": "event_or_place",
                        "label": "Tickets and reservations",
                        "status": "manual",
                        "stores_reservation": True,
                    },
                ],
            },
            "trip_packet": {
                "status": "ready",
                "headline": "This Adventour has a clear booking packet.",
                "booking_command_center": {
                    "status": "ready",
                    "commands": [],
                },
            },
        })
        db.session.commit()
        session_id = session.id

    create_response = client.post(
        "/api/reservations",
        headers=auth_headers("booker@example.com"),
        json={
            "adventour_session_id": session_id,
            "reservation_type": "stay",
            "title": "Austin Hotel",
            "provider": "Manual",
            "confirmation_code": "HOTEL123",
            "starts_at": "2026-07-10T15:00:00Z",
            "ends_at": "2026-07-12T11:00:00Z",
            "cost_total": "420.75",
            "booking_url": "https://example.com/hotel",
            "metadata": {"source": "beta-test"},
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()["reservation"]
    assert created["reservation_type"] == "stay"
    assert created["cost_total"] == 420.75
    assert created["metadata"] == {"source": "beta-test"}
    created_adventour = create_response.get_json()["adventour"]
    assert created_adventour["id"] == session_id
    assert created_adventour["summary"]["trip_packet"]["reservation_coverage"]["saved_count"] == 1

    with server_app.app.app_context():
        refreshed_session = db.session.get(AdventourSession, session_id)
        summary = server_app.parse_json_object(refreshed_session.summary_json)
        assert summary["booking_summary"]["reservation_count"] == 1
        assert summary["trip_packet"]["reservation_coverage"]["saved_count"] == 1
        assert summary["trip_packet"]["reservation_coverage"]["missing_labels"] == ["Tickets/events"]
        assert summary["trip_packet"]["booking_command_center"]["primary_action"]["label"] == "Save Tickets/events"

    list_response = client.get(
        f"/api/reservations?session_id={session_id}",
        headers=auth_headers("booker@example.com"),
    )
    assert list_response.status_code == 200
    assert [item["title"] for item in list_response.get_json()["reservations"]] == ["Austin Hotel"]

    history_response = client.get(
        "/api/adventours/history",
        headers=auth_headers("booker@example.com"),
    )
    assert history_response.status_code == 200
    history_reservation = history_response.get_json()["adventours"][0]["reservations"][0]
    assert history_reservation["confirmation_code"] == "HOTEL123"
    assert history_reservation["booking_url"] == "https://example.com/hotel"

    update_response = client.patch(
        f"/api/reservations/{created['id']}",
        headers=auth_headers("booker@example.com"),
        json={"confirmation_code": "UPDATED123", "cost_total": ""},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()["reservation"]
    assert updated["confirmation_code"] == "UPDATED123"
    assert updated["cost_total"] is None
    updated_adventour = update_response.get_json()["adventour"]
    assert updated_adventour["summary"]["booking_summary"]["known_cost_count"] == 0
    assert updated_adventour["summary"]["trip_packet"]["reservation_coverage"]["confirmed_count"] == 1

    with server_app.app.app_context():
        refreshed_session = db.session.get(AdventourSession, session_id)
        summary = server_app.parse_json_object(refreshed_session.summary_json)
        assert summary["booking_summary"]["confirmation_count"] == 1
        assert summary["booking_summary"]["known_cost_count"] == 0
        assert summary["trip_packet"]["reservation_coverage"]["confirmed_count"] == 1

    delete_response = client.delete(
        f"/api/reservations/{created['id']}",
        headers=auth_headers("booker@example.com"),
    )
    assert delete_response.status_code == 200
    deleted_adventour = delete_response.get_json()["adventour"]
    assert deleted_adventour["summary"]["booking_summary"]["reservation_count"] == 0
    assert deleted_adventour["summary"]["trip_packet"]["reservation_coverage"]["saved_count"] == 0

    with server_app.app.app_context():
        assert TravelReservation.query.count() == 0
        refreshed_session = db.session.get(AdventourSession, session_id)
        summary = server_app.parse_json_object(refreshed_session.summary_json)
        assert summary["booking_summary"]["reservation_count"] == 0
        assert summary["trip_packet"]["reservation_coverage"]["saved_count"] == 0
        assert summary["trip_packet"]["reservation_coverage"]["missing_labels"] == ["Stay", "Tickets/events"]


def test_reservation_cannot_attach_to_another_users_adventour():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        create_user_with_session("owner@example.com")
        _, other_session = create_user_with_session("other@example.com", "Other Route")
        other_session_id = other_session.id

    response = client.post(
        "/api/reservations",
        headers=auth_headers("owner@example.com"),
        json={
            "adventour_session_id": other_session_id,
            "reservation_type": "flight",
            "title": "Not Mine",
        },
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Adventour session not found"


def test_planned_adventour_stop_can_be_swapped_with_saved_alternative():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        user = User(
            firebase_uid="dev-swapper",
            email="swapper@example.com",
            username="swapper",
            display_name="swapper",
        )
        current_place = Place(canonical_name="Current Cafe", normalized_name="current cafe")
        db.session.add_all([user, current_place])
        db.session.flush()
        current_ref = PlaceProviderRef(
            place_id=current_place.id,
            provider="mock",
            provider_place_id="current-cafe",
        )
        session = AdventourSession(
            user_id=user.id,
            title="Swappable Route",
            summary_json=json.dumps({"source": "planned_itinerary"}),
        )
        db.session.add_all([current_ref, session])
        db.session.flush()
        stop = AdventourStop(
            session_id=session.id,
            place_id=current_place.id,
            provider_ref_id=current_ref.id,
            order_index=0,
            status="planned",
            metadata_json=json.dumps({
                "source": "planned_itinerary",
                "slot_id": "lunch_anchor",
                "slot_label": "Lunch",
                "time_window": "12:00 PM",
                "place_id": "current-cafe",
                "provider": "mock",
                "provider_place_id": "current-cafe",
                "name": "Current Cafe",
                "display": {"name": "Current Cafe", "latitude": 37.1, "longitude": -122.1},
                "score": 0.71,
                "alternatives": [
                    {
                        "place_id": "swap-bakery",
                        "provider": "mock",
                        "provider_place_id": "swap-bakery",
                        "name": "Swap Bakery",
                        "display": {"name": "Swap Bakery", "latitude": 37.2, "longitude": -122.2},
                        "score": 0.86,
                        "diversity_groups": ["coffee_sweets"],
                        "authenticity_evidence": {"label": "Local-feeling"},
                        "swap_impact": {
                            "route_score_delta": 0.12,
                            "swap_decision": {"headline": "Better local fit."},
                        },
                    },
                ],
            }),
        )
        db.session.add(stop)
        db.session.commit()
        session_id = session.id
        stop_id = stop.id

    response = client.post(
        f"/api/adventours/{session_id}/stops/{stop_id}/swap",
        headers=auth_headers("swapper@example.com"),
        json={"alternative_index": 0},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["message"] == "Stop swapped"
    assert payload["stop"]["display"]["name"] == "Swap Bakery"
    assert payload["stop"]["metadata"]["swap_history"]["from_name"] == "Current Cafe"
    assert payload["stop"]["metadata"]["swap_history"]["to_name"] == "Swap Bakery"
    assert payload["stop"]["metadata"]["alternatives"][0]["name"] == "Current Cafe"
    assert payload["adventour"]["summary"]["swap_summary"]["swapped_stop_count"] == 1
    assert payload["adventour"]["summary"]["swap_summary"]["swapped_slots"][0]["to_name"] == "Swap Bakery"

    with server_app.app.app_context():
        swapped_stop = db.session.get(AdventourStop, stop_id)
        swap_ref = PlaceProviderRef.query.filter_by(provider="mock", provider_place_id="swap-bakery").first()
        assert swapped_stop.place.canonical_name == "Swap Bakery"
        assert swapped_stop.provider_ref_id == swap_ref.id
        assert UserPlaceEvent.query.filter_by(event_type="swap", place_id=swapped_stop.place_id).count() == 1


def test_starting_planned_adventour_claims_unattached_reservations():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        user = User(
            firebase_uid="dev-planner",
            email="planner@example.com",
            username="planner",
            display_name="planner",
        )
        db.session.add(user)
        db.session.flush()
        place = Place(
            canonical_name="Route Coffee",
            normalized_name="route coffee",
            latitude=37.422,
            longitude=-122.084,
        )
        db.session.add(place)
        db.session.flush()
        provider_ref = PlaceProviderRef(
            place_id=place.id,
            provider="mock",
            provider_place_id="route-coffee",
        )
        reservation = TravelReservation(
            user_id=user.id,
            reservation_type="stay",
            title="Plan Hotel",
            confirmation_code="PLAN123",
        )
        db.session.add_all([provider_ref, reservation])
        db.session.commit()
        reservation_id = reservation.id

    response = client.post(
        "/api/adventours/from-itinerary",
        headers=auth_headers("planner@example.com"),
        json={
            "title": "Claimed Reservation Route",
            "destination": "Test City",
            "scoring_profile": "authenticity_forward",
            "trip_style": "weekend",
            "pace": "balanced",
            "budget_profile": "flexible",
            "query_tags": ["market", "coffee"],
            "route_readiness": {
                "score": 0.88,
                "label": "Strong route",
                "planned_stop_count": 1,
                "expected_stop_count": 1,
            },
            "route_explanation": {
                "headline": "This route is strong enough to test.",
                "reasons": ["Built 1 stop around the authenticity_forward scout style."],
                "stats": {"stop_count": 1},
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "items": [
                    {
                        "id": "route_stops",
                        "label": "Route stops",
                        "status": "ready",
                    },
                ],
            },
            "local_events": {
                "status": "ready",
                "events": [
                    {
                        "title": "Neighborhood Market",
                        "source_url": "https://example.com/market",
                        "reservation_url": "https://example.com/market/rsvp",
                    },
                ],
            },
            "trip_packet": {
                "status": "ready",
                "headline": "This Adventour has a clear booking packet.",
                "booking_links": [
                    {
                        "id": "event_1",
                        "label": "RSVP: Neighborhood Market",
                        "url": "https://example.com/market/rsvp",
                        "reservation_type": "event",
                    },
                ],
                "save_prompts": [
                    {
                        "id": "event_1",
                        "label": "RSVP: Neighborhood Market",
                        "reservation_type": "event",
                    },
                ],
            },
            "scenario_readiness": {
                "mode": "planned_itinerary",
                "status": "ready",
                "beta_testable": True,
                "friend_readiness": {
                    "status": "ready",
                    "covered_members": 2,
                    "total_members": 2,
                },
            },
            "destination_scout": {
                "source": "destination_compare",
                "selected_destination": {
                    "id": "test-city",
                    "label": "Test City",
                    "location": {"latitude": 37.422, "longitude": -122.084},
                },
                "scoring_profile": "authenticity_forward",
                "rank": {
                    "trip_readiness_score": 0.91,
                    "authenticity_score": 0.86,
                },
                "explanation": {
                    "headline": "Best destination for a local-first weekend.",
                },
            },
            "booking_plan": {
                "components": [
                    {
                        "id": "stay",
                        "type": "stay",
                        "label": "Stay",
                        "status": "manual",
                        "stores_reservation": True,
                    },
                    {
                        "id": "tickets",
                        "type": "event_or_place",
                        "label": "Tickets and reservations",
                        "status": "manual",
                        "stores_reservation": True,
                    },
                ],
            },
            "filter_summary": {"raw_candidates": 12, "returned": 1},
            "learned_rerank": {
                "applied": True,
                "model_type": "adventour_logistic_ltr_baseline",
                "promotion_gate": {
                    "status": "pass",
                    "can_promote": True,
                    "summary": "Learned reranker passed ranking, local-quality, and group-balance promotion checks.",
                },
            },
            "swap_summary": {
                "swapped_stop_count": 1,
                "swapped_slots": [
                    {
                        "day": 1,
                        "slot_id": "morning_anchor",
                        "slot_label": "Morning",
                        "from_place_id": 10,
                        "from_name": "Original Coffee",
                        "to_place_id": 20,
                        "to_name": "Route Coffee",
                        "impact": {"route_score_delta": 0.12},
                    },
                ],
            },
            "reservation_ids": [reservation_id],
            "stops": [
                {
                    "slot_id": "morning_anchor",
                    "label": "Morning",
                    "time_window": "Morning",
                    "role": "anchor",
                    "day": 1,
                    "day_title": "Day 1: Test City local route",
                    "why_this_stop": {
                        "headline": "A strong local-first coffee stop.",
                        "reasons": ["Hidden-gem signal", "Good fit for the whole party"],
                        "stats": {"authenticity": 0.91, "hidden_gem_score": 0.82},
                    },
                    "party_fit_summary": {
                        "headline": "Balanced pick for this travel party.",
                        "lowest_fit": 0.74,
                        "members": [{"user_id": 1, "fit": 0.83}],
                    },
                    "local_event_matches": [
                        {
                            "title": "Neighborhood Market",
                            "reservation_ready": True,
                            "reservation_url": "https://example.com/market/rsvp",
                        },
                    ],
                    "diversity_groups": ["coffee_sweets", "shops_markets"],
                    "alternatives": [
                        {
                            "place_id": "swap-bakery",
                            "provider": "mock",
                            "provider_place_id": "swap-bakery",
                            "name": "Swap Bakery",
                            "display": {"name": "Swap Bakery"},
                            "score": 0.77,
                            "diversity_groups": ["coffee_sweets"],
                            "authenticity_evidence": {"label": "Local-feeling"},
                            "swap_impact": {
                                "route_score_delta": 0.04,
                                "swap_decision": {"headline": "Worth swapping in."},
                            },
                        },
                    ],
                    "swap_history": {
                        "swapped": True,
                        "from_name": "Original Coffee",
                        "to_name": "Route Coffee",
                        "impact": {"route_score_delta": 0.12},
                    },
                    "recommendation": {
                        "place_id": "route-coffee",
                        "provider": "mock",
                        "provider_place_id": "route-coffee",
                        "name": "Route Coffee",
                        "display": {"name": "Route Coffee"},
                        "score": 0.91,
                        "diversity_groups": ["coffee_sweets", "shops_markets"],
                        "authenticity_evidence": {
                            "label": "Hidden gem",
                            "confidence": 0.88,
                        },
                        "score_components": {
                            "preference_fit": 0.82,
                            "authenticity": 0.91,
                        },
                    },
                },
            ],
        },
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["claimed_reservation_count"] == 1
    assert payload["adventour"]["reservations"][0]["confirmation_code"] == "PLAN123"
    summary = payload["adventour"]["summary"]
    assert summary["source"] == "planned_itinerary"
    assert summary["destination"] == "Test City"
    assert summary["scoring_profile"] == "authenticity_forward"
    assert summary["route_readiness"]["label"] == "Strong route"
    assert summary["route_explanation"]["headline"] == "This route is strong enough to test."
    assert summary["launch_checklist"]["can_start"] is True
    assert summary["launch_checklist"]["items"][0]["id"] == "route_stops"
    assert summary["local_events"]["events"][0]["reservation_url"].endswith("/rsvp")
    assert summary["trip_packet"]["booking_links"][0]["reservation_type"] == "event"
    assert summary["trip_packet"]["save_prompts"][0]["label"] == "RSVP: Neighborhood Market"
    assert summary["booking_summary"]["reservation_count"] == 1
    assert summary["booking_summary"]["confirmation_count"] == 1
    assert summary["trip_packet"]["reservation_coverage"]["required_count"] == 2
    assert summary["trip_packet"]["reservation_coverage"]["saved_count"] == 1
    assert summary["trip_packet"]["reservation_coverage"]["confirmed_count"] == 1
    assert summary["trip_packet"]["reservation_coverage"]["missing_labels"] == ["Tickets/events"]
    assert any(stat["id"] == "saved_reservations" for stat in summary["trip_packet"]["quick_stats"])
    assert summary["trip_packet"]["required_actions"][0]["label"] == "Save Tickets/events"
    assert summary["trip_packet"]["booking_command_center"]["primary_action"]["label"] == "Save Tickets/events"
    assert summary["trip_packet"]["booking_command_center"]["primary_action"]["can_save"] is True
    assert summary["trip_packet"]["next_step"] == "Save Tickets/events"
    assert summary["scenario_readiness"]["status"] == "ready"
    assert summary["scenario_readiness"]["friend_readiness"]["covered_members"] == 2
    assert summary["destination_scout"]["source"] == "destination_compare"
    assert summary["destination_scout"]["selected_destination"]["label"] == "Test City"
    assert summary["destination_scout"]["rank"]["authenticity_score"] == 0.86
    assert summary["destination_scout"]["explanation"]["headline"] == "Best destination for a local-first weekend."
    assert summary["learned_rerank"]["applied"] is True
    assert summary["learned_rerank"]["promotion_gate"]["status"] == "pass"
    assert summary["swap_summary"]["swapped_stop_count"] == 1
    assert summary["swap_summary"]["swapped_slots"][0]["to_name"] == "Route Coffee"

    with server_app.app.app_context():
        reservation = db.session.get(TravelReservation, reservation_id)
        assert reservation.adventour_session_id == payload["adventour"]["id"]
        stop = AdventourStop.query.filter_by(session_id=payload["adventour"]["id"]).first()
        stop_metadata = server_app.parse_json_object(stop.metadata_json)
        assert stop_metadata["swap_history"]["swapped"] is True
        assert stop_metadata["swap_history"]["from_name"] == "Original Coffee"
        assert stop_metadata["slot_label"] == "Morning"
        assert stop_metadata["role"] == "anchor"
        assert stop_metadata["why_this_stop"]["headline"] == "A strong local-first coffee stop."
        assert stop_metadata["party_fit_summary"]["headline"] == "Balanced pick for this travel party."
        assert stop_metadata["local_event_matches"][0]["title"] == "Neighborhood Market"
        assert stop_metadata["diversity_groups"] == ["coffee_sweets", "shops_markets"]
        assert stop_metadata["authenticity_evidence"]["label"] == "Hidden gem"
        assert stop_metadata["score_components"]["authenticity"] == 0.91
        assert stop_metadata["alternatives"][0]["name"] == "Swap Bakery"
        assert stop_metadata["alternatives"][0]["swap_impact"]["route_score_delta"] == 0.04

    complete_response = client.post(
        f"/api/adventours/{payload['adventour']['id']}/complete",
        headers=auth_headers("planner@example.com"),
    )
    assert complete_response.status_code == 200
    completed_summary = complete_response.get_json()["adventour"]["summary"]
    assert completed_summary["route_readiness"]["label"] == "Strong route"
    assert completed_summary["route_explanation"]["stats"]["stop_count"] == 1
    assert completed_summary["launch_checklist"]["headline"] == "Ready to launch."
    assert completed_summary["local_events"]["events"][0]["title"] == "Neighborhood Market"
    assert completed_summary["trip_packet"]["headline"] == "Save booking details so this Adventour can travel with confirmations."
    assert completed_summary["trip_packet"]["reservation_coverage"]["saved_count"] == 1
    assert completed_summary["trip_packet"]["booking_command_center"]["primary_action"]["label"] == "Save Tickets/events"
    assert completed_summary["trip_packet"]["booking_links"][0]["url"].endswith("/rsvp")
    assert completed_summary["scenario_readiness"]["beta_testable"] is True
    assert completed_summary["learned_rerank"]["model_type"] == "adventour_logistic_ltr_baseline"
    assert completed_summary["swap_summary"]["swapped_slots"][0]["from_name"] == "Original Coffee"
    assert completed_summary["completion"]["stop_count"] == 0
