from argparse import Namespace

import real_place_lab


class FakeProvider:
    name = "fake-live"

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return [
            candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], 4.7, 80, price_level=1),
            candidate("City Art Walk", "art-1", ["art_gallery"], 4.8, 55, price_level=1),
            candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], 4.7, 45, price_level=1),
            candidate("Late Night Jazz", "jazz-1", ["bar", "concert_hall"], 4.6, 40, price_level=2),
        ]


def candidate(name, place_id, types, rating, ratings_total, price_level=2):
    return {
        "provider": "fake-live",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": 37.422, "lng": -122.084}},
        "business_status": "OPERATIONAL",
    }


def args(**overrides):
    base = {
        "lat": 37.421998333333335,
        "lng": -122.084,
        "radius": 3200,
        "limit": 8,
        "tags": ["cafe", "restaurant", "art_gallery"],
        "friend_tags": [],
        "scoring_profile": None,
        "pace": "balanced",
        "trip_style": "day",
        "budget_profile": "flexible",
        "days": 1,
        "destination_label": "Fake Live City",
        "suite": None,
        "min_suite_status": "watch",
        "output": None,
        "fail_on_suite_gate": False,
        "require_friend_ready": False,
        "require_quote_ready": False,
    }
    base.update(overrides)
    return Namespace(**base)


def test_real_place_lab_planned_route_uses_provider_candidates(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    result = real_place_lab.run_lab(args(scoring_profile="phase1_balanced"), planned=True)

    assert result["mode"] == "planned_itinerary"
    assert result["scoring_profile"] == "phase1_balanced"
    assert result["route_readiness"]["planned_stop_count"] > 0
    assert result["route_readiness"]["expected_stop_count"] == 4


def test_real_place_lab_can_build_group_recommendations(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    result = real_place_lab.run_lab(
        args(scoring_profile="group_friendly", friend_tags=[["museum", "art_gallery"]]),
        planned=False,
    )

    assert result["member_count"] == 2
    assert result["group_fit_summary"]["member_count"] == 2
    assert result["recommendations"]


def test_real_place_lab_can_build_group_planned_route(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    result = real_place_lab.run_lab(
        args(scoring_profile="group_friendly", friend_tags=[["museum", "art_gallery"]]),
        planned=True,
    )

    assert result["mode"] == "planned_itinerary"
    assert result["member_count"] == 2
    assert result["route_readiness"]["expected_stop_count"] == 4
    assert result["days"][0]["party_fit"]["members"]


def test_real_place_lab_suite_returns_readiness_summary(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    report = real_place_lab.run_suite(args(suite="friend_beta"))

    assert report["suite"] == "friend_beta"
    assert report["scenario_count"] == 6
    assert len(report["scenarios"]) == 6
    assert {item["id"] for item in report["scenarios"]} == {
        "orlando_spontaneous",
        "austin_day_route",
        "chicago_friend_blend",
        "seattle_friend_route",
        "nyc_events_route",
        "nyc_weekend_quotes",
    }
    group_item = next(item for item in report["scenarios"] if item["id"] == "chicago_friend_blend")
    assert group_item["friend_count"] == 1
    group_route_item = next(item for item in report["scenarios"] if item["id"] == "seattle_friend_route")
    assert group_route_item["friend_count"] == 1
    assert group_route_item["planned"] is True
    quote_item = next(item for item in report["scenarios"] if item["id"] == "nyc_weekend_quotes")
    assert quote_item["planned"] is True
    assert quote_item["quote_readiness"]["required_count"] == 2
    assert quote_item["quote_readiness"]["ready_count"] == 2
    assert quote_item["quote_readiness"]["status"] == "ready_to_quote"
    assert {item["type"] for item in quote_item["quote_readiness"]["items"]} >= {"flight", "stay"}
    assert all("status" in item for item in report["scenarios"])
    assert all("beta_testable" in item for item in report["scenarios"])
    assert all("test_verdict" in item for item in report["scenarios"])
    assert all("pipeline_diagnostic" in item for item in report["scenarios"])
    assert all("failed_checks" in item for item in report["scenarios"])
    assert report["ready_count"] + report["watch_count"] + report["needs_attention_count"] == 6
    assert "friend_testable_count" in report
    assert report["friend_scenario_count"] == 2
    assert "friend_ready_count" in report
    assert report["friend_testing_gate"]["required"] is True
    assert report["friend_testing_gate"]["scenario_count"] == 2
    assert "passed" in report["friend_testing_gate"]
    assert report["quote_scenario_count"] == 1
    assert report["quote_ready_count"] == 1
    assert report["quote_testing_gate"]["required"] is True
    assert report["quote_testing_gate"]["passed"] is True
    assert report["quote_testing_gate"]["scenario_count"] == 1
    assert "dimension_summary" in report
    assert "pipeline_issue_summary" in report
    assert report["remediation_plan"]
    assert all(item["scenario_count"] >= 1 for item in report["remediation_plan"])
    assert all(item["actions"] for item in report["remediation_plan"])
    verdict_dimensions = {
        dimension.get("name")
        for item in report["scenarios"]
        for dimension in (item.get("test_verdict") or {}).get("dimensions", [])
    }
    assert "model_signal" in verdict_dimensions
    assert report["gate"]["min_status"] == "watch"
    assert report["gate"]["requires_friend_ready"] is False
    assert report["gate"]["requires_quote_ready"] is False
    assert "passed" in report["gate"]


def test_real_place_lab_suite_gate_can_require_ready(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    report = real_place_lab.run_suite(args(suite="friend_beta", min_suite_status="ready"))

    assert report["gate"]["min_status"] == "ready"
    assert report["gate"]["failed_scenarios"]


def test_real_place_lab_suite_gate_can_require_friend_ready(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    report = real_place_lab.run_suite(args(suite="friend_beta", require_friend_ready=True))

    assert report["gate"]["requires_friend_ready"] is True
    assert set(report["friend_testing_gate"]["failed_scenarios"]).issubset(
        set(report["gate"]["failed_scenarios"])
    )
    assert report["gate"]["friend_failed_scenarios"] == report["friend_testing_gate"]["failed_scenarios"]
    assert report["gate"]["passed"] is False


def test_real_place_lab_remediation_plan_prioritizes_friend_and_quote_gaps():
    items = [
        {
            "id": "friend_gap",
            "status": "needs_attention",
            "friend_count": 1,
            "test_verdict": {
                "friend_testable": False,
                "blockers": ["Friend route needs coverage."],
                "next_actions": ["Add a stronger museum stop for Ari."],
            },
            "friend_readiness": {
                "headline": "Ari needs a stronger match.",
                "next_actions": ["Swap in an Ari-friendly art stop."],
            },
            "failed_checks": [
                {
                    "name": "friend_route_coverage",
                    "label": "Every traveler has a strong route stop",
                    "status": "fail",
                    "message": "Swap in stops that give the underserved traveler a strong match.",
                }
            ],
        },
        {
            "id": "quote_gap",
            "status": "watch",
            "friend_count": 0,
            "test_verdict": {"friend_testable": False},
            "quote_readiness": {
                "status": "needs_inputs",
                "required_count": 2,
                "missing_inputs": ["origin", "dates"],
            },
        },
    ]

    plan = real_place_lab.suite_remediation_plan(items)

    assert plan[0]["severity"] == "needs_attention"
    assert any(item["id"] == "friend_coverage" for item in plan)
    quote_item = next(item for item in plan if item["id"] == "travel_quotes")
    assert quote_item["scenario_ids"] == ["quote_gap"]
    assert "origin, dates" in quote_item["actions"][0]


def test_real_place_lab_suite_gate_can_require_quote_ready(monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())

    report = real_place_lab.run_suite(args(suite="friend_beta", require_quote_ready=True))

    assert report["gate"]["requires_quote_ready"] is True
    assert report["quote_testing_gate"]["passed"] is True
    assert report["gate"]["quote_failed_scenarios"] == []


def test_real_place_lab_writes_suite_report(tmp_path, monkeypatch):
    monkeypatch.setattr(real_place_lab, "GooglePlacesProvider", lambda: FakeProvider())
    report = real_place_lab.run_suite(args(suite="friend_beta"))
    path = tmp_path / "friend-beta-report.json"

    output_path = real_place_lab.write_suite_report(path, report)

    assert output_path == path
    assert path.exists()
    assert '"suite": "friend_beta"' in path.read_text(encoding="utf-8")
    assert '"gate"' in path.read_text(encoding="utf-8")
    assert '"friend_testing_gate"' in path.read_text(encoding="utf-8")
    assert '"quote_testing_gate"' in path.read_text(encoding="utf-8")
    assert '"remediation_plan"' in path.read_text(encoding="utf-8")
    assert '"test_verdict"' in path.read_text(encoding="utf-8")
    assert '"dimension_summary"' in path.read_text(encoding="utf-8")
    assert '"pipeline_issue_summary"' in path.read_text(encoding="utf-8")
