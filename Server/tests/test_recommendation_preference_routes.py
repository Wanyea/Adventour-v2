import os

os.environ["ADVENTOUR_DEV_AUTH"] = "true"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import app as server_app
from adventour_backend.models import Friendship, User, db


def auth_headers(email):
    return {"Authorization": f"Bearer dev:{email}"}


def reset_db():
    with server_app.app.app_context():
        db.drop_all()
        db.create_all()


def seed_user(email, preferences):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"dev-{username}",
        email=email,
        username=username,
        display_name=username,
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.flush()
    return user


def test_preference_insights_can_include_selected_accepted_friends_only():
    reset_db()
    client = server_app.app.test_client()

    with server_app.app.app_context():
        viewer = seed_user("viewer@example.com", ["cafe"])
        friend = seed_user("friend@example.com", ["museum"])
        stranger = seed_user("stranger@example.com", ["bar"])
        db.session.add(Friendship(user_id=viewer.id, friend_id=friend.id, status="accepted"))
        db.session.commit()
        friend_id = friend.id
        stranger_id = stranger.id

    response = client.get(
        f"/api/recommendations/preferences?member_ids={friend_id},{stranger_id}",
        headers=auth_headers("viewer@example.com"),
    )

    assert response.status_code == 200
    payload = response.get_json()
    insights = payload["preference_insights"]

    assert [insight["display_name"] for insight in insights] == ["viewer", "friend"]
    assert [member["display_name"] for member in payload["members"]] == ["viewer", "friend"]
    assert payload["members"][0]["is_viewer"] is True
    assert payload["members"][1]["is_viewer"] is False
    assert insights[0]["top_categories"][0]["tag"] == "cafe"
    assert insights[1]["top_categories"][0]["tag"] == "museum"


class FakeRecommendationService:
    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        return {
            "recommendations": [
                {
                    "name": "Hidden Cafe",
                    "display": {"types": ["cafe"]},
                    "authenticity_evidence": {"label": "Hidden gem"},
                    "recommendation_story": {
                        "headline": "A local-gem leaning pick.",
                        "reasons": ["Matches your cafe taste."],
                        "metrics": [{"id": "hidden_gem", "value": "strong"}],
                    },
                },
                {
                    "name": "Art Yard",
                    "display": {"types": ["art_gallery"]},
                    "authenticity_evidence": {"label": "Local-feeling"},
                    "recommendation_story": {
                        "headline": "A culture stop worth checking.",
                        "reasons": ["Adds variety."],
                        "metrics": [{"id": "variety", "value": "arts"}],
                    },
                },
            ],
            "provider_errors": [],
            "member_count": 1,
            "recommendation_quality": {
                "metrics": {
                    "returned": 2,
                    "local_feeling_share": 1.0,
                    "hidden_gem_count": 1,
                    "generic_risk_share": 0.0,
                },
                "strengths": ["Strong local-feeling mix in this basket."],
                "warnings": [],
            },
        }

    def build_preference_vector(self, member):
        return {"categories": {}}

    def preference_insights(self, member, vector):
        return {"user_id": member.id, "display_name": member.display_name, "top_categories": []}

    def learned_ranker_status(self):
        return {
            "applied": False,
            "available": False,
            "ready": False,
            "status": "not_loaded",
            "reason": "no_model",
            "model_type": None,
            "message": "No learned ranker model is loaded on the backend.",
        }


class FakeBasketCompareService:
    def __init__(self):
        self.calls = []

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        profile = constraints.get("scoring_profile")
        self.calls.append({
            "profile": profile,
            "learned_rerank": constraints.get("learned_rerank"),
            "location": location,
            "radius_meters": radius_meters,
            "member_ids": member_ids,
            "mode": mode,
            "record_impressions": constraints.get("record_impressions"),
        })
        strong_profile = profile == "authenticity_forward"
        return {
            "mode": mode,
            "scoring_profile": profile,
            "recommendations": [
                {
                    "name": f"{profile} first pick",
                    "score": 0.88 if strong_profile else 0.66,
                    "diversity_groups": ["arts_culture", "food_drink"] if strong_profile else ["food_drink"],
                    "authenticity_evidence": {"label": "Hidden gem" if strong_profile else "Local-feeling"},
                },
            ],
            "query_tags": ["museum", "cafe"],
            "member_count": 2,
            "group_fit_summary": {
                "fairness_score": 0.91 if strong_profile else 0.62,
                "lowest_fit": 0.74 if strong_profile else 0.48,
                "underserved_members": [] if strong_profile else [{"user_id": 2, "display_name": "friend"}],
            },
            "recommendation_quality": {
                "headline": "Recommendation basket is strong enough to test.",
                "metrics": {
                    "returned": 8,
                    "average_score": 0.88 if strong_profile else 0.66,
                    "local_feeling_share": 0.88 if strong_profile else 0.38,
                    "hidden_gem_count": 3 if strong_profile else 0,
                    "hidden_gem_share": 0.38 if strong_profile else 0.0,
                    "generic_risk_share": 0.03 if strong_profile else 0.22,
                    "average_group_fit": 0.82 if strong_profile else 0.58,
                    "provider_error_count": 0,
                },
                "strengths": ["Strong local-feeling mix in this basket."] if strong_profile else [],
                "warnings": [] if strong_profile else ["One traveler may need stronger matches."],
                "diagnostic": {
                    "status": "ready" if strong_profile else "watch",
                    "headline": "Recommendation pipeline looks healthy for this run." if strong_profile else "Experience variety is the first thing to tune.",
                    "primary_issue": None if strong_profile else {
                        "name": "variety",
                        "label": "Experience variety",
                        "status": "warn",
                        "score": 0.48,
                        "summary": "The weaker scout collapsed into one mood.",
                        "next_action": "Boost missing friend/tag groups or broaden the query mix.",
                    },
                },
            },
        }


class FakeGroupCoverageCompareService:
    def __init__(self):
        self.calls = []

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        profile = constraints.get("scoring_profile")
        self.calls.append(profile)
        group_profile = profile == "group_friendly"
        return {
            "mode": mode,
            "scoring_profile": profile,
            "member_count": 2,
            "scenario_readiness": {
                "status": "needs_attention",
                "beta_testable": False,
                "headline": "Recommendation basket needs tuning before it should be trusted.",
            },
            "recommendations": [
                {
                    "name": "Shared Gallery Cafe" if group_profile else "Solo Score Winner",
                    "score": 0.76 if group_profile else 0.91,
                    "diversity_groups": ["coffee_sweets", "arts_culture"] if group_profile else ["coffee_sweets"],
                    "authenticity_evidence": {"label": "Local-feeling"},
                    "recommendation_story": {"headline": "Explained pick."},
                },
            ],
            "group_fit_summary": {
                "fairness_score": 0.92 if group_profile else 0.58,
                "lowest_fit": 0.72 if group_profile else 0.42,
                "underserved_members": [] if group_profile else [{"user_id": 2, "display_name": "friend"}],
            },
            "slate_summary": {
                "metrics": {
                    "member_coverage_share": 1.0 if group_profile else 0.5,
                    "diversity_coverage": 0.7,
                    "dominant_group_share": 0.5 if group_profile else 1.0,
                    "missing_intent_count": 0,
                },
            },
            "recommendation_quality": {
                "headline": "Comparison test basket.",
                "metrics": {
                    "returned": 8,
                    "average_score": 0.76 if group_profile else 0.91,
                    "local_feeling_share": 0.6 if group_profile else 0.82,
                    "hidden_gem_count": 1 if group_profile else 3,
                    "hidden_gem_share": 0.12 if group_profile else 0.38,
                    "generic_risk_share": 0.08,
                    "average_group_fit": 0.8 if group_profile else 0.62,
                    "provider_error_count": 0,
                },
                "strengths": ["Travel-party fit is balanced enough to test."] if group_profile else [],
                "warnings": [] if group_profile else ["At least one traveler lacks a strong match in the current slate."],
            },
        }


class FakeLocalDiscoveryCompareService:
    def __init__(self):
        self.calls = []

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        profile = constraints.get("scoring_profile")
        self.calls.append(profile)
        local_opener = profile == "authenticity_forward"
        return {
            "mode": mode,
            "scoring_profile": profile,
            "member_count": 1,
            "scenario_readiness": {
                "status": "ready",
                "beta_testable": True,
                "headline": "Recommendation basket is strong enough to test.",
            },
            "recommendations": [
                {
                    "name": "Tiny Alley Kitchen" if local_opener else "Polished Brunch Hall",
                    "score": 0.84 if local_opener else 0.91,
                    "diversity_groups": ["food_drink"],
                    "authenticity_evidence": {"label": "Hidden gem" if local_opener else "Popular local"},
                    "ranking": {"local_discovery_rescue": local_opener},
                },
            ],
            "slate_summary": {
                "metrics": {
                    "diversity_coverage": 0.6,
                    "dominant_group_share": 1.0,
                    "missing_intent_count": 0,
                    "first_page_local_discovery_count": 1 if local_opener else 0,
                    "local_discovery_rescue_count": 1 if local_opener else 0,
                },
            },
            "recommendation_quality": {
                "headline": "Recommendation basket is strong enough to test.",
                "metrics": {
                    "returned": 8,
                    "average_score": 0.84 if local_opener else 0.91,
                    "local_feeling_share": 0.82 if local_opener else 0.58,
                    "hidden_gem_count": 2 if local_opener else 0,
                    "hidden_gem_share": 0.25 if local_opener else 0.0,
                    "generic_risk_share": 0.02 if local_opener else 0.08,
                    "provider_error_count": 0,
                    "first_page_local_discovery_count": 1 if local_opener else 0,
                    "local_discovery_rescue_count": 1 if local_opener else 0,
                },
                "strengths": ["Adventour made room for 1 first-page local discovery pick."] if local_opener else [],
                "warnings": [],
            },
        }


class FakeEventAnchorCompareService:
    def __init__(self):
        self.calls = []

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        profile = constraints.get("scoring_profile")
        self.calls.append(profile)
        event_profile = profile == "event_anchor"
        return {
            "mode": mode,
            "scoring_profile": profile,
            "member_count": 1,
            "recommendations": [
                {
                    "name": "Night Market Courtyard" if event_profile else "Popular Dinner Room",
                    "score": 0.79 if event_profile else 0.9,
                    "diversity_groups": ["shopping_market", "food_drink"] if event_profile else ["food_drink"],
                    "authenticity_evidence": {"label": "Local-feeling"},
                    "local_event_match": {
                        "title": "Neighborhood Night Market",
                        "reservation_url": "https://example.com/rsvp",
                        "source_url": "https://example.com/event",
                        "social": {"signal": 0.55, "friend_signal_count": 1},
                    } if event_profile else None,
                    "recommendation_story": {
                        "headline": "Explained event-backed pick." if event_profile else "Explained popular pick.",
                    },
                },
            ],
            "slate_summary": {
                "metrics": {
                    "diversity_coverage": 0.7,
                    "dominant_group_share": 0.5 if event_profile else 1.0,
                    "missing_intent_count": 0,
                },
            },
            "recommendation_quality": {
                "headline": "Recommendation basket is strong enough to test.",
                "metrics": {
                    "returned": 8,
                    "average_score": 0.79 if event_profile else 0.9,
                    "local_feeling_share": 0.76 if event_profile else 0.72,
                    "hidden_gem_count": 1,
                    "hidden_gem_share": 0.12,
                    "generic_risk_share": 0.04,
                    "provider_error_count": 0,
                    "local_event_backed_count": 2 if event_profile else 0,
                    "local_event_reservation_ready_count": 1 if event_profile else 0,
                    "local_event_source_ready_count": 2 if event_profile else 0,
                    "local_event_friend_signal_count": 1 if event_profile else 0,
                    "local_event_social_score": 0.55 if event_profile else 0.0,
                },
                "strengths": ["2 event-backed picks can anchor something timely nearby."] if event_profile else [],
                "warnings": [],
            },
        }


class FakeInactiveLearnedCompareService(FakeBasketCompareService):
    learned_reason = "no_model"
    training_data_health = None

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        result = super().recommend(
            user,
            location,
            radius_meters=radius_meters,
            member_ids=member_ids,
            constraints=constraints,
            mode=mode,
        )
        constraints = constraints or {}
        if constraints.get("learned_rerank"):
            result["learned_rerank"] = {
                "applied": False,
                "reason": self.learned_reason,
                "model_type": None,
            }
            if self.training_data_health:
                result["learned_rerank"]["training_data_health"] = self.training_data_health
        else:
            result["learned_rerank"] = {
                "applied": False,
                "reason": "not_enabled",
            }
        return result


class FakeThinDataLearnedCompareService(FakeInactiveLearnedCompareService):
    learned_reason = "training_data_needs_data"
    training_data_health = {
        "status": "needs_data",
        "summary": "Training data is too thin to trust beyond a smoke test.",
        "counts": {"labeled": 6, "requests": 3, "event_friend_signal": 1},
    }


class FakeProviderRegistry:
    def __init__(self):
        self.calls = []

    def search(self, tags, location, radius_meters=3200, constraints=None):
        self.calls.append({
            "tags": list(tags),
            "location": dict(location),
            "radius_meters": radius_meters,
            "constraints": dict(constraints or {}),
        })
        return ([{"name": "Cached Local Cafe"}], [])


def test_learned_ranker_status_reports_no_loaded_model(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    monkeypatch.setattr(server_app, "recommendation_service", FakeRecommendationService())

    response = client.get(
        "/api/recommendations/learned-ranker/status",
        headers=auth_headers("learnedstatus@example.com"),
    )

    assert response.status_code == 200
    payload = response.get_json()["learned_rerank"]
    assert payload["ready"] is False
    assert payload["available"] is False
    assert payload["reason"] == "no_model"


def test_learned_ranker_status_reports_ready_model(monkeypatch):
    class ReadyLearnedService(FakeRecommendationService):
        def learned_ranker_status(self):
            return {
                "applied": False,
                "available": True,
                "ready": True,
                "status": "ready",
                "reason": "promotion_gate_passed",
                "model_type": "adventour_logistic_ltr_baseline",
                "message": "Learned beta is loaded, current, and passed Adventour promotion gates.",
                "feature_compatibility": {"status": "pass", "reason": "feature_schema_current"},
                "promotion_gate": {"status": "pass", "can_promote": True},
                "training_data_health": {
                    "status": "watch",
                    "summary": "Training data can run, but needs more representative friend/event outcomes.",
                    "counts": {"labeled": 18, "requests": 6, "event_friend_signal": 1},
                    "blocking_checks": [],
                    "watch_checks": [
                        {"name": "request_diversity", "label": "Enough recommendation requests", "status": "warn"}
                    ],
                },
            }

    reset_db()
    client = server_app.app.test_client()
    monkeypatch.setattr(server_app, "recommendation_service", ReadyLearnedService())

    response = client.get(
        "/api/recommendations/learned-ranker/status",
        headers=auth_headers("learnedready@example.com"),
    )

    assert response.status_code == 200
    payload = response.get_json()["learned_rerank"]
    assert payload["ready"] is True
    assert payload["available"] is True
    assert payload["reason"] == "promotion_gate_passed"
    assert payload["feature_compatibility"]["status"] == "pass"
    assert payload["training_data_health"]["status"] == "watch"
    assert payload["training_data_health"]["counts"]["event_friend_signal"] == 1


def test_recommendations_response_includes_scenario_readiness(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    monkeypatch.setattr(server_app, "recommendation_service", FakeRecommendationService())

    response = client.post(
        "/api/recommendations",
        headers=auth_headers("ready@example.com"),
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scenario_readiness"]["mode"] == "basket"
    assert payload["scenario_readiness"]["status"] == "needs_attention"
    assert payload["scenario_readiness"]["checks"][0]["name"] == "candidate_depth"


def test_cached_provider_registry_reuses_fetches_across_scoring_profiles():
    registry = FakeProviderRegistry()
    cached = server_app._CachedProviderRegistry(registry)

    first = cached.search(
        ["cafe", "museum"],
        {"latitude": 37.422, "longitude": -122.084},
        radius_meters=3200,
        constraints={
            "avoid_chains": True,
            "scoring_profile": "phase1_balanced",
            "record_impressions": False,
        },
    )
    second = cached.search(
        ["museum", "cafe"],
        {"latitude": 37.422, "longitude": -122.084},
        radius_meters=3200,
        constraints={
            "avoid_chains": True,
            "scoring_profile": "authenticity_forward",
            "record_impressions": False,
            "learned_rerank": True,
            "allow_unpromoted_learned_rerank": True,
        },
    )

    assert first == second
    assert len(registry.calls) == 1
    assert registry.calls[0]["constraints"] == {"avoid_chains": True}
    assert cached.usage_summary() == {
        "search_count": 2,
        "provider_fetch_count": 1,
        "cache_hit_count": 1,
        "cache_entry_count": 1,
        "saved_fetch_count": 1,
        "stripped_constraint_keys": [
            "allow_unpromoted_learned_rerank",
            "learned_rerank",
            "record_impressions",
            "scoring_profile",
        ],
    }


def test_recommendation_compare_ranks_authentic_group_basket_first(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeBasketCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("compare@example.com"),
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 4200,
            "member_ids": [2],
            "mode": "spontaneous",
            "constraints": {"avoid_chains": True},
            "scoring_profiles": ["phase1_balanced", "authenticity_forward"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "authenticity_forward",
        "phase1_balanced",
    ]
    recommended = payload["comparisons"][0]
    assert recommended["first_pick"]["name"] == "authenticity_forward first pick"
    assert recommended["first_pick"]["authenticity_label"] == "Hidden gem"
    assert recommended["comparison_rank"]["local_feeling_share"] == 0.88
    assert recommended["comparison_rank"]["hidden_gem_count"] == 3
    assert any(tradeoff["label"] == "Local" for tradeoff in recommended["comparison_explanation"]["tradeoffs"])
    weaker = payload["comparisons"][1]
    assert weaker["pipeline_diagnostic"]["name"] == "variety"
    assert any(tradeoff["label"] == "Pipeline" for tradeoff in weaker["comparison_explanation"]["tradeoffs"])
    assert "Boost missing friend/tag groups" in weaker["comparison_explanation"]["cautions"][0]
    assert "recommendations" not in recommended
    assert [call["profile"] for call in fake_service.calls] == ["phase1_balanced", "authenticity_forward"]
    assert all(call["record_impressions"] is False for call in fake_service.calls)
    assert all(call["radius_meters"] == 4200 for call in fake_service.calls)


def test_recommendation_compare_prioritizes_friend_coverage_for_group_auto_scout(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeGroupCoverageCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("groupcompare@example.com"),
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "member_ids": [2],
            "mode": "spontaneous",
            "constraints": {"avoid_chains": True},
            "scoring_profiles": ["phase1_balanced", "group_friendly"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "group_friendly"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "group_friendly",
        "phase1_balanced",
    ]
    recommended = payload["comparisons"][0]
    raw_score_winner = payload["comparisons"][1]
    assert recommended["comparison_rank"]["party_readiness_score"] > raw_score_winner["comparison_rank"]["party_readiness_score"]
    assert recommended["comparison_rank"]["member_coverage_share"] == 1.0
    assert raw_score_winner["comparison_rank"]["average_score"] > recommended["comparison_rank"]["average_score"]
    assert recommended["comparison_explanation"]["tradeoffs"][1]["label"] == "Party"


def test_recommendation_compare_prioritizes_first_page_local_discovery(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeLocalDiscoveryCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("localopener@example.com"),
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "mode": "spontaneous",
            "constraints": {"avoid_chains": True},
            "scoring_profiles": ["phase1_balanced", "authenticity_forward"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "authenticity_forward",
        "phase1_balanced",
    ]
    recommended = payload["comparisons"][0]
    raw_score_winner = payload["comparisons"][1]
    assert recommended["comparison_rank"]["average_score"] == 0.84
    assert raw_score_winner["comparison_rank"]["average_score"] == 0.91
    assert recommended["comparison_rank"]["first_page_local_discovery_count"] == 1
    assert recommended["comparison_rank"]["local_discovery_rescue_count"] == 1
    assert raw_score_winner["comparison_rank"]["first_page_local_discovery_count"] == 0
    assert recommended["comparison_explanation"]["headline"] == "Best basket with local discoveries in the opening cards."
    assert any(
        tradeoff["label"] == "Local opener" and tradeoff["value"] == "1 rescued"
        for tradeoff in recommended["comparison_explanation"]["tradeoffs"]
    )


def test_recommendation_compare_prioritizes_event_anchor_profile(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeEventAnchorCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("eventanchor@example.com"),
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "mode": "spontaneous",
            "constraints": {"avoid_chains": True, "include_local_events": True},
            "scoring_profiles": ["phase1_balanced", "event_anchor"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "event_anchor"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "event_anchor",
        "phase1_balanced",
    ]
    recommended = payload["comparisons"][0]
    raw_score_winner = payload["comparisons"][1]
    assert recommended["comparison_rank"]["average_score"] == 0.79
    assert raw_score_winner["comparison_rank"]["average_score"] == 0.9
    assert recommended["comparison_rank"]["local_event_backed_count"] == 2
    assert recommended["comparison_rank"]["local_event_reservation_ready_count"] == 1
    assert recommended["comparison_rank"]["local_event_friend_signal_count"] == 1
    assert recommended["comparison_explanation"]["headline"] == (
        "Best basket for anchoring the Adventour around a timely local event."
    )
    assert any(
        tradeoff["label"] == "Event anchor" and tradeoff["value"] == "1 bookable"
        for tradeoff in recommended["comparison_explanation"]["tradeoffs"]
    )


def test_recommendation_compare_can_include_full_recommendations(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeBasketCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("debug@example.com"),
        json={
            "location": {"latitude": 28.538, "longitude": -81.379},
            "scoring_profiles": ["authenticity_forward"],
            "include_recommendations": True,
        },
    )

    assert response.status_code == 200
    comparison = response.get_json()["comparisons"][0]
    assert comparison["recommendations"][0]["name"] == "authenticity_forward first pick"
    assert comparison["result"]["recommendations"][0]["score"] == 0.88


def test_recommendation_compare_supports_learned_beta_variant(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeBasketCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("learnedcompare@example.com"),
        json={
            "location": {"latitude": 28.538, "longitude": -81.379},
            "scoring_profiles": ["learned_beta"],
            "include_recommendations": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    comparison = payload["comparisons"][0]
    assert payload["recommended_profile"] == "learned_beta"
    assert comparison["scoring_profile"] == "learned_beta"
    assert comparison["result"]["comparison_profile"] == "learned_beta"
    assert fake_service.calls[0]["profile"] == "phase1_balanced"
    assert fake_service.calls[0]["learned_rerank"] is True
    assert fake_service.calls[0]["record_impressions"] is False


def test_recommendation_compare_demotes_inactive_learned_beta(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeInactiveLearnedCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("learnedinactive@example.com"),
        json={
            "location": {"latitude": 28.538, "longitude": -81.379},
            "scoring_profiles": ["learned_beta", "authenticity_forward"],
            "include_recommendations": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    assert payload["comparisons"][0]["scoring_profile"] == "authenticity_forward"
    learned = next(item for item in payload["comparisons"] if item["scoring_profile"] == "learned_beta")
    assert learned["comparison_rank"]["learned_inactive"] is True
    assert learned["comparison_rank"]["learned_reason"] == "no_model"
    assert any(
        tradeoff["label"] == "Learning" and tradeoff["value"] == "Paused"
        for tradeoff in learned["comparison_explanation"]["tradeoffs"]
    )
    assert "loaded model" in learned["comparison_explanation"]["cautions"][0]


def test_recommendation_compare_explains_thin_learned_training_data(monkeypatch):
    reset_db()
    client = server_app.app.test_client()
    fake_service = FakeThinDataLearnedCompareService()
    monkeypatch.setattr(server_app, "_comparison_recommendation_service", lambda: fake_service)

    response = client.post(
        "/api/recommendations/compare",
        headers=auth_headers("learnedthin@example.com"),
        json={
            "location": {"latitude": 28.538, "longitude": -81.379},
            "scoring_profiles": ["learned_beta", "authenticity_forward"],
            "include_recommendations": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    learned = next(item for item in payload["comparisons"] if item["scoring_profile"] == "learned_beta")

    assert payload["recommended_profile"] == "authenticity_forward"
    assert learned["comparison_rank"]["learned_reason"] == "training_data_needs_data"
    assert learned["comparison_rank"]["learned_training_data_status"] == "needs_data"
    assert "too thin" in learned["comparison_explanation"]["cautions"][0]
