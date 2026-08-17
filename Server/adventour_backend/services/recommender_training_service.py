import csv
import json

from adventour_backend.models import PlaceFeature, UserPlaceEvent


POSITIVE_EVENTS = {"accept", "swap", "navigate", "arrival", "save", "share"}
NEGATIVE_EVENTS = {"reject"}


def _json_loads(value, default=None):
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def _rating_label(value):
    if value is None:
        return None
    rating = float(value)
    if rating >= 4:
        return 1.0
    if rating <= 2:
        return 0.0
    return 0.5


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _outcome_weight(event_type, label):
    if event_type in {"arrival", "save", "share"}:
        return 1.0
    if event_type == "navigate":
        return 0.9
    if event_type == "swap":
        return 0.82
    if event_type in {"accept", "reject"}:
        return 0.75
    if event_type == "rate":
        if label is None:
            return 0.0
        return max(0.35, abs(float(label) - 0.5) * 2)
    return 0.5


def _member_fit_summary(member_fit):
    rows = member_fit if isinstance(member_fit, list) else []
    fit_values = [
        value
        for value in (_safe_float(row.get("fit")) for row in rows if isinstance(row, dict))
        if value is not None
    ]
    if not fit_values:
        return {
            "member_fit_count": len(rows),
            "lowest_member_fit": None,
            "highest_member_fit": None,
            "member_fit_spread": None,
        }

    lowest = min(fit_values)
    highest = max(fit_values)
    return {
        "member_fit_count": len(rows),
        "lowest_member_fit": round(lowest, 4),
        "highest_member_fit": round(highest, 4),
        "member_fit_spread": round(highest - lowest, 4),
    }


def _explanation_kinds(explanation_details):
    rows = explanation_details if isinstance(explanation_details, list) else []
    return [
        row.get("kind")
        for row in rows
        if isinstance(row, dict) and row.get("kind")
    ]


def _first_float(*values):
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _local_event_route_anchor_score(local_event_match):
    event = local_event_match if isinstance(local_event_match, dict) else {}
    route_context = event.get("route_context") if isinstance(event.get("route_context"), dict) else {}
    return _first_float(
        event.get("route_anchor_score"),
        route_context.get("route_fit"),
    )


def _local_event_friend_signal_count(local_event_match):
    event = local_event_match if isinstance(local_event_match, dict) else {}
    social = event.get("social") if isinstance(event.get("social"), dict) else {}
    direct = _first_float(
        event.get("friend_signal_count"),
        social.get("friend_signal_count"),
    )
    if direct is not None:
        return max(0, direct)

    going = _safe_float(social.get("friend_going_count"), 0.0)
    interested = _safe_float(social.get("friend_interested_count"), 0.0)
    total = going + interested
    return total if total > 0 else None


def _local_event_social_signal(local_event_match):
    event = local_event_match if isinstance(local_event_match, dict) else {}
    social = event.get("social") if isinstance(event.get("social"), dict) else {}
    components = event.get("components") if isinstance(event.get("components"), dict) else {}
    return _first_float(
        event.get("social_signal"),
        social.get("signal"),
        components.get("social_signal"),
    )


class RecommendationTrainingExportService:
    """Convert Adventour recommendation events into learning-to-rank examples.

    The beta ranker stays deterministic, but every scored impression/outcome can
    become training data later. This exporter keeps that bridge explicit and
    auditable instead of burying it in a notebook.
    """

    def build_examples(self, limit=None, since=None):
        query = UserPlaceEvent.query.order_by(UserPlaceEvent.occurred_at.asc())
        if since is not None:
            query = query.filter(UserPlaceEvent.occurred_at >= since)
        if limit:
            query = query.limit(int(limit))

        return [
            self._example_for_event(event)
            for event in query.all()
            if self._label_for_event(event) is not None
        ]

    def write_jsonl(self, path, examples):
        with open(path, "w", encoding="utf-8") as handle:
            for example in examples:
                handle.write(json.dumps(example, sort_keys=True) + "\n")

    def write_csv(self, path, examples):
        fieldnames = [
            "event_id",
            "user_id",
            "place_id",
            "event_type",
            "label",
            "label_source",
            "outcome_weight",
            "occurred_at",
            "context",
            "attribution_source",
            "request_id",
            "rank_position",
            "scoring_profile",
            "model_score",
            "base_rank_score",
            "ranking_strategy",
            "diversity_adjusted_score",
            "diversity_bonus",
            "diversity_penalty",
            "intent_coverage_bonus",
            "member_coverage_bonus",
            "friend_adjusted_retrieval",
            "local_event_backed",
            "local_event_fit",
            "local_event_distance_to_place_meters",
            "local_event_reservation_ready",
            "local_event_source_ready",
            "local_event_route_anchor_score",
            "local_event_friend_signal_count",
            "local_event_social_signal",
            "session_context_fit",
            "session_context_signal_count",
            "friend_history_fit",
            "friend_history_signal_count",
            "boost_query_tags",
            "boosted_query_tags",
            "covered_new_intents_count",
            "served_new_members_count",
            "objective_positive_total",
            "objective_penalty_total",
            "objective_final_score",
            "objective_top_positive",
            "objective_top_penalty",
            "group_average_fit",
            "group_consensus_fit",
            "group_min_fit",
            "group_min_fit_weight",
            "group_fairness_penalty",
            "member_fit_count",
            "lowest_member_fit",
            "highest_member_fit",
            "member_fit_spread",
            "exploration",
            "exploration_uncertainty",
            "preference_confidence",
            "average_member_signal_count",
            "diversity_group_count",
            "top_explanation_kind",
            "authenticity_label",
            "authenticity_score",
            "hidden_gem_score",
            "chain_probability",
            "tourist_trap_score",
            "quality_score",
            "popularity_score",
            "price_band",
            "repeat_after_exhaustion",
        ]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for example in examples:
                writer.writerow({field: example.get(field) for field in fieldnames})

    def _example_for_event(self, event):
        feature = PlaceFeature.query.filter_by(place_id=event.place_id).first()
        metadata = _json_loads(event.metadata_json)
        attribution_metadata, attribution_source = self._attribution_metadata(event, metadata)
        ranking = metadata.get("ranking") or attribution_metadata.get("ranking") or {}
        member_fit = metadata.get("member_fit") or attribution_metadata.get("member_fit") or []
        explanation_details = (
            metadata.get("explanation_details")
            or attribution_metadata.get("explanation_details")
            or []
        )
        explanation_kinds = _explanation_kinds(explanation_details)
        authenticity_evidence = (
            metadata.get("authenticity_evidence")
            or attribution_metadata.get("authenticity_evidence")
            or {}
        )
        diversity_groups = metadata.get("diversity_groups") or attribution_metadata.get("diversity_groups", [])
        query_tags = metadata.get("query_tags") or attribution_metadata.get("query_tags", [])
        intent_target_groups = (
            metadata.get("intent_target_groups")
            or attribution_metadata.get("intent_target_groups", [])
        )
        retrieval_context = (
            metadata.get("retrieval_context")
            or attribution_metadata.get("retrieval_context")
            or {}
        )
        components = (
            metadata.get("components")
            or metadata.get("score_components")
            or attribution_metadata.get("components")
            or attribution_metadata.get("score_components")
            or {}
        )
        local_event_match = metadata.get("local_event_match") or attribution_metadata.get("local_event_match") or None
        objective_breakdown = ranking.get("objective_breakdown") or {}
        label = self._label_for_event(event)
        member_summary = _member_fit_summary(member_fit)

        return {
            "event_id": event.id,
            "user_id": event.user_id,
            "place_id": event.place_id,
            "provider_ref_id": event.provider_ref_id,
            "event_type": event.event_type,
            "event_value": event.event_value,
            "label": label,
            "label_source": self._label_source(event),
            "outcome_weight": _outcome_weight(event.event_type, label),
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "context": event.context,
            "attribution_source": attribution_source,
            "request_id": metadata.get("request_id") or attribution_metadata.get("request_id"),
            "rank_position": metadata.get("rank_position") or attribution_metadata.get("rank_position"),
            "scoring_profile": ranking.get("scoring_profile") or components.get("scoring_profile"),
            "model_score": metadata.get("score") if metadata.get("score") is not None else attribution_metadata.get("score"),
            "base_rank_score": (
                metadata.get("base_rank_score")
                if metadata.get("base_rank_score") is not None
                else attribution_metadata.get("base_rank_score")
            ),
            "ranking_strategy": ranking.get("strategy"),
            "diversity_adjusted_score": ranking.get("diversity_adjusted_score"),
            "diversity_bonus": ranking.get("diversity_bonus"),
            "diversity_penalty": ranking.get("diversity_penalty"),
            "intent_coverage_bonus": ranking.get("intent_coverage_bonus"),
            "covered_new_intents": ranking.get("covered_new_intents", []),
            "covered_new_intents_count": len(ranking.get("covered_new_intents", []) or []),
            "member_coverage_bonus": ranking.get("member_coverage_bonus"),
            "served_new_members": ranking.get("served_new_members", []),
            "served_new_members_count": len(ranking.get("served_new_members", []) or []),
            "objective_breakdown": objective_breakdown,
            "objective_positive_total": objective_breakdown.get("positive_total"),
            "objective_penalty_total": objective_breakdown.get("penalty_total"),
            "objective_final_score": objective_breakdown.get("final_score"),
            "objective_top_positive": (objective_breakdown.get("top_positive") or [None])[0],
            "objective_top_penalty": objective_breakdown.get("top_penalty"),
            "group_average_fit": components.get("group_average_fit"),
            "group_consensus_fit": components.get("group_consensus_fit"),
            "group_min_fit": components.get("group_min_fit"),
            "group_min_fit_weight": components.get("group_min_fit_weight"),
            "group_fairness_penalty": components.get("group_fairness_penalty"),
            "member_fit": member_fit,
            **member_summary,
            "exploration": components.get("exploration"),
            "exploration_uncertainty": components.get("exploration_uncertainty"),
            "preference_confidence": components.get("preference_confidence"),
            "average_member_signal_count": components.get("average_member_signal_count"),
            "session_context_fit": components.get("session_context_fit"),
            "session_context_signal_count": components.get("session_context_signal_count"),
            "friend_history_fit": components.get("friend_history_fit"),
            "friend_history_signal_count": components.get("friend_history_signal_count"),
            "mode": metadata.get("mode") or attribution_metadata.get("mode"),
            "repeat_after_exhaustion": bool(
                metadata.get("repeat_after_exhaustion")
                if metadata.get("repeat_after_exhaustion") is not None
                else attribution_metadata.get("repeat_after_exhaustion")
            ),
            "history": metadata.get("history") or attribution_metadata.get("history", {}),
            "components": components,
            "diversity_groups": diversity_groups,
            "diversity_group_count": len(diversity_groups or []),
            "query_tags": query_tags,
            "intent_target_groups": intent_target_groups,
            "intent_target_group_count": len(intent_target_groups or []),
            "retrieval_context": retrieval_context,
            "boost_query_tags": retrieval_context.get("boost_query_tags", []) if isinstance(retrieval_context, dict) else [],
            "boosted_query_tags": retrieval_context.get("boosted_query_tags", []) if isinstance(retrieval_context, dict) else [],
            "friend_adjusted_retrieval": bool(
                retrieval_context.get("friend_adjusted")
                if isinstance(retrieval_context, dict)
                else False
            ),
            "local_event_match": local_event_match,
            "local_event_backed": bool(local_event_match),
            "local_event_fit": components.get("local_event_fit") or (local_event_match or {}).get("score"),
            "local_event_distance_to_place_meters": (local_event_match or {}).get("distance_to_place_meters"),
            "local_event_reservation_ready": bool((local_event_match or {}).get("reservation_url")),
            "local_event_source_ready": bool((local_event_match or {}).get("source_url") or (local_event_match or {}).get("source_name")),
            "local_event_route_anchor_score": _local_event_route_anchor_score(local_event_match),
            "local_event_friend_signal_count": _local_event_friend_signal_count(local_event_match),
            "local_event_social_signal": _local_event_social_signal(local_event_match),
            "explanation_details": explanation_details,
            "explanation_kinds": explanation_kinds,
            "top_explanation_kind": explanation_kinds[0] if explanation_kinds else None,
            "authenticity_evidence": authenticity_evidence,
            "authenticity_label": authenticity_evidence.get("label") if isinstance(authenticity_evidence, dict) else None,
            "category_vector": _json_loads(feature.category_vector) if feature else {},
            "cuisine_vector": _json_loads(feature.cuisine_vector) if feature else {},
            "activity_vector": _json_loads(feature.activity_vector) if feature else {},
            "price_band": feature.price_band if feature else None,
            "chain_probability": feature.chain_probability if feature else None,
            "authenticity_score": feature.authenticity_score if feature else None,
            "hidden_gem_score": feature.hidden_gem_score if feature else None,
            "tourist_trap_score": feature.tourist_trap_score if feature else None,
            "quality_score": feature.quality_score_adventour if feature else None,
            "popularity_score": feature.popularity_score_adventour if feature else None,
            "feature_version": feature.feature_version if feature else None,
        }

    def _label_for_event(self, event):
        if event.event_type in POSITIVE_EVENTS:
            return 1.0
        if event.event_type in NEGATIVE_EVENTS:
            return 0.0
        if event.event_type == "rate":
            return _rating_label(event.event_value)
        return None

    def _label_source(self, event):
        if event.event_type == "rate":
            return "rating"
        return event.event_type

    def _attribution_metadata(self, event, metadata):
        if metadata.get("request_id") and metadata.get("rank_position"):
            return metadata, "direct_metadata"

        query = UserPlaceEvent.query.filter(
            UserPlaceEvent.user_id == event.user_id,
            UserPlaceEvent.place_id == event.place_id,
            UserPlaceEvent.event_type == "impression",
        )
        if event.occurred_at is not None:
            query = query.filter(UserPlaceEvent.occurred_at <= event.occurred_at)
        if event.id:
            query = query.filter(UserPlaceEvent.id != event.id)

        impression = query.order_by(
            UserPlaceEvent.occurred_at.desc(),
            UserPlaceEvent.id.desc(),
        ).first()
        if not impression:
            return {}, "none"

        impression_metadata = _json_loads(impression.metadata_json)
        if not impression_metadata.get("request_id") or not impression_metadata.get("rank_position"):
            return {}, "none"
        return impression_metadata, "latest_impression"
