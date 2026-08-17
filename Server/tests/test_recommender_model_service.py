import json
from types import SimpleNamespace

import pytest

from recommender_refresh_model import refresh_model, summarize_training_data_health
from adventour_backend.services.recommender_model_service import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    LearningToRankBaselineService,
    learned_ranker_artifact_status,
    model_feature_compatibility,
)


def training_examples():
    return [
        {
            "request_id": "a",
            "rank_position": 1,
            "label": 1.0,
            "outcome_weight": 1.0,
            "model_score": 0.7,
            "base_rank_score": 0.68,
            "authenticity_score": 0.92,
            "hidden_gem_score": 0.8,
            "chain_probability": 0.0,
            "quality_score": 0.88,
            "group_min_fit": 0.82,
            "group_fairness_penalty": 0.02,
            "exploration": 0.5,
            "exploration_uncertainty": 0.25,
            "preference_confidence": 0.75,
            "average_member_signal_count": 9.0,
            "covered_new_intents_count": 2,
            "served_new_members_count": 1,
            "friend_adjusted_retrieval": True,
            "objective_positive_total": 0.88,
            "objective_penalty_total": 0.08,
            "price_band": 2,
            "local_event_backed": True,
            "local_event_fit": 0.82,
            "local_event_distance_to_place_meters": 320,
            "local_event_reservation_ready": True,
            "local_event_source_ready": True,
            "local_event_route_anchor_score": 0.76,
            "local_event_friend_signal_count": 2,
            "local_event_social_signal": 0.6,
            "session_context_fit": 0.55,
            "friend_history_fit": 0.4,
            "components": {
                "personal_fit": 0.8,
                "group_fit": 0.82,
                "group_average_fit": 0.86,
                "group_consensus_fit": 0.85,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.78,
                "time_fit": 0.7,
                "novelty": 0.7,
            },
        },
        {
            "request_id": "a",
            "rank_position": 2,
            "label": 0.0,
            "outcome_weight": 0.75,
            "model_score": 0.62,
            "base_rank_score": 0.6,
            "authenticity_score": 0.18,
            "hidden_gem_score": 0.05,
            "chain_probability": 0.95,
            "quality_score": 0.62,
            "group_min_fit": 0.35,
            "group_fairness_penalty": 0.42,
            "exploration": 0.0,
            "exploration_uncertainty": 0.1,
            "preference_confidence": 0.9,
            "average_member_signal_count": 12.0,
            "price_band": 4,
            "repeat_after_exhaustion": True,
            "components": {
                "personal_fit": 0.2,
                "group_fit": 0.3,
                "group_average_fit": 0.64,
                "group_consensus_fit": 0.56,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.25,
                "time_fit": 0.2,
                "novelty": 0.1,
            },
        },
        {
            "request_id": "b",
            "rank_position": 1,
            "label": 1.0,
            "outcome_weight": 0.9,
            "model_score": 0.75,
            "base_rank_score": 0.73,
            "authenticity_score": 0.86,
            "hidden_gem_score": 0.64,
            "chain_probability": 0.02,
            "quality_score": 0.91,
            "group_min_fit": 0.76,
            "group_fairness_penalty": 0.05,
            "exploration": 0.35,
            "exploration_uncertainty": 0.5,
            "preference_confidence": 0.5,
            "average_member_signal_count": 6.0,
            "price_band": 2,
            "components": {
                "personal_fit": 0.75,
                "group_fit": 0.78,
                "group_average_fit": 0.82,
                "group_consensus_fit": 0.8,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.82,
                "time_fit": 0.76,
                "novelty": 0.6,
            },
        },
        {
            "request_id": "b",
            "rank_position": 2,
            "label": 0.0,
            "outcome_weight": 0.75,
            "model_score": 0.4,
            "base_rank_score": 0.39,
            "authenticity_score": 0.25,
            "hidden_gem_score": 0.1,
            "chain_probability": 0.75,
            "quality_score": 0.5,
            "group_min_fit": 0.4,
            "group_fairness_penalty": 0.3,
            "exploration": 0.0,
            "exploration_uncertainty": 0.3,
            "preference_confidence": 0.7,
            "average_member_signal_count": 8.0,
            "price_band": 3,
            "components": {
                "personal_fit": 0.35,
                "group_fit": 0.38,
                "group_average_fit": 0.62,
                "group_consensus_fit": 0.56,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.4,
                "time_fit": 0.42,
                "novelty": 0.3,
            },
        },
        {
            "request_id": "c",
            "rank_position": 1,
            "label": 1.0,
            "outcome_weight": 1.0,
            "model_score": 0.8,
            "base_rank_score": 0.79,
            "authenticity_score": 0.88,
            "hidden_gem_score": 0.7,
            "chain_probability": 0.0,
            "quality_score": 0.86,
            "group_min_fit": 0.8,
            "group_fairness_penalty": 0.0,
            "exploration": 0.6,
            "exploration_uncertainty": 0.75,
            "preference_confidence": 0.25,
            "average_member_signal_count": 3.0,
            "price_band": 1,
            "components": {
                "personal_fit": 0.82,
                "group_fit": 0.84,
                "group_average_fit": 0.86,
                "group_consensus_fit": 0.84,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.8,
                "time_fit": 0.74,
                "novelty": 0.78,
            },
        },
        {
            "request_id": "c",
            "rank_position": 2,
            "label": 0.0,
            "outcome_weight": 0.75,
            "model_score": 0.35,
            "base_rank_score": 0.36,
            "authenticity_score": 0.12,
            "hidden_gem_score": 0.04,
            "chain_probability": 0.88,
            "quality_score": 0.45,
            "group_min_fit": 0.3,
            "group_fairness_penalty": 0.44,
            "exploration": 0.0,
            "exploration_uncertainty": 0.2,
            "preference_confidence": 0.8,
            "average_member_signal_count": 10.0,
            "price_band": 4,
            "repeat_after_exhaustion": True,
            "components": {
                "personal_fit": 0.25,
                "group_fit": 0.28,
                "group_average_fit": 0.6,
                "group_consensus_fit": 0.52,
                "group_min_fit_weight": 0.26,
                "context_fit": 0.35,
                "time_fit": 0.2,
                "novelty": 0.12,
            },
        },
    ]


def ready_training_data_health():
    return {
        "status": "ready",
        "summary": "Training data is ready for learned-ranker evaluation.",
        "counts": {
            "examples": 60,
            "labeled": 60,
            "positive": 30,
            "negative": 30,
            "requests": 24,
            "group_examples": 12,
            "friend_adjusted": 12,
            "event_backed": 8,
            "event_reservation_ready": 8,
            "event_source_ready": 8,
            "event_friend_signal": 3,
            "event_social_signal": 4,
        },
        "checks": [
            {"name": "labeled_outcomes", "label": "Enough labeled outcomes", "status": "pass"},
            {"name": "request_diversity", "label": "Enough recommendation requests", "status": "pass"},
            {"name": "positive_negative_mix", "label": "Both positive and negative outcomes exist", "status": "pass"},
            {"name": "group_friend_signal", "label": "Group/friend examples exist", "status": "pass"},
            {"name": "event_anchor_signal", "label": "Event-backed examples are actionable", "status": "pass"},
            {"name": "event_social_signal", "label": "Event social/friend signal exists", "status": "pass"},
        ],
    }


def test_learning_to_rank_baseline_trains_and_scores_examples():
    service = LearningToRankBaselineService()
    examples = training_examples()

    model = service.train(examples, iterations=250, validation_fraction=0)

    positive = examples[0]
    negative = examples[1]
    assert model["model_type"] == "adventour_logistic_ltr_baseline"
    assert model["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert "exploration_uncertainty" in model["feature_names"]
    assert "preference_confidence" in model["feature_names"]
    assert "profile_signal_density" in model["feature_names"]
    assert "friend_adjusted_retrieval" in model["feature_names"]
    assert "local_event_friend_signal_density" in model["feature_names"]
    assert "local_event_actionability" in model["feature_names"]
    assert "group_consensus_fit" in model["feature_names"]
    assert "group_consensus_gap_inverse" in model["feature_names"]
    assert "covered_intents_density" in model["feature_names"]
    assert "served_members_density" in model["feature_names"]
    assert model["training_summary"]["example_count"] == len(examples)
    assert service.predict(positive, model) > service.predict(negative, model)
    assert any(item["feature"] == "authenticity_score" for item in model["top_positive_weights"])
    assert any(item["feature"] == "chain_inverse" for item in model["top_positive_weights"])


def test_learning_to_rank_baseline_feature_vector_includes_profile_confidence():
    service = LearningToRankBaselineService()
    features = service._feature_values(training_examples()[0])

    assert "exploration_uncertainty" in FEATURE_NAMES
    assert "preference_confidence" in FEATURE_NAMES
    assert "profile_signal_density" in FEATURE_NAMES
    assert "local_event_fit" in FEATURE_NAMES
    assert "local_event_proximity" in FEATURE_NAMES
    assert "local_event_route_anchor_score" in FEATURE_NAMES
    assert "local_event_friend_signal_density" in FEATURE_NAMES
    assert "local_event_social_signal" in FEATURE_NAMES
    assert "local_event_actionability" in FEATURE_NAMES
    assert "session_context_fit" in FEATURE_NAMES
    assert "session_momentum" in FEATURE_NAMES
    assert "session_mismatch_inverse" in FEATURE_NAMES
    assert "friend_history_fit" in FEATURE_NAMES
    assert "friend_history_positive" in FEATURE_NAMES
    assert "friend_history_conflict_inverse" in FEATURE_NAMES
    assert "friend_adjusted_retrieval" in FEATURE_NAMES
    assert "group_average_fit" in FEATURE_NAMES
    assert "group_consensus_fit" in FEATURE_NAMES
    assert "group_min_fit_weight" in FEATURE_NAMES
    assert "group_consensus_gap_inverse" in FEATURE_NAMES
    assert "objective_penalty_inverse" in FEATURE_NAMES
    assert features["group_average_fit"] == 0.86
    assert features["group_consensus_fit"] == 0.85
    assert features["group_min_fit_weight"] == 0.26
    assert features["group_consensus_gap_inverse"] == pytest.approx(0.99)
    assert features["exploration_uncertainty"] == 0.25
    assert features["preference_confidence"] == 0.75
    assert features["profile_signal_density"] == 0.75
    assert features["covered_intents_density"] == 0.5
    assert features["served_members_density"] == pytest.approx(0.3333333333333333)
    assert features["friend_adjusted_retrieval"] == 1.0
    assert features["objective_positive_total"] == 0.88
    assert features["objective_penalty_inverse"] == 0.92
    assert features["local_event_fit"] == 0.82
    assert features["local_event_backed"] == 1.0
    assert features["local_event_proximity"] == 0.872
    assert features["local_event_reservation_ready"] == 1.0
    assert features["local_event_source_ready"] == 1.0
    assert features["local_event_route_anchor_score"] == 0.76
    assert features["local_event_friend_signal_density"] == 1.0
    assert features["local_event_social_signal"] == 0.6
    assert features["local_event_actionability"] == pytest.approx(0.87)
    assert features["session_context_fit"] == 0.55
    assert features["session_momentum"] == 0.55
    assert features["session_mismatch_inverse"] == 1.0
    assert features["friend_history_fit"] == 0.4
    assert features["friend_history_positive"] == 0.4
    assert features["friend_history_conflict_inverse"] == 1.0


def test_learning_to_rank_baseline_can_rerank_request_examples():
    service = LearningToRankBaselineService()
    examples = training_examples()
    model = service.train(examples, iterations=250, validation_fraction=0)

    reranked = service.rerank_examples([
        {**examples[1], "request_id": "rerank", "rank_position": 1},
        {**examples[0], "request_id": "rerank", "rank_position": 2},
    ], model)
    by_place_score = sorted(reranked, key=lambda row: row["learned_rank_position"])

    assert by_place_score[0]["label"] == 1.0
    assert by_place_score[0]["learned_score"] > by_place_score[1]["learned_score"]


def test_learning_to_rank_baseline_model_artifact_round_trips(tmp_path):
    service = LearningToRankBaselineService()
    model = service.train(training_examples(), iterations=50, validation_fraction=0)
    path = tmp_path / "learned-ranker.json"

    service.write_model(path, model)
    loaded = service.load_model(path)

    assert loaded["feature_names"] == model["feature_names"]
    assert loaded["feature_schema_version"] == model["feature_schema_version"]
    assert loaded["weights"] == model["weights"]


def test_training_data_health_reports_friend_event_coverage():
    health = summarize_training_data_health(training_examples())
    checks = {check["name"]: check for check in health["checks"]}

    assert health["counts"]["labeled"] == len(training_examples())
    assert health["counts"]["event_backed"] == 1
    assert health["counts"]["event_friend_signal"] == 1
    assert checks["positive_negative_mix"]["status"] == "pass"
    assert checks["event_anchor_signal"]["status"] == "pass"
    assert checks["event_social_signal"]["status"] == "pass"
    assert health["status"] in {"watch", "needs_data"}


def test_training_data_health_flags_sparse_social_event_data():
    sparse = [
        {
            "request_id": "solo",
            "rank_position": 1,
            "label": 1.0,
            "local_event_backed": False,
        },
        {
            "request_id": "solo",
            "rank_position": 2,
            "label": 0.0,
        },
    ]

    health = summarize_training_data_health(sparse)
    checks = {check["name"]: check for check in health["checks"]}

    assert health["status"] == "needs_data"
    assert checks["labeled_outcomes"]["status"] == "fail"
    assert checks["group_friend_signal"]["status"] == "fail"
    assert checks["event_social_signal"]["status"] == "fail"


def test_model_feature_compatibility_blocks_stale_artifacts():
    current_model = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
    }
    stale_model = {
        "feature_schema_version": "phase1_legacy",
        "feature_names": [
            name for name in FEATURE_NAMES
            if name != "friend_adjusted_retrieval"
        ],
    }

    assert model_feature_compatibility(current_model)["status"] == "pass"

    compatibility = model_feature_compatibility(stale_model)

    assert compatibility["status"] == "fail"
    assert compatibility["reason"] == "feature_schema_mismatch"
    assert "friend_adjusted_retrieval" in compatibility["missing_features"]
    assert compatibility["expected_feature_schema_version"] == FEATURE_SCHEMA_VERSION


def test_learned_ranker_artifact_status_requires_promotion_gate():
    model = {
        "model_type": "adventour_logistic_ltr_baseline",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "training_data_health": ready_training_data_health(),
    }

    status = learned_ranker_artifact_status(model)

    assert status["ready"] is False
    assert status["status"] == "needs_evaluation"
    assert status["reason"] == "promotion_gate_missing"
    assert status["feature_compatibility"]["status"] == "pass"
    assert status["training_data_health"]["status"] == "ready"

    model["promotion_gate"] = {
        "status": "pass",
        "can_promote": True,
        "summary": "Ready for live beta.",
        "checks": [],
    }

    status = learned_ranker_artifact_status(model)

    assert status["ready"] is True
    assert status["status"] == "ready"
    assert status["reason"] == "promotion_gate_passed"
    assert status["training_data_health"]["counts"]["labeled"] == 60


def test_learned_ranker_artifact_status_blocks_thin_training_data():
    model = {
        "model_type": "adventour_logistic_ltr_baseline",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "promotion_gate": {
            "status": "pass",
            "can_promote": True,
            "summary": "Ready for live beta.",
            "checks": [],
        },
        "training_data_health": summarize_training_data_health(training_examples()),
    }

    status = learned_ranker_artifact_status(model)

    assert status["ready"] is False
    assert status["status"] == "blocked"
    assert status["reason"] == "training_data_needs_data"
    assert status["training_data_health"]["status"] == "needs_data"
    assert status["training_data_health"]["counts"]["event_friend_signal"] == 1
    assert status["training_data_health"]["blocking_checks"]


def test_learned_ranker_artifact_status_marks_missing_training_health_unknown():
    model = {
        "model_type": "adventour_logistic_ltr_baseline",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
    }

    status = learned_ranker_artifact_status(model)

    assert status["ready"] is False
    assert status["reason"] == "training_data_unknown"
    assert status["training_data_health"]["status"] == "unknown"
    assert "Refresh the learned ranker" in status["training_data_health"]["summary"]


def test_refresh_model_writes_promotion_gate_into_model_artifact(monkeypatch, tmp_path):
    def fake_build_examples(self, limit=None, since=None):
        return training_examples()

    monkeypatch.setattr(
        "recommender_refresh_model.RecommendationTrainingExportService.build_examples",
        fake_build_examples,
    )

    summary = refresh_model(SimpleNamespace(
        db_uri="sqlite:///:memory:",
        artifact_dir=str(tmp_path),
        limit=None,
        since=None,
        min_labeled=1,
        iterations=50,
        learning_rate=0.08,
        l2=0.01,
        validation_fraction=0,
        positive_threshold=0.75,
        k_values=(1, 3),
    ))
    model_path = tmp_path / "recommender-model.latest.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))

    assert summary["model_path"] == str(model_path)
    assert model["promotion_gate"]["status"] in {"pass", "fail", "insufficient_data"}
    assert model["live_readiness"]["reason"] in {
        "promotion_gate_passed",
        "promotion_gate_fail",
        "promotion_gate_insufficient_data",
        "training_data_needs_data",
    }
    assert summary["live_readiness"] == model["live_readiness"]
    assert summary["training_data_health"] == model["training_data_health"]
    assert model["training_data_health"]["counts"]["event_friend_signal"] == 1
    assert any(
        check["name"] == "ranking_improved"
        for check in model["promotion_gate"]["checks"]
    )
    assert "promotion_evaluation" in model
