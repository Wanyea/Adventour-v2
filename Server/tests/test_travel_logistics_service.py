from adventour_backend.services.travel_logistics_service import TravelLogisticsService


def test_booking_plan_exposes_provider_status_and_local_transport_estimate():
    service = TravelLogisticsService()
    route_days = [{
        "day": 1,
        "stops": [
            {"slot_id": "morning_anchor"},
            {"slot_id": "lunch"},
            {"slot_id": "evening_finish"},
        ],
    }]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=2,
        destination_label="Austin, TX",
        origin_label="Orlando, FL",
        travel_dates={"start": "2026-07-01", "end": "2026-07-03"},
        trip_style="day",
    )

    assert result["status"] == "provider_ready_contract"
    assert result["party_size"] == 2
    assert result["days"] == 1
    assert result["nights"] == 2
    assert result["duration_alignment"]["status"] == "watch"
    assert result["duration_alignment"]["route_days"] == 1
    assert result["duration_alignment"]["calendar_nights"] == 2
    assert "overnight dates" in result["duration_alignment"]["headline"]
    assert result["reservation_storage"]["endpoint"] == "/api/reservations"
    assert result["missing_inputs"] == []
    assert result["summary"]["readiness_score"] >= 0.75
    assert result["summary"]["duration_alignment_status"] == "watch"
    assert result["summary"]["missing_input_count"] == 0
    assert result["summary"]["next_action_count"] > 0
    assert result["summary"]["reservation_storage_ready"] is True
    assert result["planning_burden"]["level"] == "medium"
    assert result["planning_burden"]["action_needed_count"] == 0
    assert result["planning_burden"]["setup_count"] == 1
    assert result["planning_burden"]["highest_friction_item"]["id"] == "local_transport"
    assert result["planning_burden"]["booking_order"][0]["id"] == "duration_alignment"
    assert result["booking_timeline"]["status"] == "needs_attention"
    assert result["booking_timeline"]["headline"].startswith("A few booking")
    assert result["booking_timeline"]["items"][0]["component_type"] == "trip_duration"
    assert [item["phase"] for item in result["booking_timeline"]["items"][1:4]] == ["book", "book", "setup"]
    assert result["booking_timeline"]["items"][1]["source_url"].startswith("https://www.google.com/travel/flights")
    assert result["booking_timeline"]["items"][1]["stores_reservation"] is True
    assert result["booking_handoff"]["status"] == "ready"
    assert result["booking_handoff"]["ready_to_quote_count"] == 2
    assert result["booking_handoff"]["ready_to_save_count"] >= 4
    assert result["booking_handoff"]["missing_input_count"] == 2
    assert [item["component_type"] for item in result["booking_handoff"]["quote_ready"]] == ["flight", "stay"]
    assert any(item["reservation_type"] == "flight" for item in result["booking_handoff"]["save_ready"])
    assert result["booking_handoff"]["setup_ready"][0]["provider_label"] == "CapMetro"
    assert result["booking_handoff"]["setup_ready"][0]["recommended_option"]["id"] == "transit"
    assert result["booking_checklist"]["status"] == "ready_with_manual_steps"
    assert result["booking_checklist"]["blocking_count"] == 0
    assert result["booking_checklist"]["ready_count"] >= 4
    checklist_items = {item["id"]: item for item in result["booking_checklist"]["items"]}
    prep_items_by_id = {item["id"]: item for item in result["prep_checklist"]["items"]}
    assert prep_items_by_id["duration_alignment"]["status"] == "manual"
    assert "Switch to Weekend/Vacation" in prep_items_by_id["duration_alignment"]["action"]
    assert checklist_items["trip_basics"]["status"] == "ready"
    assert checklist_items["provider_links"]["link_count"] >= 2
    assert checklist_items["reservation_wallet"]["status"] == "ready"
    assert checklist_items["local_transport"]["provider"] == "CapMetro"
    assert checklist_items["tickets_and_rsvps"]["status"] == "manual"
    assert any(action["type"] == "local_transport" for action in result["next_best_actions"])
    assert result["prep_checklist"]["status"] == "ready_with_optional_steps"
    assert result["prep_checklist"]["headline"].startswith("Core travel setup is ready")
    assert [link["component_type"] for link in result["booking_action_links"][:2]] == ["flight", "stay"]
    assert result["booking_action_links"][0]["reservation_type"] == "flight"
    assert result["booking_action_links"][0]["draft_title"] == "Flights"
    assert result["booking_action_links"][0]["draft_provider"] == "Google Flights"
    assert result["booking_action_links"][0]["draft_booking_url"].startswith("https://www.google.com/travel/flights")
    assert "Search hint:" in result["booking_action_links"][0]["draft_notes"]
    assert any(link["component_type"] == "local_transport" and link["provider_label"] == "CapMetro" for link in result["booking_action_links"])

    components = {component["type"]: component for component in result["components"]}
    prep_items = {item["id"]: item for item in result["prep_checklist"]["items"]}
    assert components["flight"]["status"] == "ready_for_provider"
    assert components["flight"]["estimate"] is None
    assert components["flight"]["provider_options"][0]["label"] == "Google Flights"
    assert components["flight"]["provider_options"][0]["url"].startswith("https://www.google.com/travel/flights?q=")
    assert "Orlando%2C+FL+to+Austin%2C+TX" in components["flight"]["provider_options"][0]["url"]
    assert "Orlando, FL to Austin, TX" in components["flight"]["search_hint"]
    assert components["stay"]["status"] == "ready_for_provider"
    assert components["stay"]["nights"] == 2
    assert components["stay"]["missing_inputs"] == ["lodging_type", "neighborhood"]
    assert components["local_transport"]["status"] == "estimated"
    assert components["local_transport"]["estimate"]["per_person_high"] > 0
    assert components["local_transport"]["setup_provider"] == "CapMetro"
    assert "CapMetro" in components["local_transport"]["setup"]
    assert components["local_transport"]["options"]
    assert components["local_transport"]["next_steps"]
    assert components["local_transport"]["provider_options"][0]["label"] == "CapMetro"
    assert any(option["id"] == "transit" and option["recommended"] for option in components["local_transport"]["options"])
    assert prep_items["local_transport"]["provider"] == "CapMetro"
    assert prep_items["local_transport"]["status"] == "ready"
    assert prep_items["tickets"]["status"] == "manual"
    assert components["event_or_place"]["stores_reservation"] is True
    assert components["event_or_place"]["next_steps"]


def test_booking_plan_marks_weekend_duration_aligned():
    service = TravelLogisticsService()
    route_days = [
        {"day": 1, "stops": [{"slot_id": "morning_anchor"}]},
        {"day": 2, "stops": [{"slot_id": "brunch"}]},
    ]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=2,
        destination_label="New York, NY",
        origin_label="Orlando, FL",
        travel_dates={"start": "2026-07-10", "end": "2026-07-12"},
        trip_style="weekend",
    )

    assert result["duration_alignment"]["status"] == "aligned"
    assert result["duration_alignment"]["trip_style"] == "weekend"
    assert result["duration_alignment"]["route_days"] == 2
    assert result["duration_alignment"]["calendar_nights"] == 2
    assert "duration_alignment" not in {item["id"] for item in result["prep_checklist"]["items"]}


def test_booking_plan_marks_stay_needed_for_overnight_routes():
    service = TravelLogisticsService()
    route_days = [
        {"day": 1, "stops": [{"slot_id": "morning_anchor"}, {"slot_id": "lunch"}]},
        {"day": 2, "stops": [{"slot_id": "museum"}, {"slot_id": "dinner"}]},
    ]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=1,
        destination_label="New York, NY",
        trip_style="weekend",
    )

    components = {component["type"]: component for component in result["components"]}
    assert result["trip_style"] == "weekend"
    assert result["nights"] == 1
    assert result["missing_inputs"] == ["origin", "start_date", "end_date"]
    assert result["summary"]["missing_input_count"] == 3
    assert result["summary"]["blocked_component_count"] == 2
    assert result["summary"]["readiness_score"] < 0.5
    assert result["planning_burden"]["level"] == "high"
    assert result["planning_burden"]["action_needed_count"] >= 3
    assert result["planning_burden"]["highest_friction_item"]["id"] == "trip_details"
    assert "origin" in result["planning_burden"]["highest_friction_item"]["detail"]
    assert result["planning_burden"]["next_action"].startswith("Finish destination")
    assert result["booking_timeline"]["status"] == "needs_details"
    assert result["booking_timeline"]["items"][0]["phase"] == "unlock"
    assert result["booking_timeline"]["items"][0]["status"] == "action_needed"
    assert "origin" in result["booking_timeline"]["items"][0]["detail"]
    assert result["booking_handoff"]["status"] == "needs_details"
    assert result["booking_handoff"]["quote_ready"][0]["component_type"] == "flight"
    assert result["booking_handoff"]["quote_ready"][1]["component_type"] == "stay"
    assert result["booking_handoff"]["ready_to_quote_count"] == 2
    assert result["booking_handoff"]["missing_input_count"] >= 3
    assert result["booking_handoff"]["required_inputs"][0]["id"] == "origin"
    assert any(item.get("component_type") == "stay" for item in result["booking_handoff"]["required_inputs"])
    assert result["booking_checklist"]["status"] == "needs_details"
    assert result["booking_checklist"]["blocking_count"] >= 1
    assert result["booking_checklist"]["next_action"].startswith("Add origin")
    checklist_items = {item["id"]: item for item in result["booking_checklist"]["items"]}
    assert checklist_items["trip_basics"]["blocking"] is True
    assert "origin" in checklist_items["trip_basics"]["missing_inputs"]
    assert checklist_items["provider_links"]["blocking"] is True
    assert result["prep_checklist"]["status"] == "needs_attention"
    assert result["prep_checklist"]["items"][0]["id"] == "trip_details"
    assert result["prep_checklist"]["items"][0]["status"] == "action_needed"
    assert components["flight"]["status"] == "needs_provider"
    assert components["flight"]["missing_inputs"] == ["origin", "dates"]
    assert components["flight"]["next_steps"][0] == "Add your departure city so Adventour can prepare flight search."
    assert components["stay"]["status"] == "needs_provider"
    assert components["stay"]["nights"] == 1
    assert components["stay"]["missing_inputs"] == ["dates", "lodging_type", "neighborhood"]
    assert components["stay"]["provider_options"][0]["label"] == "Hotels"
    assert components["stay"]["provider_options"][0]["url"].startswith("https://www.google.com/travel/hotels?q=")
    assert "New+York%2C+NY" in components["stay"]["provider_options"][0]["url"]
    assert components["stay"]["provider_options"][1]["url"].startswith("https://www.airbnb.com/s/all?q=")
    assert "New York, NY" in components["stay"]["search_hint"]
    assert result["booking_action_links"][0]["component_type"] == "flight"
    assert result["booking_action_links"][1]["component_type"] == "stay"
    assert result["booking_action_links"][1]["url"].startswith("https://www.google.com/travel/hotels?q=")
    assert components["local_transport"]["setup_provider"] == "MTA / OMNY"
    assert "OMNY" in components["local_transport"]["setup"]
    assert components["local_transport"]["setup_source_url"].startswith("https://www.mta.info")
    assert result["next_best_actions"][0]["type"] == "missing_input"


def test_booking_plan_uses_lodging_preferences_for_stay_search():
    service = TravelLogisticsService()
    route_days = [
        {"day": 1, "stops": [{"slot_id": "morning_anchor"}, {"slot_id": "evening_finish"}]},
        {"day": 2, "stops": [{"slot_id": "lunch"}, {"slot_id": "afternoon_gem"}]},
    ]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=3,
        destination_label="New York, NY",
        origin_label="Orlando, FL",
        travel_dates={"start": "2026-07-10", "end": "2026-07-12"},
        trip_style="weekend",
        lodging_type="home_share",
        stay_neighborhood="Williamsburg",
    )

    components = {component["type"]: component for component in result["components"]}
    stay = components["stay"]

    assert result["lodging_type"] == "home_share"
    assert result["stay_neighborhood"] == "Williamsburg"
    assert stay["missing_inputs"] == []
    assert stay["provider_options"][0]["label"] == "Home-share"
    assert "Williamsburg" in stay["provider_options"][0]["url"]
    assert "home-share in New York, NY near Williamsburg" in stay["search_hint"]
    assert any("Williamsburg" in step for step in stay["next_steps"])


def test_booking_plan_recommends_rental_for_spread_out_overnight_route():
    service = TravelLogisticsService()
    route_days = [
        {
            "day": 1,
            "stops": [
                {"recommendation": {"latitude": 28.5384, "longitude": -81.3789}},
                {"recommendation": {"latitude": 28.6100, "longitude": -81.2000}},
                {"recommendation": {"latitude": 28.4158, "longitude": -81.2989}},
            ],
        },
        {
            "day": 2,
            "stops": [
                {"recommendation": {"latitude": 28.5384, "longitude": -81.3789}},
                {"recommendation": {"latitude": 28.3100, "longitude": -81.5500}},
            ],
        },
    ]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=2,
        destination_label="Orlando, FL",
        origin_label="Atlanta, GA",
        travel_dates={"start": "2026-07-10", "end": "2026-07-12"},
        trip_style="weekend",
        lodging_type="hotel",
        stay_neighborhood="Downtown Orlando",
    )

    local_transport = {
        component["type"]: component
        for component in result["components"]
    }["local_transport"]

    assert local_transport["route_distance_meters"] > 25000
    assert local_transport["mode"] == "transit_pass_or_rental"
    assert local_transport["setup_provider"] == "LYNX / SunRail"
    assert "rental" in local_transport["setup"].lower()
    assert any("parking" in step.lower() for step in local_transport["setup_steps"])
    assert any(option["id"] == "rental_car" and option["recommended"] for option in local_transport["options"])
    prep_local_transport = next(item for item in result["prep_checklist"]["items"] if item["id"] == "local_transport")
    assert prep_local_transport["detail"].startswith("Rental car")
    assert prep_local_transport["source_url"].startswith("https://www.golynx.com")
    assert result["summary"]["estimate_ready_count"] == 1
    assert result["planning_burden"]["setup_items"][0]["provider"] == "LYNX / SunRail"
    assert result["planning_burden"]["highest_friction_item"]["id"] == "local_transport"
    assert "LYNX / SunRail" in result["planning_burden"]["highest_friction_item"]["action"]


def test_booking_plan_respects_preferred_local_transport():
    service = TravelLogisticsService()
    route_days = [{
        "day": 1,
        "stops": [
            {"recommendation": {"latitude": 40.7128, "longitude": -74.0060}},
            {"recommendation": {"latitude": 40.7306, "longitude": -73.9352}},
            {"recommendation": {"latitude": 40.7580, "longitude": -73.9855}},
        ],
    }]

    result = service.build_booking_plan(
        route_days=route_days,
        party_size=2,
        destination_label="New York, NY",
        preferred_local_transport="rideshare",
    )

    local_transport = {
        component["type"]: component
        for component in result["components"]
    }["local_transport"]

    assert result["preferred_local_transport"] == "rideshare"
    assert local_transport["mode"] == "rideshare"
    assert local_transport["preferred_local_transport"] == "rideshare"
    assert any(option["id"] == "rideshare" and option["recommended"] for option in local_transport["options"])
    assert all(
        option["id"] == "rideshare" or not option["recommended"]
        for option in local_transport["options"]
    )
