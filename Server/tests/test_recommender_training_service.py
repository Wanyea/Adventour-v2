import json
import csv

import pytest
from flask import Flask

from adventour_backend.models import db, Place, PlaceFeature, User, UserPlaceEvent
from adventour_backend.services.recommender_training_service import RecommendationTrainingExportService


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


def create_training_fixture():
    user = User(
        firebase_uid="training-user",
        email="training@example.com",
        username="training",
        display_name="Training User",
    )
    place = Place(
        canonical_name="Tiny Local Museum",
        normalized_name="tiny local museum",
        latitude=37.422,
        longitude=-122.084,
    )
    db.session.add_all([user, place])
    db.session.flush()
    db.session.add(PlaceFeature(
        place_id=place.id,
        category_vector=json.dumps({"museum": 1.0}),
        cuisine_vector=json.dumps({}),
        activity_vector=json.dumps({}),
        price_band=1,
        chain_probability=0.0,
        authenticity_score=0.84,
        hidden_gem_score=0.8,
        tourist_trap_score=0.0,
        quality_score_adventour=0.92,
        popularity_score_adventour=0.22,
    ))
    db.session.add_all([
        UserPlaceEvent(
            user_id=user.id,
            place_id=place.id,
            event_type="impression",
            metadata_json=json.dumps({
                "request_id": "request-123",
                "rank_position": 2,
                "score": 0.74,
                "base_rank_score": 0.71,
                "mode": "spontaneous",
                "ranking": {
                    "strategy": "score_then_diversity",
                    "scoring_profile": "phase1_balanced",
                    "diversity_adjusted_score": 0.79,
                    "diversity_bonus": 0.05,
                    "diversity_penalty": 0.02,
                    "intent_coverage_bonus": 0.07,
                    "covered_new_intents": ["arts_culture"],
                    "member_coverage_bonus": 0.09,
                    "served_new_members": ["Art Friend"],
                    "objective_breakdown": {
                        "model_family": "hybrid_multi_objective",
                        "positive_total": 0.82,
                        "penalty_total": 0.08,
                        "final_score": 0.74,
                        "top_positive": ["authenticity", "travel_party"],
                        "top_penalty": "repeat",
                    },
                },
                "score_components": {
                    "time_fit": 0.86,
                    "scoring_profile": "phase1_balanced",
                    "group_average_fit": 0.8,
                    "group_consensus_fit": 0.78,
                    "group_min_fit": 0.72,
                    "group_min_fit_weight": 0.14,
                    "group_fairness_penalty": 0.0,
                    "exploration": 0.81,
                    "exploration_uncertainty": 0.42,
                    "preference_confidence": 0.58,
                    "average_member_signal_count": 7.0,
                    "local_event_fit": 0.82,
                    "session_context_fit": 0.55,
                    "session_context_signal_count": 2,
                    "friend_history_fit": 0.4,
                    "friend_history_signal_count": 1,
                },
                "local_event_match": {
                    "event_id": 9,
                    "title": "Neighborhood Night Market",
                    "score": 0.82,
                    "route_anchor_score": 0.76,
                    "distance_to_place_meters": 320,
                    "source_name": "City calendar",
                    "source_url": "https://example.com/events/night-market",
                    "reservation_url": "https://example.com/events/night-market/rsvp",
                    "social": {
                        "friend_going_count": 1,
                        "friend_interested_count": 1,
                        "signal": 0.6,
                    },
                },
                "member_fit": [
                    {"user_id": user.id, "display_name": "Training User", "fit": 0.72},
                    {"user_id": 404, "display_name": "Art Friend", "fit": 0.88},
                ],
                "explanation_details": [
                    {"kind": "authenticity_forward", "label": "Hidden gems scout", "value": "Strong local signal"},
                    {"kind": "group_fit", "label": "Travel-party fit", "value": "Works for the group"},
                ],
                "authenticity_evidence": {"label": "Hidden gem", "reasons": ["low chain risk"]},
                "query_tags": ["museum", "art_gallery"],
                "intent_target_groups": ["arts_culture"],
                "retrieval_context": {
                    "query_tags": ["museum", "art_gallery"],
                    "boost_query_tags": ["arts_culture"],
                    "boosted_query_tags": ["museum", "art_gallery"],
                    "friend_adjusted": True,
                },
                "diversity_groups": ["arts_culture"],
            }),
        ),
        UserPlaceEvent(
            user_id=user.id,
            place_id=place.id,
            event_type="accept",
            metadata_json=json.dumps({
                "request_id": "request-123",
                "rank_position": 2,
                "score": 0.74,
                "base_rank_score": 0.71,
                "ranking": {
                    "strategy": "score_then_diversity",
                    "scoring_profile": "phase1_balanced",
                    "diversity_adjusted_score": 0.79,
                    "diversity_bonus": 0.05,
                    "diversity_penalty": 0.02,
                    "intent_coverage_bonus": 0.07,
                    "covered_new_intents": ["arts_culture"],
                    "member_coverage_bonus": 0.09,
                    "served_new_members": ["Art Friend"],
                    "objective_breakdown": {
                        "model_family": "hybrid_multi_objective",
                        "positive_total": 0.82,
                        "penalty_total": 0.08,
                        "final_score": 0.74,
                        "top_positive": ["authenticity", "travel_party"],
                        "top_penalty": "repeat",
                    },
                },
                "score_components": {
                    "time_fit": 0.86,
                    "scoring_profile": "phase1_balanced",
                    "group_average_fit": 0.8,
                    "group_consensus_fit": 0.78,
                    "group_min_fit": 0.72,
                    "group_min_fit_weight": 0.14,
                    "group_fairness_penalty": 0.0,
                    "exploration": 0.81,
                    "exploration_uncertainty": 0.42,
                    "preference_confidence": 0.58,
                    "average_member_signal_count": 7.0,
                    "local_event_fit": 0.82,
                    "session_context_fit": 0.55,
                    "session_context_signal_count": 2,
                    "friend_history_fit": 0.4,
                    "friend_history_signal_count": 1,
                },
                "local_event_match": {
                    "event_id": 9,
                    "title": "Neighborhood Night Market",
                    "score": 0.82,
                    "route_anchor_score": 0.76,
                    "distance_to_place_meters": 320,
                    "source_name": "City calendar",
                    "source_url": "https://example.com/events/night-market",
                    "reservation_url": "https://example.com/events/night-market/rsvp",
                    "social": {
                        "friend_going_count": 1,
                        "friend_interested_count": 1,
                        "signal": 0.6,
                    },
                },
                "member_fit": [
                    {"user_id": user.id, "display_name": "Training User", "fit": 0.72},
                    {"user_id": 404, "display_name": "Art Friend", "fit": 0.88},
                ],
                "explanation_details": [
                    {"kind": "authenticity_forward", "label": "Hidden gems scout", "value": "Strong local signal"},
                    {"kind": "group_fit", "label": "Travel-party fit", "value": "Works for the group"},
                ],
                "authenticity_evidence": {"label": "Hidden gem", "reasons": ["low chain risk"]},
                "query_tags": ["museum", "art_gallery"],
                "intent_target_groups": ["arts_culture"],
                "retrieval_context": {
                    "query_tags": ["museum", "art_gallery"],
                    "boost_query_tags": ["arts_culture"],
                    "boosted_query_tags": ["museum", "art_gallery"],
                    "friend_adjusted": True,
                },
                "diversity_groups": ["arts_culture"],
            }),
        ),
        UserPlaceEvent(user_id=user.id, place_id=place.id, event_type="reject"),
        UserPlaceEvent(user_id=user.id, place_id=place.id, event_type="rate", event_value=5),
    ])
    db.session.commit()
    return user, place


def test_training_export_labels_outcome_events(app_context):
    create_training_fixture()

    examples = RecommendationTrainingExportService().build_examples()

    assert [example["event_type"] for example in examples] == ["accept", "reject", "rate"]
    labels = {example["event_type"]: example["label"] for example in examples}
    assert labels["accept"] == 1.0
    assert labels["reject"] == 0.0
    assert labels["rate"] == 1.0
    assert next(example for example in examples if example["event_type"] == "accept")["outcome_weight"] == 0.75
    assert next(example for example in examples if example["event_type"] == "rate")["outcome_weight"] == 1.0


def test_training_export_includes_feature_payload(app_context):
    create_training_fixture()

    examples = RecommendationTrainingExportService().build_examples()
    accepted = next(example for example in examples if example["event_type"] == "accept")

    assert accepted["category_vector"] == {"museum": 1.0}
    assert accepted["authenticity_score"] == 0.84
    assert accepted["hidden_gem_score"] == 0.8
    assert accepted["feature_version"] == "phase1"
    assert accepted["request_id"] == "request-123"
    assert accepted["rank_position"] == 2
    assert accepted["scoring_profile"] == "phase1_balanced"
    assert accepted["ranking_strategy"] == "score_then_diversity"
    assert accepted["diversity_bonus"] == 0.05
    assert accepted["diversity_penalty"] == 0.02
    assert accepted["intent_coverage_bonus"] == 0.07
    assert accepted["covered_new_intents"] == ["arts_culture"]
    assert accepted["member_coverage_bonus"] == 0.09
    assert accepted["covered_new_intents_count"] == 1
    assert accepted["served_new_members_count"] == 1
    assert accepted["objective_positive_total"] == 0.82
    assert accepted["objective_penalty_total"] == 0.08
    assert accepted["objective_final_score"] == 0.74
    assert accepted["objective_top_positive"] == "authenticity"
    assert accepted["objective_top_penalty"] == "repeat"
    assert accepted["group_average_fit"] == 0.8
    assert accepted["group_consensus_fit"] == 0.78
    assert accepted["group_min_fit"] == 0.72
    assert accepted["group_min_fit_weight"] == 0.14
    assert accepted["group_fairness_penalty"] == 0.0
    assert accepted["member_fit_count"] == 2
    assert accepted["lowest_member_fit"] == 0.72
    assert accepted["highest_member_fit"] == 0.88
    assert accepted["member_fit_spread"] == pytest.approx(0.16)
    assert accepted["exploration"] == 0.81
    assert accepted["exploration_uncertainty"] == 0.42
    assert accepted["preference_confidence"] == 0.58
    assert accepted["average_member_signal_count"] == 7.0
    assert accepted["session_context_fit"] == 0.55
    assert accepted["session_context_signal_count"] == 2
    assert accepted["friend_history_fit"] == 0.4
    assert accepted["friend_history_signal_count"] == 1
    assert accepted["diversity_group_count"] == 1
    assert accepted["query_tags"] == ["museum", "art_gallery"]
    assert accepted["intent_target_groups"] == ["arts_culture"]
    assert accepted["friend_adjusted_retrieval"] is True
    assert accepted["boost_query_tags"] == ["arts_culture"]
    assert accepted["boosted_query_tags"] == ["museum", "art_gallery"]
    assert accepted["local_event_backed"] is True
    assert accepted["local_event_fit"] == 0.82
    assert accepted["local_event_distance_to_place_meters"] == 320
    assert accepted["local_event_reservation_ready"] is True
    assert accepted["local_event_source_ready"] is True
    assert accepted["local_event_route_anchor_score"] == 0.76
    assert accepted["local_event_friend_signal_count"] == 2.0
    assert accepted["local_event_social_signal"] == 0.6
    assert accepted["local_event_match"]["title"] == "Neighborhood Night Market"
    assert accepted["top_explanation_kind"] == "authenticity_forward"
    assert accepted["explanation_kinds"] == ["authenticity_forward", "group_fit"]
    assert accepted["authenticity_label"] == "Hidden gem"
    assert accepted["components"] == {
        "time_fit": 0.86,
        "scoring_profile": "phase1_balanced",
        "group_average_fit": 0.8,
        "group_consensus_fit": 0.78,
        "group_min_fit": 0.72,
        "group_min_fit_weight": 0.14,
        "group_fairness_penalty": 0.0,
        "exploration": 0.81,
        "exploration_uncertainty": 0.42,
        "preference_confidence": 0.58,
        "average_member_signal_count": 7.0,
        "local_event_fit": 0.82,
        "session_context_fit": 0.55,
        "session_context_signal_count": 2,
        "friend_history_fit": 0.4,
        "friend_history_signal_count": 1,
    }
    assert accepted["attribution_source"] == "direct_metadata"


def test_training_export_attributes_later_outcomes_to_latest_impression(app_context):
    create_training_fixture()

    examples = RecommendationTrainingExportService().build_examples()
    rated = next(example for example in examples if example["event_type"] == "rate")

    assert rated["label"] == 1.0
    assert rated["label_source"] == "rating"
    assert rated["request_id"] == "request-123"
    assert rated["rank_position"] == 2
    assert rated["scoring_profile"] == "phase1_balanced"
    assert rated["model_score"] == 0.74
    assert rated["ranking_strategy"] == "score_then_diversity"
    assert rated["intent_coverage_bonus"] == 0.07
    assert rated["covered_new_intents"] == ["arts_culture"]
    assert rated["friend_adjusted_retrieval"] is True
    assert rated["boost_query_tags"] == ["arts_culture"]
    assert rated["local_event_backed"] is True
    assert rated["local_event_fit"] == 0.82
    assert rated["local_event_distance_to_place_meters"] == 320
    assert rated["local_event_route_anchor_score"] == 0.76
    assert rated["local_event_friend_signal_count"] == 2.0
    assert rated["local_event_social_signal"] == 0.6
    assert rated["member_fit_count"] == 2
    assert rated["objective_positive_total"] == 0.82
    assert rated["objective_top_positive"] == "authenticity"
    assert rated["group_average_fit"] == 0.8
    assert rated["group_consensus_fit"] == 0.78
    assert rated["lowest_member_fit"] == 0.72
    assert rated["highest_member_fit"] == 0.88
    assert rated["exploration"] == 0.81
    assert rated["exploration_uncertainty"] == 0.42
    assert rated["preference_confidence"] == 0.58
    assert rated["average_member_signal_count"] == 7.0
    assert rated["session_context_fit"] == 0.55
    assert rated["session_context_signal_count"] == 2
    assert rated["friend_history_fit"] == 0.4
    assert rated["friend_history_signal_count"] == 1
    assert rated["diversity_groups"] == ["arts_culture"]
    assert rated["diversity_group_count"] == 1
    assert rated["query_tags"] == ["museum", "art_gallery"]
    assert rated["intent_target_groups"] == ["arts_culture"]
    assert rated["top_explanation_kind"] == "authenticity_forward"
    assert rated["authenticity_label"] == "Hidden gem"
    assert rated["attribution_source"] == "latest_impression"


def test_training_export_csv_includes_ranker_signal_columns(app_context, tmp_path):
    create_training_fixture()
    path = tmp_path / "training.csv"
    service = RecommendationTrainingExportService()

    service.write_csv(path, service.build_examples())

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    accepted = next(row for row in rows if row["event_type"] == "accept")
    assert accepted["intent_coverage_bonus"] == "0.07"
    assert accepted["covered_new_intents_count"] == "1"
    assert accepted["served_new_members_count"] == "1"
    assert accepted["group_min_fit"] == "0.72"
    assert accepted["group_average_fit"] == "0.8"
    assert accepted["group_consensus_fit"] == "0.78"
    assert accepted["group_min_fit_weight"] == "0.14"
    assert accepted["group_fairness_penalty"] == "0.0"
    assert accepted["member_fit_count"] == "2"
    assert accepted["lowest_member_fit"] == "0.72"
    assert accepted["highest_member_fit"] == "0.88"
    assert accepted["member_fit_spread"] == "0.16"
    assert accepted["exploration"] == "0.81"
    assert accepted["exploration_uncertainty"] == "0.42"
    assert accepted["preference_confidence"] == "0.58"
    assert accepted["average_member_signal_count"] == "7.0"
    assert accepted["session_context_fit"] == "0.55"
    assert accepted["session_context_signal_count"] == "2"
    assert accepted["friend_history_fit"] == "0.4"
    assert accepted["friend_history_signal_count"] == "1"
    assert accepted["local_event_backed"] == "True"
    assert accepted["local_event_fit"] == "0.82"
    assert accepted["local_event_distance_to_place_meters"] == "320"
    assert accepted["local_event_reservation_ready"] == "True"
    assert accepted["local_event_source_ready"] == "True"
    assert accepted["local_event_route_anchor_score"] == "0.76"
    assert accepted["local_event_friend_signal_count"] == "2.0"
    assert accepted["local_event_social_signal"] == "0.6"
    assert accepted["objective_positive_total"] == "0.82"
    assert accepted["objective_top_positive"] == "authenticity"
    assert accepted["top_explanation_kind"] == "authenticity_forward"
    assert accepted["authenticity_label"] == "Hidden gem"
