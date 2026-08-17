import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask

from adventour_backend.models import db, Friendship, LocalEvent, LocalEventInterest, Place, User, UserPlaceEvent, UserPreferenceVector
from adventour_backend.services.recommender_service import (
    MEMBER_COVERAGE_FIT_THRESHOLD,
    RecommendationService,
    SCORING_PROFILES,
    ScoringProfile,
)
from adventour_backend.services.recommender_model_service import FEATURE_NAMES, FEATURE_SCHEMA_VERSION


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
        display_name=username,
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.commit()
    return user


def make_friends(user, friend):
    db.session.add(Friendship(user_id=user.id, friend_id=friend.id, status="accepted"))
    db.session.commit()


def candidate(name, place_id, types, rating, ratings_total, lat=37.422, lng=-122.084, price_level=2):
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


def recommend_for(user, candidates, member_ids=None, constraints=None):
    service = RecommendationService(MockProviderRegistry(candidates))
    return service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=3200,
        member_ids=member_ids or [],
        constraints=constraints or {"limit": 10, "avoid_chains": True},
    )


def test_hidden_gem_beats_chain_for_local_food_user(app_context):
    user = create_user("local@example.com", ["restaurant", "cafe"])
    candidates = [
        candidate("Starbucks", "chain-1", ["cafe", "restaurant"], 4.7, 5000),
        candidate("Maya's Corner Cafe", "gem-1", ["cafe", "restaurant"], 4.8, 42),
    ]

    result = recommend_for(user, candidates)

    assert result["recommendations"][0]["name"] == "Maya's Corner Cafe"
    assert result["recommendations"][0]["components"]["authenticity"] > result["recommendations"][1]["components"]["authenticity"]
    assert result["recommendations"][1]["components"]["chain_penalty"] > 0
    assert result["recommendations"][0]["authenticity_evidence"]["label"] == "Hidden gem"
    assert result["recommendations"][0]["authenticity_evidence"]["confidence_status"] in {"usable", "strong"}
    assert result["recommendations"][0]["authenticity_evidence"]["rating_count"] == 42
    assert result["recommendations"][0]["components"]["authenticity_confidence"] >= 0.5
    assert result["recommendations"][1]["authenticity_evidence"]["label"] == "Generic risk"
    objective_breakdown = result["recommendations"][0]["ranking"]["objective_breakdown"]
    assert objective_breakdown["model_family"] == "hybrid_multi_objective"
    assert objective_breakdown["final_score"] == result["recommendations"][0]["score"]
    assert objective_breakdown["positive_total"] > objective_breakdown["penalty_total"]
    assert objective_breakdown["top_positive"][0] in {"personal_taste", "travel_party", "authenticity", "quality"}
    authenticity_objective = next(
        item for item in objective_breakdown["positive"]
        if item["id"] == "authenticity"
    )
    assert authenticity_objective["weight"] > 0
    assert authenticity_objective["contribution"] > 0
    chain_breakdown = result["recommendations"][1]["ranking"]["objective_breakdown"]
    assert any(item["id"] == "chain" and item["penalty"] > 0 for item in chain_breakdown["penalties"])
    gem_details = result["recommendations"][0]["explanation_details"]
    chain_details = result["recommendations"][1]["explanation_details"]
    gem_story = result["recommendations"][0]["recommendation_story"]
    chain_story = result["recommendations"][1]["recommendation_story"]
    assert any(detail["kind"] == "authenticity" and detail["label"] == "Hidden-gem signal" for detail in gem_details)
    assert any(detail["kind"] == "chain_guard" and detail["label"] == "Chain guard active" for detail in chain_details)
    assert gem_story["headline"] == "A local-gem leaning pick Adventour wants you to see."
    assert gem_story["authenticity_label"] == "Hidden gem"
    assert any(metric["id"] == "hidden_gem" for metric in gem_story["metrics"])
    assert any(metric["id"] == "local_proof" for metric in gem_story["metrics"])
    assert any("Generic or chain-like signals" in caution for caution in chain_story["cautions"])
    quality = result["recommendation_quality"]
    assert quality["metrics"]["hidden_gem_count"] >= 1
    assert quality["metrics"]["average_authenticity_confidence"] > 0
    assert quality["metrics"]["generic_risk_count"] >= 1
    assert any("hidden-gem" in strength for strength in quality["strengths"])
    decision = quality["decision_summary"]
    decision_dimensions = {item["name"]: item for item in decision["dimensions"]}
    assert decision["score"] > 0
    assert {"local_texture", "slate_variety", "learning", "provider_health"}.issubset(decision_dimensions)
    assert decision_dimensions["provider_health"]["status"] == "pass"


def test_thin_hidden_gem_evidence_is_visible_in_basket_quality(app_context):
    user = create_user("thinproof@example.com", ["restaurant", "cafe"])
    candidates = [
        candidate("Two Review Local Cafe", "thin-local-1", ["cafe", "restaurant"], 4.9, 2),
        candidate("Starbucks", "thin-chain-1", ["cafe", "restaurant"], 4.7, 5000),
    ]

    result = recommend_for(user, candidates)
    thin_pick = next(item for item in result["recommendations"] if item["name"] == "Two Review Local Cafe")

    assert thin_pick["authenticity_evidence"]["label"] == "Hidden gem"
    assert thin_pick["authenticity_evidence"]["confidence_status"] == "thin"
    assert thin_pick["authenticity_evidence"]["rating_count"] == 2
    assert thin_pick["components"]["authenticity_confidence_status"] == "thin"
    assert any(detail["kind"] == "authenticity_confidence" for detail in thin_pick["explanation_details"])
    assert any("Local proof is still thin" in caution for caution in thin_pick["recommendation_story"]["cautions"])
    assert result["recommendation_quality"]["metrics"]["thin_local_evidence_count"] == 1
    assert any("need more evidence" in warning for warning in result["recommendation_quality"]["warnings"])


def test_local_authenticity_guardrail_removes_chains_when_local_pool_is_deep(app_context):
    user = create_user("localguard@example.com", ["restaurant", "cafe"])
    candidates = [
        candidate("Starbucks", "guard-chain-1", ["cafe", "restaurant"], 4.9, 6000),
        candidate("McDonald's", "guard-chain-2", ["restaurant", "fast_food"], 4.7, 9000),
        candidate("Maya's Corner Cafe", "guard-gem-1", ["cafe", "restaurant"], 4.8, 42),
        candidate("Lake Eola Arepas", "guard-gem-2", ["restaurant"], 4.7, 64),
        candidate("The Tiny Noodle Bar", "guard-gem-3", ["restaurant"], 4.6, 81),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 3, "avoid_chains": True})
    names = [item["name"] for item in result["recommendations"]]

    assert "Starbucks" not in names
    assert "McDonald's" not in names
    assert len(result["recommendations"]) == 3
    assert all(
        item["authenticity_evidence"]["label"] in {"Hidden gem", "Local-feeling"}
        for item in result["recommendations"]
    )
    assert result["filter_summary"]["skipped"]["local_authenticity_guardrail"] == 2
    assert result["recommendation_quality"]["metrics"]["generic_risk_count"] == 0


def test_first_page_local_discovery_rescue_makes_room_for_close_hidden_gem(app_context):
    user = create_user("localrescue@example.com", ["restaurant"])
    candidates = [
        candidate("Polished Brunch Hall", "local-rescue-popular-1", ["restaurant"], 4.9, 2600),
        candidate("Busy Dinner Room", "local-rescue-popular-2", ["restaurant"], 4.8, 2100),
        candidate("Crowded Lunch Counter", "local-rescue-popular-3", ["restaurant"], 4.8, 1800),
        candidate("Tiny Alley Kitchen", "local-rescue-gem", ["restaurant"], 4.6, 18),
    ]
    profile = ScoringProfile(
        name="local_discovery_rescue_test",
        personal_fit_weight=0.2,
        group_fit_weight=0.0,
        authenticity_weight=0.0,
        quality_weight=0.78,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.0,
        local_event_weight=0.0,
        session_context_weight=0.0,
        friend_history_weight=0.0,
        chain_penalty=0.0,
        diversity_new_group_bonus=0.0,
        diversity_authenticity_bonus_weight=0.0,
        diversity_authenticity_bonus_max=0.0,
        intent_coverage_bonus_per_group=0.0,
        intent_coverage_bonus_max=0.0,
        member_coverage_bonus_per_member=0.0,
        member_coverage_bonus_max=0.0,
        diversity_group_repeat_penalty=0.0,
        diversity_type_repeat_penalty=0.0,
        diversity_repeat_penalty_max=0.0,
        local_discovery_frontier_gap=0.2,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 3, "avoid_chains": True},
    )

    first_page_names = [item["name"] for item in result["recommendations"][:3]]
    rescue = next(item for item in result["recommendations"] if item["name"] == "Tiny Alley Kitchen")

    assert "Tiny Alley Kitchen" in first_page_names
    assert rescue["ranking"]["local_discovery_rescue"] is True
    assert rescue["ranking"]["rescue_reason"] == "first_page_local_authenticity"
    assert rescue["ranking"]["score_gap"] <= 0.2
    assert rescue["authenticity_evidence"]["label"] == "Hidden gem"
    assert result["slate_summary"]["metrics"]["first_page_local_discovery_count"] == 1
    assert result["slate_summary"]["metrics"]["local_discovery_rescue_count"] == 1
    assert any(
        "first-page local discovery" in strength
        for strength in result["recommendation_quality"]["strengths"]
    )


def test_local_event_near_place_adds_event_context_to_recommendation(app_context):
    user = create_user("events@example.com", ["market", "cafe"])
    friend = create_user("events-friend@example.com", ["market", "cafe"])
    make_friends(user, friend)
    event = LocalEvent(
        title="Neighborhood Night Market",
        description="Local makers, food stalls, and community music.",
        city="Mountain View",
        latitude=37.422,
        longitude=-122.084,
        starts_at=datetime.utcnow() + timedelta(days=3),
        category="market",
        source_name="City calendar",
        source_url="https://example.com/events/night-market",
        reservation_url="https://example.com/events/night-market/rsvp",
        authenticity_score=0.9,
        status="active",
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(LocalEventInterest(
        event_id=event.id,
        user_id=friend.id,
        status="going",
    ))
    db.session.commit()
    candidates = [
        candidate("Alley Cat Coffee", "event-cafe", ["cafe"], 4.6, 72),
        candidate("Farther Generic Cafe", "plain-cafe", ["cafe"], 4.6, 72, lat=37.422, lng=-122.12),
    ]

    result = recommend_for(user, candidates, member_ids=[friend.id])

    event_pick = next(item for item in result["recommendations"] if item["name"] == "Alley Cat Coffee")
    assert event_pick["local_event_match"]["title"] == "Neighborhood Night Market"
    assert event_pick["local_event_match"]["social"]["friend_signal_count"] == 1
    assert event_pick["local_event_match"]["social"]["friend_going_count"] == 1
    assert event_pick["local_event_match"]["components"]["social_signal"] > 0
    assert event_pick["components"]["local_event_fit"] > 0.6
    assert any(detail["kind"] == "local_event" for detail in event_pick["explanation_details"])
    assert any(metric["id"] == "local_event" for metric in event_pick["recommendation_story"]["metrics"])
    local_event_objective = next(
        item for item in event_pick["ranking"]["objective_breakdown"]["positive"]
        if item["id"] == "local_event"
    )
    assert local_event_objective["contribution"] > 0
    assert result["recommendation_quality"]["metrics"]["local_event_backed_count"] == 1
    assert result["recommendation_quality"]["metrics"]["local_event_reservation_ready_count"] == 1
    assert result["recommendation_quality"]["metrics"]["local_event_friend_signal_count"] == 1
    assert result["recommendation_quality"]["metrics"]["local_event_social_score"] > 0
    assert any("event-backed" in strength for strength in result["recommendation_quality"]["strengths"])
    assert any("selected-friend event signal" in strength for strength in result["recommendation_quality"]["strengths"])


def test_scoring_profile_can_prioritize_taste_fit_over_authenticity(app_context):
    user = create_user("profile@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-1", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-1", ["cafe"], 4.1, 800),
    ]
    profile = ScoringProfile(
        name="taste_forward_test",
        personal_fit_weight=0.75,
        group_fit_weight=0.0,
        authenticity_weight=0.02,
        quality_weight=0.05,
        context_fit_weight=0.03,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        chain_penalty=0.0,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": False},
    )

    assert result["recommendations"][0]["name"] == "Polished Corner Cafe"
    assert result["recommendations"][0]["components"]["scoring_profile"] == "taste_forward_test"
    assert result["recommendations"][0]["ranking"]["scoring_profile"] == "taste_forward_test"


def learned_promotion_gate(status="pass", can_promote=True):
    return {
        "status": status,
        "can_promote": can_promote,
        "summary": "Learned reranker passed ranking, local-quality, and group-balance promotion checks."
        if can_promote
        else "Keep the transparent ranker active; the learned reranker failed at least one promotion check.",
        "checks": [
            {
                "name": "ranking_improved",
                "label": "Ranking quality did not regress",
                "status": "pass" if can_promote else "fail",
                "value": "MRR +0.1000, NDCG +0.1000",
                "message": "" if can_promote else "Keep the transparent ranker until the learned model improves MRR or NDCG.",
            },
        ],
    }


def learned_training_data_health(status="ready"):
    if status == "needs_data":
        return {
            "status": "needs_data",
            "summary": "Training data is too thin to trust beyond a smoke test.",
            "counts": {"labeled": 6, "requests": 3, "event_friend_signal": 1},
            "checks": [
                {"name": "labeled_outcomes", "label": "Enough labeled outcomes", "status": "fail"},
                {"name": "event_social_signal", "label": "Event social/friend signal exists", "status": "fail"},
            ],
        }
    return {
        "status": "ready",
        "summary": "Training data is ready for learned-ranker evaluation.",
        "counts": {"labeled": 60, "requests": 24, "event_friend_signal": 3},
        "checks": [
            {"name": "labeled_outcomes", "label": "Enough labeled outcomes", "status": "pass"},
            {"name": "request_diversity", "label": "Enough recommendation requests", "status": "pass"},
            {"name": "event_social_signal", "label": "Event social/friend signal exists", "status": "pass"},
        ],
    }


def learned_authenticity_model(promotion_gate=None):
    model = {
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
    }
    model["promotion_gate"] = learned_promotion_gate() if promotion_gate is None else promotion_gate
    model["training_data_health"] = learned_training_data_health()
    return model


def learned_popularity_model(promotion_gate=None):
    model = {
        "model_type": "adventour_logistic_ltr_baseline",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "intercept": 0.0,
        "weights": {
            "popularity_score": 8.0,
        },
        "feature_stats": {
            name: {"mean": 0.0, "std": 1.0}
            for name in FEATURE_NAMES
        },
    }
    model["promotion_gate"] = learned_promotion_gate() if promotion_gate is None else promotion_gate
    model["training_data_health"] = learned_training_data_health()
    return model


def stale_learned_authenticity_model():
    model = learned_authenticity_model()
    model["feature_schema_version"] = "phase1_legacy"
    model["feature_names"] = [
        name for name in FEATURE_NAMES
        if name != "friend_adjusted_retrieval"
    ]
    model["feature_stats"] = {
        name: {"mean": 0.0, "std": 1.0}
        for name in model["feature_names"]
    }
    return model


def test_learned_model_path_can_be_relative_to_server_dir():
    server_dir = Path(__file__).resolve().parents[1]
    relative_path = Path("instance") / "recommender" / "test-relative-model.json"
    model_path = server_dir / relative_path
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(learned_authenticity_model()), encoding="utf-8")
    try:
        service = RecommendationService(
            MockProviderRegistry([]),
            learned_model_path=str(relative_path),
        )
        assert service.learned_model["model_type"] == "adventour_logistic_ltr_baseline"
    finally:
        model_path.unlink(missing_ok=True)


def test_learned_rerank_is_opt_in_and_preserves_default_order(app_context):
    user = create_user("learneddefault@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-1", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-1", ["cafe"], 4.1, 800),
    ]
    profile = ScoringProfile(
        name="taste_forward_test",
        personal_fit_weight=0.75,
        group_fit_weight=0.0,
        authenticity_weight=0.02,
        quality_weight=0.05,
        context_fit_weight=0.03,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        chain_penalty=0.0,
    )
    service = RecommendationService(
        MockProviderRegistry(candidates),
        scoring_profile=profile,
        learned_model=learned_authenticity_model(),
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": False},
    )

    assert result["learned_rerank"]["applied"] is False
    assert result["recommendations"][0]["name"] == "Polished Corner Cafe"
    assert "learned_score" not in result["recommendations"][0]


def test_learned_rerank_can_reorder_candidates_when_enabled(app_context):
    user = create_user("learnedrerank@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-2", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-2", ["cafe"], 4.1, 800),
    ]
    profile = ScoringProfile(
        name="taste_forward_test",
        personal_fit_weight=0.75,
        group_fit_weight=0.0,
        authenticity_weight=0.02,
        quality_weight=0.05,
        context_fit_weight=0.03,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        chain_penalty=0.0,
    )
    service = RecommendationService(
        MockProviderRegistry(candidates),
        scoring_profile=profile,
        learned_model=learned_authenticity_model(),
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": False, "learned_rerank": True},
    )

    assert result["learned_rerank"]["applied"] is True
    assert result["recommendations"][0]["name"] == "Tiny Local Museum"
    assert result["recommendations"][0]["learned_rank_position"] == 1
    assert (
        result["recommendations"][0]["ranking"]["learned_model_score"]
        > result["recommendations"][1]["ranking"]["learned_model_score"]
    )
    assert result["learned_rerank"]["promotion_gate"]["status"] == "pass"


def test_learned_rerank_runtime_guard_blocks_chain_from_leapfrogging_local_pick(app_context):
    user = create_user("learnedguard@example.com", ["cafe", "restaurant"])
    candidates = [
        candidate("Starbucks", "learned-guard-chain", ["cafe", "restaurant"], 4.8, 5000),
        candidate("Maya's Corner Cafe", "learned-guard-gem", ["cafe", "restaurant"], 4.8, 42),
    ]
    service = RecommendationService(
        MockProviderRegistry(candidates),
        learned_model=learned_popularity_model(),
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True, "learned_rerank": True},
    )

    chain = next(item for item in result["recommendations"] if item["name"] == "Starbucks")
    local = next(item for item in result["recommendations"] if item["name"] == "Maya's Corner Cafe")

    assert result["learned_rerank"]["applied"] is True
    assert result["learned_rerank"]["runtime_guard"]["status"] == "constrained"
    assert result["learned_rerank"]["runtime_guard"]["counts"]["fail"] == 1
    assert chain["learned_score"] > local["learned_score"]
    assert result["recommendations"][0]["name"] == "Maya's Corner Cafe"
    assert chain["ranking"]["learned_runtime_guard"]["status"] == "fail"
    assert local["ranking"]["learned_runtime_guard"]["status"] == "pass"


def test_learned_rerank_blocks_unpromoted_model(app_context):
    user = create_user("learnedblocked@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-blocked", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-blocked", ["cafe"], 4.1, 800),
    ]
    service = RecommendationService(
        MockProviderRegistry(candidates),
        learned_model=learned_authenticity_model(promotion_gate=None),
    )
    service.learned_model.pop("promotion_gate")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": False, "learned_rerank": True},
    )

    assert result["learned_rerank"]["applied"] is False
    assert result["learned_rerank"]["reason"] == "promotion_gate_missing"
    assert result["learned_rerank"]["promotion_gate"]["status"] == "missing"
    assert "learned_score" not in result["recommendations"][0]


def test_learned_rerank_blocks_promoted_model_with_thin_training_data(app_context):
    user = create_user("learnedhealthblocked@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-health-blocked", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-health-blocked", ["cafe"], 4.1, 800),
    ]
    model = learned_authenticity_model()
    model["training_data_health"] = learned_training_data_health("needs_data")
    service = RecommendationService(
        MockProviderRegistry(candidates),
        learned_model=model,
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": False, "learned_rerank": True},
    )

    assert result["learned_rerank"]["applied"] is False
    assert result["learned_rerank"]["reason"] == "training_data_needs_data"
    assert result["learned_rerank"]["training_data_health"]["status"] == "needs_data"
    assert result["learned_rerank"]["promotion_gate"]["status"] == "pass"
    assert "learned_score" not in result["recommendations"][0]


def test_learned_rerank_dev_override_can_run_unpromoted_model(app_context):
    user = create_user("learnedoverride@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-override", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-override", ["cafe"], 4.1, 800),
    ]
    service = RecommendationService(
        MockProviderRegistry(candidates),
        learned_model=learned_authenticity_model(promotion_gate=learned_promotion_gate("fail", False)),
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={
            "limit": 10,
            "avoid_chains": False,
            "learned_rerank": True,
            "allow_unpromoted_learned_rerank": True,
        },
    )

    assert result["learned_rerank"]["applied"] is True
    assert result["learned_rerank"]["override_applied"] is True
    assert result["learned_rerank"]["promotion_gate"]["status"] == "fail"
    assert result["recommendations"][0]["name"] == "Tiny Local Museum"


def test_learned_rerank_blocks_stale_feature_schema(app_context):
    user = create_user("learnedstale@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Museum", "museum-learned-stale", ["museum"], 4.9, 25),
        candidate("Polished Corner Cafe", "cafe-learned-stale", ["cafe"], 4.1, 800),
    ]
    service = RecommendationService(
        MockProviderRegistry(candidates),
        learned_model=stale_learned_authenticity_model(),
    )

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={
            "limit": 10,
            "avoid_chains": False,
            "learned_rerank": True,
            "allow_unpromoted_learned_rerank": True,
        },
    )

    compatibility = result["learned_rerank"]["feature_compatibility"]

    assert result["learned_rerank"]["applied"] is False
    assert result["learned_rerank"]["reason"] == "feature_schema_mismatch"
    assert compatibility["status"] == "fail"
    assert "friend_adjusted_retrieval" in compatibility["missing_features"]
    assert result["learned_rerank"]["promotion_gate"]["status"] == "pass"
    assert "learned_score" not in result["recommendations"][0]


def test_requested_named_scoring_profile_is_used_for_request(app_context):
    user = create_user("authentic@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Cafe", "gem-1", ["cafe"], 4.8, 25),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={"limit": 10, "avoid_chains": True, "scoring_profile": "authenticity_forward"},
    )

    assert result["scoring_profile"] == "authenticity_forward"
    assert "authenticity_forward" in result["available_scoring_profiles"]
    assert result["recommendations"][0]["components"]["scoring_profile"] == "authenticity_forward"
    assert result["recommendations"][0]["ranking"]["scoring_profile"] == "authenticity_forward"


def test_controlled_exploration_lifts_underexposed_local_gems(app_context):
    user = create_user("explore@example.com", ["cafe"])
    candidates = [
        candidate("Polished Popular Cafe", "popular-cafe", ["cafe"], 4.7, 3000),
        candidate("Tiny Local Cafe", "underexposed-cafe", ["cafe"], 4.6, 12),
    ]
    profile = ScoringProfile(
        name="exploration_test",
        personal_fit_weight=0.25,
        group_fit_weight=0.0,
        authenticity_weight=0.05,
        quality_weight=0.05,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.40,
        chain_penalty=0.0,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    first = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    gem = next(item for item in first["recommendations"] if item["name"] == "Tiny Local Cafe")
    popular = next(item for item in first["recommendations"] if item["name"] == "Polished Popular Cafe")

    assert first["recommendations"][0]["name"] == "Tiny Local Cafe"
    assert gem["components"]["exploration"] > 0
    assert gem["components"]["exploration_uncertainty"] == 1.0
    assert popular["components"]["exploration"] == 0
    assert "promising underexposed local pick" in gem["explanation"]
    assert gem["recommendation_story"]["headline"]
    assert any(metric["id"] == "learning" for metric in gem["recommendation_story"]["metrics"])
    assert any(detail["kind"] == "exploration" and detail["label"] == "Learning pick" for detail in gem["explanation_details"])
    result_quality = first["recommendation_quality"]
    assert result_quality["metrics"]["exploration_count"] == 1
    assert result_quality["metrics"]["exploration_eligible_count"] == 1
    assert result_quality["metrics"]["serendipity_score"] == 0.86
    assert result_quality["serendipity_plan"]["status"] == "balanced"
    assert result_quality["serendipity_plan"]["allowed_count"] == 1
    assert result_quality["serendipity_plan"]["target_min"] == 1
    assert result_quality["serendipity_plan"]["learning_picks"][0]["name"] == "Tiny Local Cafe"
    assert result_quality["model_confidence"]["learning_status"] == "cold_start"
    assert result_quality["model_confidence"]["status"] in {"cold_start", "learning"}
    assert result_quality["model_confidence"]["exploration_count"] == 1
    assert result_quality["model_confidence"]["serendipity_score"] == 0.86
    assert any("still learning" in warning for warning in result_quality["model_confidence"]["warnings"])
    assert any("guarded learning pick" in strength for strength in result_quality["strengths"])

    service.record_event(
        user=user,
        place=db.session.get(Place, gem["place_id"]),
        event_type="impression",
    )
    second = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    seen_gem = next(item for item in second["recommendations"] if item["name"] == "Tiny Local Cafe")

    assert seen_gem["components"]["exploration"] == 0


def test_exploration_cools_down_when_profile_has_enough_feedback(app_context):
    cold_user = create_user("coldexplore@example.com", ["cafe"])
    warm_user = create_user("warmexplore@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Cafe", "uncertainty-underexposed-cafe", ["cafe"], 4.7, 12),
        candidate("Polished Popular Cafe", "uncertainty-popular-cafe", ["cafe"], 4.8, 3000),
    ]
    profile = ScoringProfile(
        name="exploration_uncertainty_test",
        personal_fit_weight=0.25,
        group_fit_weight=0.0,
        authenticity_weight=0.05,
        quality_weight=0.05,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.40,
        chain_penalty=0.0,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    for index in range(12):
        training_place, _, _ = service.upsert_candidate(
            candidate(f"Training Cafe {index}", f"warm-training-{index}", ["cafe"], 4.4, 80 + index)
        )
        db.session.commit()
        service.record_event(user=warm_user, place=training_place, event_type="accept")

    cold_result = service.recommend(
        user=cold_user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    warm_result = service.recommend(
        user=warm_user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    cold_gem = next(item for item in cold_result["recommendations"] if item["name"] == "Tiny Local Cafe")
    warm_gem = next(item for item in warm_result["recommendations"] if item["name"] == "Tiny Local Cafe")
    warm_vector = service.build_preference_vector(warm_user)

    assert warm_vector["signal_count"] >= 12
    assert warm_vector["confidence"] == 1.0
    assert cold_gem["components"]["exploration_uncertainty"] == 1.0
    assert warm_gem["components"]["exploration_uncertainty"] == 0.0
    assert cold_gem["components"]["exploration"] > warm_gem["components"]["exploration"]
    assert cold_result["recommendation_quality"]["model_confidence"]["learning_status"] == "cold_start"
    assert warm_result["recommendation_quality"]["model_confidence"]["learning_status"] == "personalized"
    assert (
        warm_result["recommendation_quality"]["model_confidence"]["average_preference_confidence"]
        > cold_result["recommendation_quality"]["model_confidence"]["average_preference_confidence"]
    )


def test_exploration_budget_limits_first_page_experimental_picks(app_context):
    user = create_user("explorebudget@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Cafe One", "underexposed-cafe-1", ["cafe"], 4.7, 12),
        candidate("Tiny Local Cafe Two", "underexposed-cafe-2", ["cafe"], 4.7, 13),
        candidate("Tiny Local Cafe Three", "underexposed-cafe-3", ["cafe"], 4.7, 14),
        candidate("Tiny Local Cafe Four", "underexposed-cafe-4", ["cafe"], 4.7, 15),
    ]
    profile = ScoringProfile(
        name="exploration_budget_test",
        personal_fit_weight=0.0,
        group_fit_weight=0.0,
        authenticity_weight=0.05,
        quality_weight=0.05,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.40,
        chain_penalty=0.0,
        exploration_frontier_gap=1.0,
        exploration_page_share=0.25,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 4, "avoid_chains": True},
    )

    allowed = [
        item for item in result["recommendations"]
        if item["ranking"]["exploration_budget"]["allowed"]
    ]
    throttled = [
        item for item in result["recommendations"]
        if item["ranking"]["exploration_budget"]["eligible"]
        and not item["ranking"]["exploration_budget"]["allowed"]
    ]

    assert len(allowed) == 1
    assert len(throttled) == 3
    assert result["recommendation_quality"]["serendipity_plan"]["status"] == "balanced"
    assert result["recommendation_quality"]["serendipity_plan"]["target_max"] == 1
    assert result["recommendation_quality"]["serendipity_plan"]["allowed_count"] == 1
    assert result["recommendation_quality"]["serendipity_plan"]["eligible_count"] == 4
    assert {item["ranking"]["exploration_budget"]["reason"] for item in throttled} == {"too_many_exploratory_picks"}
    assert all(item["components"]["exploration_applied"] == 0 for item in throttled)
    assert all(
        next(
            objective for objective in item["ranking"]["objective_breakdown"]["positive"]
            if objective["id"] == "exploration"
        )["contribution"] == 0
        for item in throttled
    )
    assert all(item["ranking"]["objective_breakdown"]["final_score"] == item["score"] for item in throttled)


def test_exploration_budget_blocks_candidates_outside_score_frontier(app_context):
    user = create_user("explorefrontier@example.com", ["cafe"])
    candidates = [
        candidate("Polished Popular Cafe", "frontier-popular", ["cafe"], 4.9, 5000),
        candidate("Tiny Local Bookshop", "frontier-underexposed", ["book_store"], 4.6, 10),
    ]
    profile = ScoringProfile(
        name="exploration_frontier_test",
        personal_fit_weight=0.25,
        group_fit_weight=0.0,
        authenticity_weight=0.15,
        quality_weight=0.30,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.50,
        chain_penalty=0.0,
        exploration_frontier_gap=0.01,
        exploration_page_share=0.50,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 2, "avoid_chains": True},
    )
    gem = next(item for item in result["recommendations"] if item["name"] == "Tiny Local Bookshop")

    assert result["recommendations"][0]["name"] == "Polished Popular Cafe"
    assert gem["ranking"]["exploration_budget"]["allowed"] is False
    assert gem["ranking"]["exploration_budget"]["reason"] == "outside_score_frontier"
    assert gem["components"]["exploration"] > 0
    assert gem["components"]["exploration_applied"] == 0
    assert result["recommendation_quality"]["serendipity_plan"]["status"] == "under_target"
    assert result["recommendation_quality"]["serendipity_plan"]["allowed_count"] == 0
    assert result["recommendation_quality"]["serendipity_plan"]["safe_count"] == 1


def test_exploration_budget_prioritizes_friend_learning_pick(app_context):
    cafe_user = create_user("explore-friend-cafe@example.com", ["cafe"])
    museum_user = create_user("explore-friend-museum@example.com", ["museum"])
    make_friends(cafe_user, museum_user)
    candidates = [
        candidate("Tiny Local Cafe", "friend-explore-cafe", ["cafe"], 4.7, 12),
        candidate("Tiny Local Museum", "friend-explore-museum", ["museum"], 4.7, 12),
    ]
    profile = ScoringProfile(
        name="friend_exploration_test",
        personal_fit_weight=0.25,
        group_fit_weight=0.0,
        authenticity_weight=0.05,
        quality_weight=0.05,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.40,
        chain_penalty=0.0,
        exploration_frontier_gap=1.0,
        exploration_page_share=0.5,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=cafe_user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        member_ids=[museum_user.id],
        constraints={"limit": 2, "avoid_chains": True},
    )
    cafe = next(item for item in result["recommendations"] if item["name"] == "Tiny Local Cafe")
    museum = next(item for item in result["recommendations"] if item["name"] == "Tiny Local Museum")

    assert museum["ranking"]["exploration_budget"]["allowed"] is True
    assert museum["ranking"]["exploration_budget"]["reason"] == "friend_learning_allowed"
    assert museum["ranking"]["exploration_budget"]["friend_learning"] is True
    assert museum_user.display_name in museum["ranking"]["exploration_budget"]["served_learning_members"]
    assert result["recommendation_quality"]["serendipity_plan"]["friend_learning"] is True
    assert museum_user.display_name in result["recommendation_quality"]["serendipity_plan"]["served_learning_members"]
    assert cafe["ranking"]["exploration_budget"]["eligible"] is True
    assert cafe["ranking"]["exploration_budget"]["allowed"] is False
    assert cafe["ranking"]["exploration_budget"]["reason"] == "group_fit_guardrail"
    assert cafe["components"]["exploration_applied"] == 0


def test_slate_similarity_penalty_moves_near_duplicate_below_fresher_option(app_context):
    user = create_user("slate-variety@example.com", [])
    candidates = [
        candidate("Harbor Local Cafe", "slate-cafe-1", ["cafe", "coffee_shop"], 4.7, 80),
        candidate("Harbor Coffee Bar", "slate-cafe-2", ["cafe", "coffee_shop"], 4.7, 80),
        candidate("Neighborhood Art Yard", "slate-art-1", ["art_gallery"], 4.7, 80),
    ]
    profile = ScoringProfile(
        name="slate_similarity_test",
        personal_fit_weight=0.0,
        group_fit_weight=0.0,
        authenticity_weight=0.0,
        quality_weight=0.10,
        context_fit_weight=0.0,
        time_fit_weight=0.0,
        novelty_weight=0.0,
        exploration_weight=0.0,
        value_weight=0.0,
        local_event_weight=0.0,
        session_context_weight=0.0,
        friend_history_weight=0.0,
        group_disagreement_penalty=0.0,
        chain_penalty=0.0,
        diversity_new_group_bonus=0.0,
        diversity_authenticity_bonus_weight=0.0,
        diversity_authenticity_bonus_max=0.0,
        intent_coverage_bonus_per_group=0.0,
        intent_coverage_bonus_max=0.0,
        member_coverage_bonus_per_member=0.0,
        member_coverage_bonus_max=0.0,
        diversity_group_repeat_penalty=0.0,
        diversity_type_repeat_penalty=0.0,
        diversity_repeat_penalty_max=0.0,
        slate_similarity_penalty_weight=0.30,
        slate_similarity_penalty_max=0.30,
    )
    service = RecommendationService(MockProviderRegistry(candidates), scoring_profile=profile)

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={
            "limit": 3,
            "avoid_chains": True,
            "record_impressions": False,
        },
    )
    names = [item["name"] for item in result["recommendations"]]
    duplicate = next(item for item in result["recommendations"] if item["name"] == "Harbor Coffee Bar")
    art = next(item for item in result["recommendations"] if item["name"] == "Neighborhood Art Yard")

    assert names == ["Harbor Local Cafe", "Neighborhood Art Yard", "Harbor Coffee Bar"]
    assert duplicate["ranking"]["slate_similarity"] > art["ranking"]["slate_similarity"]
    assert duplicate["ranking"]["slate_similarity_penalty"] > art["ranking"]["slate_similarity_penalty"]
    assert duplicate["ranking"]["diversity_adjusted_score"] < art["ranking"]["diversity_adjusted_score"]


def test_unknown_scoring_profile_is_rejected(app_context):
    user = create_user("badprofile@example.com", ["cafe"])
    candidates = [
        candidate("Tiny Local Cafe", "gem-1", ["cafe"], 4.8, 25),
    ]

    with pytest.raises(ValueError, match="Unknown scoring_profile"):
        recommend_for(
            user,
            candidates,
            constraints={"limit": 10, "avoid_chains": True, "scoring_profile": "too_spicy"},
        )


def test_accept_event_increases_matching_category(app_context):
    user = create_user("food@example.com", ["restaurant"])
    candidates = [
        candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], 4.7, 55),
        candidate("Quiet Sculpture Garden", "garden-1", ["park", "tourist_attraction"], 4.8, 40),
    ]

    service = RecommendationService(MockProviderRegistry(candidates))
    first = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    taco = next(item for item in first["recommendations"] if item["name"] == "Local Taco Stand")
    taco_place = db.session.get(Place, taco["place_id"])

    service.record_event(user=user, place=taco_place, event_type="accept")
    vector = service.build_preference_vector(user)

    assert vector["categories"]["restaurant"] > 0
    assert vector["categories"]["mexican_restaurant"] > 0


def test_passive_impressions_do_not_train_preference_vector(app_context):
    user = create_user("passive@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    museum_place, _, _ = service.upsert_candidate(
        candidate("Museum Shown Once", "passive-museum", ["museum"], 4.7, 80)
    )
    db.session.commit()

    service.record_event(user=user, place=museum_place, event_type="impression")
    vector = service.build_preference_vector(user)

    assert vector["categories"] == {}
    assert UserPlaceEvent.query.filter_by(user_id=user.id, event_type="impression").count() == 1


def test_recent_events_outweigh_stale_preference_history(app_context):
    user = create_user("recency@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    old_place, _, _ = service.upsert_candidate(
        candidate("Old Museum Phase", "old-museum", ["museum"], 4.7, 50)
    )
    new_place, _, _ = service.upsert_candidate(
        candidate("Fresh Cafe Phase", "fresh-cafe", ["cafe"], 4.6, 50)
    )
    db.session.commit()

    service.record_event(user=user, place=old_place, event_type="accept")
    old_event = UserPlaceEvent.query.filter_by(user_id=user.id, place_id=old_place.id, event_type="accept").first()
    old_event.occurred_at = datetime.utcnow() - timedelta(days=180)
    db.session.commit()
    service.record_event(user=user, place=new_place, event_type="accept")

    vector = service.rebuild_preference_vector(user)

    assert vector["categories"]["cafe"] > vector["categories"]["museum"]
    assert vector["categories"]["museum"] > 0


def test_preference_vector_learns_positive_price_comfort(app_context):
    user = create_user("pricelearn@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    cheap_place, _, _ = service.upsert_candidate(
        candidate("Tiny Taco Window", "cheap-like", ["restaurant"], 4.7, 50, price_level=1)
    )
    splurge_place, _, _ = service.upsert_candidate(
        candidate("Special Occasion Counter", "splurge-like", ["restaurant"], 4.8, 50, price_level=4)
    )
    db.session.commit()

    service.record_event(user=user, place=cheap_place, event_type="accept")
    service.record_event(user=user, place=splurge_place, event_type="reject")
    vector = service.rebuild_preference_vector(user)

    assert vector["price_preference"] == pytest.approx(1.0)


def test_hidden_gem_acceptance_lifts_future_hidden_gem_scoring(app_context):
    user = create_user("gemhunter@example.com", ["cafe"])
    training_candidate = candidate("Tiny Alley Cafe", "training-gem", ["cafe"], 4.8, 20)
    candidates = [
        training_candidate,
        candidate("New Local Cafe", "future-gem", ["cafe"], 4.7, 24),
        candidate("Polished Cafe", "polished", ["cafe"], 4.9, 900),
    ]
    service = RecommendationService(MockProviderRegistry(candidates))
    training_place, _, _ = service.upsert_candidate(training_candidate)
    db.session.commit()
    service.record_event(user=user, place=training_place, event_type="accept")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    future_gem = next(item for item in result["recommendations"] if item["name"] == "New Local Cafe")

    assert future_gem["components"]["hidden_gem_affinity"] > 0.75
    assert "lifted by your local-gem history" in future_gem["explanation"]


def test_chain_rejection_increases_future_chain_avoidance(app_context):
    user = create_user("chainavoid@example.com", ["cafe"])
    candidates = [
        candidate("Starbucks", "chain-training", ["cafe"], 4.8, 2000),
        candidate("Starbucks Reserve", "chain-future", ["cafe"], 4.9, 1500),
    ]
    service = RecommendationService(MockProviderRegistry(candidates))
    chain_place, _, _ = service.upsert_candidate(candidates[0])
    db.session.commit()
    service.record_event(user=user, place=chain_place, event_type="reject")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True, "repeat_decided_on_exhaustion": True},
    )
    chain_future = next(item for item in result["recommendations"] if item["name"] == "Starbucks Reserve")

    assert chain_future["components"]["chain_avoidance"] > 0.75
    assert chain_future["components"]["chain_penalty"] > 0.25
    assert "deprioritized by your chain-avoidance history" in chain_future["explanation"]


def test_negative_only_preferences_do_not_drive_provider_query_tags(app_context):
    user = create_user("avoidonly@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    museum_place, _, _ = service.upsert_candidate(
        candidate("Museum That Missed", "avoid-museum", ["museum"], 4.7, 80)
    )
    db.session.commit()

    service.record_event(user=user, place=museum_place, event_type="reject")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert "museum" not in result["query_tags"]
    assert result["query_tags"] == ["restaurant", "tourist_attraction", "park"]


def test_preference_insights_summarize_learned_taste_for_debugging(app_context):
    user = create_user("insights@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    cafe_place, _, _ = service.upsert_candidate(
        candidate("Tiny Alley Cafe", "insight-cafe", ["cafe", "coffee_shop"], 4.8, 24, price_level=1)
    )
    museum_place, _, _ = service.upsert_candidate(
        candidate("Overdone Museum", "insight-museum", ["museum"], 4.5, 2500, price_level=3)
    )
    db.session.commit()

    service.record_event(user=user, place=cafe_place, event_type="accept")
    service.record_event(user=user, place=museum_place, event_type="reject")
    insights = service.preference_insights(user)

    assert insights["learning_status"] == "cold_start"
    assert insights["signal_count"] == 2
    assert insights["event_counts"]["accept"] == 1
    assert insights["event_counts"]["reject"] == 1
    assert insights["top_categories"][0]["tag"] == "cafe"
    assert any(item["tag"] == "museum" for item in insights["avoided_categories"])
    assert insights["price_preference"] == pytest.approx(1.0)
    assert insights["last_signal_at"] is not None


def test_stale_preference_vector_cache_rebuilds_for_recency_decay(app_context):
    user = create_user("stale-cache@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    cafe_place, _, _ = service.upsert_candidate(
        candidate("Fresh Cafe Phase", "cache-cafe", ["cafe"], 4.6, 50)
    )
    db.session.add(UserPreferenceVector(
        user_id=user.id,
        vector_type="phase1",
        vector_json=json.dumps({
            "categories": {"museum": 1.0},
            "cuisines": {},
            "activities": {},
            "avoid_chains": 0.75,
            "hidden_gem_affinity": 0.75,
            "price_preference": None,
        }),
        updated_at=datetime.utcnow() - timedelta(days=2),
    ))
    db.session.add(UserPlaceEvent(user_id=user.id, place_id=cafe_place.id, event_type="accept"))
    db.session.commit()

    vector = service.build_preference_vector(user)

    assert "museum" not in vector["categories"]
    assert vector["categories"]["cafe"] > 0


def test_fresh_preference_vector_cache_is_reused(app_context):
    user = create_user("fresh-cache@example.com", [])
    service = RecommendationService(MockProviderRegistry([]))
    db.session.add(UserPreferenceVector(
        user_id=user.id,
        vector_type="phase1",
        vector_json=json.dumps({
            "categories": {"cached": 1.0},
            "cuisines": {},
            "activities": {},
            "avoid_chains": 0.75,
            "hidden_gem_affinity": 0.75,
            "price_preference": None,
        }),
        updated_at=datetime.utcnow(),
    ))
    db.session.commit()

    vector = service.build_preference_vector(user)

    assert vector["categories"] == {"cached": 1.0}


def test_group_scoring_penalizes_split_preferences(app_context):
    food_user = create_user("food@example.com", ["restaurant", "cafe"])
    art_user = create_user("art@example.com", ["museum", "art_gallery"])
    make_friends(food_user, art_user)
    candidates = [
        candidate("Cafe Gallery", "balanced-1", ["cafe", "art_gallery"], 4.7, 75),
        candidate("Only Burgers", "food-only-1", ["restaurant"], 4.9, 80),
        candidate("Only Museum", "art-only-1", ["museum"], 4.9, 80),
    ]

    result = recommend_for(food_user, candidates, member_ids=[art_user.id])

    assert result["member_count"] == 2
    assert [member["id"] for member in result["members"]] == [food_user.id, art_user.id]
    assert result["recommendations"][0]["name"] == "Cafe Gallery"
    assert result["recommendations"][0]["components"]["group_fit"] >= result["recommendations"][1]["components"]["group_fit"]
    assert result["recommendations"][0]["member_fit"][0]["user_id"] == food_user.id
    assert result["recommendations"][0]["member_fit"][1]["user_id"] == art_user.id
    assert result["group_fit_summary"]["member_count"] == 2
    assert result["group_fit_summary"]["fairness_score"] >= 0.85
    assert len(result["group_fit_summary"]["underserved_members"]) == 2
    assert "may need stronger matches" in result["group_fit_summary"]["message"]
    assert result["group_fit_summary"]["ready_for_friend_testing"] is False
    assert result["group_fit_summary"]["coverage_plan"]["status"] == "needs_member_coverage"
    assert result["group_fit_summary"]["coverage_plan"]["next_actions"]
    assert result["group_fit_summary"]["members"][0]["suggested_query_tags"]
    assert result["group_fit_summary"]["members"][0]["preferred_groups"]
    assert result["group_fit_summary"]["coverage_plan"]["cold_start_member_count"] == 2
    assert all(
        member["learning_status"] == "cold_start"
        and member["signal_count"] == 0
        and member["confidence"] == 0
        for member in result["group_fit_summary"]["members"]
    )
    assert "swipe or rate a few picks" in result["group_fit_summary"]["coverage_plan"]["next_actions"][0]


def test_friend_accepted_place_lifts_group_recommendation(app_context):
    user = create_user("friend-history-user@example.com", ["arcade"])
    friend = create_user("friend-history-fan@example.com", ["arcade"])
    make_friends(user, friend)
    candidates = [
        candidate("Friend Favorite Arcade", "friend-history-liked", ["amusement_center"], 4.5, 80),
        candidate("Neutral Arcade", "friend-history-neutral", ["amusement_center"], 4.8, 600),
    ]
    service = RecommendationService(
        MockProviderRegistry(candidates),
        scoring_profile=ScoringProfile(
            name="friend_history_test",
            personal_fit_weight=0.0,
            group_fit_weight=0.0,
            authenticity_weight=0.0,
            quality_weight=0.0,
            context_fit_weight=0.0,
            time_fit_weight=0.0,
            novelty_weight=0.0,
            exploration_weight=0.0,
            local_event_weight=0.0,
            session_context_weight=0.0,
            friend_history_weight=0.3,
            chain_penalty=0.0,
        ),
    )
    liked_place, _, _ = service.upsert_candidate(candidates[0])
    service.record_event(user=friend, place=liked_place, event_type="accept")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=3200,
        member_ids=[friend.id],
        constraints={"limit": 2, "avoid_chains": True},
    )

    top = result["recommendations"][0]
    assert top["name"] == "Friend Favorite Arcade"
    assert top["components"]["friend_history_fit"] > 0
    assert top["history"]["friend_liked_by"] == [friend.display_name]
    assert any(
        item["id"] == "friend_history" and item["contribution"] > 0
        for item in top["ranking"]["objective_breakdown"]["positive"]
    )
    assert any(detail["kind"] == "friend_history" and detail["label"] == "Friend liked this" for detail in top["explanation_details"])
    assert any(metric["id"] == "friend_history" for metric in top["recommendation_story"]["metrics"])
    assert result["recommendation_quality"]["metrics"]["friend_history_positive_count"] == 1
    assert result["recommendation_quality"]["metrics"]["friend_history_conflict_count"] == 0
    assert any("positive selected-friend history" in strength for strength in result["recommendation_quality"]["strengths"])


def test_friend_rejected_place_adds_group_caution(app_context):
    user = create_user("friend-history-caution-user@example.com", ["arcade"])
    friend = create_user("friend-history-caution-friend@example.com", ["arcade"])
    make_friends(user, friend)
    candidates = [
        candidate("Passed Arcade", "friend-history-rejected", ["amusement_center"], 4.8, 600),
        candidate("Neutral Arcade Two", "friend-history-neutral-two", ["amusement_center"], 4.6, 60),
    ]
    service = RecommendationService(MockProviderRegistry(candidates))
    rejected_place, _, _ = service.upsert_candidate(candidates[0])
    service.record_event(user=friend, place=rejected_place, event_type="reject")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        radius_meters=3200,
        member_ids=[friend.id],
        constraints={"limit": 2, "avoid_chains": True},
    )
    rejected = next(item for item in result["recommendations"] if item["name"] == "Passed Arcade")

    assert rejected["components"]["friend_history_fit"] < 0
    assert rejected["history"]["friend_rejected_by"] == [friend.display_name]
    assert any(
        item["id"] == "friend_history_conflict" and item["penalty"] > 0
        for item in rejected["ranking"]["objective_breakdown"]["penalties"]
    )
    assert any(detail["kind"] == "friend_history" and detail["label"] == "Friend passed here" for detail in rejected["explanation_details"])
    assert any(metric["id"] == "friend_history" for metric in rejected["recommendation_story"]["metrics"])
    assert result["recommendation_quality"]["metrics"]["friend_history_conflict_count"] == 1
    assert any("selected-friend pass history" in warning for warning in result["recommendation_quality"]["warnings"])


def test_group_query_tags_reserve_friend_retrieval_signals(app_context):
    food_user = create_user("query-food@example.com", ["food_drink", "coffee_sweets", "nightlife"])
    art_user = create_user("query-art@example.com", ["arts_culture"])
    make_friends(food_user, art_user)
    candidates = [
        candidate("Cafe Gallery", "query-balanced-1", ["cafe", "art_gallery"], 4.7, 75),
    ]

    result = recommend_for(
        food_user,
        candidates,
        member_ids=[art_user.id],
        constraints={"limit": 4, "avoid_chains": True},
    )

    assert {"restaurant", "bar", "cafe", "coffee_shop", "night_club"}.intersection(result["query_tags"])
    assert {"museum", "art_gallery"}.intersection(result["query_tags"])
    assert len(result["query_tags"]) > 5


def test_boost_query_tags_are_merged_into_provider_query(app_context):
    user = create_user("boost-tags@example.com", ["restaurant"])
    candidates = [
        candidate("Small Gallery", "boost-gallery", ["art_gallery"], 4.7, 80),
        candidate("Local Dinner", "boost-dinner", ["restaurant"], 4.8, 90),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={
            "limit": 4,
            "avoid_chains": True,
            "boost_query_tags": ["arts_culture"],
        },
    )

    assert result["query_tags"][:2] == ["museum", "art_gallery"]
    assert "restaurant" in result["query_tags"]
    assert result["retrieval_context"]["friend_adjusted"] is True
    assert result["retrieval_context"]["boost_query_tags"] == ["arts_culture"]
    assert result["retrieval_context"]["boosted_query_tags"][:2] == ["museum", "art_gallery"]


def test_group_scoring_deprioritizes_lowest_member_fit(app_context):
    cafe_user = create_user("fair-cafe@example.com", ["cafe"])
    museum_user = create_user("fair-museum@example.com", ["museum"])
    make_friends(cafe_user, museum_user)
    candidates = [
        candidate("Perfect Cafe For One", "solo-cafe-1", ["cafe"], 5.0, 55),
        candidate("Shared Cafe Museum", "shared-1", ["cafe", "museum"], 4.4, 70),
    ]

    result = recommend_for(
        cafe_user,
        candidates,
        member_ids=[museum_user.id],
        constraints={"limit": 2, "avoid_chains": True, "scoring_profile": "group_friendly"},
    )

    shared = next(item for item in result["recommendations"] if item["name"] == "Shared Cafe Museum")
    solo = next(item for item in result["recommendations"] if item["name"] == "Perfect Cafe For One")

    assert result["recommendations"][0]["name"] == "Shared Cafe Museum"
    assert SCORING_PROFILES["group_friendly"].group_min_fit_weight > SCORING_PROFILES["phase1_balanced"].group_min_fit_weight
    assert shared["components"]["group_consensus_fit"] == shared["components"]["group_average_fit"]
    assert solo["components"]["group_consensus_fit"] < solo["components"]["group_average_fit"]
    assert solo["components"]["group_min_fit_weight"] == SCORING_PROFILES["group_friendly"].group_min_fit_weight
    assert shared["components"]["group_min_fit"] > solo["components"]["group_min_fit"]
    assert shared["components"]["group_fairness_penalty"] == 0
    assert solo["components"]["group_fairness_penalty"] > 0
    assert solo["ranking"]["exploration_budget"]["authenticity_guardrail"]["allowed"] is False
    assert solo["ranking"]["exploration_budget"]["authenticity_guardrail"]["reason"] == "group_fit_guardrail"
    assert "balanced fit across the group" in shared["explanation"]
    assert "one traveler may not enjoy it" in solo["explanation"]
    assert any(detail["kind"] == "group_fit" and detail["label"] == "Travel-party fit" for detail in shared["explanation_details"])
    assert any(detail["kind"] == "group_fit" and detail["label"] == "Mixed party fit" for detail in solo["explanation_details"])
    assert shared["party_fit_summary"]["headline"] == "Balanced pick for this travel party."
    assert shared["party_fit_summary"]["lowest_fit"] >= SCORING_PROFILES["group_friendly"].group_low_fit_threshold
    assert len(shared["party_fit_summary"]["members"]) == 2
    assert solo["party_fit_summary"]["weak_members"]
    assert shared["recommendation_story"]["headline"] == "A balanced pick for this travel party."
    assert any(metric["id"] == "party_fit" for metric in shared["recommendation_story"]["metrics"])
    assert any("May be weaker" in caution for caution in solo["recommendation_story"]["cautions"])
    assert result["recommendation_quality"]["metrics"]["average_group_fit"] is not None
    assert result["recommendation_quality"]["metrics"]["average_consensus_fit"] is not None
    assert result["recommendation_quality"]["metrics"]["group_consensus_gap"] > 0
    assert any("Travel-party fit" in strength for strength in result["recommendation_quality"]["strengths"])
    assert result["group_fit_summary"]["lowest_fit"] < MEMBER_COVERAGE_FIT_THRESHOLD
    assert result["group_fit_summary"]["average_consensus_fit"] < result["group_fit_summary"]["average_group_average_fit"]
    assert result["group_fit_summary"]["consensus_gap"] > 0
    assert result["group_fit_summary"]["coverage_share"] == 0.5
    assert result["group_fit_summary"]["coverage_plan"]["status"] == "needs_member_coverage"
    assert result["group_fit_summary"]["coverage_plan"]["next_actions"]


def test_group_scoring_rejects_non_friend_member_ids(app_context):
    user = create_user("owner@example.com", ["restaurant"])
    stranger = create_user("stranger@example.com", ["museum"])
    candidates = [
        candidate("Cafe Gallery", "balanced-1", ["cafe", "art_gallery"], 4.7, 75),
    ]

    with pytest.raises(ValueError, match="accepted friends"):
        recommend_for(user, candidates, member_ids=[stranger.id])


def test_diversified_results_preserve_top_pick_but_mix_early_basket(app_context):
    user = create_user("variety@example.com", ["restaurant", "cafe", "park"])
    candidates = [
        candidate("Best Local Cafe", "cafe-1", ["cafe"], 5.0, 80),
        candidate("Second Local Cafe", "cafe-2", ["cafe"], 4.9, 80),
        candidate("Third Local Cafe", "cafe-3", ["cafe"], 4.8, 80),
        candidate("Pocket Park", "park-1", ["park"], 4.7, 70),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 4, "avoid_chains": True})
    names = [item["name"] for item in result["recommendations"]]

    assert names[0] == "Best Local Cafe"
    assert result["recommendations"][0]["ranking"]["preserved_top_pick"] is True
    assert "Pocket Park" in names[:3]
    park = next(item for item in result["recommendations"] if item["name"] == "Pocket Park")
    assert "outdoors" in park["diversity_groups"]
    assert park["ranking"]["strategy"] == "score_then_diversity"


def test_diversified_results_cover_user_intent_groups(app_context):
    user = create_user("intent@example.com", ["cafe", "park", "art_gallery"])
    candidates = [
        candidate("Best Local Cafe", "intent-cafe-1", ["cafe"], 5.0, 80),
        candidate("Second Local Cafe", "intent-cafe-2", ["cafe"], 4.9, 80),
        candidate("Pocket Park", "intent-park-1", ["park"], 4.7, 70),
        candidate("Tiny Art Room", "intent-art-1", ["art_gallery"], 4.6, 70),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 4, "avoid_chains": True})
    names = [item["name"] for item in result["recommendations"]]
    park = next(item for item in result["recommendations"] if item["name"] == "Pocket Park")
    art = next(item for item in result["recommendations"] if item["name"] == "Tiny Art Room")

    assert {"coffee_sweets", "outdoors", "arts_culture"}.issubset(set(result["intent_target_groups"]))
    assert names[0] == "Best Local Cafe"
    assert "Pocket Park" in names[:3]
    assert park["ranking"]["intent_coverage_bonus"] > 0
    assert "outdoors" in park["ranking"]["covered_new_intents"]
    assert art["ranking"]["intent_coverage_bonus"] > 0
    assert "arts_culture" in art["ranking"]["covered_new_intents"]
    assert result["slate_summary"]["status"] == "balanced"
    assert result["slate_summary"]["metrics"]["diversity_coverage"] == 1.0
    assert result["slate_summary"]["missing_intent_groups"] == []
    assert result["recommendation_quality"]["metrics"]["diversity_coverage"] == 1.0
    decision = result["recommendation_quality"]["decision_summary"]
    dimensions = {item["name"]: item for item in decision["dimensions"]}
    assert decision["status"] in {"ready", "watch"}
    assert dimensions["slate_variety"]["status"] == "pass"
    assert dimensions["provider_health"]["summary"] == "Place providers returned cleanly."


def test_quality_summary_warns_when_slate_is_too_narrow(app_context):
    user = create_user("narrow@example.com", ["cafe", "park", "art_gallery"])
    candidates = [
        candidate("Best Local Cafe", "narrow-cafe-1", ["cafe"], 5.0, 80),
        candidate("Second Local Cafe", "narrow-cafe-2", ["cafe"], 4.9, 80),
        candidate("Third Local Cafe", "narrow-cafe-3", ["cafe"], 4.8, 80),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 3, "avoid_chains": True})

    assert result["slate_summary"]["status"] == "narrow"
    assert result["slate_summary"]["metrics"]["diversity_coverage"] < 0.5
    assert result["slate_summary"]["metrics"]["dominant_group_share"] == 1.0
    assert result["slate_summary"]["missing_intent_groups"]
    assert "Basket slate is narrow" in " ".join(result["recommendation_quality"]["warnings"])
    decision = result["recommendation_quality"]["decision_summary"]
    dimensions = {item["name"]: item for item in decision["dimensions"]}
    assert decision["status"] in {"watch", "needs_attention"}
    assert dimensions["slate_variety"]["status"] in {"warn", "fail"}
    assert dimensions["slate_variety"]["next_action"]


def test_quality_summary_warns_when_first_swipe_screen_is_too_narrow(app_context):
    service = RecommendationService(MockProviderRegistry([]))
    member = type("Member", (), {"id": 1, "display_name": "Wanyea", "username": "wanye"})()
    recommendations = [
        {
            "name": "First Cafe",
            "score": 0.9,
            "diversity_groups": ["coffee_sweets"],
            "components": {"authenticity": 0.72},
            "authenticity_evidence": {"label": "Local-feeling"},
            "member_fit": [{"user_id": 1, "display_name": "Wanyea", "fit": 0.86}],
        },
        {
            "name": "Second Cafe",
            "score": 0.88,
            "diversity_groups": ["coffee_sweets"],
            "components": {"authenticity": 0.7},
            "authenticity_evidence": {"label": "Local-feeling"},
            "member_fit": [{"user_id": 1, "display_name": "Wanyea", "fit": 0.84}],
        },
        {
            "name": "Third Cafe",
            "score": 0.86,
            "diversity_groups": ["coffee_sweets"],
            "components": {"authenticity": 0.68},
            "authenticity_evidence": {"label": "Local-feeling"},
            "member_fit": [{"user_id": 1, "display_name": "Wanyea", "fit": 0.82}],
        },
        {
            "name": "Pocket Park",
            "score": 0.82,
            "diversity_groups": ["outdoors"],
            "components": {"authenticity": 0.74},
            "authenticity_evidence": {"label": "Hidden gem"},
            "member_fit": [{"user_id": 1, "display_name": "Wanyea", "fit": 0.76}],
        },
        {
            "name": "Tiny Art Room",
            "score": 0.8,
            "diversity_groups": ["arts_culture"],
            "components": {"authenticity": 0.73},
            "authenticity_evidence": {"label": "Hidden gem"},
            "member_fit": [{"user_id": 1, "display_name": "Wanyea", "fit": 0.74}],
        },
    ]

    slate_summary = service._slate_summary(
        recommendations,
        [member],
        {"coffee_sweets", "outdoors", "arts_culture"},
    )
    group_fit_summary = service._group_fit_summary(recommendations, [member])
    quality = service._recommendation_quality_summary(
        recommendations,
        [member],
        group_fit_summary=group_fit_summary,
        slate_summary=slate_summary,
    )

    assert slate_summary["metrics"]["diversity_coverage"] == 1.0
    assert slate_summary["metrics"]["first_page_diversity_coverage"] == 0.333
    assert slate_summary["metrics"]["first_page_dominant_group_share"] == 1.0
    assert slate_summary["first_page_missing_intent_groups"] == ["arts_culture", "outdoors"]
    assert quality["metrics"]["first_page_diversity_coverage"] == 0.333
    assert "First swipe screen is narrow" in " ".join(quality["warnings"])
    decision = quality["decision_summary"]
    dimensions = {item["name"]: item for item in decision["dimensions"]}
    assert dimensions["slate_variety"]["status"] == "pass"
    assert dimensions["first_swipes"]["status"] == "fail"
    assert dimensions["first_swipes"]["next_action"]


def test_group_results_promote_under_served_friend_match(app_context):
    cafe_user = create_user("cafe@example.com", ["cafe"])
    museum_user = create_user("museum@example.com", ["museum"])
    make_friends(cafe_user, museum_user)
    candidates = [
        candidate("Best Local Cafe", "cafe-1", ["cafe"], 5.0, 80),
        candidate("Second Local Cafe", "cafe-2", ["cafe"], 4.9, 80),
        candidate("Third Local Cafe", "cafe-3", ["cafe"], 4.8, 80),
        candidate("Tiny Local Museum", "museum-1", ["museum"], 4.6, 70),
    ]

    result = recommend_for(
        cafe_user,
        candidates,
        member_ids=[museum_user.id],
        constraints={"limit": 4, "avoid_chains": True},
    )
    names = [item["name"] for item in result["recommendations"]]
    museum = next(item for item in result["recommendations"] if item["name"] == "Tiny Local Museum")

    assert names[0] == "Best Local Cafe"
    assert "Tiny Local Museum" in names[:3]
    assert museum["ranking"]["member_coverage_bonus"] > 0
    assert museum_user.display_name in museum["ranking"]["served_new_members"]
    assert result["slate_summary"]["metrics"]["member_coverage_share"] == 1.0
    assert result["slate_summary"]["underserved_members"] == []
    assert result["group_fit_summary"]["ready_for_friend_testing"] is True
    assert result["group_fit_summary"]["coverage_plan"]["status"] == "watch"
    assert result["group_fit_summary"]["coverage_plan"]["ready_for_friend_testing"] is True
    assert result["group_fit_summary"]["coverage_plan"]["cold_start_member_count"] == 2
    assert result["group_fit_summary"]["coverage_plan"]["next_actions"][-1] == "Keep this basket or start swiping with the group."
    assert all(member["best_match"] for member in result["group_fit_summary"]["members"])
    coverage_by_name = {
        member["display_name"]: member
        for member in result["slate_summary"]["member_coverage"]
    }
    museum_coverage = coverage_by_name[museum_user.display_name]
    assert museum_coverage["best_match"]["name"] == "Tiny Local Museum"
    assert museum_coverage["best_match"]["rank_position"] == names.index("Tiny Local Museum") + 1
    assert museum_coverage["strong_matches"][0]["name"] == "Tiny Local Museum"
    assert museum_coverage["strong_matches"][0]["authenticity_label"] in {"Hidden gem", "Local-feeling"}
    decision = result["recommendation_quality"]["decision_summary"]
    dimensions = {item["name"]: item for item in decision["dimensions"]}
    assert dimensions["friend_fit"]["status"] == "pass"
    assert "friend coverage" in dimensions["friend_fit"]["summary"]


def test_group_results_rescue_friend_match_on_small_page(app_context):
    service = RecommendationService(MockProviderRegistry([]))
    scored = [
        {
            "name": "Owner Favorite Cafe",
            "score": 0.95,
            "components": {"authenticity": 0.7, "group_member_count": 2, "group_min_fit": 0.2},
            "ranking": {"scoring_profile": "phase1_balanced"},
            "display": {"types": ["cafe"]},
            "diversity_groups": ["coffee_sweets"],
            "member_fit": [
                {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.95},
                {"user_id": 2, "display_name": "Museum Fan", "fit": 0.2},
            ],
        },
        {
            "name": "Owner Backup Cafe",
            "score": 0.90,
            "components": {"authenticity": 0.7, "group_member_count": 2, "group_min_fit": 0.18},
            "ranking": {"scoring_profile": "phase1_balanced"},
            "display": {"types": ["cafe"]},
            "diversity_groups": ["coffee_sweets"],
            "member_fit": [
                {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.9},
                {"user_id": 2, "display_name": "Museum Fan", "fit": 0.18},
            ],
        },
        {
            "name": "Tiny Local Museum",
            "score": 0.45,
            "components": {"authenticity": 0.72, "group_member_count": 2, "group_min_fit": 0.68},
            "ranking": {"scoring_profile": "phase1_balanced"},
            "display": {"types": ["museum"]},
            "diversity_groups": ["arts_culture"],
            "member_fit": [
                {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.22},
                {"user_id": 2, "display_name": "Museum Fan", "fit": 0.85},
            ],
        },
    ]

    recommendations = service._diversify_ranked_results(
        scored,
        limit=2,
        constraints={"preserve_top_result": True},
        scoring_profile=SCORING_PROFILES["phase1_balanced"],
        intent_target_groups={"coffee_sweets", "arts_culture"},
    )
    names = [item["name"] for item in recommendations]
    museum = next(item for item in recommendations if item["name"] == "Tiny Local Museum")
    slate_summary = service._slate_summary(
        recommendations,
        [
            type("Member", (), {"id": 1, "display_name": "Cafe Fan", "username": "cafe"})(),
            type("Member", (), {"id": 2, "display_name": "Museum Fan", "username": "museum"})(),
        ],
        {"coffee_sweets", "arts_culture"},
    )
    group_fit_summary = service._group_fit_summary(
        recommendations,
        [
            type("Member", (), {"id": 1, "display_name": "Cafe Fan", "username": "cafe"})(),
            type("Member", (), {"id": 2, "display_name": "Museum Fan", "username": "museum"})(),
        ],
    )
    quality = service._recommendation_quality_summary(
        recommendations,
        [
            type("Member", (), {"id": 1, "display_name": "Cafe Fan", "username": "cafe"})(),
            type("Member", (), {"id": 2, "display_name": "Museum Fan", "username": "museum"})(),
        ],
        group_fit_summary=group_fit_summary,
        slate_summary=slate_summary,
    )
    friend_dimension = next(
        item for item in quality["decision_summary"]["dimensions"]
        if item["name"] == "friend_fit"
    )

    assert names[0] == "Owner Favorite Cafe"
    assert names[1] == "Tiny Local Museum"
    assert museum["ranking"]["party_coverage_rescue"] is True
    assert museum["ranking"]["rescued_member"] == "Museum Fan"
    assert museum["ranking"]["replaced_pick"] == "Owner Backup Cafe"
    assert slate_summary["metrics"]["member_coverage_share"] == 1.0
    assert slate_summary["underserved_members"] == []
    assert quality["metrics"]["party_coverage_rescue_count"] == 1
    assert quality["metrics"]["party_coverage_rescued_members"] == ["Museum Fan"]
    assert any("made room" in strength for strength in quality["strengths"])
    assert "rescued 1 match for Museum Fan" in friend_dimension["summary"]


def test_group_friendly_diversification_can_unseat_low_fit_top_pick(app_context):
    service = RecommendationService(MockProviderRegistry([]))
    solo_top = {
        "name": "Solo Favorite Cafe",
        "score": 0.83,
        "components": {
            "authenticity": 0.7,
            "group_member_count": 2,
            "group_min_fit": 0.25,
        },
        "ranking": {"scoring_profile": "group_friendly"},
        "display": {"types": ["cafe"]},
        "diversity_groups": ["coffee_sweets"],
        "member_fit": [
            {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.88},
            {"user_id": 2, "display_name": "Museum Fan", "fit": 0.25},
        ],
    }
    shared_pick = {
        "name": "Gallery Cafe Everyone Likes",
        "score": 0.76,
        "components": {
            "authenticity": 0.7,
            "group_member_count": 2,
            "group_min_fit": 0.7,
        },
        "ranking": {"scoring_profile": "group_friendly"},
        "display": {"types": ["cafe", "museum"]},
        "diversity_groups": ["coffee_sweets", "arts_culture"],
        "member_fit": [
            {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.72},
            {"user_id": 2, "display_name": "Museum Fan", "fit": 0.7},
        ],
    }

    diversified = service._diversify_ranked_results(
        [solo_top, shared_pick],
        limit=2,
        constraints={"preserve_top_result": True},
        scoring_profile=SCORING_PROFILES["group_friendly"],
        intent_target_groups={"coffee_sweets", "arts_culture"},
    )

    assert diversified[0]["name"] == "Gallery Cafe Everyone Likes"
    assert diversified[0]["ranking"]["served_new_members"] == ["Cafe Fan", "Museum Fan"]
    assert diversified[0]["ranking"]["member_coverage_bonus"] > solo_top["ranking"].get("member_coverage_bonus", 0)
    assert diversified[0]["ranking"].get("preserved_top_pick") is None


def test_default_diversification_still_preserves_top_pick(app_context):
    service = RecommendationService(MockProviderRegistry([]))
    scored = [
        {
            "name": "Solo Favorite Cafe",
            "score": 0.83,
            "components": {"authenticity": 0.7, "group_member_count": 2, "group_min_fit": 0.25},
            "ranking": {"scoring_profile": "phase1_balanced"},
            "display": {"types": ["cafe"]},
            "diversity_groups": ["coffee_sweets"],
            "member_fit": [
                {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.88},
                {"user_id": 2, "display_name": "Museum Fan", "fit": 0.25},
            ],
        },
        {
            "name": "Gallery Cafe Everyone Likes",
            "score": 0.76,
            "components": {"authenticity": 0.7, "group_member_count": 2, "group_min_fit": 0.7},
            "ranking": {"scoring_profile": "phase1_balanced"},
            "display": {"types": ["cafe", "museum"]},
            "diversity_groups": ["coffee_sweets", "arts_culture"],
            "member_fit": [
                {"user_id": 1, "display_name": "Cafe Fan", "fit": 0.72},
                {"user_id": 2, "display_name": "Museum Fan", "fit": 0.7},
            ],
        },
    ]

    diversified = service._diversify_ranked_results(
        scored,
        limit=2,
        constraints={"preserve_top_result": True},
        scoring_profile=SCORING_PROFILES["phase1_balanced"],
        intent_target_groups={"coffee_sweets", "arts_culture"},
    )

    assert diversified[0]["name"] == "Solo Favorite Cafe"
    assert diversified[0]["ranking"]["preserved_top_pick"] is True


def test_impressions_are_logged_for_returned_recommendations(app_context):
    user = create_user("impressions@example.com", ["park"])
    candidates = [
        candidate("Neighborhood Park", "park-1", ["park"], 4.6, 20),
    ]

    result = recommend_for(user, candidates)

    assert len(result["recommendations"]) == 1
    events = UserPlaceEvent.query.filter_by(user_id=user.id, event_type="impression").all()
    assert len(events) == 1
    metadata = json.loads(events[0].metadata_json)
    assert metadata["request_id"] == result["request_id"]
    assert metadata["rank_position"] == 1
    assert metadata["ranking"]["strategy"] == "score_then_diversity"
    assert metadata["member_fit"][0]["user_id"] == user.id
    assert metadata["explanation_details"]
    assert metadata["authenticity_evidence"]["label"] in {"Hidden gem", "Local-feeling", "Generic risk"}
    assert metadata["query_tags"]
    assert metadata["retrieval_context"]["query_tags"] == metadata["query_tags"]
    assert metadata["intent_target_groups"]
    assert metadata["member_ids"] == [user.id]


def test_impressions_can_be_disabled_for_preview_recommendations(app_context):
    user = create_user("preview@example.com", ["park"])
    candidates = [
        candidate("Neighborhood Park", "park-1", ["park"], 4.6, 20),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={"limit": 10, "avoid_chains": True, "record_impressions": False},
    )

    assert len(result["recommendations"]) == 1
    assert UserPlaceEvent.query.filter_by(user_id=user.id, event_type="impression").count() == 0


def test_recommendations_include_free_travel_time_estimates(app_context):
    user = create_user("travel@example.com", ["museum"])
    candidates = [
        candidate("City Museum", "museum-1", ["museum"], 4.7, 80, lat=37.431, lng=-122.084),
    ]

    result = recommend_for(user, candidates)
    travel_times = result["recommendations"][0]["travel_times"]

    assert travel_times["walk_minutes"] >= 1
    assert travel_times["drive_minutes"] >= 1
    assert travel_times["transit_minutes"] >= 2


def test_time_context_boosts_morning_appropriate_places(app_context):
    user = create_user("morning@example.com", ["cafe", "bar"])
    candidates = [
        candidate("Late Night Lounge", "bar-1", ["bar"], 4.9, 80),
        candidate("Sunrise Coffee", "coffee-1", ["cafe", "coffee_shop"], 4.4, 80),
    ]

    result = recommend_for(user, candidates, constraints={
        "limit": 10,
        "avoid_chains": True,
        "time_context": {"period": "morning", "local_hour": 8},
    })

    assert result["recommendations"][0]["name"] == "Sunrise Coffee"
    assert result["recommendations"][0]["components"]["time_fit"] > result["recommendations"][1]["components"]["time_fit"]
    assert "fits the morning vibe" in result["recommendations"][0]["explanation"]


def test_time_context_marks_evening_places_as_timely(app_context):
    user = create_user("evening@example.com", ["bar", "restaurant"])
    candidates = [
        candidate("Neighborhood Jazz Bar", "jazz-1", ["bar", "concert_hall"], 4.6, 80),
    ]

    result = recommend_for(user, candidates, constraints={
        "limit": 10,
        "avoid_chains": True,
        "time_context": {"period": "evening", "local_hour": 20},
    })

    assert result["recommendations"][0]["components"]["time_fit"] >= 0.75
    assert "fits the evening vibe" in result["recommendations"][0]["explanation"]


def test_price_constraint_applies_penalty(app_context):
    user = create_user("budget@example.com", ["restaurant"])
    candidates = [
        candidate("Affordable Noodles", "cheap-1", ["restaurant"], 4.5, 60, price_level=1),
        candidate("Expensive Tasting Room", "expensive-1", ["restaurant"], 4.8, 50, price_level=4),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 10, "avoid_chains": True, "price_max": 2})
    expensive = next(item for item in result["recommendations"] if item["name"] == "Expensive Tasting Room")

    assert expensive["components"]["price_penalty"] > 0


def test_affordable_local_places_get_value_gem_signal(app_context):
    user = create_user("valuegem@example.com", ["restaurant"])
    candidates = [
        candidate("Tiny Taco Window", "value-cheap-1", ["restaurant", "mexican_restaurant"], 4.7, 35, price_level=1),
        candidate("Special Occasion Counter", "value-splurge-1", ["restaurant"], 4.8, 65, price_level=4),
    ]

    result = recommend_for(user, candidates, constraints={"limit": 10, "avoid_chains": True, "price_max": 2})
    cheap = next(item for item in result["recommendations"] if item["name"] == "Tiny Taco Window")
    splurge = next(item for item in result["recommendations"] if item["name"] == "Special Occasion Counter")

    assert cheap["components"]["value_gem"] >= 0.6
    assert splurge["components"]["value_gem"] == 0
    assert any(detail["kind"] == "value_gem" for detail in cheap["explanation_details"])
    assert any(metric["id"] == "value_gem" for metric in cheap["recommendation_story"]["metrics"])
    assert any("Affordable without losing" in reason for reason in cheap["recommendation_story"]["reasons"])
    assert result["recommendation_quality"]["metrics"]["value_gem_count"] == 1
    assert any("value-gem" in strength for strength in result["recommendation_quality"]["strengths"])


def test_learned_price_preference_applies_soft_penalty(app_context):
    user = create_user("pricecomfort@example.com", ["restaurant"])
    candidates = [
        candidate("Tiny Taco Window", "cheap-1", ["restaurant"], 4.5, 60, price_level=1),
        candidate("Special Occasion Counter", "splurge-1", ["restaurant"], 4.9, 50, price_level=4),
    ]
    service = RecommendationService(MockProviderRegistry(candidates))
    cheap_place, _, _ = service.upsert_candidate(candidates[0])
    db.session.commit()
    service.record_event(user=user, place=cheap_place, event_type="accept")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    splurge = next(item for item in result["recommendations"] if item["name"] == "Special Occasion Counter")

    assert splurge["components"]["price_penalty"] > 0
    assert "above your usual price comfort zone" in splurge["explanation"]


def test_excluded_tag_groups_are_hard_filtered(app_context):
    user = create_user("skipnightlife@example.com", ["bar", "museum"])
    candidates = [
        candidate("Late Night Lounge", "bar-1", ["bar", "night_club"], 4.9, 80),
        candidate("Tiny Local Museum", "museum-1", ["museum"], 4.5, 40),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={
            "limit": 10,
            "avoid_chains": True,
            "excluded_tag_groups": ["nightlife"],
        },
    )
    names = [item["name"] for item in result["recommendations"]]

    assert "Late Night Lounge" not in names
    assert names == ["Tiny Local Museum"]
    assert result["filter_summary"]["hard_constraints_active"] is True
    assert result["filter_summary"]["skipped"]["hard_constraints"] == 1


def test_included_tag_groups_are_hard_filtered(app_context):
    user = create_user("onlyoutdoors@example.com", ["park", "restaurant"])
    candidates = [
        candidate("Pocket Park", "park-1", ["park"], 4.7, 40),
        candidate("Local Taco Stand", "taco-1", ["restaurant"], 4.8, 55),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={
            "limit": 10,
            "avoid_chains": True,
            "included_tag_groups": ["outdoors"],
        },
    )
    names = [item["name"] for item in result["recommendations"]]

    assert names == ["Pocket Park"]
    assert result["filter_summary"]["hard_constraints_active"] is True
    assert result["filter_summary"]["skipped"]["hard_constraints"] == 1


def test_filter_summary_counts_distance_and_discoverability_skips(app_context):
    user = create_user("filtersummary@example.com", ["museum", "restaurant"])
    candidates = [
        candidate("RaceTrac", "racetrac-1", ["gas_station"], 4.2, 1000),
        candidate("Faraway Museum", "far-1", ["museum"], 4.8, 100, lat=38.0, lng=-122.084),
        candidate("Nearby Museum", "near-1", ["museum"], 4.5, 40),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert result["filter_summary"]["raw_candidates"] == 3
    assert result["filter_summary"]["returned"] == 1
    assert result["filter_summary"]["skipped"]["not_discoverable"] == 1
    assert result["filter_summary"]["skipped"]["distance"] == 1
    diagnostic = result["recommendation_quality"]["diagnostic"]
    stages = {stage["name"]: stage for stage in diagnostic["stages"]}
    assert diagnostic["summary"]["raw_candidates"] == 3
    assert diagnostic["summary"]["returned"] == 1
    assert stages["retrieval"]["status"] == "warn"
    assert stages["candidate_depth"]["status"] == "fail"
    assert stages["filtering"]["summary"].startswith("Filters skipped 2 of 3")


def test_pipeline_diagnostic_flags_hard_filter_pressure(app_context):
    user = create_user("filterpressure@example.com", ["park", "restaurant"])
    candidates = [
        candidate("Pocket Park", "pressure-park", ["park"], 4.7, 40),
        candidate("Local Taco Stand", "pressure-taco", ["restaurant"], 4.8, 55),
        candidate("Tiny Gallery", "pressure-gallery", ["art_gallery"], 4.6, 65),
        candidate("Corner Cafe", "pressure-cafe", ["cafe"], 4.5, 70),
        candidate("Neighborhood Bar", "pressure-bar", ["bar"], 4.5, 60),
        candidate("Weekend Market", "pressure-market", ["market"], 4.6, 75),
    ]

    result = recommend_for(
        user,
        candidates,
        constraints={
            "limit": 10,
            "avoid_chains": True,
            "included_tag_groups": ["outdoors"],
        },
    )

    diagnostic = result["recommendation_quality"]["diagnostic"]
    stages = {stage["name"]: stage for stage in diagnostic["stages"]}
    assert diagnostic["primary_issue"]["name"] in {"candidate_depth", "filtering"}
    assert stages["filtering"]["status"] == "fail"
    assert "tag" in stages["filtering"]["summary"]
    assert stages["filtering"]["next_action"]


def test_rejected_place_is_excluded_from_next_recommendation_batch(app_context):
    user = create_user("reject@example.com", ["restaurant", "cafe"])
    candidates = [
        candidate("Wawa", "wawa-1", ["convenience_store", "restaurant"], 4.3, 400),
        candidate("Local Sandwich Shop", "sandwich-1", ["restaurant"], 4.7, 55),
    ]

    service = RecommendationService(MockProviderRegistry(candidates))
    first = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    wawa = next(item for item in first["recommendations"] if item["name"] == "Wawa")
    wawa_place = db.session.get(Place, wawa["place_id"])

    service.record_event(user=user, place=wawa_place, event_type="reject")
    second = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert all(item["name"] != "Wawa" for item in second["recommendations"])


def test_recently_shown_places_are_deprioritized_for_fresh_picks(app_context):
    user = create_user("fresh@example.com", ["cafe"])
    repeated_candidate = candidate("Famous Corner Cafe", "repeat-1", ["cafe"], 5.0, 90)
    fresh_candidate = candidate("New Neighborhood Cafe", "fresh-1", ["cafe"], 4.4, 90)
    service = RecommendationService(MockProviderRegistry([repeated_candidate, fresh_candidate]))
    repeated_place, _, _ = service.upsert_candidate(repeated_candidate)
    db.session.commit()

    for _ in range(3):
        service.record_event(user=user, place=repeated_place, event_type="impression")

    result = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert result["recommendations"][0]["name"] == "New Neighborhood Cafe"
    repeated = next(item for item in result["recommendations"] if item["name"] == "Famous Corner Cafe")
    assert repeated["components"]["repeat_penalty"] > 0
    assert repeated["history"]["recent_impressions"] == 3
    assert "shown recently" in repeated["explanation"]


def test_current_session_feedback_nudges_next_recommendations(app_context):
    user = create_user("session@example.com", ["museum"])
    service = RecommendationService(MockProviderRegistry([]))
    accepted_training = candidate("Accepted Taco Window", "session-training-taco", ["restaurant", "mexican_restaurant"], 4.7, 80)
    rejected_training = candidate("Passed Museum Wing", "session-training-museum", ["museum"], 4.7, 80)
    accepted_place, _, _ = service.upsert_candidate(accepted_training)
    rejected_place, _, _ = service.upsert_candidate(rejected_training)
    db.session.add(UserPreferenceVector(
        user_id=user.id,
        vector_type="phase1",
        vector_json=json.dumps({
            "categories": {"museum": 1.0},
            "cuisines": {},
            "activities": {},
            "avoid_chains": 0.75,
            "hidden_gem_affinity": 0.75,
            "confidence": 0.8,
            "signal_count": 10,
        }),
    ))
    db.session.add_all([
        UserPlaceEvent(user_id=user.id, place_id=accepted_place.id, event_type="accept", occurred_at=datetime.utcnow()),
        UserPlaceEvent(user_id=user.id, place_id=rejected_place.id, event_type="reject", occurred_at=datetime.utcnow()),
    ])
    db.session.commit()

    result = RecommendationService(MockProviderRegistry([
        candidate("New Taco Walkup", "session-taco", ["restaurant", "mexican_restaurant"], 4.7, 80),
        candidate("Formal Museum", "session-museum", ["museum"], 4.7, 80),
    ])).recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert result["session_context"]["status"] == "active"
    assert result["session_context"]["positive_signal_count"] == 1
    assert result["session_context"]["negative_signal_count"] == 1
    assert result["recommendations"][0]["name"] == "New Taco Walkup"
    taco = result["recommendations"][0]
    museum = next(item for item in result["recommendations"] if item["name"] == "Formal Museum")
    assert taco["components"]["session_context_fit"] > 0
    assert museum["components"]["session_context_fit"] < 0
    assert any(detail["kind"] == "session_context" for detail in taco["explanation_details"])
    session_objective = next(
        item for item in taco["ranking"]["objective_breakdown"]["positive"]
        if item["id"] == "session_momentum"
    )
    assert session_objective["contribution"] > 0


def test_decided_places_repeat_when_batch_would_be_empty(app_context):
    user = create_user("exhausted@example.com", ["museum"])
    candidates = [
        candidate("City Museum", "museum-1", ["museum"], 4.8, 300),
    ]

    service = RecommendationService(MockProviderRegistry(candidates))
    first = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )
    museum = first["recommendations"][0]
    museum_place = db.session.get(Place, museum["place_id"])

    service.record_event(user=user, place=museum_place, event_type="reject")
    second = service.recommend(
        user=user,
        location={"latitude": 37.421998333333335, "longitude": -122.084},
        constraints={"limit": 10, "avoid_chains": True},
    )

    assert second["repeated_decided"] is True
    assert second["recommendations"][0]["name"] == "City Museum"
    assert second["recommendations"][0]["repeat_after_exhaustion"] is True
    assert second["recommendations"][0]["components"]["decision_penalty"] > 0
    assert second["recommendations"][0]["history"]["rejected"] is True
    assert "previously rejected" in second["recommendations"][0]["explanation"]


def test_food_lane_classifies_hybrid_food_chains(app_context):
    user = create_user("lanes@example.com", ["restaurant"])
    candidates = [
        candidate("Wawa", "wawa-1", ["convenience_store", "restaurant"], 4.3, 400),
        candidate("Culver's", "culvers-1", ["fast_food_restaurant"], 4.5, 300),
        candidate("Local Seafood Shack", "seafood-1", ["seafood_restaurant"], 4.6, 90),
        candidate("Orlando Science Center", "science-1", ["museum"], 4.7, 1200),
    ]

    result = recommend_for(user, candidates)
    categories = {item["name"]: item["category"] for item in result["recommendations"]}

    assert categories["Wawa"] == "food"
    assert categories["Culver's"] == "food"
    assert categories["Local Seafood Shack"] == "food"
    assert categories["Orlando Science Center"] == "activity"


def test_utility_only_places_are_filtered_from_discovery(app_context):
    user = create_user("utility@example.com", ["restaurant", "museum"])
    candidates = [
        candidate("RaceTrac", "racetrac-1", ["gas_station", "convenience_store"], 4.2, 1000),
        candidate("City Museum", "museum-1", ["museum"], 4.8, 300),
    ]

    result = recommend_for(user, candidates)
    names = [item["name"] for item in result["recommendations"]]

    assert "RaceTrac" not in names
    assert "City Museum" in names
