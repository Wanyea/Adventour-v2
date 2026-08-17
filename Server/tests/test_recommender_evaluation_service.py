import json

import pytest

from adventour_backend.services.recommender_model_service import FEATURE_NAMES
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService


def test_evaluation_groups_examples_by_request_and_rank():
    examples = [
        {"request_id": "a", "rank_position": 1, "label": 1.0},
        {"request_id": "a", "rank_position": 2, "label": 0.0},
        {"request_id": "b", "rank_position": 1, "label": 0.0},
        {"request_id": "b", "rank_position": 2, "label": 0.5},
        {"request_id": "b", "rank_position": 3, "label": 1.0},
        {"request_id": "c", "rank_position": 1, "label": 0.0},
        {"request_id": "c", "rank_position": 2, "label": 0.0},
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples, k_values=(1, 3))
    overall = evaluation["overall"]

    assert overall["request_count"] == 3
    assert overall["positive_request_count"] == 2
    assert overall["labeled_example_count"] == 7
    assert overall["grouped_example_count"] == 7
    assert overall["mean_reciprocal_rank"] == pytest.approx(0.4444)
    assert overall["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(0.3333)
    assert overall["metrics_at_k"]["3"]["hit_rate"] == pytest.approx(0.6667)
    assert overall["metrics_at_k"]["3"]["precision"] == pytest.approx(0.2778)
    assert overall["metrics_at_k"]["3"]["weighted_average_label"] == pytest.approx(0.3333)
    assert overall["metrics_at_k"]["3"]["ndcg"] == pytest.approx(0.54)


def test_evaluation_reports_weighted_average_label_when_examples_have_outcome_weights():
    examples = [
        {"request_id": "a", "rank_position": 1, "label": 1.0, "outcome_weight": 1.0},
        {"request_id": "a", "rank_position": 2, "label": 0.0, "outcome_weight": 0.25},
        {"request_id": "b", "rank_position": 1, "label": 0.0, "outcome_weight": 1.0},
        {"request_id": "b", "rank_position": 2, "label": 1.0, "outcome_weight": 0.5},
    ]

    overall = RecommendationEvaluationService().evaluate_examples(examples, k_values=(2,))["overall"]

    assert overall["metrics_at_k"]["2"]["average_label"] == pytest.approx(0.5)
    assert overall["metrics_at_k"]["2"]["weighted_average_label"] == pytest.approx(0.5666)


def test_evaluation_can_compare_shown_order_to_learned_model_rerank():
    examples = [
        {
            "request_id": "rerank-a",
            "rank_position": 1,
            "label": 0.0,
            "authenticity_score": 0.1,
            "hidden_gem_score": 0.0,
            "chain_probability": 0.95,
        },
        {
            "request_id": "rerank-a",
            "rank_position": 2,
            "label": 1.0,
            "authenticity_score": 0.9,
            "hidden_gem_score": 0.8,
            "chain_probability": 0.0,
        },
        {
            "request_id": "rerank-b",
            "rank_position": 1,
            "label": 0.0,
            "authenticity_score": 0.2,
            "hidden_gem_score": 0.1,
            "chain_probability": 0.9,
        },
        {
            "request_id": "rerank-b",
            "rank_position": 2,
            "label": 1.0,
            "authenticity_score": 0.85,
            "hidden_gem_score": 0.7,
            "chain_probability": 0.0,
        },
    ]
    model = {
        "feature_names": FEATURE_NAMES,
        "intercept": 0.0,
        "weights": {
            "authenticity_score": 2.5,
            "hidden_gem_score": 1.0,
            "chain_inverse": 1.5,
        },
        "feature_stats": {
            name: {"mean": 0.0, "std": 1.0}
            for name in FEATURE_NAMES
        },
    }

    comparison = RecommendationEvaluationService().compare_with_learned_model(
        examples,
        model,
        k_values=(1, 2),
    )

    assert comparison["baseline"]["overall"]["mean_reciprocal_rank"] == pytest.approx(0.5)
    assert comparison["learned"]["overall"]["mean_reciprocal_rank"] == pytest.approx(1.0)
    assert comparison["delta"]["mean_reciprocal_rank"] == pytest.approx(0.5)
    assert comparison["delta"]["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(1.0)
    assert comparison["learned"]["requests"][0]["first_positive_rank"] == 1
    assert comparison["promotion_gate"]["status"] == "insufficient_data"


def _identity_stats_model(weights):
    return {
        "feature_names": FEATURE_NAMES,
        "intercept": 0.0,
        "weights": weights,
        "feature_stats": {
            name: {"mean": 0.0, "std": 1.0}
            for name in FEATURE_NAMES
        },
    }


def _local_vs_generic_examples(count=20):
    examples = []
    for index in range(count):
        request_id = f"safe-promotion-{index}"
        examples.extend([
            {
                "request_id": request_id,
                "rank_position": 1,
                "label": 0.0,
                "authenticity_score": 0.2,
                "hidden_gem_score": 0.1,
                "chain_probability": 0.85,
            },
            {
                "request_id": request_id,
                "rank_position": 2,
                "label": 1.0,
                "authenticity_score": 0.88,
                "hidden_gem_score": 0.72,
                "chain_probability": 0.02,
            },
        ])
    return examples


def test_evaluation_promotion_gate_passes_safe_learned_model_with_enough_data():
    model = _identity_stats_model({
        "authenticity_score": 3.0,
        "hidden_gem_score": 1.5,
        "chain_inverse": 2.0,
    })

    comparison = RecommendationEvaluationService().compare_with_learned_model(
        _local_vs_generic_examples(),
        model,
        k_values=(1, 3),
    )

    gate = comparison["promotion_gate"]
    assert gate["status"] == "pass"
    assert gate["can_promote"] is True
    assert comparison["delta"]["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(1.0)
    assert comparison["delta"]["exposure_quality_at_k"]["1"]["local_quality_score"] > 0
    assert {check["status"] for check in gate["checks"]} == {"pass"}


def test_evaluation_promotion_gate_blocks_chain_heavy_learned_model():
    examples = []
    for index in range(20):
        request_id = f"unsafe-promotion-{index}"
        examples.extend([
            {
                "request_id": request_id,
                "rank_position": 1,
                "label": 0.0,
                "authenticity_score": 0.85,
                "hidden_gem_score": 0.7,
                "chain_probability": 0.02,
            },
            {
                "request_id": request_id,
                "rank_position": 2,
                "label": 1.0,
                "authenticity_score": 0.15,
                "hidden_gem_score": 0.05,
                "chain_probability": 0.95,
            },
        ])
    model = _identity_stats_model({
        "authenticity_score": -3.0,
        "hidden_gem_score": -1.5,
        "chain_inverse": -2.0,
    })

    comparison = RecommendationEvaluationService().compare_with_learned_model(
        examples,
        model,
        k_values=(1, 3),
    )

    gate = comparison["promotion_gate"]
    checks = {check["name"]: check for check in gate["checks"]}
    assert gate["status"] == "fail"
    assert gate["can_promote"] is False
    assert comparison["delta"]["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(1.0)
    assert comparison["delta"]["exposure_quality_at_k"]["1"]["local_quality_score"] < 0
    assert checks["local_quality_safe"]["status"] == "fail"
    assert checks["guardrails_safe"]["status"] == "fail"


def test_evaluation_promotion_gate_blocks_group_consensus_regression():
    service = RecommendationEvaluationService()
    baseline = {
        "request_count": 20,
        "guardrails": {"status": "pass"},
        "group_balance": {
            "group_positive_count": 20,
            "average_lowest_member_fit": 0.78,
            "average_group_consensus_fit": 0.9,
            "average_group_consensus_gap": 0.0,
            "average_group_fairness_penalty": 0.02,
            "underserved_positive_rate": 0.0,
        },
    }
    learned = {
        "request_count": 20,
        "guardrails": {"status": "pass"},
        "group_balance": {
            "group_positive_count": 20,
            "average_lowest_member_fit": 0.76,
            "average_group_consensus_fit": 0.84,
            "average_group_consensus_gap": 0.052,
            "average_group_fairness_penalty": 0.03,
            "underserved_positive_rate": 0.0,
        },
    }
    delta = {
        "mean_reciprocal_rank": 0.1,
        "metrics_at_k": {"1": {"ndcg": 0.1, "weighted_average_label": 0.1}},
        "outcome_quality": {
            "local_quality_score": 0.0,
            "average_positive_authenticity": 0.0,
            "average_positive_chain_probability": 0.0,
        },
        "exposure_quality_at_k": {
            "1": {
                "local_quality_score": 0.0,
                "average_authenticity": 0.0,
                "average_chain_probability": 0.0,
            },
        },
        "group_balance": service._summary_delta(
            baseline["group_balance"],
            learned["group_balance"],
            (
                "average_lowest_member_fit",
                "average_group_consensus_fit",
                "average_group_consensus_gap",
                "average_group_fairness_penalty",
                "underserved_positive_rate",
            ),
        ),
    }

    gate = service._promotion_gate(baseline, learned, delta)
    checks = {check["name"]: check for check in gate["checks"]}

    assert gate["status"] == "fail"
    assert gate["can_promote"] is False
    assert checks["ranking_improved"]["status"] == "pass"
    assert checks["local_quality_safe"]["status"] == "pass"
    assert checks["guardrails_safe"]["status"] == "pass"
    assert checks["group_balance_safe"]["status"] == "fail"
    assert "consensus -0.0600" in checks["group_balance_safe"]["value"]
    assert "gap +0.0520" in checks["group_balance_safe"]["value"]


def test_evaluation_promotion_gate_blocks_critical_event_segment_regression():
    examples = []
    for index in range(20):
        request_id = f"normal-improves-{index}"
        examples.extend([
            {
                "request_id": request_id,
                "rank_position": 1,
                "label": 0.0,
                "authenticity_score": 0.15,
                "hidden_gem_score": 0.05,
                "chain_probability": 0.25,
            },
            {
                "request_id": request_id,
                "rank_position": 2,
                "label": 1.0,
                "authenticity_score": 0.9,
                "hidden_gem_score": 0.7,
                "chain_probability": 0.02,
            },
        ])

    for index in range(5):
        request_id = f"event-regresses-{index}"
        examples.extend([
            {
                "request_id": request_id,
                "rank_position": 1,
                "label": 1.0,
                "authenticity_score": 0.55,
                "hidden_gem_score": 0.3,
                "chain_probability": 0.02,
                "local_event_backed": True,
                "local_event_fit": 0.9,
            },
            {
                "request_id": request_id,
                "rank_position": 2,
                "label": 0.0,
                "authenticity_score": 0.98,
                "hidden_gem_score": 0.8,
                "chain_probability": 0.02,
                "local_event_backed": False,
                "local_event_fit": 0.0,
            },
        ])

    comparison = RecommendationEvaluationService().compare_with_learned_model(
        examples,
        _identity_stats_model({"authenticity_score": 4.0}),
        k_values=(1, 3),
    )

    gate = comparison["promotion_gate"]
    checks = {check["name"]: check for check in gate["checks"]}
    assert comparison["delta"]["mean_reciprocal_rank"] > 0
    assert comparison["segment_delta"]["event_backed"]["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(-1.0)
    assert gate["status"] == "fail"
    assert gate["can_promote"] is False
    assert checks["critical_segments_safe"]["status"] == "fail"
    assert "event_backed" in checks["critical_segments_safe"]["value"]


def test_evaluation_summarizes_metrics_by_scoring_profile():
    examples = [
        {"request_id": "balanced-good", "rank_position": 1, "label": 1.0, "scoring_profile": "phase1_balanced"},
        {"request_id": "balanced-good", "rank_position": 2, "label": 0.0, "scoring_profile": "phase1_balanced"},
        {"request_id": "taste-late", "rank_position": 1, "label": 0.0, "scoring_profile": "taste_forward"},
        {"request_id": "taste-late", "rank_position": 2, "label": 1.0, "scoring_profile": "taste_forward"},
        {"request_id": "missing-profile", "rank_position": 1, "label": 1.0},
    ]

    by_profile = RecommendationEvaluationService().evaluate_examples(
        examples,
        k_values=(1, 2),
    )["by_scoring_profile"]

    assert by_profile["phase1_balanced"]["request_count"] == 1
    assert by_profile["phase1_balanced"]["metrics_at_k"]["1"]["hit_rate"] == 1.0
    assert by_profile["taste_forward"]["request_count"] == 1
    assert by_profile["taste_forward"]["metrics_at_k"]["1"]["hit_rate"] == 0.0
    assert by_profile["taste_forward"]["metrics_at_k"]["2"]["hit_rate"] == 1.0
    assert by_profile["unknown"]["request_count"] == 1


def test_evaluation_summarizes_metrics_by_recommendation_segment():
    examples = [
        {
            "request_id": "group-friend-adjusted",
            "rank_position": 1,
            "label": 1.0,
            "context": "group",
            "member_fit_count": 2,
            "lowest_member_fit": 0.72,
            "highest_member_fit": 0.88,
            "authenticity_score": 0.86,
            "hidden_gem_score": 0.62,
            "chain_probability": 0.02,
            "friend_adjusted_retrieval": True,
            "boost_query_tags": ["arts_culture"],
            "local_event_backed": True,
            "local_event_fit": 0.82,
        },
        {
            "request_id": "group-friend-adjusted",
            "rank_position": 2,
            "label": 0.0,
            "context": "group",
            "member_fit_count": 2,
            "chain_probability": 0.1,
        },
        {
            "request_id": "generic-low-signal",
            "rank_position": 1,
            "label": 0.0,
            "authenticity_score": 0.2,
            "hidden_gem_score": 0.05,
            "chain_probability": 0.92,
            "preference_confidence": 0.18,
            "average_member_signal_count": 1,
        },
        {
            "request_id": "generic-low-signal",
            "rank_position": 2,
            "label": 1.0,
            "authenticity_score": 0.78,
            "hidden_gem_score": 0.5,
            "chain_probability": 0.02,
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples, k_values=(1, 2))
    by_segment = evaluation["by_segment"]
    request_segments = {
        item["request_id"]: item["segments"]
        for item in evaluation["requests"]
    }

    assert {"group", "friend_adjusted", "local_authentic", "hidden_gem", "event_backed"}.issubset(
        set(request_segments["group-friend-adjusted"])
    )
    assert {"solo", "generic_risk", "low_signal", "local_authentic"}.issubset(
        set(request_segments["generic-low-signal"])
    )
    assert by_segment["friend_adjusted"]["request_count"] == 1
    assert by_segment["event_backed"]["request_count"] == 1
    assert by_segment["event_backed"]["metrics_at_k"]["1"]["hit_rate"] == 1.0
    assert by_segment["friend_adjusted"]["metrics_at_k"]["1"]["hit_rate"] == 1.0
    assert by_segment["generic_risk"]["metrics_at_k"]["1"]["hit_rate"] == 0.0
    assert by_segment["low_signal"]["metrics_at_k"]["2"]["hit_rate"] == 1.0


def test_learned_model_comparison_reports_segment_deltas():
    examples = _local_vs_generic_examples(count=20)
    model = _identity_stats_model({
        "authenticity_score": 3.0,
        "hidden_gem_score": 1.5,
        "chain_inverse": 2.0,
    })

    comparison = RecommendationEvaluationService().compare_with_learned_model(
        examples,
        model,
        k_values=(1, 2),
    )

    segment_delta = comparison["segment_delta"]
    assert "local_authentic" in segment_delta
    assert segment_delta["local_authentic"]["metrics_at_k"]["1"]["hit_rate"] == pytest.approx(1.0)


def test_evaluation_reports_positive_outcome_quality():
    examples = [
        {
            "request_id": "local-good",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "authenticity_forward",
            "authenticity_score": 0.9,
            "hidden_gem_score": 0.8,
            "chain_probability": 0.0,
        },
        {
            "request_id": "chain-ok",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "phase1_balanced",
            "authenticity_score": 0.3,
            "hidden_gem_score": 0.1,
            "chain_probability": 1.0,
        },
        {
            "request_id": "negative-local",
            "rank_position": 1,
            "label": 0.0,
            "scoring_profile": "authenticity_forward",
            "authenticity_score": 1.0,
            "hidden_gem_score": 1.0,
            "chain_probability": 0.0,
        },
        {
            "request_id": "old-export",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "phase1_balanced",
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples)
    quality = evaluation["overall"]["outcome_quality"]

    assert quality["positive_quality_count"] == 2
    assert quality["authenticity_count"] == 2
    assert quality["hidden_gem_count"] == 2
    assert quality["chain_probability_count"] == 2
    assert quality["local_quality_count"] == 2
    assert quality["average_positive_authenticity"] == pytest.approx(0.6)
    assert quality["average_positive_hidden_gem"] == pytest.approx(0.45)
    assert quality["average_positive_chain_probability"] == pytest.approx(0.5)
    assert quality["local_quality_score"] == pytest.approx(0.5167)

    by_profile = evaluation["by_scoring_profile"]
    assert by_profile["authenticity_forward"]["outcome_quality"]["local_quality_score"] == pytest.approx(0.9)
    assert by_profile["phase1_balanced"]["outcome_quality"]["local_quality_score"] == pytest.approx(0.1333)


def test_evaluation_guardrails_flag_chain_heavy_positive_outcomes():
    examples = [
        {
            "request_id": "chain-heavy",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "phase1_balanced",
            "authenticity_score": 0.25,
            "hidden_gem_score": 0.05,
            "chain_probability": 0.95,
        },
        {
            "request_id": "chain-heavy",
            "rank_position": 2,
            "label": 0.0,
            "scoring_profile": "phase1_balanced",
            "authenticity_score": 0.95,
            "hidden_gem_score": 0.9,
            "chain_probability": 0.0,
        },
    ]

    guardrails = RecommendationEvaluationService().evaluate_examples(examples)["overall"]["guardrails"]
    checks = {check["name"]: check for check in guardrails["checks"]}

    assert guardrails["status"] == "fail"
    assert checks["chain_probability"]["status"] == "fail"
    assert checks["authenticity"]["status"] == "fail"
    assert checks["hidden_gem"]["status"] == "fail"


def test_evaluation_guardrails_report_group_fit_risk():
    examples = [
        {
            "request_id": "group-weak",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "group_friendly",
            "authenticity_score": 0.85,
            "hidden_gem_score": 0.55,
            "chain_probability": 0.0,
            "group_min_fit": 0.32,
            "group_fairness_penalty": 0.42,
        },
        {
            "request_id": "group-strong-rejected",
            "rank_position": 1,
            "label": 0.0,
            "scoring_profile": "group_friendly",
            "authenticity_score": 0.8,
            "hidden_gem_score": 0.55,
            "chain_probability": 0.0,
            "group_min_fit": 0.82,
            "group_fairness_penalty": 0.0,
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples)
    quality = evaluation["overall"]["outcome_quality"]
    checks = {check["name"]: check for check in evaluation["overall"]["guardrails"]["checks"]}

    assert quality["average_positive_group_min_fit"] == pytest.approx(0.32)
    assert quality["average_positive_group_fairness_penalty"] == pytest.approx(0.42)
    assert checks["group_min_fit"]["status"] == "fail"
    assert checks["group_fairness_penalty"]["status"] == "fail"


def test_evaluation_reports_group_balance_across_positive_outcomes():
    examples = [
        {
            "request_id": "group-balanced",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "group_friendly",
            "group_min_fit": 0.72,
            "group_average_fit": 0.79,
            "group_consensus_fit": 0.78,
            "group_min_fit_weight": 0.14,
            "group_fairness_penalty": 0.04,
            "member_fit_count": 2,
            "lowest_member_fit": 0.72,
            "highest_member_fit": 0.86,
            "member_fit_spread": 0.14,
        },
        {
            "request_id": "group-underserved",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "group_friendly",
            "group_min_fit": 0.44,
            "group_average_fit": 0.675,
            "group_consensus_fit": 0.51,
            "group_min_fit_weight": 0.7,
            "group_fairness_penalty": 0.28,
            "member_fit": [
                {"user_id": 1, "fit": 0.44},
                {"user_id": 2, "fit": 0.91},
            ],
        },
        {
            "request_id": "solo-positive",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "authenticity_forward",
            "group_min_fit": None,
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples)
    balance = evaluation["overall"]["group_balance"]
    checks = {check["name"]: check for check in evaluation["overall"]["guardrails"]["checks"]}

    assert balance["group_positive_count"] == 2
    assert balance["member_fit_count"] == 2
    assert balance["average_lowest_member_fit"] == pytest.approx(0.58)
    assert balance["group_consensus_fit_count"] == 2
    assert balance["group_consensus_gap_count"] == 2
    assert balance["average_group_consensus_fit"] == pytest.approx(0.645)
    assert balance["average_group_consensus_gap"] == pytest.approx(0.0875)
    assert balance["average_member_fit_spread"] == pytest.approx(0.305)
    assert balance["average_group_fairness_penalty"] == pytest.approx(0.16)
    assert balance["underserved_positive_count"] == 1
    assert balance["underserved_positive_rate"] == pytest.approx(0.5)
    assert checks["group_underserved_rate"]["status"] == "warn"
    assert checks["group_consensus_gap"]["status"] == "warn"


def test_evaluation_reports_event_anchor_quality_across_positive_outcomes():
    examples = [
        {
            "request_id": "event-backed-accepted",
            "rank_position": 1,
            "label": 1.0,
            "authenticity_score": 0.86,
            "hidden_gem_score": 0.48,
            "chain_probability": 0.02,
            "local_event_backed": True,
            "local_event_fit": 0.8,
            "route_anchor_score": 0.9,
            "local_event_reservation_ready": True,
            "local_event_source_ready": True,
            "local_event_friend_signal_count": 2,
            "local_event_social_signal": 0.6,
        },
        {
            "request_id": "local-no-event-accepted",
            "rank_position": 1,
            "label": 1.0,
            "authenticity_score": 0.82,
            "hidden_gem_score": 0.4,
            "chain_probability": 0.04,
        },
        {
            "request_id": "event-backed-rejected",
            "rank_position": 1,
            "label": 0.0,
            "local_event_backed": True,
            "local_event_fit": 0.95,
            "local_event_reservation_ready": True,
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples)
    quality = evaluation["overall"]["event_anchor_quality"]
    event_segment = evaluation["by_segment"]["event_backed"]["event_anchor_quality"]

    assert quality["positive_count"] == 2
    assert quality["event_backed_positive_count"] == 1
    assert quality["event_backed_positive_rate"] == pytest.approx(0.5)
    assert quality["average_positive_event_fit"] == pytest.approx(0.8)
    assert quality["average_positive_route_anchor_score"] == pytest.approx(0.9)
    assert quality["event_anchor_score"] == pytest.approx(0.868)
    assert quality["reservation_ready_rate"] == pytest.approx(1.0)
    assert quality["source_ready_rate"] == pytest.approx(1.0)
    assert quality["friend_signal_positive_rate"] == pytest.approx(1.0)
    assert quality["average_positive_social_signal"] == pytest.approx(0.6)
    assert event_segment["event_backed_positive_count"] == 1
    assert event_segment["event_anchor_score"] == pytest.approx(0.868)


def test_evaluation_guardrails_flag_weak_event_anchor_outcomes():
    examples = [
        {
            "request_id": "weak-event-anchor",
            "rank_position": 1,
            "label": 1.0,
            "authenticity_score": 0.84,
            "hidden_gem_score": 0.46,
            "chain_probability": 0.02,
            "local_event_backed": True,
            "local_event_fit": 0.3,
            "local_event_reservation_ready": False,
            "local_event_source_ready": True,
        },
    ]

    evaluation = RecommendationEvaluationService().evaluate_examples(examples)
    checks = {check["name"]: check for check in evaluation["overall"]["guardrails"]["checks"]}

    assert evaluation["overall"]["guardrails"]["status"] == "fail"
    assert checks["event_anchor_score"]["status"] == "fail"
    assert checks["event_reservation_ready_rate"]["status"] == "fail"


def test_evaluation_guardrails_pass_for_authentic_group_positive_outcomes():
    examples = [
        {
            "request_id": "local-group-good",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "group_friendly",
            "authenticity_score": 0.82,
            "hidden_gem_score": 0.45,
            "chain_probability": 0.05,
            "group_min_fit": 0.76,
            "group_fairness_penalty": 0.04,
        },
        {
            "request_id": "local-solo-good",
            "rank_position": 1,
            "label": 1.0,
            "scoring_profile": "authenticity_forward",
            "authenticity_score": 0.9,
            "hidden_gem_score": 0.35,
            "chain_probability": 0.0,
        },
    ]

    guardrails = RecommendationEvaluationService().evaluate_examples(examples)["overall"]["guardrails"]
    balance = RecommendationEvaluationService().evaluate_examples(examples)["overall"]["group_balance"]
    known_statuses = [
        check["status"]
        for check in guardrails["checks"]
        if check["status"] != "unknown"
    ]

    assert balance["group_positive_count"] == 1
    assert balance["underserved_positive_rate"] == 0.0
    assert guardrails["status"] == "pass"
    assert set(known_statuses) == {"pass"}


def test_evaluation_reports_examples_that_cannot_be_grouped():
    examples = [
        {"request_id": "a", "rank_position": 1, "label": 1.0},
        {"request_id": None, "rank_position": 2, "label": 0.0},
        {"request_id": "b", "rank_position": None, "label": 1.0},
        {"request_id": "c", "label": None},
    ]

    overall = RecommendationEvaluationService().evaluate_examples(examples)["overall"]

    assert overall["request_count"] == 1
    assert overall["labeled_example_count"] == 3
    assert overall["grouped_example_count"] == 1
    assert overall["skipped_without_request"] == 1
    assert overall["skipped_without_rank"] == 1


def test_evaluation_loads_jsonl_export(tmp_path):
    path = tmp_path / "training.jsonl"
    path.write_text(
        "\n".join([
            json.dumps({"request_id": "jsonl", "rank_position": 1, "label": 1.0}),
            json.dumps({"request_id": "jsonl", "rank_position": 2, "label": 0.0}),
        ]),
        encoding="utf-8",
    )

    examples = RecommendationEvaluationService().load_jsonl(path)

    assert len(examples) == 2
    assert examples[0]["request_id"] == "jsonl"


def _readiness_place(name, types, label="Local-feeling"):
    return {
        "name": name,
        "display": {"types": types},
        "authenticity_evidence": {"label": label},
        "recommendation_story": {
            "headline": f"Why {name} fits.",
            "reasons": ["Matches the selected traveler taste."],
            "metrics": [{"id": "authenticity", "value": "local"}],
        },
    }


def test_scenario_readiness_report_marks_strong_basket_ready_for_friend_testing():
    result = {
        "member_count": 2,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Art Yard", ["art_gallery"]),
            _readiness_place("Park Market", ["park", "market"]),
            _readiness_place("Jazz Room", ["bar", "concert_hall"]),
            _readiness_place("Corner Bakery", ["bakery"]),
            _readiness_place("Small Museum", ["museum"]),
            _readiness_place("Garden Walk", ["garden"]),
            _readiness_place("Book Nook", ["book_store"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
                "average_group_fit": 0.81,
                "local_event_backed_count": 1,
                "local_event_social_score": 0.6,
                "local_event_friend_signal_count": 1,
                "local_event_reservation_ready_count": 1,
            },
            "strengths": ["Strong local-feeling mix in this basket."],
            "warnings": [],
        },
        "slate_summary": {
            "metrics": {
                "diversity_coverage": 1.0,
                "missing_intent_count": 0,
                "member_coverage_share": 1.0,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["mode"] == "basket"
    assert report["status"] == "ready"
    assert report["ready_for_friend_testing"] is True
    assert report["beta_testable"] is True
    assert checks["local_authentic_mix"]["status"] == "pass"
    assert checks["group_fit"]["status"] == "pass"
    assert checks["variety"]["status"] == "pass"
    assert checks["intent_coverage"]["status"] == "pass"
    assert checks["event_social_anchor"]["status"] == "pass"
    assert checks["friend_coverage"]["status"] == "pass"
    assert checks["explanation_coverage"]["value"] == pytest.approx(1.0)
    assert report["metrics"]["event_actionable_score"] == pytest.approx(0.8667)
    assert report["test_verdict"]["dimensions"][5]["name"] == "events"
    assert report["test_verdict"]["dimensions"][5]["status"] == "pass"
    assert report["friend_readiness"]["status"] == "ready"
    assert report["friend_readiness"]["covered_member_count"] == 2
    assert report["friend_readiness"]["underserved_count"] == 0


def test_scenario_readiness_report_marks_cold_start_friend_coverage_as_watch():
    result = {
        "member_count": 2,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Art Yard", ["art_gallery"]),
            _readiness_place("Park Market", ["park", "market"]),
            _readiness_place("Jazz Room", ["bar", "concert_hall"]),
            _readiness_place("Corner Bakery", ["bakery"]),
            _readiness_place("Small Museum", ["museum"]),
            _readiness_place("Garden Walk", ["garden"]),
            _readiness_place("Book Nook", ["book_store"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
                "average_group_fit": 0.81,
                "local_event_backed_count": 1,
                "local_event_social_score": 0.6,
                "local_event_friend_signal_count": 1,
                "local_event_reservation_ready_count": 1,
            },
            "strengths": ["Strong local-feeling mix in this basket."],
            "warnings": [],
        },
        "group_fit_summary": {
            "members": [
                {
                    "user_id": 1,
                    "display_name": "Owner",
                    "average_fit": 0.82,
                    "matched_count": 2,
                    "learning_status": "cold_start",
                    "signal_count": 0,
                    "confidence": 0.0,
                },
                {
                    "user_id": 2,
                    "display_name": "Friend",
                    "average_fit": 0.8,
                    "matched_count": 2,
                    "learning_status": "cold_start",
                    "signal_count": 1,
                    "confidence": 0.083,
                },
            ],
        },
        "slate_summary": {
            "metrics": {
                "diversity_coverage": 1.0,
                "missing_intent_count": 0,
                "member_coverage_share": 1.0,
            },
            "member_coverage": [
                {
                    "user_id": 1,
                    "display_name": "Owner",
                    "strong_match_count": 2,
                    "best_fit": 0.82,
                    "best_match": {"name": "Hidden Cafe", "fit": 0.82},
                },
                {
                    "user_id": 2,
                    "display_name": "Friend",
                    "strong_match_count": 2,
                    "best_fit": 0.8,
                    "best_match": {"name": "Art Yard", "fit": 0.8},
                },
            ],
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)

    assert report["status"] == "watch"
    assert report["ready_for_friend_testing"] is False
    assert report["beta_testable"] is True
    assert report["friend_readiness"]["status"] == "watch"
    assert report["friend_readiness"]["cold_start_member_count"] == 2
    assert report["friend_readiness"]["members"][1]["learning_status"] == "cold_start"
    assert report["friend_readiness"]["members"][1]["signal_count"] == 1
    assert "still learning this party" in report["friend_readiness"]["headline"]
    assert "swipe or rate a few picks" in report["friend_readiness"]["next_actions"][0]
    assert report["test_verdict"]["status"] == "watch"
    assert report["test_verdict"]["friend_testable"] is False
    assert any(item["id"] == "friend_coverage" for item in report["remediation_plan"])


def test_scenario_readiness_report_flags_weak_generic_basket():
    result = {
        "member_count": 1,
        "provider_errors": [{"provider": "google", "message": "quota"}],
        "recommendations": [
            _readiness_place("Big Chain Coffee", ["cafe"], label="Generic risk"),
            {"name": "Unexplained Chain", "display": {"types": ["restaurant"]}},
            _readiness_place("Generic Store", ["shopping_mall"], label="Generic risk"),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 3,
                "local_feeling_share": 0.0,
                "hidden_gem_count": 0,
                "generic_risk_share": 0.75,
            },
            "strengths": [],
            "warnings": ["Generic or chain-like risk is higher than ideal."],
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "needs_attention"
    assert report["ready_for_friend_testing"] is False
    assert checks["provider_health"]["status"] == "fail"
    assert checks["generic_risk"]["status"] == "fail"
    assert checks["candidate_depth"]["status"] == "fail"
    assert any("provider" in action.lower() for action in report["next_actions"])
    assert report["remediation_plan"]
    assert report["remediation_plan"][0]["severity"] == "needs_attention"
    provider_repair = next(item for item in report["remediation_plan"] if item["id"] == "check_provider_health")
    assert provider_repair["adjustment"]["scoring_profile"] == "fresh_discovery"
    assert provider_repair["adjustment"]["radius_multiplier"] == 1.5
    assert provider_repair["adjustment"]["clear_excluded_tag_groups"] is True


def test_scenario_readiness_report_uses_slate_summary_for_friend_coverage():
    result = {
        "member_count": 2,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Pocket Park", ["park"]),
            _readiness_place("Art Yard", ["art_gallery"]),
            _readiness_place("Jazz Room", ["bar", "concert_hall"]),
            _readiness_place("Corner Bakery", ["bakery"]),
            _readiness_place("Small Museum", ["museum"]),
            _readiness_place("Garden Walk", ["garden"]),
            _readiness_place("Book Nook", ["book_store"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
                "average_group_fit": 0.76,
            },
            "strengths": [],
            "warnings": [],
        },
        "group_fit_summary": {
            "members": [
                {
                    "user_id": 1,
                    "display_name": "Owner",
                    "average_fit": 0.82,
                    "matched_count": 2,
                    "preferred_groups": [{"id": "coffee_sweets", "label": "Coffee Sweets"}],
                    "suggested_query_tags": ["cafe", "bakery"],
                },
                {
                    "user_id": 2,
                    "display_name": "Friend",
                    "average_fit": 0.48,
                    "matched_count": 0,
                    "preferred_groups": [{"id": "arts_culture", "label": "Arts Culture"}],
                    "suggested_query_tags": ["museum", "art_gallery"],
                },
            ],
        },
        "slate_summary": {
            "status": "needs_party_coverage",
            "metrics": {
                "diversity_coverage": 0.95,
                "missing_intent_count": 0,
                "member_coverage_share": 0.5,
            },
            "member_coverage": [
                {
                    "user_id": 1,
                    "display_name": "Owner",
                    "strong_match_count": 2,
                    "best_fit": 0.82,
                    "best_match": {"name": "Hidden Cafe", "fit": 0.82},
                },
                {
                    "user_id": 2,
                    "display_name": "Friend",
                    "strong_match_count": 0,
                    "best_fit": 0.48,
                    "best_match": {"name": "Pocket Park", "fit": 0.48},
                },
            ],
            "underserved_members": [
                {"user_id": 2, "display_name": "Friend", "strong_match_count": 0, "best_fit": 0.48},
            ],
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "needs_attention"
    assert report["ready_for_friend_testing"] is False
    assert checks["friend_coverage"]["status"] == "fail"
    assert checks["friend_coverage"]["value"] == pytest.approx(0.5)
    assert checks["variety"]["status"] == "pass"
    assert report["friend_readiness"]["status"] == "needs_attention"
    assert report["friend_readiness"]["underserved_members"][0]["display_name"] == "Friend"
    assert report["friend_readiness"]["underserved_members"][0]["suggested_query_tags"] == ["museum", "art_gallery"]
    assert report["friend_readiness"]["underserved_members"][0]["preferred_groups"][0]["label"] == "Arts Culture"
    assert "Friend needs a stronger match" in report["friend_readiness"]["headline"]
    assert any("Group fit scout" in action for action in report["friend_readiness"]["next_actions"])
    assert any("Friend" in warning for warning in report["warnings"])
    friend_repair = next(item for item in report["remediation_plan"] if item["id"] == "friend_coverage")
    assert friend_repair["adjustment"]["scoring_profile"] == "group_friendly"
    assert friend_repair["adjustment"]["boost_query_tags"] == ["museum", "art_gallery"]


def test_scenario_readiness_report_flags_low_group_consensus_even_with_average_fit():
    result = {
        "member_count": 2,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Pocket Park", ["park"]),
            _readiness_place("Art Yard", ["art_gallery"]),
            _readiness_place("Jazz Room", ["bar", "concert_hall"]),
            _readiness_place("Corner Bakery", ["bakery"]),
            _readiness_place("Small Museum", ["museum"]),
            _readiness_place("Garden Walk", ["garden"]),
            _readiness_place("Book Nook", ["book_store"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
                "average_group_fit": 0.78,
                "average_consensus_fit": 0.54,
                "group_consensus_gap": 0.24,
            },
            "strengths": [],
            "warnings": [],
        },
        "group_fit_summary": {
            "average_fit": 0.78,
            "average_consensus_fit": 0.54,
            "consensus_gap": 0.24,
            "members": [
                {"user_id": 1, "display_name": "Owner", "average_fit": 0.86, "matched_count": 2},
                {"user_id": 2, "display_name": "Friend", "average_fit": 0.7, "matched_count": 1},
            ],
        },
        "slate_summary": {
            "metrics": {
                "diversity_coverage": 1.0,
                "missing_intent_count": 0,
                "member_coverage_share": 1.0,
            },
            "member_coverage": [
                {"user_id": 1, "display_name": "Owner", "strong_match_count": 2, "best_fit": 0.86},
                {"user_id": 2, "display_name": "Friend", "strong_match_count": 1, "best_fit": 0.7},
            ],
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert report["ready_for_friend_testing"] is False
    assert checks["group_fit"]["status"] == "pass"
    assert checks["friend_coverage"]["status"] == "pass"
    assert checks["group_consensus"]["status"] == "fail"
    assert report["metrics"]["average_consensus_fit"] == 0.54
    assert report["metrics"]["group_consensus_gap"] == 0.24
    assert report["friend_readiness"]["status"] == "needs_attention"
    assert "average is hiding" in report["friend_readiness"]["headline"]
    assert verdict_dimensions["friends"]["status"] == "fail"
    consensus_repair = next(item for item in report["remediation_plan"] if item["id"] == "check_group_consensus")
    assert consensus_repair["adjustment"]["scoring_profile"] == "group_friendly"


def test_scenario_readiness_report_flags_missing_slate_intents():
    result = {
        "member_count": 1,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Second Cafe", ["cafe"]),
            _readiness_place("Third Cafe", ["cafe"]),
            _readiness_place("Fourth Cafe", ["cafe"]),
            _readiness_place("Fifth Cafe", ["cafe"]),
            _readiness_place("Sixth Cafe", ["cafe"]),
            _readiness_place("Seventh Cafe", ["cafe"]),
            _readiness_place("Eighth Cafe", ["cafe"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
                "diversity_coverage": 0.33,
                "missing_intent_count": 2,
            },
            "strengths": [],
            "warnings": [],
        },
        "slate_summary": {
            "status": "narrow",
            "metrics": {
                "diversity_coverage": 0.33,
                "missing_intent_count": 2,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "needs_attention"
    assert checks["variety"]["status"] == "fail"
    assert checks["intent_coverage"]["status"] == "fail"


def test_scenario_readiness_report_flags_repetitive_first_swipes():
    result = {
        "member_count": 1,
        "provider_errors": [],
        "recommendations": [
            _readiness_place("Hidden Cafe", ["cafe"], label="Hidden gem"),
            _readiness_place("Second Cafe", ["cafe"]),
            _readiness_place("Third Cafe", ["cafe"]),
            _readiness_place("Park Market", ["park", "market"]),
            _readiness_place("Art Yard", ["art_gallery"]),
            _readiness_place("Garden Walk", ["garden"]),
            _readiness_place("Book Nook", ["book_store"]),
            _readiness_place("Jazz Room", ["bar", "concert_hall"]),
        ],
        "recommendation_quality": {
            "metrics": {
                "returned": 8,
                "local_feeling_share": 0.75,
                "hidden_gem_count": 1,
                "generic_risk_share": 0.0,
            },
            "model_confidence": {
                "status": "ready",
                "score": 0.82,
                "learning_status": "personalized",
                "next_actions": [],
            },
        },
        "slate_summary": {
            "metrics": {
                "diversity_coverage": 1.0,
                "missing_intent_count": 0,
                "first_page_diversity_coverage": 0.33,
                "first_page_dominant_group_share": 1.0,
                "first_page_missing_intent_count": 2,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert checks["variety"]["status"] == "pass"
    assert checks["first_swipe_variety"]["status"] == "fail"
    assert report["metrics"]["first_page_score"] < 0.3
    assert report["test_verdict"]["friend_testable"] is False
    assert verdict_dimensions["first_swipes"]["status"] == "fail"


def test_scenario_readiness_report_marks_strong_planned_route_ready():
    route_stop = _readiness_place("Stop", ["cafe"])
    route_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.86},
        {"user_id": 2, "display_name": "Friend", "fit": 0.78},
    ]
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 2,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.86,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.62,
            "strengths": ["Most route slots are filled."],
            "warnings": [],
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["mode"] == "planned_itinerary"
    assert report["status"] == "ready"
    assert report["ready_for_friend_testing"] is True
    assert checks["swap_options"]["status"] == "pass"
    assert checks["party_fit"]["status"] == "pass"
    assert checks["friend_route_coverage"]["status"] == "pass"
    assert checks["friend_route_fit"]["status"] == "pass"
    assert checks["social_events"]["status"] == "pass"
    assert checks["price_estimate"]["status"] == "pass"
    assert report["friend_readiness"]["status"] == "ready"
    assert report["friend_readiness"]["covered_member_count"] == 2
    assert report["test_verdict"]["status"] == "ready"
    assert report["test_verdict"]["friend_testable"] is True
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}
    assert verdict_dimensions["friends"]["status"] == "pass"
    assert verdict_dimensions["booking"]["status"] == "pass"
    assert verdict_dimensions["local"]["status"] == "pass"
    assert verdict_dimensions["social_events"]["status"] == "pass"


def test_scenario_readiness_report_warns_on_trip_duration_mismatch():
    route_stop = _readiness_place("Stop", ["cafe"])
    route_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.86},
        {"user_id": 2, "display_name": "Friend", "fit": 0.78},
    ]
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 2,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.86,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.62,
            "strengths": ["Most route slots are filled."],
            "warnings": [],
        },
        "booking_plan": {
            "duration_alignment": {
                "status": "watch",
                "headline": "Day trip has overnight dates.",
                "message": "This route has one itinerary day, but the selected dates add an overnight stay.",
                "next_action": "Switch to Weekend/Vacation or shorten the date range before booking.",
                "trip_style": "day",
                "route_days": 1,
                "calendar_nights": 2,
            },
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    duration_repair = next(item for item in report["remediation_plan"] if item["id"] == "duration_alignment")

    assert report["status"] == "watch"
    assert report["ready_for_friend_testing"] is False
    assert checks["duration_alignment"]["status"] == "warn"
    assert report["metrics"]["duration_alignment_status"] == "watch"
    assert "Day trip has overnight dates." in report["warnings"]
    assert duration_repair["adjustment"]["kind"] == "collect_trip_inputs"
    assert duration_repair["adjustment"]["required_inputs"] == ["trip_style", "travel_dates"]


def test_scenario_readiness_report_flags_planned_route_with_weak_booking_packet():
    route_stop = _readiness_place("Stop", ["cafe"])
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 1,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.84,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.34,
            "event_score": 0.78,
            "event_social_score": 0.62,
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert checks["booking_readiness"]["status"] == "fail"
    assert verdict_dimensions["booking"]["status"] == "fail"
    booking_repair = next(item for item in report["remediation_plan"] if item["id"] == "check_booking_readiness")
    assert booking_repair["adjustment"]["kind"] == "collect_booking_details"
    assert "Booking and logistics" in booking_repair["label"]


def test_scenario_readiness_report_flags_planned_route_without_model_or_logistics_confidence():
    route_stop = _readiness_place("Stop", ["cafe"])
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 1,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.86,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.62,
        },
        "route_model_confidence": {
            "status": "cold_start",
            "score": 0.31,
            "next_actions": ["Collect more accepted/rejected outcomes before trusting the route model."],
        },
        "trip_logistics_readiness": {
            "status": "needs_details",
            "score": 0.38,
            "missing_input_count": 3,
            "blocking_count": 1,
            "next_actions": ["Add origin, dates, and local transport details."],
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert checks["route_model_confidence"]["status"] == "fail"
    assert checks["trip_logistics"]["status"] == "fail"
    assert report["metrics"]["route_model_confidence_score"] == 0.31
    assert report["metrics"]["trip_logistics_score"] == 0.38
    assert report["metrics"]["trip_logistics_missing_input_count"] == 3
    assert verdict_dimensions["model_signal"]["status"] == "fail"
    assert verdict_dimensions["trip_logistics"]["status"] == "fail"
    assert any(
        "Collect more accepted/rejected outcomes" in action
        for action in report["test_verdict"]["next_actions"]
    )
    assert any(item["id"] == "model_signal" for item in report["remediation_plan"])
    logistics_repair = next(item for item in report["remediation_plan"] if item["id"] == "trip_logistics")
    assert logistics_repair["adjustment"]["kind"] == "collect_trip_inputs"


def test_scenario_readiness_report_flags_planned_route_without_travel_quote_links():
    route_stop = _readiness_place("Stop", ["cafe"])
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 1,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.86,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.62,
        },
        "route_model_confidence": {"status": "ready", "score": 0.82},
        "trip_logistics_readiness": {"status": "ready", "score": 0.82},
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
            "quote_plan": {
                "status": "needs_inputs",
                "required_count": 2,
                "ready_count": 0,
                "missing_inputs": ["origin", "dates"],
                "message": "Add origin and dates so Adventour can prepare travel quote links.",
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "needs_attention"
    assert checks["travel_quotes"]["status"] == "fail"
    assert report["metrics"]["travel_quote_required_count"] == 2
    assert report["metrics"]["travel_quote_ready_count"] == 0
    assert report["metrics"]["travel_quote_missing_input_count"] == 2
    assert report["metrics"]["travel_quote_ready_coverage"] == 0
    quote_item = next(item for item in report["remediation_plan"] if item["id"] == "travel_quotes")
    assert "origin, dates" in quote_item["actions"][0]
    assert quote_item["adjustment"]["kind"] == "collect_trip_inputs"
    assert quote_item["adjustment"]["required_inputs"] == ["origin", "dates"]


def test_scenario_readiness_report_flags_when_planned_route_events_lack_social_anchor():
    route_stop = _readiness_place("Stop", ["cafe"])
    route_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.86},
        {"user_id": 2, "display_name": "Friend", "fit": 0.78},
    ]
    stop_template = {
        "alternatives": [{"name": "Swap option"}],
        "recommendation": route_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 2,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.86,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.16,
            "strengths": ["Most route slots are filled."],
            "warnings": ["Local events are paired, but they need social signal before meetup testing."],
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert report["ready_for_friend_testing"] is False
    assert checks["local_events"]["status"] == "pass"
    assert checks["social_events"]["status"] == "fail"
    assert report["metrics"]["event_social_score"] == 0.16
    assert report["test_verdict"]["status"] == "needs_attention"
    assert report["test_verdict"]["friend_testable"] is False
    assert verdict_dimensions["social_events"]["status"] == "fail"
    assert "Ask friends to mark Interested/Going" in report["test_verdict"]["blockers"][0]
    assert "Social event anchor needs improvement before friend testing." in report["test_verdict"]["next_actions"]
    social_event_repair = next(item for item in report["remediation_plan"] if item["id"] == "check_social_events")
    assert social_event_repair["adjustment"]["kind"] == "collect_event_social_signal"
    assert "Interested/Going" in social_event_repair["actions"][0]


def test_scenario_readiness_report_flags_planned_route_friend_gap():
    owner_stop = _readiness_place("Owner Cafe", ["cafe"])
    owner_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.82},
        {"user_id": 2, "display_name": "Friend", "fit": 0.42},
    ]
    friend_swap = _readiness_place("Friend Gallery", ["art_gallery"])
    friend_swap["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.58},
        {"user_id": 2, "display_name": "Friend", "fit": 0.81},
    ]
    friend_swap["swap_impact"] = {
        "member_fit_delta": 0.17,
        "member_rebalance_delta": 0.2,
        "low_friction_score": 0.82,
        "reasons": ["Helps rebalance the party for Friend."],
    }
    stop_template = {
        "alternatives": [friend_swap],
        "recommendation": owner_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 2,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {**stop_template, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.82,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "strengths": ["Most route slots are filled."],
            "warnings": [],
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "needs_attention"
    assert report["ready_for_friend_testing"] is False
    assert checks["friend_route_coverage"]["status"] == "fail"
    assert checks["friend_route_fit"]["status"] == "pass"
    assert report["friend_readiness"]["status"] == "needs_attention"
    assert report["friend_readiness"]["underserved_members"][0]["display_name"] == "Friend"
    assert report["friend_readiness"]["suggested_swaps"][0]["to_stop"] == "Friend Gallery"
    assert report["friend_readiness"]["underserved_members"][0]["suggested_swaps"][0]["fit"] == 0.81
    assert "Swap Owner Cafe for Friend Gallery" in report["friend_readiness"]["next_actions"][0]
    assert report["test_verdict"]["status"] == "needs_attention"
    assert report["test_verdict"]["friend_testable"] is False
    assert any(
        dimension["name"] == "friends" and dimension["status"] == "fail"
        for dimension in report["test_verdict"]["dimensions"]
    )
    assert any("Friend" in warning for warning in report["warnings"])


def test_scenario_readiness_report_flags_planned_route_consensus_gap():
    owner_heavy_stop = _readiness_place("Owner Cafe", ["cafe"])
    owner_heavy_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.98},
        {"user_id": 2, "display_name": "Friend", "fit": 0.61},
    ]
    owner_heavy_stop["components"] = {"group_min_fit_weight": 1.0}
    friend_stop = _readiness_place("Friend Gallery", ["art_gallery"])
    friend_stop["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.74},
        {"user_id": 2, "display_name": "Friend", "fit": 0.71},
    ]
    balanced_swap = _readiness_place("Balanced Market", ["market"])
    balanced_swap["member_fit"] = [
        {"user_id": 1, "display_name": "Owner", "fit": 0.75},
        {"user_id": 2, "display_name": "Friend", "fit": 0.78},
    ]
    balanced_swap["components"] = {"group_min_fit_weight": 0.5}
    stop_template = {
        "alternatives": [balanced_swap],
        "recommendation": owner_heavy_stop,
    }
    result = {
        "mode": "planned_itinerary",
        "member_count": 2,
        "provider_errors": [],
        "days": [
            {
                "stops": [
                    {**stop_template, "slot_id": "morning_anchor"},
                    {**stop_template, "slot_id": "late_morning_discovery"},
                    {"alternatives": [{"name": "Swap option"}], "recommendation": friend_stop, "slot_id": "lunch"},
                    {**stop_template, "slot_id": "evening_finish"},
                ],
            },
        ],
        "route_readiness": {
            "score": 0.84,
            "planned_stop_count": 4,
            "expected_stop_count": 4,
            "stop_coverage": 1.0,
            "variety_score": 0.74,
            "party_score": 0.82,
            "booking_score": 0.76,
            "event_score": 0.78,
            "event_social_score": 0.62,
            "strengths": ["Most route slots are filled."],
            "warnings": [],
        },
        "price_breakdown": {
            "per_person": {
                "total_known_low": 85,
                "total_known_high": 140,
            },
        },
    }

    report = RecommendationEvaluationService().scenario_readiness_report(result)
    checks = {check["name"]: check for check in report["checks"]}
    verdict_dimensions = {item["name"]: item for item in report["test_verdict"]["dimensions"]}

    assert report["status"] == "needs_attention"
    assert checks["friend_route_coverage"]["status"] == "pass"
    assert checks["friend_route_fit"]["status"] == "pass"
    assert checks["route_group_consensus"]["status"] == "fail"
    assert report["metrics"]["average_consensus_fit"] == pytest.approx(0.638, abs=0.001)
    assert report["metrics"]["group_consensus_gap"] == pytest.approx(0.14, abs=0.001)
    assert report["friend_readiness"]["status"] == "needs_attention"
    assert report["friend_readiness"]["suggested_swaps"][0]["to_stop"] == "Balanced Market"
    assert report["friend_readiness"]["suggested_swaps"][0]["group_consensus_delta"] == pytest.approx(0.148, abs=0.001)
    assert report["friend_readiness"]["suggested_swaps"][0]["group_consensus_gap_delta"] == pytest.approx(0.178, abs=0.001)
    assert "Balanced Market" in report["friend_readiness"]["next_actions"][0]
    assert verdict_dimensions["friends"]["status"] == "fail"
    consensus_repair = next(item for item in report["remediation_plan"] if item["id"] == "check_route_group_consensus")
    assert consensus_repair["adjustment"]["scoring_profile"] == "group_friendly"
