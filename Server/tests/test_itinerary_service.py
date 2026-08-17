import pytest
from flask import Flask
from datetime import datetime, timedelta

from adventour_backend.models import db, Friendship, LocalEvent, LocalEventInterest, User
from adventour_backend.services.itinerary_service import ItineraryRecommendationService
from adventour_backend.services.local_event_service import LocalEventRecommendationService
from adventour_backend.services.recommender_model_service import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from adventour_backend.services.recommender_service import RecommendationService
from adventour_backend.services.travel_logistics_service import TravelLogisticsService


class MockProviderRegistry:
    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return self.candidates, []


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def create_user(email, preferences):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"test-{username}",
        email=email,
        username=username,
        display_name=username.title(),
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.commit()
    return user


def make_friends(user, friend):
    db.session.add(Friendship(user_id=user.id, friend_id=friend.id, status="accepted"))
    db.session.commit()


def candidate(name, place_id, types, rating=4.7, ratings_total=80, price_level=2, lat=37.422, lng=-122.084):
    return {
        "provider": "mock",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "business_status": "OPERATIONAL",
    }


def itinerary_for(user, candidates, member_ids=None, days=1, constraints=None):
    recommender = RecommendationService(MockProviderRegistry(candidates))
    service = ItineraryRecommendationService(
        recommender,
        LocalEventRecommendationService(),
        TravelLogisticsService(),
    )
    return service.recommend_itinerary(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=8000,
        member_ids=member_ids or [],
        days=days,
        constraints=constraints or {},
        destination_label="Test City",
    )


def promoted_learned_model():
    return {
        "model_type": "adventour_logistic_ltr_baseline",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "intercept": 0.0,
        "weights": {
            "authenticity_score": 2.5,
            "hidden_gem_score": 1.5,
            "chain_inverse": 1.0,
        },
        "feature_stats": {
            name: {"mean": 0.0, "std": 1.0}
            for name in FEATURE_NAMES
        },
        "promotion_gate": {
            "status": "pass",
            "can_promote": True,
            "summary": "Learned reranker passed ranking, local-quality, and group-balance promotion checks.",
            "checks": [
                {
                    "name": "ranking_improved",
                    "label": "Ranking quality did not regress",
                    "status": "pass",
                    "value": "MRR +0.1000, NDCG +0.1000",
                },
            ],
        },
        "training_data_health": {
            "status": "ready",
            "summary": "Training data is ready for learned-ranker evaluation.",
            "counts": {"labeled": 60, "requests": 24, "event_friend_signal": 3},
            "checks": [
                {"name": "labeled_outcomes", "label": "Enough labeled outcomes", "status": "pass"},
                {"name": "request_diversity", "label": "Enough recommendation requests", "status": "pass"},
                {"name": "event_social_signal", "label": "Event social/friend signal exists", "status": "pass"},
            ],
        },
    }


def rich_candidate_set():
    return [
        candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], price_level=1),
        candidate("Sunrise Bakery", "bakery-1", ["bakery", "cafe"], price_level=1),
        candidate("City Art Walk", "art-1", ["art_gallery"], price_level=1),
        candidate("Neighborhood Museum", "museum-1", ["museum"], price_level=2),
        candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], price_level=1),
        candidate("Garden Market", "market-1", ["market", "tourist_attraction"], price_level=1),
        candidate("Indie Theater", "theater-1", ["performing_arts_theater"], price_level=3),
        candidate("Late Night Jazz", "jazz-1", ["bar", "concert_hall"], price_level=2),
    ]


def diversity_candidate_set():
    return [
        candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], price_level=1),
        candidate("City Art Walk", "art-1", ["art_gallery"], price_level=1),
        candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], price_level=1),
        candidate("Garden Market", "market-1", ["market", "tourist_attraction"], price_level=1),
        candidate("Dinner Bistro", "dinner-1", ["restaurant"], rating=5.0, ratings_total=300, price_level=2),
        candidate("Late Night Jazz", "jazz-1", ["bar", "concert_hall"], rating=4.6, ratings_total=40, price_level=2),
    ]


def long_vacation_candidate_set():
    slot_types = [
        ("Coffee", ["cafe", "coffee_shop"]),
        ("Gallery", ["art_gallery"]),
        ("Taco", ["restaurant", "mexican_restaurant"]),
        ("Market", ["market", "tourist_attraction"]),
        ("Jazz", ["bar", "concert_hall"]),
    ]
    return [
        candidate(
            f"{label} Stop {index}",
            f"{label.lower()}-{index}",
            types,
            rating=4.5 + ((index % 5) * 0.05),
            ratings_total=35 + index,
            price_level=index % 3,
            lat=37.422 + (index * 0.0001),
            lng=-122.084 + (index * 0.0001),
        )
        for index in range(1, 31)
        for label, types in [slot_types[index % len(slot_types)]]
    ]


def test_itinerary_builds_slots_with_alternatives_and_costs(app_context):
    user = create_user("planner@example.com", ["cafe", "restaurant", "art_gallery", "market"])

    result = itinerary_for(user, rich_candidate_set())

    assert result["mode"] == "planned_itinerary"
    assert result["title"] == "One-day Adventour in Test City"
    assert result["days"]
    stops = result["days"][0]["stops"]
    assert len(stops) >= 4
    assert stops[0]["slot_id"] == "morning_anchor"
    assert stops[0]["recommendation"]["name"] in {"Corner Coffee", "Sunrise Bakery"}
    assert stops[0]["alternatives"]
    assert stops[0]["alternatives"][0]["diversity_groups"]
    assert stops[0]["alternatives"][0]["swap_impact"]["reasons"]
    assert "route_score_delta" in stops[0]["alternatives"][0]["swap_impact"]
    assert "low_friction_score" in stops[0]["alternatives"][0]["swap_impact"]
    assert stops[0]["alternatives"][0]["swap_impact"]["swap_readiness"]["low_friction_label"]
    assert stops[0]["alternatives"][0]["swap_impact"]["swap_decision"]["headline"]
    assert stops[0]["alternatives"][0]["swap_impact"]["swap_decision"]["best_when"]
    assert stops[0]["alternatives"][0]["swap_impact"]["swap_decision"]["badges"]
    assert result["swap_guide"]["stop_count"] == len(stops)
    assert result["swap_guide"]["swappable_stop_count"] >= 1
    assert result["swap_guide"]["alternative_count"] >= len(stops[0]["alternatives"])
    assert result["swap_guide"]["best_swaps"]
    assert result["swap_guide"]["next_action"]
    assert result["trip_packet"]["swap_guide"]["swap_coverage"] == result["swap_guide"]["swap_coverage"]
    assert result["route_model_confidence"]["score"] > 0
    assert result["route_model_confidence"]["stop_coverage"] == result["route_readiness"]["stop_coverage"]
    assert result["route_model_confidence"]["authenticity_score"] == result["route_readiness"]["authenticity_score"]
    assert result["trip_packet"]["route_model_confidence"]["score"] == result["route_model_confidence"]["score"]
    assert result["trip_logistics_readiness"]["score"] > 0
    assert result["trip_logistics_readiness"]["status"] == "ready"
    assert result["trip_logistics_readiness"]["reservation_storage_ready"] is True
    assert result["trip_logistics_readiness"]["local_transport_status"] == "estimated"
    assert result["trip_packet"]["trip_logistics_readiness"]["score"] == result["trip_logistics_readiness"]["score"]
    assert stops[0]["why_this_stop"]["headline"]
    assert stops[0]["why_this_stop"]["reasons"]
    assert "authenticity" in stops[0]["why_this_stop"]["stats"]
    assert "hidden_gem_score" in stops[0]["why_this_stop"]["stats"]
    assert result["price_breakdown"]["per_person"]["total_known_low"] > 0
    assert result["logistics"]["local_transport"]["estimated_segments"] == len(stops) - 1
    assert result["booking_plan"]["reservation_storage"]["status"] == "ready"
    assert result["booking_plan"]["summary"]["readiness_score"] >= 0.9
    assert result["booking_plan"]["booking_handoff"]["status"] == "ready"
    assert result["booking_plan"]["booking_handoff"]["ready_to_save_count"] >= 1
    assert result["booking_plan"]["booking_handoff"]["setup_ready"]
    assert result["route_readiness"]["score"] >= 0.7
    assert result["route_readiness"]["planned_stop_count"] == len(stops)
    assert result["route_readiness"]["expected_stop_count"] == 4
    assert result["route_readiness"]["authenticity_score"] == result["route_authenticity"]["score"]
    assert result["route_readiness"]["authenticity_summary"]["stop_count"] == len(stops)
    assert result["route_readiness"]["booking_summary"]["reservation_storage_ready"] is True
    assert result["launch_checklist"]["can_start"] is True
    assert result["launch_checklist"]["items"][0]["id"] == "route_stops"
    assert any(item["id"] == "booking_details" for item in result["launch_checklist"]["items"])
    assert result["route_explanation"]["headline"]
    assert any("Built" in reason for reason in result["route_explanation"]["reasons"])
    assert result["route_explanation"]["stats"]["stop_count"] == len(stops)
    assert result["route_explanation"]["stats"]["known_per_person_low"] == result["price_breakdown"]["per_person"]["total_known_low"]
    assert result["itinerary_story"]["headline"]
    assert "local-first" in result["itinerary_story"]["headline"]
    assert "friend fit" in result["itinerary_story"]["narrative"]
    assert any("local/authenticity" in highlight for highlight in result["itinerary_story"]["highlights"])
    assert any(badge["label"] == "Planning" for badge in result["itinerary_story"]["badges"])
    assert result["itinerary_story"]["stats"]["stop_count"] == len(stops)
    assert result["route_authenticity"]["status"] in {"ready", "watch"}
    assert result["route_authenticity"]["local_feeling_count"] > 0
    assert result["route_authenticity"]["hidden_gem_count"] > 0
    assert "local" in result["route_authenticity"]["headline"].lower()
    assert result["trip_packet"]["status"] == "ready"
    assert result["trip_packet"]["can_start"] is True
    assert result["trip_packet"]["beta_readiness"]["score"] >= 0.65
    assert result["trip_packet"]["beta_readiness"]["weakest_dimension"]["id"]
    assert result["trip_packet"]["beta_readiness"]["next_action"]
    assert {dimension["id"] for dimension in result["trip_packet"]["beta_readiness"]["dimensions"]} >= {
        "route",
        "model",
        "local_promise",
        "booking",
        "friend_fit",
        "swap_safety",
        "local_events",
    }
    assert result["trip_packet"]["quick_stats"][0]["id"] == "beta_readiness"
    assert result["trip_packet"]["known_per_person"]["low"] == result["price_breakdown"]["per_person"]["total_known_low"]
    assert result["trip_packet"]["known_per_person"]["label"]
    assert result["trip_packet"]["cost_confidence"]["status"] == "estimated"
    assert result["trip_packet"]["cost_confidence"]["combined_known_low"] == result["price_breakdown"]["per_person"]["total_known_low"]
    assert result["price_breakdown"]["quote_plan"]["status"] == "local_estimate_only"
    assert result["price_breakdown"]["quote_plan"]["required_count"] == 0
    assert result["trip_packet"]["quote_plan"]["status"] == "local_estimate_only"
    assert result["trip_packet"]["reservation_storage_ready"] is True
    assert result["trip_packet"]["booking_links"]
    assert result["trip_packet"]["save_prompts"]
    assert result["trip_packet"]["booking_command_center"]["status"] in {"ready", "action_needed"}
    assert result["trip_packet"]["booking_command_center"]["primary_action"]
    assert result["trip_packet"]["booking_command_center"]["open_link_count"] >= 1
    assert result["trip_packet"]["booking_command_center"]["save_prompt_count"] >= 1
    assert any(
        command["phase"] in {"book", "setup", "save"}
        for command in result["trip_packet"]["booking_command_center"]["commands"]
    )
    assert result["trip_packet"]["next_step"] == result["trip_packet"]["booking_command_center"]["primary_action"]["label"]
    assert result["trip_packet"]["mobility_setup"]["label"]
    assert result["trip_packet"]["mobility_setup"]["can_save"] is True
    assert result["trip_packet"]["mobility_setup"]["reservation_type"] == "local_transport"
    assert result["trip_packet"]["mobility_setup"]["draft_title"]
    assert result["trip_packet"]["mobility_setup"]["draft_notes"]
    assert result["trip_packet"]["mobility_setup"]["estimate"]["per_person_high"] >= 0
    assert result["trip_packet"]["mobility_setup"]["estimate"]["currency"] == "USD"
    assert result["trip_packet"]["mobility_setup"]["setup_steps"]
    assert result["trip_packet"]["booking_checklist"]["blocking_count"] == 0
    assert result["trip_packet"]["booking_checklist"]["items"]
    assert result["trip_packet"]["authenticity_packet"]["score"] == result["route_authenticity"]["score"]
    assert result["trip_packet"]["authenticity_packet"]["hidden_gem_count"] == result["route_authenticity"]["hidden_gem_count"]
    assert result["trip_packet"]["event_packet"]["status"] == "needs_scouting"
    assert result["trip_packet"]["event_packet"]["short_label"] == "Scout"
    assert any(stat["id"] == "known_cost" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "mobility" and stat["status"] == "ready" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "booking_checklist" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "authenticity_packet" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "event_packet" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "swap_guide" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "route_model_confidence" for stat in result["trip_packet"]["quick_stats"])
    assert any(stat["id"] == "trip_logistics" for stat in result["trip_packet"]["quick_stats"])
    assert result["booking_plan"]["components"][0]["type"] == "flight"
    assert result["booking_plan"]["components"][0]["status"] == "optional_for_day_trip"
    assert any(component["type"] == "local_transport" and component["estimate"] for component in result["booking_plan"]["components"])
    assert result["local_events"]["status"] == "empty"
    assert result["local_events"]["events"] == []
    assert result["local_events"]["summary"]["readiness_score"] == 0.55
    assert result["local_events"]["external_sources"]
    assert result["local_events"]["summary"]["source_summary"]["actionable_external_source_count"] >= 4
    assert result["local_events"]["summary"]["source_summary"]["recommended_external_source"]["source_type"] == "market_popup_search"
    assert result["local_events"]["external_sources"][3]["source_type"] == "market_popup_search"
    assert result["local_events"]["external_sources"][3]["is_recommended"] is True
    assert result["local_events"]["event_plan"]["items"][0]["id"] == "recommended_external_source"
    assert result["local_events"]["event_plan"]["items"][0]["source_type"] == "market_popup_search"
    assert any(
        item["id"] == "external_official_search"
        for item in result["local_events"]["event_plan"]["items"]
    )
    assert "No local events matched this launch point yet." in result["route_readiness"]["warnings"]


def test_itinerary_pairs_local_events_with_route_stops(app_context):
    user = create_user("eventsroute@example.com", ["market", "art_gallery", "restaurant", "cafe"])
    db.session.add(LocalEvent(
        title="Neighborhood Makers Market",
        description="Local artists, food stalls, and community vendors.",
        city="Test City",
        latitude=37.423,
        longitude=-122.084,
        starts_at=datetime.utcnow() + timedelta(days=2, hours=15),
        category="market",
        source_name="Official community calendar",
        source_url="https://events.example.com/makers",
        reservation_url="https://events.example.com/makers/rsvp",
        authenticity_score=0.92,
    ))
    db.session.commit()

    result = itinerary_for(
        user,
        rich_candidate_set(),
        constraints={"travel_dates": {
            "start": (datetime.utcnow() + timedelta(days=1)).date().isoformat(),
            "end": (datetime.utcnow() + timedelta(days=4)).date().isoformat(),
        }},
    )

    event = result["local_events"]["events"][0]
    route_context = event["route_context"]
    matched_stop = next(
        stop
        for stop in result["days"][0]["stops"]
        if stop["slot_id"] == route_context["slot_id"]
    )
    assert route_context["day"] == 1
    assert route_context["slot_id"] in {"late_morning_discovery", "afternoon_gem"}
    assert route_context["distance_to_stop_meters"] is not None
    assert route_context["route_fit"] > 0
    assert route_context["fit_label"] in {"Near Local discovery", "Near Afternoon gem"}
    assert "Event category fits this route slot" in route_context["reasons"]
    assert result["local_events"]["summary"]["route_match_count"] == 1
    assert result["local_events"]["summary"]["top_route_event_title"] == "Neighborhood Makers Market"
    assert "route stops" in result["local_events"]["summary"]["route_context_message"]
    assert matched_stop["local_event_matches"][0]["title"] == "Neighborhood Makers Market"
    assert matched_stop["local_event_matches"][0]["reservation_ready"] is True
    assert matched_stop["local_event_matches"][0]["distance_to_stop_meters"] == route_context["distance_to_stop_meters"]
    assert matched_stop["local_event_matches"][0]["route_fit"] == route_context["route_fit"]
    event_booking_link = next(
        link
        for link in result["trip_packet"]["booking_links"]
        if link["reservation_type"] == "event"
    )
    assert event_booking_link["label"] == "RSVP: Neighborhood Makers Market"
    assert event_booking_link["url"].endswith("/rsvp")
    event_save_prompt = next(
        prompt
        for prompt in result["trip_packet"]["save_prompts"]
        if prompt["reservation_type"] == "event"
    )
    assert event_save_prompt["label"] == "RSVP: Neighborhood Makers Market"
    assert event_save_prompt["route_context"]["slot_id"] == route_context["slot_id"]
    assert result["trip_packet"]["event_packet"]["status"] == "ready"
    assert result["trip_packet"]["event_packet"]["route_match_count"] == 1
    assert result["trip_packet"]["event_packet"]["reservation_ready_count"] == 1
    assert result["trip_packet"]["event_packet"]["top_event_title"] == "Neighborhood Makers Market"
    assert "Neighborhood Makers Market" in result["trip_packet"]["event_packet"]["headline"]
    assert result["route_explanation"]["stats"]["route_event_count"] == 1
    assert any("Neighborhood Makers Market" in reason for reason in result["route_explanation"]["reasons"])
    assert any("Neighborhood Makers Market" in highlight for highlight in result["itinerary_story"]["highlights"])
    assert any(badge["label"] == "Events" and badge["detail"] == "1 paired" for badge in result["itinerary_story"]["badges"])


def test_itinerary_prefers_route_coherent_stop_over_far_equal_fit(app_context):
    user = create_user("routewise@example.com", ["cafe", "restaurant", "park"])
    candidates = [
        candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], price_level=1, lat=37.422, lng=-122.084),
        candidate("Far Taco", "far-taco", ["restaurant", "mexican_restaurant"], price_level=1, lat=37.47, lng=-122.13),
        candidate("Nearby Taco", "near-taco", ["restaurant", "mexican_restaurant"], price_level=1, lat=37.423, lng=-122.083),
        candidate("Pocket Park", "park-1", ["park"], price_level=0, lat=37.424, lng=-122.083),
    ]

    result = itinerary_for(
        user,
        candidates,
        constraints={"pace": "relaxed"},
    )

    lunch_stop = next(stop for stop in result["days"][0]["stops"] if stop["slot_id"] == "lunch")
    assert lunch_stop["recommendation"]["name"] == "Nearby Taco"
    far_swap = next(item for item in lunch_stop["alternatives"] if item["name"] == "Far Taco")
    assert far_swap["swap_impact"]["travel_efficiency_delta"] < 0
    assert far_swap["swap_impact"]["travel_distance_meters"] > 1000
    assert far_swap["swap_impact"]["low_friction_score"] < 0.78
    assert far_swap["swap_impact"]["swap_readiness"]["status"] in {"balanced_tradeoff", "route_risk"}
    assert far_swap["swap_impact"]["swap_readiness"]["next_action"]
    assert far_swap["swap_impact"]["swap_decision"]["tradeoff"]
    assert far_swap["swap_impact"]["swap_decision"]["confidence"] == far_swap["swap_impact"]["swap_readiness"]["score"]


def test_itinerary_balances_repeated_food_with_route_diversity(app_context):
    user = create_user("diverse@example.com", ["restaurant", "cafe", "bar", "art_gallery"])

    result = itinerary_for(user, diversity_candidate_set())

    stops = result["days"][0]["stops"]
    evening_stop = next(stop for stop in stops if stop["slot_id"] == "evening_finish")

    assert evening_stop["recommendation"]["name"] == "Late Night Jazz"
    assert "nightlife" in evening_stop["diversity_groups"]
    assert "arts_culture" in result["days"][0]["route_balance"]["unique_groups"]
    assert result["days"][0]["route_balance"]["variety_score"] > 0


def test_itinerary_supports_weekend_and_vacation_metadata(app_context):
    user = create_user("weekend@example.com", ["cafe", "restaurant", "art_gallery", "market"])

    result = itinerary_for(
        user,
        rich_candidate_set(),
        days=2,
        constraints={
            "trip_style": "weekend",
            "origin_label": "Orlando, FL",
            "travel_dates": {"start": "2026-07-10", "end": "2026-07-12"},
            "lodging_type": "hotel",
            "stay_neighborhood": "Downtown",
            "preferred_local_transport": "transit",
        },
    )

    assert result["title"] == "Weekend Adventour in Test City"
    assert result["trip_style"] == "weekend"
    assert result["nights"] == 2
    assert len(result["days"]) == 2
    assert result["trip_style_fit"]["status"] == "ready"
    assert result["trip_style_fit"]["trip_style"] == "weekend"
    assert result["trip_style_fit"]["suggested_style"] == "weekend"
    assert result["trip_style_fit"]["quote_coverage"] == 1.0
    assert result["price_breakdown"]["days"] == 2
    assert result["price_breakdown"]["nights"] == 2

    components = {component["type"]: component for component in result["booking_plan"]["components"]}
    assert result["booking_plan"]["nights"] == 2
    assert components["stay"]["nights"] == 2
    assert components["flight"]["status"] == "ready_for_provider"
    assert components["stay"]["status"] == "ready_for_provider"
    assert components["stay"]["missing_inputs"] == []
    assert "hotel in Test City near Downtown" in components["stay"]["search_hint"]
    assert result["booking_plan"]["origin"] == "Orlando, FL"
    assert result["booking_plan"]["travel_dates"]["start"] == "2026-07-10"
    assert result["booking_plan"]["lodging_type"] == "hotel"
    assert result["booking_plan"]["stay_neighborhood"] == "Downtown"
    assert result["booking_plan"]["preferred_local_transport"] == "transit"
    assert components["local_transport"]["preferred_local_transport"] == "transit"
    assert any(option["id"] == "transit" and option["recommended"] for option in components["local_transport"]["options"])
    local_transport_estimate = components["local_transport"]["estimate"]
    assert result["price_breakdown"]["per_person"]["local_transit_low"] == local_transport_estimate["per_person_low"]
    assert result["price_breakdown"]["per_person"]["local_transit_high"] == local_transport_estimate["per_person_high"]
    assert result["booking_plan"]["summary"]["readiness_score"] >= 0.85
    assert result["route_readiness"]["booking_score"] >= 0.85
    assert result["route_readiness"]["booking_action_link_count"] >= 2
    assert result["route_readiness"]["booking_saveable_item_count"] >= 2
    assert "Booking links and reservation storage are ready." in result["route_readiness"]["strengths"]
    assert result["trip_packet"]["status"] == "ready"
    assert result["trip_packet"]["beta_readiness"]["status"] in {"ready", "beta_ready_with_notes", "needs_tuning"}
    assert result["trip_packet"]["beta_readiness"]["member_count"] >= 1
    assert any(
        dimension["id"] == "booking" and dimension["status"] == "pass"
        for dimension in result["trip_packet"]["beta_readiness"]["dimensions"]
    )
    assert result["trip_packet"]["booking_score"] >= 0.85
    assert result["trip_logistics_readiness"]["status"] == "ready"
    assert result["trip_logistics_readiness"]["quote_ready_count"] >= 2
    assert result["trip_logistics_readiness"]["quote_status"] == "ready_to_quote"
    assert result["trip_logistics_readiness"]["quote_required_count"] == 2
    assert result["trip_logistics_readiness"]["provider_link_count"] >= 2
    assert result["price_breakdown"]["unknown_cost_components"] == ["flight", "stay"]
    assert result["price_breakdown"]["quote_plan"]["status"] == "ready_to_quote"
    assert result["price_breakdown"]["quote_plan"]["required_count"] == 2
    assert result["price_breakdown"]["quote_plan"]["ready_count"] == 2
    quote_items = {item["type"]: item for item in result["price_breakdown"]["quote_plan"]["items"]}
    assert quote_items["flight"]["primary_url"].startswith("https://www.google.com/travel/flights")
    assert quote_items["stay"]["primary_url"].startswith("https://www.google.com/travel/hotels")
    assert result["trip_packet"]["quote_plan"]["status"] == "ready_to_quote"
    assert result["trip_packet"]["cost_confidence"]["quote_status"] == "ready_to_quote"
    assert result["trip_packet"]["cost_confidence"]["quote_ready_count"] == 2
    assert any(stat["id"] == "travel_quotes" and stat["status"] == "ready" for stat in result["trip_packet"]["quick_stats"])
    assert result["trip_packet"]["trip_style_fit"]["status"] == "ready"
    assert any(stat["id"] == "trip_style_fit" and stat["status"] == "ready" for stat in result["trip_packet"]["quick_stats"])
    assert len(result["trip_packet"]["booking_links"]) >= 2
    assert len(result["trip_packet"]["save_prompts"]) >= 2
    assert result["trip_packet"]["missing_inputs"] == []


def test_itinerary_uses_travel_dates_for_longer_vacation_length(app_context):
    user = create_user("vacation@example.com", ["cafe", "restaurant", "art_gallery", "market", "bar"])

    result = itinerary_for(
        user,
        long_vacation_candidate_set(),
        days=3,
        constraints={
            "trip_style": "vacation",
            "origin_label": "Orlando, FL",
            "travel_dates": {"start": "2026-07-10", "end": "2026-07-14"},
            "pace": "balanced",
        },
    )

    assert result["title"] == "5-day Adventour vacation in Test City"
    assert result["trip_style"] == "vacation"
    assert len(result["days"]) == 5
    assert result["nights"] == 4
    assert result["trip_style_fit"]["suggested_style"] == "vacation"
    assert result["trip_style_fit"]["route_days"] == 5
    assert result["trip_style_fit"]["nights"] == 4
    assert result["price_breakdown"]["days"] == 5
    assert result["price_breakdown"]["nights"] == 4
    assert result["booking_plan"]["days"] == 5
    assert result["booking_plan"]["nights"] == 4
    assert result["booking_plan"]["travel_dates"]["end"] == "2026-07-14"
    assert result["route_readiness"]["expected_stop_count"] == 20


def test_itinerary_booking_readiness_flags_missing_trip_inputs(app_context):
    user = create_user("missingbooking@example.com", ["cafe", "restaurant", "art_gallery", "market"])

    result = itinerary_for(
        user,
        rich_candidate_set(),
        days=2,
        constraints={"trip_style": "weekend"},
    )

    assert result["booking_plan"]["summary"]["missing_input_count"] == 3
    assert result["booking_plan"]["summary"]["blocked_component_count"] == 2
    assert result["route_readiness"]["booking_score"] < 0.5
    assert "Add trip dates or origin to prepare booking steps." in result["route_readiness"]["warnings"]
    assert result["launch_checklist"]["can_start"] is True
    booking_item = next(item for item in result["launch_checklist"]["items"] if item["id"] == "booking_details")
    assert booking_item["status"] == "action_needed"
    assert booking_item["blocking"] is False
    assert "origin" in booking_item["detail"]
    assert result["trip_packet"]["status"] == "needs_details"
    assert result["trip_style_fit"]["status"] in {"watch", "needs_attention"}
    assert result["trip_style_fit"]["quote_required_count"] >= 1
    assert result["trip_logistics_readiness"]["status"] == "needs_details"
    assert result["trip_logistics_readiness"]["missing_input_count"] == 3
    assert result["trip_packet"]["trip_logistics_readiness"]["missing_input_count"] == 3
    assert "origin" in result["trip_packet"]["missing_inputs"]
    assert result["trip_packet"]["required_actions"][0]["status"] == "action_needed"
    assert "Add origin" == result["trip_packet"]["required_actions"][0]["label"]


def test_route_booking_score_requires_actionable_links(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    route_days = [{
        "day": 1,
        "route_balance": {"variety_score": 0.8},
        "party_fit": {"fairness_score": 0.9},
        "stops": [{"slot_id": "morning_anchor"}, {"slot_id": "lunch"}],
    }]
    booking_plan = {
        "status": "provider_ready_contract",
        "missing_inputs": [],
        "summary": {
            "readiness_score": 0.95,
            "blocked_component_count": 0,
            "reservation_storage_ready": True,
        },
        "reservation_storage": {"status": "ready"},
        "booking_action_links": [],
        "booking_timeline": {"items": []},
        "planning_burden": {"score": 0.05, "level": "low"},
    }

    readiness = service._route_readiness(
        route_days,
        expected_stop_count=2,
        booking_plan=booking_plan,
    )

    assert readiness["booking_score"] <= 0.68
    assert readiness["booking_action_link_count"] == 0
    assert "Booking steps need provider links before this route feels bookable." in readiness["warnings"]


def test_itinerary_respects_pace_and_budget_profile(app_context):
    user = create_user("pace@example.com", ["cafe", "restaurant", "art_gallery", "market"])

    result = itinerary_for(
        user,
        rich_candidate_set(),
        constraints={
            "pace": "relaxed",
            "budget_profile": "budget",
        },
    )

    assert result["pace"] == "relaxed"
    assert result["budget_profile"] == "budget"
    assert len(result["days"][0]["stops"]) <= 3
    assert result["days"][0]["route_balance"]["variety_score"] <= 1
    assert result["price_breakdown"]["budget_profile"] == "budget"
    assert result["price_breakdown"]["budget_label"] == "Budget-conscious"


def test_itinerary_exposes_requested_scoring_profile(app_context):
    user = create_user("style@example.com", ["cafe", "market"])

    result = itinerary_for(
        user,
        rich_candidate_set(),
        constraints={
            "scoring_profile": "fresh_discovery",
        },
    )

    assert result["scoring_profile"] == "fresh_discovery"
    assert "fresh_discovery" in result["available_scoring_profiles"]
    assert result["request_id"]
    assert result["days"][0]["stops"][0]["recommendation"]["components"]["scoring_profile"] == "fresh_discovery"


def test_itinerary_exposes_learned_rerank_status_when_requested(app_context):
    user = create_user("learnedroute@example.com", ["cafe"])
    recommender = RecommendationService(
        MockProviderRegistry(rich_candidate_set()),
        learned_model=promoted_learned_model(),
    )
    service = ItineraryRecommendationService(
        recommender,
        LocalEventRecommendationService(),
        TravelLogisticsService(),
    )

    result = service.recommend_itinerary(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=8000,
        constraints={
            "scoring_profile": "phase1_balanced",
            "learned_rerank": True,
        },
        destination_label="Test City",
    )

    assert result["scoring_profile"] == "phase1_balanced"
    assert result["learned_rerank"]["applied"] is True
    assert result["learned_rerank"]["promotion_gate"]["status"] == "pass"
    assert result["route_model_confidence"]["learned_rerank"]["applied"] is True
    assert result["trip_packet"]["route_model_confidence"]["learned_rerank"]["applied"] is True
    first_stop = result["days"][0]["stops"][0]["recommendation"]
    assert first_stop["learned_rank_position"] >= 1
    assert first_stop["ranking"]["learned_model_type"] == "adventour_logistic_ltr_baseline"


def test_itinerary_exposes_filter_summary_when_route_filters_remove_candidates(app_context):
    user = create_user("filteredroute@example.com", ["bar", "concert_hall"])

    result = itinerary_for(
        user,
        [candidate("Late Night Jazz", "jazz-only", ["bar", "concert_hall"], price_level=2)],
        constraints={"excluded_tag_groups": ["nightlife"]},
    )

    assert result["filter_summary"]["hard_constraints_active"] is True
    assert result["filter_summary"]["raw_candidates"] == 1
    assert result["filter_summary"]["returned"] == 0
    assert result["filter_summary"]["skipped"]["hard_constraints"] == 1
    assert result["days"][0]["stops"] == []
    assert result["route_readiness"]["label"] == "Not ready yet"
    assert "Route is missing several planned stops." in result["route_readiness"]["warnings"]
    assert result["launch_checklist"]["can_start"] is False
    assert result["launch_checklist"]["blocking_count"] == 1
    assert result["launch_checklist"]["items"][0]["status"] == "action_needed"


def test_itinerary_blends_accepted_friend_preferences(app_context):
    food_user = create_user("food@example.com", ["restaurant", "cafe"])
    art_user = create_user("art@example.com", ["museum", "art_gallery"])
    make_friends(food_user, art_user)

    result = itinerary_for(food_user, rich_candidate_set(), member_ids=[art_user.id])

    assert result["member_count"] == 2
    assert [member["id"] for member in result["members"]] == [food_user.id, art_user.id]
    traveler_costs = result["price_breakdown"]["travelers"]
    assert [traveler["display_name"] for traveler in traveler_costs] == [food_user.display_name, art_user.display_name]
    assert traveler_costs[0]["known_low"] == result["price_breakdown"]["per_person"]["total_known_low"]
    assert {component["type"] for component in traveler_costs[0]["components"]} == {
        "places",
        "local_transport",
        "flight",
        "stay",
    }
    assert next(
        component
        for component in traveler_costs[0]["components"]
        if component["type"] == "flight"
    )["status"] == "provider_needed"
    all_recommendations = [
        stop["recommendation"]
        for day in result["days"]
        for stop in day["stops"]
    ]
    assert any(item["member_fit"][1]["user_id"] == art_user.id for item in all_recommendations)
    stop_summaries = [
        stop["party_fit_summary"]
        for day in result["days"]
        for stop in day["stops"]
    ]
    assert all(summary["headline"] for summary in stop_summaries)
    assert all(summary["average_fit"] is not None for summary in stop_summaries)
    assert all(summary["lowest_fit"] is not None for summary in stop_summaries)
    assert all(summary["highest_fit"] is not None for summary in stop_summaries)
    party_fit = result["days"][0]["party_fit"]
    assert party_fit["fairness_score"] is not None
    assert [member["user_id"] for member in party_fit["members"]] == [food_user.id, art_user.id]
    assert all(member["average_fit"] >= 0 for member in party_fit["members"])


def test_itinerary_preserves_friend_boost_retrieval_context(app_context):
    user = create_user("boostroute@example.com", ["restaurant"])

    result = itinerary_for(
        user,
        rich_candidate_set(),
        constraints={"boost_query_tags": ["arts_culture"]},
    )

    assert result["retrieval_context"]["friend_adjusted"] is True
    assert result["retrieval_context"]["boost_query_tags"] == ["arts_culture"]
    assert result["retrieval_context"]["boosted_query_tags"][:2] == ["museum", "art_gallery"]


def test_itinerary_stop_explains_friend_coverage_rescue(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {
        "label": "Afternoon stop",
        "preferred_types": {"art_gallery", "museum"},
    }
    recommendation = {
        "place_id": "friend-art-rescue",
        "name": "Tiny Local Gallery",
        "score": 0.69,
        "display": {"types": ["art_gallery"]},
        "components": {
            "authenticity": 0.72,
            "quality": 0.68,
            "group_fit": 0.71,
            "group_member_count": 2,
            "group_min_fit": 0.58,
        },
        "authenticity_evidence": {
            "label": "Local gem",
            "hidden_gem_score": 0.74,
            "chain_risk": 0.0,
        },
        "member_fit": [
            {"user_id": 1, "display_name": "Owner", "fit": 0.57},
            {"user_id": 2, "display_name": "Ari", "fit": 0.86},
        ],
        "ranking": {
            "party_coverage_rescue": True,
            "rescued_member": "Ari",
            "rescued_member_fit": 0.86,
            "replaced_pick": "Owner Favorite Cafe",
            "rescue_reason": "member_without_strong_match",
            "score_gap": 0.04,
        },
    }
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [],
        "last_point": None,
    }

    summary = service._stop_party_fit_summary(recommendation)
    reasoning = service._stop_reasoning(slot, recommendation, route_context)

    assert summary["headline"] == "Made room for Ari at 86% fit."
    assert summary["coverage_rescue"]["member"] == "Ari"
    assert summary["coverage_rescue"]["replaced_pick"] == "Owner Favorite Cafe"
    assert reasoning["reasons"][0] == (
        "Adventour made room for this stop because it gives Ari a 86% personal match."
    )
    assert reasoning["stats"]["rescued_member_fit"] == 0.86


def test_route_authenticity_packet_flags_thin_local_evidence(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    route_days = [{
        "day": 1,
        "stops": [
            {
                "slot_id": "morning_anchor",
                "label": "Morning launch",
                "recommendation": {
                    "name": "Two Review Local Cafe",
                    "components": {
                        "authenticity": 0.82,
                        "authenticity_confidence": 0.42,
                        "authenticity_confidence_status": "thin",
                    },
                    "authenticity_evidence": {
                        "label": "Hidden gem",
                        "score": 0.82,
                        "hidden_gem_score": 0.78,
                        "chain_risk": 0.0,
                        "confidence": 0.42,
                        "confidence_status": "thin",
                    },
                },
            },
            {
                "slot_id": "lunch",
                "label": "Lunch",
                "recommendation": {
                    "name": "Confident Local Kitchen",
                    "components": {
                        "authenticity": 0.86,
                        "authenticity_confidence": 0.82,
                        "authenticity_confidence_status": "strong",
                    },
                    "authenticity_evidence": {
                        "label": "Local-feeling",
                        "score": 0.86,
                        "hidden_gem_score": 0.5,
                        "chain_risk": 0.0,
                        "confidence": 0.82,
                        "confidence_status": "strong",
                    },
                },
            },
        ],
    }]

    packet = service._route_authenticity_packet(route_days)

    assert packet["status"] == "watch"
    assert packet["headline"] == "Route has local texture, but some proof is thin."
    assert packet["local_feeling_count"] == 2
    assert packet["hidden_gem_count"] == 1
    assert packet["thin_local_evidence_count"] == 1
    assert packet["average_authenticity_confidence"] == pytest.approx(0.62)
    assert packet["strongest_local_stops"][0]["authenticity_confidence_status"] == "strong"
    assert any("need more proof" in warning for warning in packet["warnings"])
    assert any("thin-proof" in action for action in packet["next_actions"])


def test_itinerary_stop_explains_positive_friend_history(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {
        "label": "Coffee stop",
        "preferred_types": {"cafe"},
    }
    recommendation = {
        "place_id": "friend-liked-cafe",
        "name": "Friend Loved Cafe",
        "display": {"types": ["cafe"]},
        "components": {
            "authenticity": 0.78,
            "group_fit": 0.74,
            "group_member_count": 2,
            "group_min_fit": 0.64,
            "friend_history_fit": 0.35,
        },
        "history": {"friend_liked_by": ["Ari"]},
        "authenticity_evidence": {
            "label": "Local gem",
            "hidden_gem_score": 0.76,
            "chain_risk": 0.0,
        },
    }
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [],
        "last_point": None,
    }

    reasoning = service._stop_reasoning(slot, recommendation, route_context)

    assert reasoning["stats"]["friend_history_fit"] == 0.35
    assert any("Ari already liked this place" in reason for reason in reasoning["reasons"])


def test_itinerary_stop_flags_negative_friend_history(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {
        "label": "Dinner stop",
        "preferred_types": {"restaurant"},
    }
    recommendation = {
        "place_id": "friend-passed-dinner",
        "name": "Friend Passed Dinner",
        "display": {"types": ["restaurant"]},
        "components": {
            "authenticity": 0.68,
            "group_fit": 0.58,
            "group_member_count": 2,
            "group_min_fit": 0.49,
            "friend_history_fit": -0.2,
        },
        "history": {"friend_rejected_by": ["Noah"]},
        "authenticity_evidence": {
            "label": "Local",
            "hidden_gem_score": 0.54,
            "chain_risk": 0.0,
        },
    }
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [],
        "last_point": None,
    }

    reasoning = service._stop_reasoning(slot, recommendation, route_context)

    assert reasoning["stats"]["friend_history_fit"] == -0.2
    assert any("Noah passed on this before" in caution for caution in reasoning["cautions"])


def test_itinerary_slot_scoring_rebalances_underserved_traveler(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {
        "preferred_types": {"restaurant"},
    }
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {1: 0.9, 2: 0.45},
        "member_counts": {1: 1, 2: 1},
        "points": [],
        "last_point": None,
    }
    owner_favorite = {
        "place_id": "owner-favorite",
        "score": 0.72,
        "display": {"types": ["restaurant"]},
        "components": {"authenticity": 0.6, "quality": 0.6},
        "member_fit": [
            {"user_id": 1, "display_name": "Cafe", "fit": 0.95},
            {"user_id": 2, "display_name": "Museum", "fit": 0.55},
        ],
    }
    friend_rebalance = {
        "place_id": "friend-rebalance",
        "score": 0.70,
        "display": {"types": ["restaurant"]},
        "components": {"authenticity": 0.6, "quality": 0.6},
        "member_fit": [
            {"user_id": 1, "display_name": "Cafe", "fit": 0.60},
            {"user_id": 2, "display_name": "Museum", "fit": 0.90},
        ],
    }

    owner_score = service._slot_score_components(slot, owner_favorite, route_context)
    friend_score = service._slot_score_components(slot, friend_rebalance, route_context)
    swap_impact = service._swap_impact(slot, owner_favorite, friend_rebalance, route_context)

    assert owner_score["member_rebalance_bonus"] == 0
    assert friend_score["member_rebalance_bonus"] > 0
    assert friend_score["route_score"] > owner_score["route_score"]
    assert swap_impact["member_rebalance_delta"] > 0
    assert "Helps rebalance the party" in swap_impact["reasons"]
    assert swap_impact["swap_readiness"]["status"] in {"safe_upgrade", "party_rebalance"}
    assert "group fit" in swap_impact["swap_readiness"]["next_action"] or "Swap this in" in swap_impact["swap_readiness"]["next_action"]
    assert swap_impact["swap_decision"]["should_swap"] is True
    assert swap_impact["swap_decision"]["headline"] in {"Worth swapping in.", "Best for the group."}
    assert any(badge["label"] == "Party" for badge in swap_impact["swap_decision"]["badges"])


def test_itinerary_swap_impact_surfaces_positive_friend_history(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {"preferred_types": {"cafe", "coffee_shop"}}
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [],
        "last_point": None,
    }
    current = {
        "place_id": "current-cafe",
        "score": 0.71,
        "display": {"types": ["cafe"]},
        "components": {"authenticity": 0.7, "quality": 0.7, "friend_history_fit": 0.0},
    }
    friend_backed = {
        "place_id": "friend-backed-cafe",
        "score": 0.70,
        "display": {"types": ["cafe", "coffee_shop"]},
        "components": {"authenticity": 0.72, "quality": 0.7, "friend_history_fit": 0.35},
        "history": {"friend_liked_by": ["Ari"]},
    }

    impact = service._swap_impact(slot, current, friend_backed, route_context)

    assert impact["friend_history_delta"] == 0.35
    assert impact["friend_signal"]["status"] == "positive"
    assert impact["friend_signal"]["replacement_liked_by"] == ["Ari"]
    assert "Adds friend-backed social proof" in impact["reasons"]
    assert any(
        badge["label"] == "Friend" and badge["detail"] == "Ari liked" and badge["tone"] == "positive"
        for badge in impact["swap_decision"]["badges"]
    )


def test_itinerary_swap_impact_warns_when_swap_loses_friend_history(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {"preferred_types": {"restaurant"}}
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [],
        "last_point": None,
    }
    current = {
        "place_id": "liked-dinner",
        "score": 0.71,
        "display": {"types": ["restaurant"]},
        "components": {"authenticity": 0.7, "quality": 0.7, "friend_history_fit": 0.34},
        "history": {"friend_liked_by": ["Noah"]},
    }
    no_friend_signal = {
        "place_id": "unknown-dinner",
        "score": 0.72,
        "display": {"types": ["restaurant"]},
        "components": {"authenticity": 0.7, "quality": 0.7, "friend_history_fit": 0.0},
    }

    impact = service._swap_impact(slot, current, no_friend_signal, route_context)

    assert impact["friend_history_delta"] == -0.34
    assert impact["friend_signal"]["status"] == "caution"
    assert impact["friend_signal"]["current_liked_by"] == ["Noah"]
    assert "weaker friend signal" in impact["swap_decision"]["tradeoff"]
    assert any(
        badge["label"] == "Friend" and badge["tone"] == "caution"
        for badge in impact["swap_decision"]["badges"]
    )


def test_itinerary_swap_impact_flags_pricier_replacement(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {"preferred_types": {"restaurant"}}
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [(28.538, -81.379)],
        "last_point": (28.538, -81.379),
    }
    current = {
        "place_id": "current-dinner",
        "score": 0.72,
        "display": {"types": ["restaurant"], "price_level": 1},
        "components": {"authenticity": 0.7, "quality": 0.7},
        "latitude": 28.538,
        "longitude": -81.379,
    }
    pricier = {
        "place_id": "splurge-dinner",
        "score": 0.76,
        "display": {"types": ["restaurant"], "price_level": 4},
        "components": {"authenticity": 0.78, "quality": 0.74},
        "latitude": 28.5382,
        "longitude": -81.3792,
    }

    impact = service._swap_impact(slot, current, pricier, route_context)

    assert impact["price_level_delta"] == 3
    assert impact["known_cost_delta_low"] == 75
    assert impact["known_cost_delta_high"] == 130
    assert impact["cost_impact_status"] == "pricier"
    assert impact["cost_impact_label"] == "Pricier swap"
    assert "higher estimated cost" in impact["swap_decision"]["tradeoff"]
    assert any(
        badge["label"] == "Cost" and badge["tone"] == "caution" and badge["detail"] == "+$75-$130"
        for badge in impact["swap_decision"]["badges"]
    )


def test_itinerary_swap_impact_surfaces_saving_replacement(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {"preferred_types": {"cafe", "coffee_shop"}}
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [(37.422, -122.084)],
        "last_point": (37.422, -122.084),
    }
    current = {
        "place_id": "current-cafe",
        "score": 0.71,
        "display": {"types": ["cafe"], "price_level": 3},
        "components": {"authenticity": 0.68, "quality": 0.7},
        "latitude": 37.422,
        "longitude": -122.084,
    }
    cheaper = {
        "place_id": "neighborhood-counter",
        "score": 0.72,
        "display": {"types": ["cafe", "coffee_shop"], "price_level": 1},
        "components": {"authenticity": 0.7, "quality": 0.7},
        "latitude": 37.4221,
        "longitude": -122.0841,
    }

    impact = service._swap_impact(slot, current, cheaper, route_context)

    assert impact["price_level_delta"] == -2
    assert impact["cost_impact_status"] == "saves"
    assert impact["cost_impact_detail"] == "-$35-$65"
    assert "May save about $35-$65 per person" in impact["reasons"]
    assert any(
        badge["label"] == "Cost" and badge["tone"] == "positive" and badge["detail"] == "-$35-$65"
        for badge in impact["swap_decision"]["badges"]
    )


def test_itinerary_party_fit_marks_daily_friend_coverage(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    stops = [
        {
            "slot_id": "morning_anchor",
            "label": "Morning launch",
            "recommendation": {
                "place_id": "coffee",
                "name": "Corner Coffee",
                "member_fit": [
                    {"user_id": 1, "display_name": "Wanyea", "fit": 0.82},
                    {"user_id": 2, "display_name": "Ari", "fit": 0.42},
                ],
            },
        },
        {
            "slot_id": "afternoon_gem",
            "label": "Afternoon gem",
            "recommendation": {
                "place_id": "gallery",
                "name": "Tiny Local Gallery",
                "member_fit": [
                    {"user_id": 1, "display_name": "Wanyea", "fit": 0.58},
                    {"user_id": 2, "display_name": "Ari", "fit": 0.72},
                ],
            },
        },
    ]

    party_fit = service._party_fit(stops)

    assert party_fit["coverage_share"] == 1.0
    assert party_fit["covered_member_count"] == 2
    assert party_fit["underserved_count"] == 0
    assert party_fit["ready_for_friend_testing"] is True
    assert party_fit["coverage_plan"]["status"] == "ready"
    assert [member["coverage_status"] for member in party_fit["members"]] == ["covered", "covered"]
    assert party_fit["members"][0]["best_match"]["name"] == "Corner Coffee"
    assert party_fit["members"][1]["best_match"]["name"] == "Tiny Local Gallery"
    assert party_fit["members"][0]["strong_match_count"] == 1
    assert party_fit["members"][1]["strong_match_count"] == 1
    assert party_fit["compromise_brief"]["status"] == "balanced"
    assert party_fit["compromise_brief"]["headline"] == "Balanced for the whole party."
    assert party_fit["compromise_brief"]["most_compromised_member"]["display_name"] == "Ari"


def test_itinerary_party_fit_flags_underserved_friend_without_strong_stop(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    stops = [
        {
            "slot_id": "lunch",
            "label": "Lunch stop",
            "recommendation": {
                "place_id": "lunch",
                "name": "Local Lunch",
                "member_fit": [
                    {"user_id": 1, "display_name": "Wanyea", "fit": 0.82},
                    {"user_id": 2, "display_name": "Ari", "fit": 0.52},
                ],
            },
        },
    ]

    party_fit = service._party_fit(stops)

    assert party_fit["coverage_share"] == 0.5
    assert party_fit["covered_member_count"] == 1
    assert party_fit["underserved_count"] == 1
    assert party_fit["underserved_members"][0]["display_name"] == "Ari"
    assert party_fit["members"][1]["coverage_status"] == "needs_match"
    assert party_fit["coverage_plan"]["status"] == "needs_member_coverage"
    assert "Ari may need a stronger route stop" in party_fit["message"]
    assert party_fit["compromise_brief"]["status"] == "needs_coverage"
    assert party_fit["compromise_brief"]["most_compromised_member"]["display_name"] == "Ari"
    assert party_fit["compromise_brief"]["dominant_member"]["display_name"] == "Wanyea"
    assert "Ari need" in party_fit["compromise_brief"]["headline"]


def test_swap_guide_surfaces_group_coverage_plan(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    route_days = [
        {
            "day": 1,
            "party_fit": {
                "members": [
                    {
                        "user_id": 1,
                        "display_name": "Wanyea",
                        "average_fit": 0.82,
                        "coverage_status": "covered",
                        "strong_match_count": 1,
                    },
                    {
                        "user_id": 2,
                        "display_name": "Ari",
                        "average_fit": 0.48,
                        "coverage_status": "needs_match",
                        "strong_match_count": 0,
                    },
                ],
            },
            "stops": [
                {
                    "slot_id": "afternoon_gem",
                    "label": "Afternoon gem",
                    "recommendation": {
                        "place_id": "owner-gallery",
                        "name": "Owner Favorite Gallery",
                    },
                    "alternatives": [
                        {
                            "place_id": "ari-market",
                            "name": "Ari's Makers Market",
                            "swap_impact": {
                                "route_score_delta": -0.02,
                                "authenticity_delta": 0.07,
                                "member_fit_delta": 0.14,
                                "member_rebalance_delta": 0.11,
                                "group_consensus_delta": 0.09,
                                "group_consensus_gap_delta": 0.12,
                                "travel_efficiency_delta": 0.01,
                                "low_friction_score": 0.82,
                                "low_friction_label": "Low-friction swap",
                                "target_members": [
                                    {
                                        "user_id": 2,
                                        "display_name": "Ari",
                                        "current_fit": 0.48,
                                        "replacement_fit": 0.78,
                                        "delta": 0.3,
                                        "coverage_status": "covered_by_swap",
                                    },
                                ],
                                "swap_readiness": {
                                    "status": "party_rebalance",
                                    "label": "Party rebalance",
                                    "score": 0.84,
                                    "low_friction_score": 0.82,
                                    "low_friction_label": "Low-friction swap",
                                    "next_action": "Use this if the group fit matters more than keeping the current stop.",
                                },
                                "swap_decision": {
                                    "headline": "Best for the group.",
                                    "should_swap": True,
                                    "best_when": "Choose this when one traveler needs a better fit.",
                                    "tradeoff": "Small route tradeoff.",
                                    "confidence": 0.84,
                                    "badges": [{"label": "Party", "detail": "better", "tone": "positive"}],
                                },
                                "reasons": ["Gives Ari a stronger match"],
                            },
                        },
                    ],
                },
            ],
        },
    ]

    guide = service._swap_guide(route_days)

    assert guide["consensus_upgrade_count"] == 1
    assert guide["party_upgrade_count"] == 1
    assert guide["party_coverage_plan"]["status"] == "actionable"
    assert guide["party_coverage_plan"]["actionable_member_count"] == 1
    assert "Ari" in guide["party_coverage_plan"]["headline"]
    ari = next(member for member in guide["party_coverage_plan"]["members"] if member["display_name"] == "Ari")
    assert ari["suggested_swaps"][0]["to_name"] == "Ari's Makers Market"
    assert ari["suggested_swaps"][0]["coverage_status"] == "covered_by_swap"
    assert guide["best_swaps"][0]["group_consensus_delta"] == 0.09
    assert guide["best_swaps"][0]["group_consensus_gap_delta"] == 0.12
    assert guide["best_swaps"][0]["target_members"][0]["display_name"] == "Ari"
    assert guide["next_action"] == "Preview the suggested swap for Ari before sharing this route."


def test_itinerary_swap_marks_nearby_same_slot_option_low_friction(app_context):
    service = ItineraryRecommendationService(
        recommendation_service=None,
        local_event_service=None,
        travel_logistics_service=None,
    )
    slot = {
        "preferred_types": {"cafe", "coffee_shop"},
    }
    route_context = {
        "groups": {},
        "types": {},
        "member_totals": {},
        "member_counts": {},
        "points": [(37.422, -122.084)],
        "last_point": (37.422, -122.084),
    }
    current = {
        "place_id": "current-cafe",
        "score": 0.70,
        "display": {"types": ["cafe"]},
        "components": {"authenticity": 0.58, "quality": 0.62},
        "latitude": 37.422,
        "longitude": -122.084,
    }
    alternative = {
        "place_id": "nearby-coffee",
        "score": 0.74,
        "display": {"types": ["cafe", "coffee_shop"]},
        "components": {"authenticity": 0.66, "quality": 0.65},
        "latitude": 37.4222,
        "longitude": -122.0842,
    }

    swap_impact = service._swap_impact(slot, current, alternative, route_context)

    assert swap_impact["low_friction_score"] >= 0.78
    assert swap_impact["low_friction_label"] == "Low-friction swap"
    assert swap_impact["swap_readiness"]["low_friction_label"] == "Low-friction swap"
    assert swap_impact["swap_decision"]["should_swap"] is True
    assert any(
        badge["label"] == "Friction" and badge["detail"] == "low"
        for badge in swap_impact["swap_decision"]["badges"]
    )


def test_itinerary_rejects_non_friend_members(app_context):
    user = create_user("owner@example.com", ["restaurant"])
    stranger = create_user("stranger@example.com", ["museum"])

    with pytest.raises(ValueError, match="accepted friends"):
        itinerary_for(user, rich_candidate_set(), member_ids=[stranger.id])


def test_itinerary_includes_nearby_local_events(app_context):
    user = create_user("events@example.com", ["market", "art_gallery"])
    db.session.add(LocalEvent(
        title="Neighborhood Night Market",
        description="Local makers, food pop-ups, and music.",
        city="Test City",
        latitude=37.423,
        longitude=-122.084,
        starts_at=datetime.utcnow() + timedelta(days=3),
        category="market",
        source_name="Community board",
        source_url="https://example.com/night-market",
        reservation_url="https://example.com/night-market/rsvp",
        authenticity_score=0.92,
    ))
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set())

    assert result["local_events"]["status"] == "ready"
    assert result["local_events"]["events"][0]["title"] == "Neighborhood Night Market"
    assert result["local_events"]["events"][0]["reservation_url"].endswith("/rsvp")
    assert result["local_events"]["events"][0]["preference_fit"] > 0.5
    assert result["local_events"]["summary"]["reservation_ready_count"] == 1
    assert result["local_events"]["summary"]["sourced_count"] == 1
    assert result["local_events"]["summary"]["top_event_title"] == "Neighborhood Night Market"
    assert "Matches your Adventour interests" in result["local_events"]["events"][0]["explanation"]
    assert result["route_readiness"]["event_score"] >= 0.82
    assert result["route_readiness"]["event_summary"]["top_event_title"] == "Neighborhood Night Market"
    assert result["route_readiness"]["event_summary"]["route_reservation_ready_count"] == 1
    assert "Reservation-ready local events are paired with this route." in result["route_readiness"]["strengths"]


def test_itinerary_route_readiness_values_friend_backed_local_events(app_context):
    user = create_user("socialroute@example.com", ["market", "art_gallery"])
    friend = create_user("socialfriend@example.com", ["market", "music"])
    make_friends(user, friend)
    event = LocalEvent(
        title="Friend-Loved Makers Market",
        description="A local market with friend interest and RSVP details.",
        city="Test City",
        latitude=37.423,
        longitude=-122.084,
        starts_at=datetime.utcnow() + timedelta(days=3),
        category="market",
        source_name="Community board",
        source_url="https://example.com/friend-market",
        reservation_url="https://example.com/friend-market/rsvp",
        authenticity_score=0.92,
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(LocalEventInterest(
        event_id=event.id,
        user_id=friend.id,
        status="interested",
    ))
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set(), member_ids=[friend.id])

    assert result["local_events"]["summary"]["social_readiness"]["status"] == "ready"
    assert result["local_events"]["summary"]["route_friend_signal_count"] == 1
    assert result["local_events"]["summary"]["route_social_anchor_count"] == 1
    route_anchor = result["local_events"]["summary"]["route_social_anchor"]
    assert route_anchor["title"] == "Friend-Loved Makers Market"
    assert route_anchor["friend_signal_count"] == 1
    assert route_anchor["reservation_ready"] is True
    assert route_anchor["action_url"].endswith("/rsvp")
    assert route_anchor["route_context"]["slot_id"] in {"late_morning_discovery", "afternoon_gem"}
    assert "selected friend signal" in route_anchor["reason"]
    assert result["route_readiness"]["event_social_score"] >= 0.5
    assert result["route_readiness"]["event_social_summary"]["meetup_ready"] is True
    assert result["route_readiness"]["event_score"] >= 0.86
    assert "Friend-backed local events are paired with this route." in result["route_readiness"]["strengths"]
    event_packet = result["trip_packet"]["event_packet"]
    assert event_packet["route_social_anchor"]["title"] == "Friend-Loved Makers Market"
    assert event_packet["route_social_anchor"]["score"] == route_anchor["score"]
    assert event_packet["meetup_anchor"]["title"] == "Friend-Loved Makers Market"
    assert event_packet["meetup_anchor"]["friend_signal_count"] == 1
    assert event_packet["meetup_anchor"]["reservation_ready"] is True
    assert event_packet["meetup_anchor"]["action_url"].endswith("/rsvp")
    assert event_packet["meetup_anchor"]["route_context"]["slot_id"] in {"late_morning_discovery", "afternoon_gem"}
    assert "friend signal" in event_packet["meetup_anchor"]["reason"]
    assert "RSVP" in event_packet["meetup_anchor"]["next_action"]


def test_itinerary_event_readiness_penalizes_unpaired_events(app_context):
    user = create_user("unpairedevent@example.com", ["market", "art_gallery"])
    db.session.add(LocalEvent(
        title="Far Lecture Night",
        description="A sourced event that is too far away and does not match route timing.",
        city="Test City",
        latitude=37.465,
        longitude=-122.125,
        starts_at=(datetime.utcnow() + timedelta(days=2)).replace(hour=4, minute=0, second=0, microsecond=0),
        category="lecture",
        source_name="Official calendar",
        source_url="https://example.com/far-lecture",
        reservation_url="https://example.com/far-lecture/rsvp",
        authenticity_score=0.9,
    ))
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set())

    assert result["local_events"]["status"] == "ready"
    assert result["local_events"]["summary"]["route_match_count"] == 0
    assert result["route_readiness"]["event_score"] <= 0.68
    assert "Local events found, but they are not paired to the route yet." in result["route_readiness"]["warnings"]


def test_itinerary_local_events_rank_preference_fit(app_context):
    user = create_user("eventfit@example.com", ["market"])
    starts_at = datetime.utcnow() + timedelta(days=2)
    db.session.add_all([
        LocalEvent(
            title="Makers Market",
            description="Local makers and food stands.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=starts_at,
            category="market",
            source_name="Local calendar",
            authenticity_score=0.82,
        ),
        LocalEvent(
            title="Late Comedy Showcase",
            description="A nearby show with the same date and local signal.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=starts_at,
            category="comedy",
            source_name="Local calendar",
            authenticity_score=0.82,
        ),
    ])
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set())
    events = result["local_events"]["events"]

    assert [event["title"] for event in events[:2]] == ["Makers Market", "Late Comedy Showcase"]
    assert events[0]["score_components"]["preference_fit"] > events[1]["score_components"]["preference_fit"]


def test_itinerary_local_events_rank_actionable_sources(app_context):
    user = create_user("eventlinks@example.com", ["market"])
    starts_at = datetime.utcnow() + timedelta(days=2)
    db.session.add_all([
        LocalEvent(
            title="Sourced Makers Market",
            description="Local makers with a ticket link.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=starts_at,
            category="market",
            source_name="Official local calendar",
            source_url="https://example.com/sourced-market",
            reservation_url="https://example.com/sourced-market/rsvp",
            authenticity_score=0.82,
        ),
        LocalEvent(
            title="Loose Market Mention",
            description="Similar event, but missing links.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=starts_at,
            category="market",
            source_name="Flyer",
            authenticity_score=0.82,
        ),
    ])
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set())
    events = result["local_events"]["events"]

    assert [event["title"] for event in events[:2]] == ["Sourced Makers Market", "Loose Market Mention"]
    assert events[0]["score_components"]["source_quality"] > events[1]["score_components"]["source_quality"]
    assert events[0]["score_components"]["reservation_readiness"] > events[1]["score_components"]["reservation_readiness"]
    assert result["local_events"]["summary"]["reservation_ready_count"] == 1
    assert result["local_events"]["summary"]["readiness_score"] >= events[0]["score"]
    assert "Reliable source attached" in events[0]["explanation"]
    assert "Reservation link ready" in events[0]["explanation"]


def test_itinerary_local_events_recommend_event_platform_when_reservation_missing(app_context):
    user = create_user("eventrsvp@example.com", ["market"])
    db.session.add(LocalEvent(
        title="Source Only Night Market",
        description="A local market with a source but no RSVP link yet.",
        city="Test City",
        latitude=37.423,
        longitude=-122.084,
        starts_at=datetime.utcnow() + timedelta(days=2),
        category="market",
        source_name="Local calendar",
        source_url="https://example.com/source-only-market",
        authenticity_score=0.84,
    ))
    db.session.commit()

    result = itinerary_for(user, rich_candidate_set())
    source_summary = result["local_events"]["summary"]["source_summary"]
    recommended = source_summary["recommended_external_source"]

    assert result["local_events"]["status"] == "ready"
    assert result["local_events"]["summary"]["reservation_ready_count"] == 0
    assert recommended["source_type"] == "event_platform_search"
    assert "RSVP" in recommended["reason"]
    assert any(
        source["source_type"] == "event_platform_search" and source["is_recommended"]
        for source in result["local_events"]["external_sources"]
    )


def test_itinerary_local_events_respect_travel_dates(app_context):
    user = create_user("datedevents@example.com", ["market", "art_gallery"])
    trip_start = datetime.utcnow() + timedelta(days=8)
    matching_event_time = trip_start + timedelta(hours=19)
    outside_event_time = trip_start + timedelta(days=4)
    db.session.add_all([
        LocalEvent(
            title="Trip Weekend Makers Market",
            description="A local market during the planned trip.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=matching_event_time,
            category="market",
            source_name="Local calendar",
            source_url="https://example.com/makers-market",
            reservation_url="https://example.com/makers-market/rsvp",
            authenticity_score=0.9,
        ),
        LocalEvent(
            title="Wrong Weekend Popup",
            description="Interesting, but outside the planned dates.",
            city="Test City",
            latitude=37.423,
            longitude=-122.084,
            starts_at=outside_event_time,
            category="popup",
            source_name="Local calendar",
            authenticity_score=0.95,
        ),
    ])
    db.session.commit()

    result = itinerary_for(
        user,
        rich_candidate_set(),
        constraints={
            "travel_dates": {
                "start": trip_start.date().isoformat(),
                "end": (trip_start + timedelta(days=1)).date().isoformat(),
            },
        },
    )

    titles = [event["title"] for event in result["local_events"]["events"]]
    assert titles == ["Trip Weekend Makers Market"]
    assert result["local_events"]["date_window"]["source"] == "travel_dates"
    assert result["local_events"]["events"][0]["fit_label"] == "During trip"
