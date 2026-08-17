from recommender_lab import run_scenario


def test_recommender_lab_group_scenario_creates_friendship():
    result = run_scenario("group_blend", scoring_profile="group_friendly")

    assert result["member_count"] == 2
    assert result["scoring_profile"] == "group_friendly"
    assert result["recommendations"]


def test_recommender_lab_planned_route_returns_readiness():
    result = run_scenario("planned_city", scoring_profile="phase1_balanced", planned=True)

    assert result["mode"] == "planned_itinerary"
    assert result["route_readiness"]["planned_stop_count"] > 0
    assert result["route_readiness"]["expected_stop_count"] == 4
    assert result["price_breakdown"]["travelers"]
