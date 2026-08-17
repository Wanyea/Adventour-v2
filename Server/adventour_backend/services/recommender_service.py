import json
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from adventour_backend.models import (
    db,
    Friendship,
    LocalEvent,
    Place,
    PlaceFeature,
    PlaceProviderRef,
    User,
    UserPlaceEvent,
    UserPreferenceVector,
)
from adventour_backend.providers.place_providers import ProviderRegistry
from adventour_backend.services.google_services_api import first_photo_url
from adventour_backend.services.recommender_model_service import (
    LearningToRankBaselineService,
    learned_ranker_artifact_status,
    model_feature_compatibility,
)
from adventour_backend.services.place_classification import classify_recommendation_lane, is_discoverable_candidate
from adventour_backend.utils import is_chain, is_hidden_gem, review_sentiment_score
from sqlalchemy import and_, or_


EVENT_WEIGHTS = {
    "impression": 0.0,
    "reject": -1.0,
    "accept": 2.0,
    "swap": 2.5,
    "navigate": 3.0,
    "arrival": 5.0,
    "rate": 0.0,
    "save": 4.0,
    "share": 4.0,
}

RECENT_HISTORY_DAYS = 14
PREFERENCE_EVENT_HALF_LIFE_DAYS = 45
PREFERENCE_VECTOR_CACHE_TTL_HOURS = 24
MEMBER_COVERAGE_FIT_THRESHOLD = 0.65
SESSION_CONTEXT_HOURS = 6
SESSION_CONTEXT_HALF_LIFE_HOURS = 1.5


@dataclass(frozen=True)
class ScoringProfile:
    """Tunable ranking weights for Adventour's transparent hybrid ranker."""

    name: str = "phase1_balanced"
    personal_fit_weight: float = 0.30
    group_fit_weight: float = 0.20
    authenticity_weight: float = 0.20
    quality_weight: float = 0.15
    context_fit_weight: float = 0.08
    time_fit_weight: float = 0.07
    novelty_weight: float = 0.05
    exploration_weight: float = 0.04
    value_weight: float = 0.0
    local_event_weight: float = 0.05
    session_context_weight: float = 0.14
    friend_history_weight: float = 0.10
    group_disagreement_penalty: float = 0.35
    group_min_fit_weight: float = 0.14
    group_low_fit_threshold: float = 0.55
    group_low_fit_penalty: float = 0.18
    authenticity_hidden_gem_weight: float = 0.25
    authenticity_chain_penalty_weight: float = 0.35
    authenticity_tourist_trap_penalty_weight: float = 0.25
    chain_penalty: float = 0.25
    chain_penalty_threshold: float = 0.7
    time_mismatch_penalty: float = 0.12
    time_mismatch_threshold: float = 0.25
    price_penalty: float = 0.20
    repeat_penalty_per_impression: float = 0.07
    repeat_penalty_max: float = 0.28
    rejected_repeat_penalty: float = 0.32
    accepted_repeat_penalty: float = 0.14
    diversity_new_group_bonus: float = 0.08
    diversity_authenticity_bonus_weight: float = 0.04
    diversity_authenticity_bonus_max: float = 0.06
    intent_coverage_bonus_per_group: float = 0.07
    intent_coverage_bonus_max: float = 0.14
    member_coverage_bonus_per_member: float = 0.09
    member_coverage_bonus_max: float = 0.16
    diversity_group_repeat_penalty: float = 0.09
    diversity_type_repeat_penalty: float = 0.025
    diversity_repeat_penalty_max: float = 0.22
    slate_similarity_penalty_weight: float = 0.06
    slate_similarity_penalty_max: float = 0.14
    local_discovery_frontier_gap: float = 0.18
    local_discovery_first_page_size: int = 3
    exploration_frontier_gap: float = 0.22
    exploration_page_share: float = 0.25


DEFAULT_SCORING_PROFILE = ScoringProfile(value_weight=0.04)
SCORING_PROFILES = {
    DEFAULT_SCORING_PROFILE.name: DEFAULT_SCORING_PROFILE,
    "authenticity_forward": replace(
        DEFAULT_SCORING_PROFILE,
        name="authenticity_forward",
        personal_fit_weight=0.25,
        group_fit_weight=0.17,
        authenticity_weight=0.28,
        quality_weight=0.13,
        novelty_weight=0.06,
        exploration_weight=0.06,
        value_weight=0.05,
        authenticity_hidden_gem_weight=0.35,
        chain_penalty=0.32,
        diversity_authenticity_bonus_max=0.08,
    ),
    "group_friendly": replace(
        DEFAULT_SCORING_PROFILE,
        name="group_friendly",
        personal_fit_weight=0.24,
        group_fit_weight=0.32,
        authenticity_weight=0.18,
        group_disagreement_penalty=0.25,
        group_min_fit_weight=0.26,
        group_low_fit_threshold=0.55,
        group_low_fit_penalty=0.22,
        member_coverage_bonus_per_member=0.12,
        member_coverage_bonus_max=0.22,
    ),
    "fresh_discovery": replace(
        DEFAULT_SCORING_PROFILE,
        name="fresh_discovery",
        novelty_weight=0.12,
        exploration_weight=0.10,
        value_weight=0.05,
        repeat_penalty_per_impression=0.09,
        repeat_penalty_max=0.36,
        diversity_new_group_bonus=0.11,
        intent_coverage_bonus_per_group=0.10,
        intent_coverage_bonus_max=0.18,
        diversity_group_repeat_penalty=0.11,
        diversity_repeat_penalty_max=0.28,
    ),
    "event_anchor": replace(
        DEFAULT_SCORING_PROFILE,
        name="event_anchor",
        personal_fit_weight=0.24,
        group_fit_weight=0.20,
        authenticity_weight=0.21,
        quality_weight=0.12,
        context_fit_weight=0.06,
        time_fit_weight=0.08,
        novelty_weight=0.04,
        exploration_weight=0.04,
        value_weight=0.04,
        local_event_weight=0.16,
        session_context_weight=0.10,
        friend_history_weight=0.12,
        diversity_new_group_bonus=0.09,
        intent_coverage_bonus_per_group=0.08,
        intent_coverage_bonus_max=0.16,
    ),
}

TAG_GROUP_SEARCH_TYPES = {
    "food_drink": [
        "restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "bakery",
        "bar",
    ],
    "coffee_sweets": [
        "cafe",
        "coffee_shop",
        "dessert_restaurant",
        "ice_cream_shop",
        "tea_house",
    ],
    "arts_culture": [
        "museum",
        "art_gallery",
        "historical_landmark",
        "performing_arts_theater",
        "tourist_attraction",
    ],
    "outdoors": [
        "park",
        "hiking_area",
        "garden",
        "zoo",
        "aquarium",
    ],
    "nightlife": [
        "bar",
        "night_club",
        "comedy_club",
        "concert_hall",
    ],
    "entertainment": [
        "amusement_park",
        "movie_theater",
        "concert_hall",
        "performing_arts_theater",
        "comedy_club",
    ],
    "shopping": [
        "market",
        "book_store",
        "clothing_store",
        "shopping_mall",
    ],
    "wellness": [
        "spa",
    ],
    "local_gems": [
        "tourist_attraction",
        "restaurant",
        "park",
        "art_gallery",
        "market",
    ],
}

TYPE_DIVERSITY_GROUPS = {
    "food_drink": {
        "restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "mexican_restaurant",
        "seafood_restaurant",
        "sandwich_shop",
        "bar",
    },
    "coffee_sweets": {
        "cafe",
        "coffee_shop",
        "bakery",
        "dessert_restaurant",
        "ice_cream_shop",
        "tea_house",
    },
    "arts_culture": {
        "museum",
        "art_gallery",
        "historical_landmark",
        "performing_arts_theater",
        "concert_hall",
        "comedy_club",
    },
    "outdoors": {
        "park",
        "hiking_area",
        "garden",
        "zoo",
        "aquarium",
    },
    "shopping_market": {
        "market",
        "book_store",
        "clothing_store",
        "shopping_mall",
    },
    "wellness": {
        "spa",
    },
}

TIME_CONTEXT_TYPES = {
    "morning": {
        "preferred": {"cafe", "coffee_shop", "bakery", "breakfast_restaurant", "brunch_restaurant", "park", "garden"},
        "avoid": {"bar", "night_club"},
    },
    "midday": {
        "preferred": {"restaurant", "lunch_restaurant", "museum", "art_gallery", "park", "market", "book_store"},
        "avoid": set(),
    },
    "afternoon": {
        "preferred": {"museum", "art_gallery", "park", "market", "tourist_attraction", "cafe", "book_store"},
        "avoid": set(),
    },
    "evening": {
        "preferred": {"restaurant", "bar", "concert_hall", "performing_arts_theater", "comedy_club", "night_club"},
        "avoid": {"breakfast_restaurant"},
    },
    "late_night": {
        "preferred": {"bar", "night_club", "concert_hall", "comedy_club", "restaurant"},
        "avoid": {"museum", "art_gallery", "park", "garden", "breakfast_restaurant"},
    },
}


def _json_loads(value, default=None):
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def _json_dumps(value):
    return json.dumps(value or {}, sort_keys=True)


def _normalize_name(name):
    return " ".join((name or "").lower().strip().split())


def _haversine_meters(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None

    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _signed_clamp(value, minimum=-1.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _expand_preference_tag(tag):
    normalized = (tag or "").strip()
    return TAG_GROUP_SEARCH_TYPES.get(normalized, [normalized] if normalized else [])


def _travel_time_estimates(distance_meters):
    if distance_meters is None:
        return None

    return {
        "walk_minutes": max(1, round(distance_meters / 80)),
        "drive_minutes": max(1, round(distance_meters / 500)),
        "transit_minutes": max(2, round(distance_meters / 300) + 5),
    }


def _candidate_types(candidate):
    types = candidate.get("types") or candidate.get("categories") or []
    if isinstance(types, str):
        return {types}
    return {str(place_type).lower().strip() for place_type in types}


def _constraint_types(values):
    resolved = set()
    for value in values or []:
        normalized = str(value or "").strip().lower()
        if not normalized:
            continue
        resolved.add(normalized)
        resolved.update(TYPE_DIVERSITY_GROUPS.get(normalized, set()))
        resolved.update(TAG_GROUP_SEARCH_TYPES.get(normalized, []))
    return {item.lower().strip() for item in resolved if item}


def _diversity_groups_for_types(types):
    groups = {
        group
        for group, group_types in TYPE_DIVERSITY_GROUPS.items()
        if types.intersection(group_types)
    }
    return groups or {"local_finds"}


def _intent_groups_for_tags(tags):
    groups = set()
    for tag in tags or []:
        normalized = str(tag or "").strip().lower()
        if not normalized:
            continue
        if normalized in TYPE_DIVERSITY_GROUPS:
            groups.add(normalized)
            continue
        matched_groups = _diversity_groups_for_types({normalized})
        if matched_groups == {"local_finds"} and normalized not in {"local_finds", "local_gems"}:
            continue
        groups.update(matched_groups)
    return groups


def _event_recency_multiplier(occurred_at, now=None):
    """Keep old taste signals as a prior while letting fresh behavior steer."""
    if not occurred_at:
        return 1.0
    now = now or datetime.utcnow()
    age_days = max(0, (now - occurred_at).total_seconds() / 86400)
    return 0.5 ** (age_days / PREFERENCE_EVENT_HALF_LIFE_DAYS)


def _preference_vector_cache_is_fresh(row, now=None):
    if not row or not row.updated_at:
        return False
    now = now or datetime.utcnow()
    return now - row.updated_at < timedelta(hours=PREFERENCE_VECTOR_CACHE_TTL_HOURS)


def _average_vector_value(member_vectors, key, default=0.75):
    values = [
        vector.get(key)
        for vector in (member_vectors or {}).values()
        if vector.get(key) is not None
    ]
    if not values:
        return default
    return _clamp(sum(values) / len(values))


def _affinity_multiplier(value, baseline=0.75, scale=0.6, minimum=0.7, maximum=1.18):
    return _clamp(1 + ((value - baseline) * scale), minimum, maximum)


class RecommendationService:
    """Build preference vectors, score places, and log recommendation events."""

    def __init__(self, provider_registry=None, scoring_profile=None, learned_model=None, learned_model_path=None):
        self.provider_registry = provider_registry or ProviderRegistry()
        self.scoring_profile = scoring_profile or DEFAULT_SCORING_PROFILE
        self.model_service = LearningToRankBaselineService()
        self.learned_model = learned_model or self._load_learned_model(learned_model_path)

    def recommend(self, user, location, radius_meters=3200, member_ids=None, constraints=None, mode="spontaneous"):
        constraints = constraints or {}
        scoring_profile = self._resolve_scoring_profile(constraints)
        members = self._resolve_members(user, member_ids or [])
        request_id = str(uuid4())

        member_vectors = {
            member.id: self.build_preference_vector(member)
            for member in members
        }
        member_insights = [
            self.preference_insights(member, member_vectors.get(member.id))
            for member in members
        ]
        boost_query_tags = list(dict.fromkeys(
            str(tag).strip()
            for tag in constraints.get("boost_query_tags") or []
            if tag is not None and str(tag).strip()
        ))
        query_tags = self._query_tags(
            member_vectors.values(),
            user,
            boost_tags=boost_query_tags,
        )
        retrieval_context = self._retrieval_context(query_tags, boost_query_tags=boost_query_tags)
        intent_target_groups = self._intent_target_groups(member_vectors.values(), query_tags, constraints)

        raw_candidates, provider_errors = self.provider_registry.search(
            query_tags,
            location,
            radius_meters=radius_meters,
            constraints=constraints,
        )

        place_history = self._place_history(user)
        friend_place_history = self._friend_place_history(members[1:])
        session_context = self._session_context(user)
        decided_place_ids = {
            place_id
            for place_id, history in place_history.items()
            if history.get("accepted") or history.get("rejected")
        } if constraints.get("exclude_decided", True) else set()
        scored, skipped_decided, filter_summary = self._score_candidates(
            raw_candidates=raw_candidates,
            user=user,
            members=members,
            member_vectors=member_vectors,
            constraints=constraints,
            location=location,
            radius_meters=radius_meters,
            mode=mode,
            decided_place_ids=decided_place_ids,
            place_history=place_history,
            friend_place_history=friend_place_history,
            scoring_profile=scoring_profile,
            session_context=session_context,
            allow_decided=False,
        )

        repeated_decided = False
        repeat_filter_summary = None
        if not scored and skipped_decided and constraints.get("repeat_decided_on_exhaustion", True):
            scored, _, repeat_filter_summary = self._score_candidates(
                raw_candidates=skipped_decided,
                user=user,
                members=members,
                member_vectors=member_vectors,
                constraints=constraints,
                location=location,
                radius_meters=radius_meters,
                mode=mode,
                decided_place_ids=set(),
                place_history=place_history,
                friend_place_history=friend_place_history,
                scoring_profile=scoring_profile,
                session_context=session_context,
                allow_decided=True,
            )
            repeated_decided = bool(scored)

        db.session.commit()
        scored.sort(key=lambda item: item["score"], reverse=True)
        self._apply_exploration_budget(scored, constraints, scoring_profile)
        scored.sort(key=lambda item: item["score"], reverse=True)
        learned_rerank_applied = self._apply_learned_rerank_if_requested(scored, constraints)
        scored, local_auth_guardrail_count = self._apply_local_authenticity_slate_guardrail(
            scored,
            constraints,
        )
        filter_summary["local_authenticity_guardrail"] = (
            filter_summary.get("local_authenticity_guardrail", 0)
            + local_auth_guardrail_count
        )
        limit = constraints.get("limit", 20)
        recommendations = self._diversify_ranked_results(
            scored,
            limit,
            constraints,
            scoring_profile,
            intent_target_groups,
        )
        if constraints.get("record_impressions", True):
            self._record_impressions_for_recommendations(
                recommendations=recommendations,
                user=user,
                members=members,
                mode=mode,
                request_id=request_id,
                constraints=constraints,
                query_tags=query_tags,
                retrieval_context=retrieval_context,
                intent_target_groups=intent_target_groups,
            )
        db.session.commit()
        filter_summary_payload = self._filter_summary_payload(
            filter_summary,
            repeat_filter_summary,
            len(raw_candidates),
            len(recommendations),
            constraints,
        )
        group_fit_summary = self._group_fit_summary(recommendations, members, member_vectors)
        slate_summary = self._slate_summary(recommendations, members, intent_target_groups)
        return {
            "mode": mode,
            "request_id": request_id,
            "scoring_profile": scoring_profile.name,
            "available_scoring_profiles": sorted(SCORING_PROFILES.keys()),
            "member_count": len(members),
            "members": [self._member_payload(member) for member in members],
            "preference_insights": member_insights,
            "group_fit_summary": group_fit_summary,
            "slate_summary": slate_summary,
            "recommendation_quality": self._recommendation_quality_summary(
                recommendations,
                members,
                group_fit_summary,
                provider_errors,
                filter_summary_payload,
                repeated_decided,
                slate_summary,
                member_insights,
                learned_rerank_applied,
            ),
            "query_tags": query_tags,
            "retrieval_context": retrieval_context,
            "session_context": session_context,
            "intent_target_groups": sorted(intent_target_groups),
            "provider_errors": provider_errors,
            "repeated_decided": repeated_decided,
            "learned_rerank": learned_rerank_applied,
            "filter_summary": filter_summary_payload,
            "recommendations": recommendations,
        }

    def record_event(self, user, place, event_type, provider_ref=None, event_value=None, context="solo", metadata=None, commit=True):
        if event_type not in EVENT_WEIGHTS:
            raise ValueError(f"Unsupported event_type: {event_type}")

        event = UserPlaceEvent(
            user_id=user.id,
            place_id=place.id,
            provider_ref_id=provider_ref.id if provider_ref else None,
            event_type=event_type,
            event_value=event_value,
            context=context,
            metadata_json=_json_dumps(metadata),
        )
        db.session.add(event)

        if commit:
            if event_type != "impression":
                self.rebuild_preference_vector(user, commit=False)
            db.session.commit()

        return event

    def preference_insights(self, user, vector=None):
        vector = vector or self.build_preference_vector(user)
        events = (
            UserPlaceEvent.query
            .filter_by(user_id=user.id)
            .order_by(UserPlaceEvent.occurred_at.desc())
            .all()
        )
        signal_events = [event for event in events if EVENT_WEIGHTS.get(event.event_type, 0) != 0 or event.event_type == "rate"]
        event_counts = {}
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        confidence = _clamp(len(signal_events) / 12.0)
        if len(signal_events) >= 8:
            learning_status = "personalized"
        elif len(signal_events) >= 3:
            learning_status = "learning"
        else:
            learning_status = "cold_start"

        return {
            "user_id": user.id,
            "display_name": user.display_name or user.username or "Adventourer",
            "learning_status": learning_status,
            "confidence": round(confidence, 3),
            "signal_count": len(signal_events),
            "event_counts": event_counts,
            "top_categories": self._top_vector_entries(vector.get("categories", {}), positive=True),
            "avoided_categories": self._top_vector_entries(vector.get("categories", {}), positive=False),
            "top_cuisines": self._top_vector_entries(vector.get("cuisines", {}), positive=True),
            "top_activities": self._top_vector_entries(vector.get("activities", {}), positive=True),
            "avoid_chains": round(vector.get("avoid_chains", 0.75), 3),
            "hidden_gem_affinity": round(vector.get("hidden_gem_affinity", 0.75), 3),
            "price_preference": vector.get("price_preference"),
            "last_signal_at": signal_events[0].occurred_at.isoformat() if signal_events else None,
        }

    def _score_candidates(
        self,
        raw_candidates,
        user,
        members,
        member_vectors,
        constraints,
        location,
        radius_meters,
        mode,
        decided_place_ids,
        place_history,
        scoring_profile,
        friend_place_history=None,
        session_context=None,
        allow_decided=False,
    ):
        friend_place_history = friend_place_history or {}
        scored = []
        skipped_decided = []
        seen_place_ids = set()
        skip_summary = {
            "raw_candidates": len(raw_candidates or []),
            "not_discoverable": 0,
            "hard_constraints": 0,
            "duplicates": 0,
            "decided": 0,
            "distance": 0,
            "non_positive_score": 0,
            "local_authenticity_guardrail": 0,
        }
        local_event_candidates = self._local_event_candidates(location, radius_meters, constraints)

        for candidate in raw_candidates:
            candidate_types = _candidate_types(candidate)
            if not is_discoverable_candidate(
                candidate.get("name"),
                candidate.get("types") or candidate.get("categories") or [],
            ):
                skip_summary["not_discoverable"] += 1
                continue
            if not self._passes_hard_type_constraints(candidate_types, constraints):
                skip_summary["hard_constraints"] += 1
                continue

            place, provider_ref, feature = self.upsert_candidate(candidate)
            if not place or place.id in seen_place_ids:
                skip_summary["duplicates"] += 1
                continue
            seen_place_ids.add(place.id)
            if place.id in decided_place_ids and not allow_decided:
                skipped_decided.append(candidate)
                skip_summary["decided"] += 1
                continue

            distance_meters = _haversine_meters(
                location.get("latitude"),
                location.get("longitude"),
                place.latitude,
                place.longitude,
            )
            if distance_meters is not None and distance_meters > radius_meters:
                skip_summary["distance"] += 1
                continue
            local_event_match = self._best_local_event_match_for_place(
                place=place,
                feature=feature,
                candidate_types=candidate_types,
                events=local_event_candidates,
                constraints=constraints,
                members=members,
                user=user,
            )

            score = self._score_place(
                feature=feature,
                candidate=candidate,
                members=members,
                member_vectors=member_vectors,
                constraints=constraints,
                distance_meters=distance_meters,
                radius_meters=radius_meters,
                mode=mode,
                history=place_history.get(place.id, {}),
                scoring_profile=scoring_profile,
                session_context=session_context,
                allow_decided=allow_decided,
                local_event_match=local_event_match,
                friend_history=friend_place_history.get(place.id, {}),
            )
            if score["score"] <= 0:
                skip_summary["non_positive_score"] += 1
                continue

            scored.append({
                "place_id": place.id,
                "provider_ref_id": provider_ref.id if provider_ref else None,
                "provider": candidate.get("provider"),
                "provider_place_id": candidate.get("place_id") or candidate.get("fsq_id"),
                "name": place.canonical_name,
                "category": self._recommendation_category(candidate),
                "latitude": place.latitude,
                "longitude": place.longitude,
                "distance_meters": round(distance_meters) if distance_meters is not None else None,
                "travel_times": _travel_time_estimates(distance_meters),
                "score": round(score["score"], 3),
                "base_rank_score": round(score["score"], 3),
                "ranking": score["ranking"],
                "components": score["components"],
                "member_fit": score["member_fit"],
                "party_fit_summary": score["party_fit_summary"],
                "model_features": self._model_feature_payload(feature),
                "explanation": score["explanation"],
                "explanation_details": score["explanation_details"],
                "recommendation_story": score["recommendation_story"],
                "history": score["history"],
                "authenticity_evidence": self._authenticity_evidence(feature, candidate),
                "local_event_match": local_event_match,
                "diversity_groups": sorted(_diversity_groups_for_types(candidate_types)),
                "display": self._display_payload(candidate),
                "repeat_after_exhaustion": allow_decided,
            })

        return scored, skipped_decided, skip_summary

    def _apply_exploration_budget(self, scored, constraints, profile):
        if not scored or constraints.get("exploration_budget", True) is False:
            return

        limit = int(constraints.get("limit", 20) or 20)
        max_exploratory = max(
            1,
            int(math.ceil(limit * max(0, min(1, profile.exploration_page_share)))),
        )
        frontier_score = max(
            item.get("ranking", {}).get("exploitation_score", item.get("score", 0))
            for item in scored
        )
        eligible_items = []

        for item in scored:
            components = item.get("components") or {}
            ranking = item.setdefault("ranking", {})
            exploration = _clamp(components.get("exploration", 0) or 0)
            if exploration <= 0:
                ranking["exploration_budget"] = {
                    "eligible": False,
                    "allowed": False,
                    "reason": "not_exploratory",
                }
                continue

            exploitation_score = ranking.get("exploitation_score", item.get("score", 0))
            frontier_gap = max(0, frontier_score - exploitation_score)
            guardrail = self._exploration_guardrail(item)
            friend_learning = self._exploration_friend_learning(item)

            ranking["exploration_budget"] = {
                "eligible": True,
                "allowed": False,
                "frontier_gap": round(frontier_gap, 3),
                "max_page_share": round(profile.exploration_page_share, 3),
                "max_exploratory": max_exploratory,
                "reason": None,
                "authenticity_guardrail": guardrail,
                "friend_learning": friend_learning["enabled"],
                "served_learning_members": friend_learning["members"],
            }

            if frontier_gap > profile.exploration_frontier_gap:
                ranking["exploration_budget"]["reason"] = "outside_score_frontier"
                continue
            if not guardrail["allowed"]:
                ranking["exploration_budget"]["reason"] = guardrail["reason"]
                continue

            eligible_items.append((
                item,
                (
                    0 if friend_learning["enabled"] else 1,
                    frontier_gap,
                    -_safe_float(components.get("authenticity")),
                    -exploration,
                ),
            ))

        eligible_items.sort(key=lambda row: row[1])
        allowed_items = {
            id(item)
            for item, _ in eligible_items[:max_exploratory]
        }

        for item, _ in eligible_items:
            ranking = item.setdefault("ranking", {})
            budget = ranking.setdefault("exploration_budget", {})
            if id(item) in allowed_items:
                budget["allowed"] = True
                budget["reason"] = "friend_learning_allowed" if budget.get("friend_learning") else "allowed"
            else:
                budget["reason"] = "too_many_exploratory_picks"

        for item in scored:
            components = item.get("components") or {}
            ranking = item.setdefault("ranking", {})
            budget = ranking.get("exploration_budget") or {}
            if not budget.get("eligible") or budget.get("allowed"):
                continue
            exploration = _clamp(components.get("exploration", 0) or 0)
            exploration_boost = exploration * profile.exploration_weight
            item["score"] = round(_clamp(item["score"] - exploration_boost), 3)
            components["exploration_applied"] = 0
            ranking["objective_breakdown"] = self._objective_breakdown(
                components,
                profile,
                final_score=item["score"],
            )

    def _exploration_guardrail(self, item):
        components = item.get("components") or {}
        model_features = item.get("model_features") or {}
        authenticity = _safe_float(components.get("authenticity", model_features.get("authenticity_score")))
        chain_probability = _safe_float(model_features.get("chain_probability"))
        tourist_trap_score = _safe_float(model_features.get("tourist_trap_score"))
        chain_penalty = _safe_float(components.get("chain_penalty"))
        friend_fit_rows = [
            member
            for index, member in enumerate(item.get("member_fit") or [])
            if index > 0
        ]
        weak_friend_count = sum(
            1
            for member in friend_fit_rows
            if _safe_float(member.get("fit")) < MEMBER_COVERAGE_FIT_THRESHOLD
        )

        allowed = (
            authenticity >= 0.5
            and chain_probability < 0.7
            and tourist_trap_score < 0.55
            and chain_penalty <= 0
            and weak_friend_count == 0
        )
        if allowed:
            reason = "passes_local_guardrail"
        elif weak_friend_count > 0:
            reason = "group_fit_guardrail"
        elif authenticity < 0.5:
            reason = "authenticity_guardrail"
        elif chain_probability >= 0.7 or chain_penalty > 0:
            reason = "chain_guardrail"
        else:
            reason = "tourist_trap_guardrail"

        return {
            "allowed": allowed,
            "reason": reason,
            "authenticity": round(authenticity, 3),
            "chain_probability": round(chain_probability, 3),
            "tourist_trap_score": round(tourist_trap_score, 3),
            "weak_friend_count": weak_friend_count,
        }

    def _exploration_friend_learning(self, item):
        members = [
            member.get("display_name") or "Traveler"
            for index, member in enumerate(item.get("member_fit") or [])
            if index > 0 and _safe_float(member.get("fit")) >= MEMBER_COVERAGE_FIT_THRESHOLD
        ]
        return {
            "enabled": bool(members),
            "members": members[:3],
        }

    def _load_learned_model(self, learned_model_path=None):
        model_path = learned_model_path or os.getenv("ADVENTOUR_LEARNED_RANKER_PATH")
        if not model_path:
            return None
        resolved_path = Path(model_path)
        if not resolved_path.is_absolute():
            resolved_path = Path(__file__).resolve().parents[2] / resolved_path
        try:
            return self.model_service.load_model(str(resolved_path))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def learned_ranker_status(self):
        """Return a cheap readiness report for the optional learned reranker."""
        status = learned_ranker_artifact_status(self.learned_model)
        if status.get("reason") == "no_model":
            return {
                **status,
                "message": "No learned ranker model is loaded on the backend.",
            }
        return status

    def _learned_rerank_enabled(self, constraints):
        configured_default = str(os.getenv("ADVENTOUR_ENABLE_LEARNED_RERANK", "")).strip().lower()
        return bool(
            constraints.get("learned_rerank")
            or constraints.get("use_learned_rerank")
            or configured_default in {"1", "true", "yes", "on"}
        )

    def _apply_learned_rerank_if_requested(self, scored, constraints):
        if not scored or not self.learned_model or not self._learned_rerank_enabled(constraints):
            return {
                "applied": False,
                "reason": "not_enabled" if not self._learned_rerank_enabled(constraints) else "no_model",
                "model_type": (self.learned_model or {}).get("model_type") if self.learned_model else None,
            }

        safety = self._learned_rerank_safety(constraints)
        if not safety["allowed"]:
            return {
                "applied": False,
                "reason": safety["reason"],
                "model_type": self.learned_model.get("model_type"),
                "feature_compatibility": safety.get("feature_compatibility"),
                "promotion_gate": safety.get("promotion_gate"),
                "training_data_health": safety.get("training_data_health"),
                "override_available": safety.get("override_available", False),
            }

        for index, item in enumerate(scored, start=1):
            example = self._model_example_from_recommendation(item, index)
            learned_score = self.model_service.predict(example, self.learned_model)
            runtime_guard = self._learned_runtime_guard(item)
            item["learned_score"] = learned_score
            item["ranking"] = {
                **(item.get("ranking") or {}),
                "learned_model_score": learned_score,
                "learned_model_type": self.learned_model.get("model_type"),
                "learned_runtime_guard": runtime_guard,
            }

        scored.sort(
            key=lambda item: (
                (item.get("ranking") or {}).get("learned_runtime_guard", {}).get("sort_bucket", 0),
                item.get("learned_score", 0),
                item.get("score", 0),
            ),
            reverse=True,
        )
        for index, item in enumerate(scored, start=1):
            item["learned_rank_position"] = index

        guard_summary = self._learned_runtime_guard_summary(scored)
        return {
            "applied": True,
            "model_type": self.learned_model.get("model_type"),
            "recommendation_count": len(scored),
            "feature_compatibility": safety.get("feature_compatibility"),
            "promotion_gate": safety.get("promotion_gate"),
            "training_data_health": safety.get("training_data_health"),
            "override_applied": safety.get("override_applied", False),
            "runtime_guard": guard_summary,
        }

    def _learned_runtime_guard(self, item):
        """Keep a learned model inside Adventour's live mission guardrails."""
        components = item.get("components") or {}
        model_features = item.get("model_features") or {}
        authenticity = _safe_float(components.get("authenticity", model_features.get("authenticity_score")))
        chain_probability = _safe_float(model_features.get("chain_probability"))
        chain_penalty = _safe_float(components.get("chain_penalty"))
        tourist_trap = _safe_float(model_features.get("tourist_trap_score"))
        group_member_count = int(components.get("group_member_count") or 1)
        group_min_fit = _safe_float(components.get("group_min_fit"), 1.0)
        group_fairness_penalty = _safe_float(components.get("group_fairness_penalty"))

        checks = [
            self._learned_runtime_guard_check(
                "chain_generic_risk",
                "Chain/generic risk stays below Adventour limit",
                "fail" if chain_probability >= 0.65 or chain_penalty > 0 else "warn" if chain_probability >= 0.35 else "pass",
                max(chain_probability, chain_penalty),
                "Avoid chain-like picks above 65% risk",
                "Transparent ranker keeps this pick from jumping ahead of local options.",
            ),
            self._learned_runtime_guard_check(
                "local_authenticity",
                "Local-authentic signal remains credible",
                "fail" if authenticity < 0.45 or tourist_trap >= 0.6 else "warn" if authenticity < 0.55 or tourist_trap >= 0.4 else "pass",
                authenticity,
                "55%+ local-authentic signal preferred",
                "Use the transparent score until the model preserves local texture.",
            ),
        ]
        if group_member_count > 1:
            checks.append(
                self._learned_runtime_guard_check(
                    "group_fairness",
                    "Travel-party fairness is protected",
                    "fail" if group_min_fit < 0.4 or group_fairness_penalty >= 0.35 else "warn" if group_min_fit < MEMBER_COVERAGE_FIT_THRESHOLD or group_fairness_penalty > 0 else "pass",
                    group_min_fit,
                    f"{MEMBER_COVERAGE_FIT_THRESHOLD:.0%}+ lowest member fit preferred",
                    "Keep group-friendly ordering until the learned model serves every traveler.",
                )
            )

        statuses = [check["status"] for check in checks]
        status = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
        return {
            "status": status,
            "sort_bucket": 0 if status == "fail" else 1 if status == "warn" else 2,
            "checks": checks,
        }

    def _learned_runtime_guard_check(self, name, label, status, value, target, message):
        return {
            "name": name,
            "label": label,
            "status": status,
            "value": round(_clamp(value), 3),
            "target": target,
            "message": message,
        }

    def _learned_runtime_guard_summary(self, scored):
        guards = [
            (item.get("ranking") or {}).get("learned_runtime_guard") or {}
            for item in scored
        ]
        counts = {
            "pass": sum(1 for guard in guards if guard.get("status") == "pass"),
            "warn": sum(1 for guard in guards if guard.get("status") == "warn"),
            "fail": sum(1 for guard in guards if guard.get("status") == "fail"),
        }
        if counts["fail"]:
            headline = "Learned beta was constrained by Adventour authenticity and party guardrails."
        elif counts["warn"]:
            headline = "Learned beta ran with watch-list guardrails active."
        else:
            headline = "Learned beta stayed within Adventour live guardrails."
        return {
            "status": "constrained" if counts["fail"] else "watch" if counts["warn"] else "pass",
            "headline": headline,
            "counts": counts,
        }

    def _learned_rerank_safety(self, constraints):
        artifact_status = learned_ranker_artifact_status(self.learned_model or {})
        feature_compatibility = model_feature_compatibility(self.learned_model or {})
        training_data_health = artifact_status.get("training_data_health")
        if feature_compatibility["status"] != "pass":
            return {
                "allowed": False,
                "reason": feature_compatibility["reason"],
                "feature_compatibility": feature_compatibility,
                "promotion_gate": self._learned_promotion_payload((self.learned_model or {}).get("promotion_gate")),
                "training_data_health": training_data_health,
            }

        allow_unpromoted = (
            bool(constraints.get("allow_unpromoted_learned_rerank"))
            or str(os.getenv("ADVENTOUR_ALLOW_UNPROMOTED_LEARNED_RERANK", "")).strip().lower()
            in {"1", "true", "yes", "on"}
        )
        promotion_gate = (self.learned_model or {}).get("promotion_gate")
        promotion_payload = self._learned_promotion_payload(promotion_gate)

        if allow_unpromoted:
            return {
                "allowed": True,
                "reason": "override",
                "feature_compatibility": feature_compatibility,
                "promotion_gate": promotion_payload,
                "training_data_health": training_data_health,
                "override_applied": True,
            }

        if artifact_status.get("reason") in {"training_data_needs_data", "training_data_unknown"}:
            return {
                "allowed": False,
                "reason": artifact_status.get("reason"),
                "feature_compatibility": feature_compatibility,
                "promotion_gate": promotion_payload,
                "training_data_health": training_data_health,
                "override_available": True,
            }

        if not promotion_gate:
            return {
                "allowed": False,
                "reason": "promotion_gate_missing",
                "feature_compatibility": feature_compatibility,
                "promotion_gate": promotion_payload,
                "training_data_health": training_data_health,
                "override_available": True,
            }

        if promotion_gate.get("can_promote") is True and promotion_gate.get("status") == "pass":
            return {
                "allowed": True,
                "reason": "promotion_gate_passed",
                "feature_compatibility": feature_compatibility,
                "promotion_gate": promotion_payload,
                "training_data_health": training_data_health,
            }

        return {
            "allowed": False,
            "reason": f"promotion_gate_{promotion_gate.get('status') or 'failed'}",
            "feature_compatibility": feature_compatibility,
            "promotion_gate": promotion_payload,
            "training_data_health": training_data_health,
            "override_available": True,
        }

    def _learned_promotion_payload(self, promotion_gate):
        if not promotion_gate:
            return {
                "status": "missing",
                "can_promote": False,
                "summary": "This model has not been evaluated against Adventour's ranking, local-quality, and group-balance gates.",
                "checks": [],
            }

        checks = promotion_gate.get("checks") or []
        return {
            "status": promotion_gate.get("status"),
            "can_promote": promotion_gate.get("can_promote") is True,
            "summary": promotion_gate.get("summary"),
            "checks": [
                {
                    "name": check.get("name"),
                    "label": check.get("label"),
                    "status": check.get("status"),
                    "value": check.get("value"),
                    "message": check.get("message"),
                }
                for check in checks
            ],
        }

    def _model_feature_payload(self, feature):
        return {
            "price_band": feature.price_band,
            "chain_probability": feature.chain_probability,
            "authenticity_score": feature.authenticity_score,
            "hidden_gem_score": feature.hidden_gem_score,
            "tourist_trap_score": feature.tourist_trap_score,
            "quality_score": feature.quality_score_adventour,
            "popularity_score": feature.popularity_score_adventour,
        }

    def _model_example_from_recommendation(self, item, rank_position):
        model_features = item.get("model_features") or {}
        ranking = item.get("ranking") or {}
        components = item.get("components") or {}
        return {
            "request_id": "runtime",
            "rank_position": rank_position,
            "model_score": item.get("score"),
            "base_rank_score": item.get("base_rank_score"),
            "components": components,
            "group_min_fit": components.get("group_min_fit"),
            "group_fairness_penalty": components.get("group_fairness_penalty"),
            "exploration": components.get("exploration"),
            "exploration_uncertainty": components.get("exploration_uncertainty"),
            "preference_confidence": components.get("preference_confidence"),
            "average_member_signal_count": components.get("average_member_signal_count"),
            "session_context_fit": components.get("session_context_fit"),
            "session_context_signal_count": components.get("session_context_signal_count"),
            "friend_history_fit": components.get("friend_history_fit"),
            "friend_history_signal_count": components.get("friend_history_signal_count"),
            "diversity_bonus": ranking.get("diversity_bonus"),
            "intent_coverage_bonus": ranking.get("intent_coverage_bonus"),
            "member_coverage_bonus": ranking.get("member_coverage_bonus"),
            "repeat_after_exhaustion": item.get("repeat_after_exhaustion", False),
            **model_features,
        }

    def _filter_summary_payload(self, primary_summary, repeat_summary, raw_count, returned_count, constraints):
        primary_summary = primary_summary or {}
        excluded_groups = list(constraints.get("excluded_tag_groups") or [])
        included_groups = list(constraints.get("included_tag_groups") or [])
        return {
            "raw_candidates": raw_count,
            "returned": returned_count,
            "skipped": primary_summary,
            "repeat_pass_skipped": repeat_summary,
            "hard_constraints_active": bool(
                excluded_groups
                or included_groups
                or constraints.get("excluded_types")
                or constraints.get("avoid_types")
                or constraints.get("required_types_any")
            ),
            "excluded_tag_groups": excluded_groups,
            "included_tag_groups": included_groups,
        }

    def _passes_hard_type_constraints(self, candidate_types, constraints):
        excluded_types = _constraint_types(
            list(constraints.get("excluded_types") or [])
            + list(constraints.get("avoid_types") or [])
            + list(constraints.get("excluded_tag_groups") or [])
        )
        if excluded_types and candidate_types.intersection(excluded_types):
            return False

        required_types = _constraint_types(
            list(constraints.get("required_types_any") or [])
            + list(constraints.get("included_tag_groups") or [])
        )
        if required_types and not candidate_types.intersection(required_types):
            return False

        return True

    def _local_event_candidates(self, location, radius_meters, constraints):
        constraints = constraints or {}
        if constraints.get("include_local_events") is False:
            return []

        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            return []

        now = datetime.utcnow()
        travel_dates = constraints.get("travel_dates") or {}
        start = self._parse_datetime(travel_dates.get("start")) or now
        end = self._parse_datetime(travel_dates.get("end")) or (start + timedelta(days=21))
        if end < start:
            end = start + timedelta(days=21)

        search_radius = max(int(radius_meters or 0), int(constraints.get("local_event_radius_meters") or 5000))
        rows = (
            LocalEvent.query
            .filter(
                LocalEvent.status == "active",
                LocalEvent.starts_at >= max(now, start),
                LocalEvent.starts_at <= end,
            )
            .all()
        )
        events = []
        for event in rows:
            distance_from_launch = _haversine_meters(latitude, longitude, event.latitude, event.longitude)
            if distance_from_launch is not None and distance_from_launch > search_radius:
                continue
            events.append({
                "event": event,
                "distance_from_launch_meters": distance_from_launch,
                "windowed": bool(travel_dates.get("start") or travel_dates.get("end")),
            })
        return events

    def _parse_datetime(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            return None

    def _best_local_event_match_for_place(self, place, feature, candidate_types, events, constraints, members=None, user=None):
        if not events or place.latitude is None or place.longitude is None:
            return None

        best = None
        selected_friend_ids = {
            member.id
            for member in (members or [])
            if user is None or member.id != user.id
        }
        for row in events:
            event = row["event"]
            distance_to_place = _haversine_meters(place.latitude, place.longitude, event.latitude, event.longitude)
            if distance_to_place is not None and distance_to_place > 2500:
                continue

            category_fit = self._local_event_category_fit(candidate_types, event.category)
            distance_fit = 0.5 if distance_to_place is None else _clamp(1 - (distance_to_place / 2500))
            authenticity = _clamp(event.authenticity_score or 0.75)
            source_fit = 0.65 if event.source_url or event.source_name or event.reservation_url else 0.35
            reservation_fit = 1.0 if event.reservation_url else 0.45
            hidden_gem_fit = _clamp(feature.hidden_gem_score or 0)
            social_context = self._local_event_social_context(event, selected_friend_ids)
            social_fit = min(1.0, social_context["signal"] or 0)
            score = _clamp(
                category_fit * 0.24
                + distance_fit * 0.24
                + authenticity * 0.22
                + source_fit * 0.10
                + reservation_fit * 0.08
                + hidden_gem_fit * 0.10
                + social_fit * 0.02
            )
            if not best or score > best["score"]:
                best = self._local_event_match_payload(
                    event=event,
                    score=score,
                    distance_to_place=distance_to_place,
                    distance_from_launch=row.get("distance_from_launch_meters"),
                    category_fit=category_fit,
                    distance_fit=distance_fit,
                    source_fit=source_fit,
                    reservation_fit=reservation_fit,
                    social_context=social_context,
                    windowed=row.get("windowed"),
                )

        return best

    def _local_event_social_context(self, event, selected_friend_ids=None):
        selected_friend_ids = set(selected_friend_ids or [])
        interests = list(getattr(event, "interests", []) or [])
        interested_count = sum(1 for interest in interests if interest.status == "interested")
        going_count = sum(1 for interest in interests if interest.status == "going")
        friend_interested_count = sum(
            1
            for interest in interests
            if interest.user_id in selected_friend_ids and interest.status == "interested"
        )
        friend_going_count = sum(
            1
            for interest in interests
            if interest.user_id in selected_friend_ids and interest.status == "going"
        )
        total_signal = interested_count + going_count
        friend_signal = friend_interested_count + friend_going_count
        signal = _clamp(
            min(1.0, friend_signal / 2) * 0.7
            + min(1.0, total_signal / 4) * 0.3
        )
        return {
            "interested_count": interested_count,
            "going_count": going_count,
            "friend_interested_count": friend_interested_count,
            "friend_going_count": friend_going_count,
            "friend_signal_count": friend_signal,
            "signal": round(signal, 3),
        }

    def _local_event_category_fit(self, candidate_types, event_category):
        candidate_types = {
            str(item).strip().lower()
            for item in candidate_types or []
            if str(item).strip()
        }
        category = (event_category or "").strip().lower()
        if not category:
            return 0.45
        category_tags = {category}
        category_tags.update(_expand_preference_tag(category))
        if candidate_types.intersection(category_tags):
            return 1.0
        if category in {"market", "makers", "popup", "food"} and candidate_types.intersection({
            "restaurant", "cafe", "bakery", "bar", "market", "shopping_mall", "book_store", "clothing_store",
        }):
            return 0.76
        if category in {"art", "gallery", "music", "concert", "theater", "comedy"} and candidate_types.intersection({
            "museum", "art_gallery", "performing_arts_theater", "concert_hall", "comedy_club", "bar",
        }):
            return 0.78
        if category in {"outdoor", "community"} and candidate_types.intersection({
            "park", "garden", "tourist_attraction", "museum", "historical_landmark", "cafe",
        }):
            return 0.68
        return 0.4

    def _local_event_match_payload(
        self,
        event,
        score,
        distance_to_place,
        distance_from_launch,
        category_fit,
        distance_fit,
        source_fit,
        reservation_fit,
        social_context=None,
        windowed=False,
    ):
        social_context = social_context or {}
        return {
            "event_id": event.id,
            "title": event.title,
            "category": event.category,
            "starts_at": event.starts_at.isoformat() if event.starts_at else None,
            "ends_at": event.ends_at.isoformat() if event.ends_at else None,
            "distance_to_place_meters": round(distance_to_place) if distance_to_place is not None else None,
            "distance_from_launch_meters": round(distance_from_launch) if distance_from_launch is not None else None,
            "score": round(score, 3),
            "fit_label": "During trip" if windowed else "Upcoming nearby",
            "source_name": event.source_name,
            "source_url": event.source_url,
            "reservation_url": event.reservation_url,
            "social": social_context,
            "components": {
                "category_fit": round(category_fit, 3),
                "distance_fit": round(distance_fit, 3),
                "source_fit": round(source_fit, 3),
                "reservation_fit": round(reservation_fit, 3),
                "social_signal": round(social_context.get("signal") or 0, 3),
                "authenticity": round(_clamp(event.authenticity_score or 0.75), 3),
            },
        }

    def _record_impressions_for_recommendations(
        self,
        recommendations,
        user,
        members,
        mode,
        request_id,
        constraints=None,
        query_tags=None,
        retrieval_context=None,
        intent_target_groups=None,
    ):
        context = "group" if len(members) > 1 else "solo"
        constraints = constraints or {}
        for index, item in enumerate(recommendations, start=1):
            item["request_id"] = request_id
            item["rank_position"] = index
            place = db.session.get(Place, item["place_id"])
            if not place:
                continue
            provider_ref = db.session.get(PlaceProviderRef, item.get("provider_ref_id")) if item.get("provider_ref_id") else None
            self.record_event(
                user=user,
                place=place,
                provider_ref=provider_ref,
                event_type="impression",
                context=context,
                metadata={
                    "request_id": request_id,
                    "rank_position": index,
                    "mode": mode,
                    "score": item.get("score"),
                    "base_rank_score": item.get("base_rank_score"),
                    "ranking": item.get("ranking", {}),
                    "components": item.get("components", {}),
                    "member_fit": item.get("member_fit", []),
                    "explanation_details": item.get("explanation_details", []),
                    "recommendation_story": item.get("recommendation_story", {}),
                    "authenticity_evidence": item.get("authenticity_evidence", {}),
                    "local_event_match": item.get("local_event_match"),
                    "repeat_after_exhaustion": item.get("repeat_after_exhaustion", False),
                    "history": item.get("history", {}),
                    "diversity_groups": item.get("diversity_groups", []),
                    "query_tags": query_tags or [],
                    "retrieval_context": retrieval_context or {},
                    "intent_target_groups": sorted(intent_target_groups or []),
                    "member_ids": [member.id for member in members],
                    "constraint_summary": {
                        "included_tag_groups": list(constraints.get("included_tag_groups") or []),
                        "excluded_tag_groups": list(constraints.get("excluded_tag_groups") or []),
                        "price_max": constraints.get("price_max"),
                        "scoring_profile": constraints.get("scoring_profile"),
                    },
                },
                commit=False,
            )

    def _apply_local_authenticity_slate_guardrail(self, scored, constraints):
        if not scored or constraints.get("avoid_chains", True) is False:
            return scored, 0

        limit = int(constraints.get("limit", 20) or 20)
        local_target = min(limit, max(3, math.ceil(limit * 0.5)))
        credible_local = [
            item for item in scored
            if self._is_credible_local_pick(item)
        ]
        if len(credible_local) < local_target:
            return scored, 0

        kept = []
        removed = []
        for item in scored:
            if self._is_generic_or_chain_risk_pick(item):
                ranking = item.setdefault("ranking", {})
                ranking["local_authenticity_guardrail"] = {
                    "removed": True,
                    "reason": "enough_local_alternatives",
                    "local_alternative_count": len(credible_local),
                }
                removed.append(item)
            else:
                kept.append(item)

        if len(kept) < local_target:
            return scored, 0

        return kept, len(removed)

    def _is_credible_local_pick(self, item):
        components = item.get("components") or {}
        model_features = item.get("model_features") or {}
        evidence = item.get("authenticity_evidence") or {}
        chain_probability = _safe_float(model_features.get("chain_probability"))
        chain_penalty = _safe_float(components.get("chain_penalty"))
        tourist_trap_score = _safe_float(model_features.get("tourist_trap_score"))
        authenticity = _safe_float(components.get("authenticity", model_features.get("authenticity_score")))
        label = evidence.get("label")
        return (
            label in {"Hidden gem", "Local-feeling"}
            or (
                authenticity >= 0.58
                and chain_probability < 0.45
                and chain_penalty <= 0
                and tourist_trap_score < 0.45
            )
        )

    def _is_generic_or_chain_risk_pick(self, item):
        components = item.get("components") or {}
        model_features = item.get("model_features") or {}
        evidence = item.get("authenticity_evidence") or {}
        return (
            evidence.get("label") == "Generic risk"
            or _safe_float(components.get("chain_penalty")) > 0
            or _safe_float(model_features.get("chain_probability")) >= 0.65
        )

    def _diversify_ranked_results(self, scored, limit, constraints, scoring_profile, intent_target_groups=None):
        if not scored or constraints.get("diversify_results", True) is False:
            return scored[:limit]

        intent_target_groups = set(intent_target_groups or [])
        remaining = list(scored)
        selected = []
        group_counts = {}
        type_counts = {}
        member_coverage = {}

        if (
            constraints.get("preserve_top_result", True)
            and remaining
            and self._should_preserve_top_result(remaining[0], remaining[1:], scoring_profile)
        ):
            first = remaining.pop(0)
            prior_ranking = first.get("ranking") or {}
            first["ranking"] = {
                **prior_ranking,
                "strategy": "score_then_diversity",
                "scoring_profile": scoring_profile.name,
                "diversity_adjusted_score": first["score"],
                "diversity_bonus": 0,
                "diversity_penalty": 0,
                "intent_coverage_bonus": 0,
                "covered_new_intents": [],
                "member_coverage_bonus": 0,
                "served_new_members": [],
                "preserved_top_pick": True,
            }
            selected.append(first)
            self._update_diversity_counts(first, group_counts, type_counts, member_coverage)

        while remaining and len(selected) < limit:
            best_index = 0
            best_score = None
            for index, item in enumerate(remaining):
                adjusted_score, diversity = self._diversity_adjusted_score(
                    item,
                    selected,
                    group_counts,
                    type_counts,
                    member_coverage,
                    scoring_profile,
                    intent_target_groups,
                )
                item["_diversity_preview"] = diversity
                if best_score is None or adjusted_score > best_score:
                    best_score = adjusted_score
                    best_index = index

            chosen = remaining.pop(best_index)
            diversity = (
                chosen.pop("_diversity_preview", None)
                or self._diversity_adjusted_score(
                    chosen,
                    selected,
                    group_counts,
                    type_counts,
                    member_coverage,
                    scoring_profile,
                    intent_target_groups,
                )[1]
            )
            prior_ranking = chosen.get("ranking") or {}
            chosen["ranking"] = {
                **prior_ranking,
                "strategy": "score_then_diversity",
                **diversity,
            }
            selected.append(chosen)
            self._update_diversity_counts(chosen, group_counts, type_counts, member_coverage)

        self._apply_party_coverage_rescue(selected, remaining, scoring_profile)
        self._apply_local_discovery_rescue(selected, remaining, scoring_profile)
        for item in selected:
            item.pop("_diversity_preview", None)
        return selected

    def _apply_local_discovery_rescue(self, selected, remaining, profile):
        if not selected or not remaining:
            return

        first_page_size = min(
            len(selected),
            max(1, int(getattr(profile, "local_discovery_first_page_size", 3) or 3)),
        )
        first_page = selected[:first_page_size]
        if any(self._is_credible_local_pick(item) for item in first_page):
            return

        rescue = self._best_remaining_local_discovery_rescue(remaining)
        if not rescue:
            return

        replace_index = self._local_discovery_replacement_index(selected, first_page_size, rescue, profile)
        if replace_index is None:
            return

        replaced = selected[replace_index]
        selected[replace_index] = rescue
        remaining.remove(rescue)
        remaining.append(replaced)
        rescue["ranking"] = {
            **(rescue.get("ranking") or {}),
            "strategy": "score_then_diversity",
            "local_discovery_rescue": True,
            "rescue_reason": "first_page_local_authenticity",
            "replaced_pick": replaced.get("name"),
            "score_gap": round(max(0, (replaced.get("score", 0) or 0) - (rescue.get("score", 0) or 0)), 3),
            "authenticity_gain": round(
                max(
                    0,
                    _safe_float((rescue.get("components") or {}).get("authenticity"))
                    - _safe_float((replaced.get("components") or {}).get("authenticity")),
                ),
                3,
            ),
        }

    def _best_remaining_local_discovery_rescue(self, remaining):
        candidates = [
            item for item in remaining
            if self._is_credible_local_pick(item)
            and not self._is_generic_or_chain_risk_pick(item)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (
                _safe_float((item.get("components") or {}).get("authenticity")),
                _safe_float((item.get("model_features") or {}).get("hidden_gem_score")),
                _safe_float(item.get("score")),
            ),
        )

    def _local_discovery_replacement_index(self, selected, first_page_size, rescue, profile):
        rescue_score = float(rescue.get("score") or 0)
        frontier_gap = float(getattr(profile, "local_discovery_frontier_gap", 0.18) or 0.18)
        coverage = self._selected_member_coverage(selected)
        rescue_serves = self._strong_fit_user_ids(rescue)
        replaceable = []
        for index, item in enumerate(selected[:first_page_size]):
            ranking = item.get("ranking") or {}
            if ranking.get("preserved_top_pick") and index == 0:
                continue
            if self._is_credible_local_pick(item):
                continue
            score_gap = max(0, float(item.get("score") or 0) - rescue_score)
            if score_gap > frontier_gap:
                continue

            item_serves = self._strong_fit_user_ids(item)
            removes_last_match = any(
                coverage.get(user_id, 0) <= 1
                and user_id not in rescue_serves
                for user_id in item_serves
            )
            if removes_last_match:
                continue

            item_components = item.get("components") or {}
            replaceable.append((
                _safe_float(item_components.get("authenticity")),
                -_safe_float(item_components.get("chain_penalty")),
                -score_gap,
                index,
            ))
        if not replaceable:
            return None
        return min(replaceable)[-1]

    def _apply_party_coverage_rescue(self, selected, remaining, profile):
        if len(selected) < 2 or not remaining:
            return
        if not any((item.get("components") or {}).get("group_member_count", 1) > 1 for item in selected + remaining):
            return

        coverage = self._selected_member_coverage(selected)
        underserved_member_ids = [
            user_id
            for user_id, count in coverage.items()
            if count == 0
        ]
        if not underserved_member_ids:
            return

        for user_id in underserved_member_ids:
            rescue = self._best_remaining_member_rescue(remaining, user_id)
            if not rescue:
                continue
            replace_index = self._party_rescue_replacement_index(selected, rescue, user_id)
            if replace_index is None:
                continue

            rescued_member = self._member_fit_row(rescue, user_id) or {}
            replaced = selected[replace_index]
            selected[replace_index] = rescue
            remaining.remove(rescue)
            remaining.append(replaced)
            rescue["ranking"] = {
                **(rescue.get("ranking") or {}),
                "strategy": "score_then_diversity",
                "party_coverage_rescue": True,
                "rescued_member": rescued_member.get("display_name") or "Traveler",
                "rescued_member_fit": round(float(rescued_member.get("fit") or 0), 3),
                "replaced_pick": replaced.get("name"),
                "rescue_reason": "member_without_strong_match",
                "score_gap": round(max(0, (replaced.get("score", 0) or 0) - (rescue.get("score", 0) or 0)), 3),
            }
            coverage = self._selected_member_coverage(selected)

    def _selected_member_coverage(self, items):
        coverage = {}
        for item in items:
            for fit_row in item.get("member_fit") or []:
                user_id = fit_row.get("user_id")
                if user_id is None:
                    continue
                coverage.setdefault(user_id, 0)
                if float(fit_row.get("fit") or 0) >= MEMBER_COVERAGE_FIT_THRESHOLD:
                    coverage[user_id] += 1
        return coverage

    def _member_fit_row(self, item, user_id):
        for fit_row in item.get("member_fit") or []:
            if fit_row.get("user_id") == user_id:
                return fit_row
        return None

    def _best_remaining_member_rescue(self, remaining, user_id):
        candidates = []
        for item in remaining:
            fit_row = self._member_fit_row(item, user_id)
            if not fit_row:
                continue
            fit = float(fit_row.get("fit") or 0)
            if fit < MEMBER_COVERAGE_FIT_THRESHOLD:
                continue
            components = item.get("components") or {}
            candidates.append((
                fit,
                float(components.get("group_min_fit") or 0),
                float(components.get("authenticity") or 0),
                float(item.get("score") or 0),
                item,
            ))
        if not candidates:
            return None
        return max(candidates, key=lambda row: row[:-1])[-1]

    def _party_rescue_replacement_index(self, selected, rescue, rescued_user_id):
        coverage = self._selected_member_coverage(selected)
        rescue_serves = self._strong_fit_user_ids(rescue)
        replaceable = []
        for index, item in enumerate(selected):
            ranking = item.get("ranking") or {}
            if ranking.get("preserved_top_pick") and index == 0:
                continue
            item_serves = self._strong_fit_user_ids(item)
            removes_last_match = any(
                coverage.get(user_id, 0) <= 1
                and user_id not in rescue_serves
                for user_id in item_serves
                if user_id != rescued_user_id
            )
            if removes_last_match:
                continue
            replaceable.append((
                len(item_serves),
                float(item.get("score") or 0),
                index,
            ))
        if not replaceable:
            return None
        return min(replaceable)[-1]

    def _strong_fit_user_ids(self, item):
        return {
            fit_row.get("user_id")
            for fit_row in item.get("member_fit") or []
            if fit_row.get("user_id") is not None
            and float(fit_row.get("fit") or 0) >= MEMBER_COVERAGE_FIT_THRESHOLD
        }

    def _should_preserve_top_result(self, top_item, alternatives, profile):
        components = top_item.get("components") or {}
        member_count = components.get("group_member_count", 1) or 1
        if profile.name != "group_friendly" or member_count <= 1:
            return True

        group_min_fit = components.get("group_min_fit")
        if group_min_fit is None or group_min_fit >= profile.group_low_fit_threshold:
            return True

        top_score = top_item.get("score", 0) or 0
        for alternative in alternatives or []:
            alternative_components = alternative.get("components") or {}
            alternative_min_fit = alternative_components.get("group_min_fit", 0) or 0
            if (
                alternative_components.get("group_member_count", 1) > 1
                and alternative_min_fit >= profile.group_low_fit_threshold
                and (alternative.get("score", 0) or 0) >= top_score - profile.exploration_frontier_gap
            ):
                return False
        return True

    def _diversity_adjusted_score(self, item, selected, group_counts, type_counts, member_coverage, profile, intent_target_groups=None):
        intent_target_groups = set(intent_target_groups or [])
        groups = item.get("diversity_groups") or ["local_finds"]
        types = item.get("display", {}).get("types") or []
        repeated_group_count = sum(group_counts.get(group, 0) for group in groups)
        repeated_type_count = sum(type_counts.get(place_type, 0) for place_type in types)
        new_group_bonus = (
            profile.diversity_new_group_bonus
            if any(group_counts.get(group, 0) == 0 for group in groups)
            else 0
        )
        authenticity_bonus = min(
            profile.diversity_authenticity_bonus_max,
            (item.get("components", {}).get("authenticity", 0) or 0)
            * profile.diversity_authenticity_bonus_weight,
        )
        covered_new_intents = sorted(
            group
            for group in groups
            if group in intent_target_groups and group_counts.get(group, 0) == 0
        )
        intent_coverage_bonus = min(
            profile.intent_coverage_bonus_max,
            len(covered_new_intents) * profile.intent_coverage_bonus_per_group,
        )
        served_new_members = [
            member.get("display_name") or "Traveler"
            for member in item.get("member_fit") or []
            if member.get("fit", 0) >= MEMBER_COVERAGE_FIT_THRESHOLD
            and member_coverage.get(member.get("user_id"), 0) == 0
        ]
        member_coverage_bonus = min(
            profile.member_coverage_bonus_max,
            len(served_new_members) * profile.member_coverage_bonus_per_member,
        )
        repeat_penalty = min(
            profile.diversity_repeat_penalty_max,
            repeated_group_count * profile.diversity_group_repeat_penalty
            + repeated_type_count * profile.diversity_type_repeat_penalty,
        )
        slate_similarity = self._slate_similarity(item, selected)
        slate_similarity_penalty = min(
            profile.slate_similarity_penalty_max,
            slate_similarity * profile.slate_similarity_penalty_weight,
        )
        adjusted_score = (
            item["score"]
            + new_group_bonus
            + authenticity_bonus
            + intent_coverage_bonus
            + member_coverage_bonus
            - repeat_penalty
            - slate_similarity_penalty
        )
        return adjusted_score, {
            "scoring_profile": profile.name,
            "diversity_adjusted_score": round(adjusted_score, 3),
            "diversity_bonus": round(new_group_bonus + authenticity_bonus, 3),
            "diversity_penalty": round(repeat_penalty + slate_similarity_penalty, 3),
            "repeat_penalty": round(repeat_penalty, 3),
            "slate_similarity": round(slate_similarity, 3),
            "slate_similarity_penalty": round(slate_similarity_penalty, 3),
            "intent_coverage_bonus": round(intent_coverage_bonus, 3),
            "covered_new_intents": covered_new_intents,
            "member_coverage_bonus": round(member_coverage_bonus, 3),
            "served_new_members": served_new_members,
        }

    def _slate_similarity(self, item, selected):
        if not selected:
            return 0.0

        item_groups = set(item.get("diversity_groups") or ["local_finds"])
        item_types = set(item.get("display", {}).get("types") or [])
        item_name_tokens = self._name_tokens(item.get("name"))
        strongest_similarity = 0.0

        for selected_item in selected:
            selected_groups = set(selected_item.get("diversity_groups") or ["local_finds"])
            selected_types = set(selected_item.get("display", {}).get("types") or [])
            selected_name_tokens = self._name_tokens(selected_item.get("name"))
            group_similarity = self._jaccard(item_groups, selected_groups)
            type_similarity = self._jaccard(item_types, selected_types)
            name_similarity = self._jaccard(item_name_tokens, selected_name_tokens)
            strongest_similarity = max(
                strongest_similarity,
                group_similarity * 0.46 + type_similarity * 0.39 + name_similarity * 0.15,
            )

        return _clamp(strongest_similarity)

    def _jaccard(self, left, right):
        left = set(left or [])
        right = set(right or [])
        if not left or not right:
            return 0.0
        return len(left.intersection(right)) / len(left.union(right))

    def _name_tokens(self, name):
        normalized = str(name or "").lower()
        tokens = []
        current = []
        for character in normalized:
            if character.isalnum():
                current.append(character)
            elif current:
                token = "".join(current)
                if len(token) > 2:
                    tokens.append(token)
                current = []
        if current:
            token = "".join(current)
            if len(token) > 2:
                tokens.append(token)
        return set(tokens)

    def _update_diversity_counts(self, item, group_counts, type_counts, member_coverage):
        for group in item.get("diversity_groups") or ["local_finds"]:
            group_counts[group] = group_counts.get(group, 0) + 1
        for place_type in item.get("display", {}).get("types") or []:
            type_counts[place_type] = type_counts.get(place_type, 0) + 1
        for member in item.get("member_fit") or []:
            if member.get("fit", 0) >= MEMBER_COVERAGE_FIT_THRESHOLD:
                user_id = member.get("user_id")
                member_coverage[user_id] = member_coverage.get(user_id, 0) + 1

    def _slate_summary(self, recommendations, members, intent_target_groups=None):
        recommendations = recommendations or []
        members = members or []
        intent_target_groups = set(intent_target_groups or [])
        group_counts = {}
        member_coverage = {
            member.id: {
                "user_id": member.id,
                "display_name": member.display_name or member.username,
                "strong_match_count": 0,
                "best_fit": 0,
                "best_match": None,
                "strong_matches": [],
            }
            for member in members
        }

        for rank_position, item in enumerate(recommendations, start=1):
            for group in item.get("diversity_groups") or ["local_finds"]:
                group_counts[group] = group_counts.get(group, 0) + 1
            for fit_row in item.get("member_fit") or []:
                user_id = fit_row.get("user_id")
                if user_id not in member_coverage:
                    continue
                fit = float(fit_row.get("fit") or 0)
                place_payload = self._member_coverage_place_payload(item, fit, rank_position)
                if fit > member_coverage[user_id]["best_fit"]:
                    member_coverage[user_id]["best_fit"] = round(fit, 3)
                    member_coverage[user_id]["best_match"] = place_payload
                if fit >= MEMBER_COVERAGE_FIT_THRESHOLD:
                    member_coverage[user_id]["strong_match_count"] += 1
                    member_coverage[user_id]["strong_matches"].append(place_payload)

        count = len(recommendations)
        unique_group_count = len(group_counts)
        target_group_count = min(max(len(intent_target_groups), 3), max(count, 1))
        diversity_coverage = min(1.0, unique_group_count / target_group_count) if count else 0
        dominant_group_count = max(group_counts.values()) if group_counts else 0
        dominant_group_share = dominant_group_count / count if count else 0
        first_page = recommendations[:min(3, count)]
        first_page_local_discovery_count = sum(1 for item in first_page if self._is_credible_local_pick(item))
        local_discovery_rescue_count = sum(
            1
            for item in recommendations
            if (item.get("ranking") or {}).get("local_discovery_rescue")
        )
        first_page_group_counts = {}
        for item in first_page:
            for group in item.get("diversity_groups") or ["local_finds"]:
                first_page_group_counts[group] = first_page_group_counts.get(group, 0) + 1
        first_page_size = len(first_page)
        first_page_target_count = min(target_group_count, max(first_page_size, 1))
        first_page_unique_group_count = len(first_page_group_counts)
        first_page_diversity_coverage = (
            min(1.0, first_page_unique_group_count / first_page_target_count)
            if first_page_size
            else 0
        )
        first_page_dominant_group_count = max(first_page_group_counts.values()) if first_page_group_counts else 0
        first_page_dominant_group_share = (
            first_page_dominant_group_count / first_page_size
            if first_page_size
            else 0
        )
        first_page_covered_intent_groups = sorted(
            group for group in intent_target_groups if first_page_group_counts.get(group, 0) > 0
        )
        first_page_missing_intent_groups = sorted(intent_target_groups.difference(first_page_covered_intent_groups))
        covered_intent_groups = sorted(group for group in intent_target_groups if group_counts.get(group, 0) > 0)
        missing_intent_groups = sorted(intent_target_groups.difference(covered_intent_groups))
        covered_members = [
            member
            for member in member_coverage.values()
            if member["strong_match_count"] > 0
        ]
        underserved_members = [
            member
            for member in member_coverage.values()
            if member["strong_match_count"] == 0
        ]
        member_coverage_share = (
            len(covered_members) / len(member_coverage)
            if member_coverage else None
        )

        if not count:
            status = "empty"
            message = "No basket has been built yet."
        elif len(members) > 1 and member_coverage_share is not None and member_coverage_share < 1:
            names = ", ".join(member["display_name"] for member in underserved_members[:2])
            status = "needs_party_coverage"
            message = f"{names or 'Someone'} needs at least one stronger match in this basket."
        elif diversity_coverage >= 0.8 and dominant_group_share <= 0.55 and not missing_intent_groups:
            status = "balanced"
            message = "This basket has a healthy mix of tastes, local texture, and trip intent."
        elif missing_intent_groups or dominant_group_share > 0.7:
            status = "narrow"
            message = "This basket may feel too narrow; a few more categories would make it livelier."
        else:
            status = "watch"
            message = "This basket is usable, but the slate mix can still improve."

        return {
            "status": status,
            "message": message,
            "metrics": {
                "returned": count,
                "unique_group_count": unique_group_count,
                "target_group_count": target_group_count,
                "diversity_coverage": round(diversity_coverage, 3),
                "dominant_group_share": round(dominant_group_share, 3),
                "covered_intent_count": len(covered_intent_groups),
                "missing_intent_count": len(missing_intent_groups),
                "first_page_size": first_page_size,
                "first_page_unique_group_count": first_page_unique_group_count,
                "first_page_diversity_coverage": round(first_page_diversity_coverage, 3),
                "first_page_dominant_group_share": round(first_page_dominant_group_share, 3),
                "first_page_covered_intent_count": len(first_page_covered_intent_groups),
                "first_page_missing_intent_count": len(first_page_missing_intent_groups),
                "first_page_local_discovery_count": first_page_local_discovery_count,
                "local_discovery_rescue_count": local_discovery_rescue_count,
                "member_coverage_share": round(member_coverage_share, 3) if member_coverage_share is not None else None,
            },
            "group_counts": dict(sorted(group_counts.items(), key=lambda item: (-item[1], item[0]))),
            "covered_intent_groups": covered_intent_groups,
            "missing_intent_groups": missing_intent_groups,
            "first_page_group_counts": dict(sorted(first_page_group_counts.items(), key=lambda item: (-item[1], item[0]))),
            "first_page_covered_intent_groups": first_page_covered_intent_groups,
            "first_page_missing_intent_groups": first_page_missing_intent_groups,
            "member_coverage": list(member_coverage.values()),
            "underserved_members": underserved_members,
        }

    def _member_coverage_place_payload(self, item, fit, rank_position):
        display = item.get("display") or {}
        return {
            "place_id": item.get("place_id"),
            "name": item.get("name") or display.get("name"),
            "rank_position": rank_position,
            "fit": round(float(fit or 0), 3),
            "score": round(float(item.get("score") or 0), 3),
            "diversity_groups": item.get("diversity_groups") or [],
            "authenticity_label": (item.get("authenticity_evidence") or {}).get("label"),
        }

    def build_preference_vector(self, user):
        existing = UserPreferenceVector.query.filter_by(user_id=user.id, vector_type="phase1").first()
        if _preference_vector_cache_is_fresh(existing):
            return _json_loads(existing.vector_json, default={})
        return self.rebuild_preference_vector(user)

    def rebuild_preference_vector(self, user, commit=True):
        vector = {
            "categories": {},
            "cuisines": {},
            "activities": {},
            "avoid_chains": 0.75,
            "hidden_gem_affinity": 0.75,
            "price_preference": None,
            "signal_count": 0,
            "confidence": 0.0,
        }

        if user.preferences:
            for tag in [tag.strip() for tag in user.preferences.split(",") if tag.strip()]:
                expanded_tags = _expand_preference_tag(tag)
                weight = 1.0 / max(len(expanded_tags), 1)
                for expanded_tag in expanded_tags:
                    vector["categories"][expanded_tag] = vector["categories"].get(expanded_tag, 0) + weight

        events = (
            UserPlaceEvent.query
            .filter_by(user_id=user.id)
            .order_by(UserPlaceEvent.occurred_at.asc())
            .all()
        )
        signal_events = [
            event
            for event in events
            if EVENT_WEIGHTS.get(event.event_type, 0) != 0 or event.event_type == "rate"
        ]
        vector["signal_count"] = len(signal_events)
        vector["confidence"] = round(_clamp(len(signal_events) / 12.0), 3)

        now = datetime.utcnow()
        for event in events:
            feature = PlaceFeature.query.filter_by(place_id=event.place_id).first()
            if not feature:
                continue

            weight = EVENT_WEIGHTS.get(event.event_type, 0)
            if event.event_type == "rate" and event.event_value is not None:
                weight = (float(event.event_value) - 3.0) * 2.0
            weight *= _event_recency_multiplier(event.occurred_at, now)

            self._apply_weight(vector["categories"], _json_loads(feature.category_vector), weight)
            self._apply_weight(vector["cuisines"], _json_loads(feature.cuisine_vector), weight)
            self._apply_weight(vector["activities"], _json_loads(feature.activity_vector), weight)

            if feature.chain_probability > 0.7 and weight < 0:
                vector["avoid_chains"] = _clamp(vector["avoid_chains"] + 0.05)
            if feature.hidden_gem_score > 0.6 and weight > 0:
                vector["hidden_gem_affinity"] = _clamp(vector["hidden_gem_affinity"] + 0.05)

        vector["price_preference"] = self._price_preference_from_events(events)
        self._normalize_vector(vector["categories"])
        self._normalize_vector(vector["cuisines"])
        self._normalize_vector(vector["activities"])

        row = UserPreferenceVector.query.filter_by(user_id=user.id, vector_type="phase1").first()
        if not row:
            row = UserPreferenceVector(user_id=user.id, vector_type="phase1", vector_json=_json_dumps(vector))
            db.session.add(row)
        else:
            row.vector_json = _json_dumps(vector)
            row.updated_at = datetime.utcnow()

        if commit:
            db.session.commit()

        return vector

    def upsert_candidate(self, candidate):
        provider = candidate.get("provider", "unknown")
        provider_place_id = candidate.get("place_id") or candidate.get("fsq_id") or candidate.get("id")
        adventour_place_id = candidate.get("adventour_place_id")

        if adventour_place_id:
            place = Place.query.get(adventour_place_id)
        else:
            existing_ref = None
            if provider_place_id:
                existing_ref = PlaceProviderRef.query.filter_by(
                    provider=provider,
                    provider_place_id=provider_place_id,
                ).first()
            place = existing_ref.place if existing_ref else None

        if not place:
            name = candidate.get("name") or "Unknown place"
            lat, lng = self._candidate_lat_lng(candidate)
            place = Place(
                canonical_name=name,
                normalized_name=_normalize_name(name),
                latitude=lat,
                longitude=lng,
                source_confidence=0.7 if provider != "local" else 1.0,
            )
            db.session.add(place)
            db.session.flush()

        provider_ref = None
        if provider_place_id:
            provider_ref = PlaceProviderRef.query.filter_by(
                provider=provider,
                provider_place_id=str(provider_place_id),
            ).first()
            if not provider_ref:
                provider_ref = PlaceProviderRef(
                    place_id=place.id,
                    provider=provider,
                    provider_place_id=str(provider_place_id),
                    attribution_required=provider != "local",
                )
                db.session.add(provider_ref)

        feature = PlaceFeature.query.filter_by(place_id=place.id).first()
        derived = self._derive_features(candidate)
        if not feature:
            feature = PlaceFeature(place_id=place.id, **derived)
            db.session.add(feature)
        else:
            for key, value in derived.items():
                setattr(feature, key, value)

        return place, provider_ref, feature

    def _resolve_scoring_profile(self, constraints):
        requested = (
            constraints.get("scoring_profile")
            or constraints.get("scoringProfile")
            or os.getenv("ADVENTOUR_SCORING_PROFILE")
        )
        if not requested:
            return self.scoring_profile

        profile_name = str(requested).strip()
        if profile_name == self.scoring_profile.name:
            return self.scoring_profile
        if profile_name in SCORING_PROFILES:
            return SCORING_PROFILES[profile_name]

        available = ", ".join(sorted(SCORING_PROFILES.keys()))
        raise ValueError(f"Unknown scoring_profile '{profile_name}'. Available profiles: {available}")

    def _resolve_members(self, user, member_ids):
        normalized_ids = []
        for member_id in member_ids:
            if not member_id:
                continue
            try:
                normalized_id = int(member_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("member_ids must be numeric user ids") from exc
            if normalized_id != user.id and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        if not normalized_ids:
            return [user]

        accepted_ids = self._accepted_friend_ids(user.id)
        unauthorized_ids = [member_id for member_id in normalized_ids if member_id not in accepted_ids]
        if unauthorized_ids:
            raise ValueError("Group recommendations can only include accepted friends")

        friends_by_id = {
            friend.id: friend
            for friend in User.query.filter(User.id.in_(normalized_ids), User.is_active == True).all()
        }
        return [user] + [friends_by_id[member_id] for member_id in normalized_ids if member_id in friends_by_id]

    def _accepted_friend_ids(self, user_id):
        friendships = Friendship.query.filter(
            and_(
                or_(Friendship.user_id == user_id, Friendship.friend_id == user_id),
                Friendship.status == "accepted",
            )
        ).all()
        return {
            friendship.friend_id if friendship.user_id == user_id else friendship.user_id
            for friendship in friendships
        }

    def _member_payload(self, member):
        return {
            "id": member.id,
            "display_name": member.display_name or member.username or "Adventourer",
            "profile_picture": member.profile_picture,
        }

    def _group_fit_summary(self, recommendations, members, member_vectors=None):
        member_vectors = member_vectors or {}
        member_lookup = {
            member.id: member.display_name or member.username or "Adventourer"
            for member in members
        }
        totals = {
            member.id: {
                "total": 0.0,
                "count": 0,
                "matched": 0,
                "best_fit": 0.0,
                "best_match": None,
                "strong_matches": [],
            }
            for member in members
        }

        for rank_position, recommendation in enumerate(recommendations or [], start=1):
            components = recommendation.get("components") or {}
            group_average_fit = components.get("group_average_fit")
            group_consensus_fit = components.get("group_consensus_fit")
            group_min_fit_weight = components.get("group_min_fit_weight")
            if group_average_fit is not None:
                totals.setdefault("_group_consensus", {}).setdefault("average_fits", []).append(
                    _safe_float(group_average_fit)
                )
            if group_consensus_fit is not None:
                totals.setdefault("_group_consensus", {}).setdefault("consensus_fits", []).append(
                    _safe_float(group_consensus_fit)
                )
            if group_min_fit_weight is not None:
                totals.setdefault("_group_consensus", {}).setdefault("min_fit_weights", []).append(
                    _safe_float(group_min_fit_weight)
                )
            for fit_row in recommendation.get("member_fit") or []:
                user_id = fit_row.get("user_id")
                if user_id not in totals:
                    continue
                fit = float(fit_row.get("fit") or 0)
                totals[user_id]["total"] += fit
                totals[user_id]["count"] += 1
                place_payload = self._member_coverage_place_payload(recommendation, fit, rank_position)
                if fit > totals[user_id]["best_fit"]:
                    totals[user_id]["best_fit"] = fit
                    totals[user_id]["best_match"] = place_payload
                if fit >= MEMBER_COVERAGE_FIT_THRESHOLD:
                    totals[user_id]["matched"] += 1
                    totals[user_id]["strong_matches"].append(place_payload)

        member_summaries = []
        for member in members:
            row = totals.get(member.id, {})
            count = row.get("count", 0)
            average_fit = round(row.get("total", 0.0) / count, 3) if count else 0.0
            member_vector = member_vectors.get(member.id, {})
            preference_cues = self._member_preference_cues(member_vector)
            learning_profile = self._member_learning_profile(member_vector)
            member_summaries.append({
                "user_id": member.id,
                "display_name": member_lookup.get(member.id, "Adventourer"),
                "average_fit": average_fit,
                "matched_count": row.get("matched", 0),
                "coverage_status": "covered" if row.get("matched", 0) > 0 else "needs_match",
                "best_fit": round(row.get("best_fit", 0.0), 3),
                "best_match": row.get("best_match"),
                "strong_matches": row.get("strong_matches", [])[:3],
                "preferred_groups": preference_cues["preferred_groups"],
                "suggested_query_tags": preference_cues["suggested_query_tags"],
                "learning_status": learning_profile["learning_status"],
                "signal_count": learning_profile["signal_count"],
                "confidence": learning_profile["confidence"],
            })

        if not member_summaries:
            return {
                "member_count": 0,
                "average_fit": 0.0,
                "lowest_fit": 0.0,
                "fairness_score": None,
                "members": [],
                "underserved_members": [],
                "ready_for_friend_testing": False,
                "coverage_plan": {
                    "status": "empty",
                    "headline": "Adventour needs recommendations before it can assess friend fit.",
                    "covered_member_count": 0,
                    "coverage_share": 0,
                    "next_actions": ["Build a basket before testing friend fit."],
                },
                "message": "Adventour needs recommendations before it can assess party balance.",
            }

        fit_values = [member["average_fit"] for member in member_summaries]
        average_fit = round(sum(fit_values) / len(fit_values), 3)
        lowest_fit = min(fit_values)
        highest_fit = max(fit_values)
        fairness_score = round(max(0, 1 - (highest_fit - lowest_fit)), 3)
        consensus_rows = totals.get("_group_consensus", {})
        average_consensus_fit = self._average_metric(consensus_rows.get("consensus_fits"))
        average_group_average_fit = self._average_metric(consensus_rows.get("average_fits"))
        average_min_fit_weight = self._average_metric(consensus_rows.get("min_fit_weights"))
        consensus_gap = None
        if average_group_average_fit is not None and average_consensus_fit is not None:
            consensus_gap = round(max(0, average_group_average_fit - average_consensus_fit), 3)
        underserved = [
            member
            for member in member_summaries
            if member["average_fit"] < MEMBER_COVERAGE_FIT_THRESHOLD
        ]
        covered_members = [
            member
            for member in member_summaries
            if member["matched_count"] > 0
        ]
        coverage_share = len(covered_members) / len(member_summaries) if member_summaries else 0
        ready_for_friend_testing = (
            len(member_summaries) == 1
            or (
                coverage_share >= 1
                and fairness_score >= 0.8
            )
        )

        if len(member_summaries) == 1:
            message = "Basket is tuned to your Adventour taste."
        elif underserved:
            names = ", ".join(member["display_name"] for member in underserved[:2])
            message = f"{names} may need stronger matches; try group-friendly scout style or swap picks."
        elif fairness_score >= 0.85:
            message = "Basket looks balanced across this travel party."
        else:
            message = "Basket is useful, but one traveler is getting stronger matches than the others."

        return {
            "member_count": len(member_summaries),
            "average_fit": average_fit,
            "lowest_fit": lowest_fit,
            "fairness_score": fairness_score,
            "average_group_average_fit": average_group_average_fit,
            "average_consensus_fit": average_consensus_fit,
            "average_min_fit_weight": average_min_fit_weight,
            "consensus_gap": consensus_gap,
            "members": member_summaries,
            "underserved_members": underserved,
            "covered_member_count": len(covered_members),
            "coverage_share": round(coverage_share, 3),
            "ready_for_friend_testing": ready_for_friend_testing,
            "coverage_plan": self._group_coverage_plan(
                member_summaries,
                underserved,
                coverage_share,
                fairness_score,
                ready_for_friend_testing,
            ),
            "message": message,
        }

    def _member_learning_profile(self, vector):
        signal_count = int(max(0, _safe_float((vector or {}).get("signal_count"))))
        confidence = _clamp(_safe_float((vector or {}).get("confidence"), signal_count / 12.0))
        learning_status = (vector or {}).get("learning_status")
        if not learning_status:
            if confidence >= 0.66:
                learning_status = "personalized"
            elif confidence >= 0.25:
                learning_status = "learning"
            else:
                learning_status = "cold_start"
        return {
            "learning_status": learning_status,
            "signal_count": signal_count,
            "confidence": round(confidence, 3),
        }

    def _member_preference_cues(self, vector):
        categories = vector.get("categories") or {}
        top_tags = [
            item["tag"]
            for item in self._top_vector_entries(categories, positive=True, limit=5)
        ]
        preferred_groups = []
        for tag in top_tags:
            for group in sorted(_intent_groups_for_tags([tag])):
                if group not in preferred_groups:
                    preferred_groups.append(group)
        if not preferred_groups:
            for group in sorted(_intent_groups_for_tags(top_tags)):
                if group not in preferred_groups:
                    preferred_groups.append(group)
        return {
            "preferred_groups": [
                {
                    "id": group,
                    "label": group.replace("_", " ").title(),
                }
                for group in preferred_groups[:4]
            ],
            "suggested_query_tags": top_tags[:5],
        }

    def _average_metric(self, values):
        if not values:
            return None
        return round(sum(values) / len(values), 3)

    def _group_consensus_needs_attention(self, group_fit_summary, member_count):
        if member_count <= 1 or not group_fit_summary:
            return False
        consensus_fit = group_fit_summary.get("average_consensus_fit")
        return (
            (group_fit_summary.get("fairness_score") or 0) < 0.65
            or (consensus_fit is not None and consensus_fit < 0.55)
            or (group_fit_summary.get("consensus_gap") or 0) > 0.12
        )

    def _group_coverage_plan(self, member_summaries, underserved, coverage_share, fairness_score, ready_for_friend_testing):
        cold_start_members = [
            member
            for member in member_summaries
            if member.get("learning_status") == "cold_start" or int(member.get("signal_count") or 0) < 3
        ]
        if ready_for_friend_testing:
            if cold_start_members:
                status = "watch"
                headline = "Every traveler has coverage, but Adventour is still learning this party."
            else:
                status = "ready"
                headline = "Every traveler has enough coverage for a friend test."
        elif underserved:
            status = "needs_member_coverage"
            names = ", ".join(member["display_name"] for member in underserved[:2])
            if cold_start_members:
                headline = f"{names} need stronger matches, and Adventour is still learning this party."
            else:
                headline = f"{names} need stronger matches before this basket feels fair."
        elif fairness_score < 0.8:
            status = "uneven"
            headline = "Everyone has a match, but the basket leans toward one traveler."
        else:
            status = "watch"
            headline = "Friend fit is usable, but the basket can still improve."

        next_actions = []
        if ready_for_friend_testing:
            for member in cold_start_members[:2]:
                next_actions.append(
                    f"Ask {member['display_name']} to swipe or rate a few picks so Adventour can learn their taste."
                )
            next_actions.append("Keep this basket or start swiping with the group.")
            return {
                "status": status,
                "headline": headline,
                "covered_member_count": len([member for member in member_summaries if member.get("matched_count", 0) > 0]),
                "coverage_share": round(coverage_share, 3),
                "fairness_score": fairness_score,
                "ready_for_friend_testing": ready_for_friend_testing,
                "cold_start_member_count": len(cold_start_members),
                "next_actions": next_actions,
            }

        for member in cold_start_members[:2]:
            next_actions.append(
                f"Ask {member['display_name']} to swipe or rate a few picks so Adventour can learn their taste."
            )

        for member in underserved[:3]:
            if len(next_actions) >= 3:
                break
            tags = member.get("suggested_query_tags") or []
            groups = member.get("preferred_groups") or []
            if tags:
                next_actions.append(
                    f"Add or refresh around {', '.join(tags[:2])} for {member['display_name']}."
                )
            elif groups:
                next_actions.append(
                    f"Add more {groups[0]['label'].lower()} picks for {member['display_name']}."
                )
            else:
                next_actions.append(f"Refresh with group-friendly scout style for {member['display_name']}.")
        if not next_actions and not ready_for_friend_testing:
            next_actions.append("Use group-friendly scout style or refresh for a more even basket.")

        return {
            "status": status,
            "headline": headline,
            "covered_member_count": len([member for member in member_summaries if member.get("matched_count", 0) > 0]),
            "coverage_share": round(coverage_share, 3),
            "fairness_score": fairness_score,
            "ready_for_friend_testing": ready_for_friend_testing,
            "cold_start_member_count": len(cold_start_members),
            "next_actions": next_actions[:3],
        }

    def _party_fit_summary(self, member_fit_details, components):
        members = sorted(
            [
                {
                    "user_id": item.get("user_id"),
                    "display_name": item.get("display_name") or "Traveler",
                    "fit": round(float(item.get("fit") or 0), 3),
                }
                for item in member_fit_details or []
                if item.get("user_id") is not None
            ],
            key=lambda item: item["fit"],
            reverse=True,
        )
        if len(members) <= 1:
            return None

        fit_values = [member["fit"] for member in members]
        average_fit = round(sum(fit_values) / len(fit_values), 3)
        lowest_fit = min(fit_values)
        highest_fit = max(fit_values)
        fairness_score = round(max(0, 1 - (highest_fit - lowest_fit)), 3)
        strong_members = [member for member in members if member["fit"] >= MEMBER_COVERAGE_FIT_THRESHOLD]
        weak_members = (
            [member for member in members if member["fit"] < MEMBER_COVERAGE_FIT_THRESHOLD]
            if (components or {}).get("group_fairness_penalty", 0) > 0
            else []
        )

        if weak_members:
            names = ", ".join(member["display_name"] for member in weak_members[:2])
            headline = f"Mixed for the party; {names} may want a swap."
        elif fairness_score >= 0.85:
            headline = "Balanced pick for this travel party."
        else:
            headline = "Good group fit, but one traveler matches it more."

        detail = (
            f"Average party fit is {round(average_fit * 100)}% "
            f"with a {round(lowest_fit * 100)}% floor."
        )
        if strong_members:
            detail = (
                f"Best for {', '.join(member['display_name'] for member in strong_members[:2])}. "
                + detail
            )
        elif not weak_members:
            detail = "No one is below the group-fit floor. " + detail

        return {
            "headline": headline,
            "detail": detail,
            "average_fit": average_fit,
            "lowest_fit": round(lowest_fit, 3),
            "highest_fit": round(highest_fit, 3),
            "fairness_score": fairness_score,
            "group_fit": round(float((components or {}).get("group_fit") or average_fit), 3),
            "strong_members": strong_members[:3],
            "weak_members": weak_members[:3],
            "members": members[:4],
        }

    def _recommendation_quality_summary(
        self,
        recommendations,
        members,
        group_fit_summary=None,
        provider_errors=None,
        filter_summary=None,
        repeated_decided=False,
        slate_summary=None,
        preference_insights=None,
        learned_rerank=None,
    ):
        recommendations = recommendations or []
        provider_errors = provider_errors or []
        filter_summary = filter_summary or {}
        slate_summary = slate_summary or {}
        count = len(recommendations)
        if not count:
            model_confidence = self._model_confidence_summary(
                recommendations=[],
                members=members,
                preference_insights=preference_insights,
                learned_rerank=learned_rerank,
                metrics={"returned": 0, "provider_error_count": len(provider_errors)},
            )
            diagnostic = self._recommendation_diagnostic(
                status="needs_attention",
                metrics={
                    "returned": 0,
                    "raw_candidates": filter_summary.get("raw_candidates", 0),
                    "provider_error_count": len(provider_errors),
                },
                filter_summary=filter_summary,
                model_confidence=model_confidence,
                group_fit_summary=group_fit_summary,
                provider_errors=provider_errors,
                repeated_decided=repeated_decided,
                members=members,
            )
            return {
                "status": "needs_attention",
                "headline": "No recommendation basket is ready yet.",
                "metrics": {
                    "returned": 0,
                    "raw_candidates": filter_summary.get("raw_candidates", 0),
                    "provider_error_count": len(provider_errors),
                },
                "strengths": [],
                "warnings": ["Try another launch point, widen the range, or clear strict trip skips."],
                "decision_summary": {
                    "status": "needs_attention",
                    "headline": "Adventour needs places before it can judge this run.",
                    "score": 0,
                    "dimensions": [],
                    "strengths": [],
                    "warnings": ["No places made it into the basket."],
                    "next_actions": ["Try another launch point, widen the range, or clear strict trip skips."],
                },
                "model_confidence": model_confidence,
                "diagnostic": diagnostic,
            }

        hidden_gem_count = sum(
            1
            for item in recommendations
            if (item.get("authenticity_evidence") or {}).get("label") == "Hidden gem"
        )
        local_feeling_count = sum(
            1
            for item in recommendations
            if (item.get("authenticity_evidence") or {}).get("label") in {"Hidden gem", "Local-feeling"}
        )
        generic_risk_count = sum(
            1
            for item in recommendations
            if (item.get("authenticity_evidence") or {}).get("label") == "Generic risk"
            or (item.get("components") or {}).get("chain_penalty", 0) > 0
        )
        authenticity_confidence_values = [
            _safe_float((item.get("authenticity_evidence") or {}).get("confidence"), None)
            for item in recommendations
        ]
        authenticity_confidence_values = [
            value
            for value in authenticity_confidence_values
            if value is not None
        ]
        average_authenticity_confidence = (
            sum(authenticity_confidence_values) / len(authenticity_confidence_values)
            if authenticity_confidence_values else None
        )
        thin_local_evidence_count = sum(
            1
            for item in recommendations
            if (item.get("authenticity_evidence") or {}).get("confidence_status") == "thin"
            and (item.get("authenticity_evidence") or {}).get("label") in {"Hidden gem", "Local-feeling", "Popular local"}
        )
        value_gem_count = sum(
            1
            for item in recommendations
            if (item.get("components") or {}).get("value_gem", 0) >= 0.6
        )
        serendipity_plan = self._serendipity_plan(recommendations, len(members))
        exploration_count = serendipity_plan["allowed_count"]
        exploration_eligible_count = serendipity_plan["eligible_count"]
        local_event_backed_count = sum(
            1
            for item in recommendations
            if item.get("local_event_match")
        )
        local_event_reservation_ready_count = sum(
            1
            for item in recommendations
            if (item.get("local_event_match") or {}).get("reservation_url")
        )
        local_event_source_ready_count = sum(
            1
            for item in recommendations
            if (item.get("local_event_match") or {}).get("source_url")
            or (item.get("local_event_match") or {}).get("source_name")
        )
        local_event_friend_signal_count = sum(
            int(((item.get("local_event_match") or {}).get("social") or {}).get("friend_signal_count") or 0)
            for item in recommendations
        )
        local_event_community_signal_count = sum(
            int(((item.get("local_event_match") or {}).get("social") or {}).get("interested_count") or 0)
            + int(((item.get("local_event_match") or {}).get("social") or {}).get("going_count") or 0)
            for item in recommendations
        )
        local_event_social_signal_values = [
            _safe_float(((item.get("local_event_match") or {}).get("social") or {}).get("signal"), None)
            for item in recommendations
            if item.get("local_event_match")
        ]
        local_event_social_signal_values = [
            value
            for value in local_event_social_signal_values
            if value is not None
        ]
        local_event_social_score = (
            round(sum(local_event_social_signal_values) / len(local_event_social_signal_values), 3)
            if local_event_social_signal_values
            else 0
        )
        friend_history_positive_count = sum(
            1
            for item in recommendations
            if (item.get("components") or {}).get("friend_history_fit", 0) > 0
        )
        friend_history_conflict_count = sum(
            1
            for item in recommendations
            if (item.get("components") or {}).get("friend_history_fit", 0) < 0
        )
        friend_history_signal_count = friend_history_positive_count + friend_history_conflict_count
        party_rescue_rows = [
            {
                "member": (item.get("ranking") or {}).get("rescued_member"),
                "place": item.get("name") or (item.get("display") or {}).get("name"),
            }
            for item in recommendations
            if (item.get("ranking") or {}).get("party_coverage_rescue")
        ]
        party_rescue_count = len(party_rescue_rows)
        avg_score = sum(item.get("score", 0) or 0 for item in recommendations) / count
        avg_authenticity = sum((item.get("components") or {}).get("authenticity", 0) or 0 for item in recommendations) / count
        avg_group_fit = group_fit_summary.get("average_fit") if group_fit_summary else None
        avg_consensus_fit = group_fit_summary.get("average_consensus_fit") if group_fit_summary else None
        group_consensus_gap = group_fit_summary.get("consensus_gap") if group_fit_summary else None
        slate_metrics = slate_summary.get("metrics") or {}
        local_share = local_feeling_count / count
        hidden_gem_share = hidden_gem_count / count
        generic_share = generic_risk_count / count
        warnings = []
        strengths = []

        if local_share >= 0.45:
            strengths.append("Strong local-feeling mix in this basket.")
        elif local_share < 0.2:
            warnings.append("Local/authentic signals are thin for this basket.")

        if hidden_gem_count:
            strengths.append(f"{hidden_gem_count} hidden-gem candidate{'s' if hidden_gem_count != 1 else ''} surfaced.")
        else:
            warnings.append("No clear hidden-gem candidates surfaced yet.")

        if thin_local_evidence_count:
            warnings.append(
                f"{thin_local_evidence_count} local-feeling pick{'s' if thin_local_evidence_count != 1 else ''} need more evidence before Adventour should fully trust them."
            )
        if value_gem_count:
            strengths.append(
                f"{value_gem_count} value-gem pick{'s' if value_gem_count != 1 else ''} keep local discovery budget-friendly."
            )

        if generic_share >= 0.35:
            warnings.append("Generic or chain-like risk is higher than ideal.")
        elif generic_risk_count == 0:
            strengths.append("Chain guard kept generic picks out of the basket.")

        if exploration_count:
            strengths.append(
                f"{exploration_count} guarded learning pick{'s' if exploration_count != 1 else ''} included to discover underexposed local gems."
            )
        elif serendipity_plan["status"] == "under_target":
            warnings.append(serendipity_plan["headline"])
        if serendipity_plan["status"] == "over_target":
            warnings.append(serendipity_plan["headline"])
        if local_event_backed_count:
            strengths.append(
                f"{local_event_backed_count} event-backed pick{'s' if local_event_backed_count != 1 else ''} can anchor something timely nearby."
            )
            if local_event_friend_signal_count:
                strengths.append(
                    f"{local_event_friend_signal_count} selected-friend event signal{'s' if local_event_friend_signal_count != 1 else ''} make the basket more social."
                )
            if local_event_reservation_ready_count:
                strengths.append(
                    f"{local_event_reservation_ready_count} event-backed pick{'s' if local_event_reservation_ready_count != 1 else ''} include RSVP or reservation links."
                )
            if not local_event_friend_signal_count and local_event_social_score < 0.2:
                warnings.append("Event-backed picks are timely, but social signal is still thin.")
        if len(members) > 1 and friend_history_positive_count:
            strengths.append(
                f"{friend_history_positive_count} pick{'s' if friend_history_positive_count != 1 else ''} have positive selected-friend history."
            )
        if len(members) > 1 and friend_history_conflict_count:
            warnings.append(
                f"{friend_history_conflict_count} pick{'s' if friend_history_conflict_count != 1 else ''} include selected-friend pass history."
            )

        if len(members) > 1 and group_fit_summary:
            consensus_fit = group_fit_summary.get("average_consensus_fit")
            consensus_gap = group_fit_summary.get("consensus_gap") or 0
            if (group_fit_summary.get("fairness_score") or 0) >= 0.8:
                strengths.append("Travel-party fit is balanced enough to test.")
            else:
                warnings.append("One or more travelers may need stronger matches.")
            if consensus_fit is not None and consensus_fit < 0.55:
                warnings.append("Group consensus fit is low; the average may be hiding a weak traveler match.")
            elif consensus_gap > 0.12:
                warnings.append("Group fit is uneven; one traveler is pulling the consensus score down.")
            if party_rescue_count:
                names = ", ".join(
                    row["member"]
                    for row in party_rescue_rows[:2]
                    if row.get("member")
                )
                strengths.append(
                    f"Adventour made room for {party_rescue_count} party-coverage pick{'s' if party_rescue_count != 1 else ''}"
                    f"{f' for {names}' if names else ''}."
                )

        diversity_coverage = slate_metrics.get("diversity_coverage")
        dominant_group_share = slate_metrics.get("dominant_group_share")
        missing_intent_count = slate_metrics.get("missing_intent_count") or 0
        first_page_diversity_coverage = slate_metrics.get("first_page_diversity_coverage")
        first_page_dominant_group_share = slate_metrics.get("first_page_dominant_group_share")
        first_page_missing_intent_count = slate_metrics.get("first_page_missing_intent_count") or 0
        first_page_local_discovery_count = slate_metrics.get("first_page_local_discovery_count") or 0
        local_discovery_rescue_count = slate_metrics.get("local_discovery_rescue_count") or 0
        member_coverage_share = slate_metrics.get("member_coverage_share")
        if diversity_coverage is not None:
            if diversity_coverage >= 0.8 and (dominant_group_share or 0) <= 0.55:
                strengths.append("Basket slate covers a healthy variety of trip moods.")
            elif diversity_coverage < 0.5 or (dominant_group_share or 0) > 0.7:
                warnings.append("Basket slate is narrow; more variety would make testing stronger.")
        if first_page_diversity_coverage is not None:
            if first_page_diversity_coverage >= 0.8 and (first_page_dominant_group_share or 0) <= 0.55:
                strengths.append("The first swipe screen opens with a healthy mix.")
            elif first_page_diversity_coverage < 0.67 or (first_page_dominant_group_share or 0) > 0.7:
                warnings.append("First swipe screen is narrow; early cards may feel repetitive.")
        if local_discovery_rescue_count:
            strengths.append(
                f"Adventour made room for {local_discovery_rescue_count} first-page local discovery pick{'s' if local_discovery_rescue_count != 1 else ''}."
            )
        elif count and not first_page_local_discovery_count and local_share >= 0.2:
            warnings.append("Local options exist, but none made the first swipe screen.")
        if missing_intent_count:
            warnings.append("Some requested trip moods are still missing from the basket.")
        if first_page_missing_intent_count:
            warnings.append("Some requested moods are missing from the first swipe screen.")
        if len(members) > 1 and member_coverage_share is not None and member_coverage_share < 1:
            warnings.append("At least one traveler lacks a strong match in the current slate.")

        if provider_errors:
            warnings.append("One or more place providers failed during search.")
        if repeated_decided:
            warnings.append("Adventour repeated decided places because fresh options were exhausted.")

        status = "ready"
        if (
            provider_errors
            or generic_share >= 0.5
            or slate_summary.get("status") == "needs_party_coverage"
            or self._group_consensus_needs_attention(group_fit_summary, len(members))
        ):
            status = "needs_attention"
        elif warnings:
            status = "watch"

        if status == "ready":
            headline = "Recommendation basket is strong enough to test."
        elif status == "watch":
            headline = "Recommendation basket is usable, with a few tradeoffs."
        else:
            headline = "Recommendation basket needs attention before it feels reliable."

        metrics = {
            "returned": count,
            "raw_candidates": filter_summary.get("raw_candidates", count),
            "average_score": round(avg_score, 3),
            "average_authenticity": round(avg_authenticity, 3),
            "average_authenticity_confidence": round(average_authenticity_confidence, 3) if average_authenticity_confidence is not None else None,
            "thin_local_evidence_count": thin_local_evidence_count,
            "value_gem_count": value_gem_count,
            "value_gem_share": round(value_gem_count / count, 3),
            "local_feeling_count": local_feeling_count,
            "local_feeling_share": round(local_share, 3),
            "hidden_gem_count": hidden_gem_count,
            "hidden_gem_share": round(hidden_gem_share, 3),
            "generic_risk_count": generic_risk_count,
            "generic_risk_share": round(generic_share, 3),
            "exploration_count": exploration_count,
            "exploration_eligible_count": exploration_eligible_count,
            "exploration_share": round(exploration_count / count, 3),
            "serendipity_score": serendipity_plan["score"],
            "serendipity_target_min": serendipity_plan["target_min"],
            "serendipity_target_max": serendipity_plan["target_max"],
            "serendipity_safe_count": serendipity_plan["safe_count"],
            "serendipity_blocked_count": serendipity_plan["blocked_count"],
            "local_event_backed_count": local_event_backed_count,
            "local_event_backed_share": round(local_event_backed_count / count, 3),
            "local_event_reservation_ready_count": local_event_reservation_ready_count,
            "local_event_source_ready_count": local_event_source_ready_count,
            "local_event_friend_signal_count": local_event_friend_signal_count,
            "local_event_community_signal_count": local_event_community_signal_count,
            "local_event_social_score": local_event_social_score,
            "friend_history_positive_count": friend_history_positive_count,
            "friend_history_conflict_count": friend_history_conflict_count,
            "friend_history_signal_count": friend_history_signal_count,
            "friend_history_signal_share": round(friend_history_signal_count / count, 3),
            "party_coverage_rescue_count": party_rescue_count,
            "party_coverage_rescued_members": [
                row["member"]
                for row in party_rescue_rows
                if row.get("member")
            ][:5],
            "average_group_fit": round(avg_group_fit, 3) if avg_group_fit is not None else None,
            "average_consensus_fit": round(avg_consensus_fit, 3) if avg_consensus_fit is not None else None,
            "group_consensus_gap": round(group_consensus_gap, 3) if group_consensus_gap is not None else None,
            "diversity_coverage": round(diversity_coverage, 3) if diversity_coverage is not None else None,
            "dominant_group_share": round(dominant_group_share, 3) if dominant_group_share is not None else None,
            "missing_intent_count": missing_intent_count,
            "first_page_diversity_coverage": round(first_page_diversity_coverage, 3) if first_page_diversity_coverage is not None else None,
            "first_page_dominant_group_share": round(first_page_dominant_group_share, 3) if first_page_dominant_group_share is not None else None,
            "first_page_missing_intent_count": first_page_missing_intent_count,
            "first_page_local_discovery_count": first_page_local_discovery_count,
            "local_discovery_rescue_count": local_discovery_rescue_count,
            "member_coverage_share": round(member_coverage_share, 3) if member_coverage_share is not None else None,
            "provider_error_count": len(provider_errors),
            "repeated_decided": bool(repeated_decided),
        }
        decision_summary = self._recommendation_decision_summary(
            status=status,
            metrics=metrics,
            members=members,
            group_fit_summary=group_fit_summary,
            provider_errors=provider_errors,
            repeated_decided=repeated_decided,
            strengths=strengths,
            warnings=warnings,
        )
        model_confidence = self._model_confidence_summary(
            recommendations=recommendations,
            members=members,
            preference_insights=preference_insights,
            learned_rerank=learned_rerank,
            metrics=metrics,
        )
        diagnostic = self._recommendation_diagnostic(
            status=status,
            metrics=metrics,
            filter_summary=filter_summary,
            model_confidence=model_confidence,
            group_fit_summary=group_fit_summary,
            provider_errors=provider_errors,
            repeated_decided=repeated_decided,
            members=members,
            decision_summary=decision_summary,
        )

        return {
            "status": status,
            "headline": headline,
            "metrics": metrics,
            "strengths": strengths[:5],
            "warnings": warnings[:4],
            "decision_summary": decision_summary,
            "model_confidence": model_confidence,
            "diagnostic": diagnostic,
            "serendipity_plan": serendipity_plan,
        }

    def _serendipity_plan(self, recommendations, member_count=1):
        recommendations = recommendations or []
        count = len(recommendations)
        allowed = []
        eligible = []
        safe = []
        blocked_reasons = {}
        friend_learning_members = set()

        for item in recommendations:
            ranking = item.get("ranking") or {}
            budget = ranking.get("exploration_budget") or {}
            if not budget.get("eligible"):
                continue

            eligible.append(item)
            guardrail = budget.get("authenticity_guardrail") or {}
            if guardrail.get("allowed"):
                safe.append(item)
            else:
                reason = guardrail.get("reason") or budget.get("reason") or "guardrail"
                blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1

            if budget.get("allowed"):
                allowed.append(item)
                for member in budget.get("served_learning_members") or []:
                    friend_learning_members.add(member)

        allowed_count = len(allowed)
        safe_count = len(safe)
        blocked_count = max(0, len(eligible) - safe_count)
        target_min = 1 if count >= 4 or safe_count > 0 else 0
        target_max = min(2, max(1, math.ceil(count * 0.25))) if count else 0

        if not count:
            status = "empty"
            headline = "No discovery mix yet."
            message = "Adventour needs recommendations before it can plan safe exploration."
            next_action = "Try another launch point or widen the search range."
            score = 0
        elif allowed_count < target_min:
            status = "under_target"
            headline = "Discovery mix is conservative."
            message = "No safe learning pick made it into this basket, so Adventour may learn more slowly here."
            next_action = "Try Hidden gems scout style or widen the range for more underexposed local options."
            score = 0.42 if safe_count else 0.28
        elif allowed_count > target_max:
            status = "over_target"
            headline = "Discovery mix may be too exploratory."
            message = "The basket has more learning picks than ideal for a first friend test."
            next_action = "Lean back toward balanced or local-forward scout style for a safer basket."
            score = 0.52
        else:
            status = "balanced"
            headline = "Discovery mix is balanced."
            message = "Adventour made room for guarded local discovery without letting exploration take over."
            next_action = "Keep testing these picks and rate accepted places so the model learns faster."
            score = 0.86 if allowed_count else 0.68

        blocked_summary = [
            {"reason": reason, "count": count}
            for reason, count in sorted(blocked_reasons.items(), key=lambda row: (-row[1], row[0]))
        ]
        learning_picks = [
            {
                "place_id": item.get("place_id"),
                "name": item.get("name") or (item.get("display") or {}).get("name"),
                "score": round(_safe_float(item.get("score")), 3),
                "authenticity_label": (item.get("authenticity_evidence") or {}).get("label"),
                "exploration": round(_safe_float((item.get("components") or {}).get("exploration_applied")), 3),
                "frontier_gap": ((item.get("ranking") or {}).get("exploration_budget") or {}).get("frontier_gap"),
                "reason": ((item.get("ranking") or {}).get("exploration_budget") or {}).get("reason"),
            }
            for item in allowed[:3]
        ]

        return {
            "status": status,
            "headline": headline,
            "message": message,
            "score": round(_clamp(score), 3),
            "target_min": target_min,
            "target_max": target_max,
            "allowed_count": allowed_count,
            "eligible_count": len(eligible),
            "safe_count": safe_count,
            "blocked_count": blocked_count,
            "friend_learning": bool(friend_learning_members),
            "served_learning_members": sorted(friend_learning_members)[:4],
            "blocked_reasons": blocked_summary,
            "learning_picks": learning_picks,
            "next_action": next_action,
            "research_basis": [
                "contextual_bandit_explore_exploit",
                "beyond_accuracy_serendipity",
            ],
        }

    def _model_confidence_summary(
        self,
        recommendations,
        members,
        preference_insights=None,
        learned_rerank=None,
        metrics=None,
    ):
        recommendations = recommendations or []
        preference_insights = preference_insights or []
        learned_rerank = learned_rerank or {}
        metrics = metrics or {}
        confidence_values = [
            _clamp(insight.get("confidence"))
            for insight in preference_insights
            if insight.get("confidence") is not None
        ]
        signal_counts = [
            max(0.0, _safe_float(insight.get("signal_count")))
            for insight in preference_insights
            if insight.get("signal_count") is not None
        ]
        if not confidence_values and recommendations:
            confidence_values = [
                _clamp((item.get("components") or {}).get("preference_confidence"))
                for item in recommendations
                if (item.get("components") or {}).get("preference_confidence") is not None
            ]
        average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0
        average_signal_count = sum(signal_counts) / len(signal_counts) if signal_counts else 0
        local_share = metrics.get("local_feeling_share") or 0
        member_coverage = metrics.get("member_coverage_share")
        group_bonus = 0.12 if len(members or []) <= 1 else 0.12 * _clamp(member_coverage if member_coverage is not None else 0)
        exploration_count = metrics.get("exploration_count") or 0
        exploration_eligible_count = metrics.get("exploration_eligible_count") or 0
        serendipity_score = metrics.get("serendipity_score")
        learned_guard = learned_rerank.get("runtime_guard") or {}
        learned_guard_status = learned_guard.get("status")
        learned_bonus = 0.0
        learned_penalty = 0.0
        if learned_rerank.get("applied"):
            learned_bonus = 0.12
            if learned_guard_status == "constrained":
                learned_penalty = 0.08
            elif learned_guard_status == "watch":
                learned_penalty = 0.04

        score = _clamp(
            average_confidence * 0.46
            + _clamp(local_share) * 0.22
            + group_bonus
            + (_clamp(serendipity_score) * 0.08 if serendipity_score is not None else (0.08 if exploration_count else 0))
            + learned_bonus
            - learned_penalty
        )
        if average_confidence >= 0.66:
            learning_status = "personalized"
        elif average_confidence >= 0.25:
            learning_status = "learning"
        else:
            learning_status = "cold_start"

        warnings = []
        next_actions = []
        basis = []
        if learning_status == "cold_start":
            warnings.append("Adventour is still learning taste from early accepts, rejects, and ratings.")
            next_actions.append("Accept or pass on a few places so the model can learn what feels right.")
        elif learning_status == "learning":
            basis.append("Taste model has early signal, but still needs more decisions.")
            next_actions.append("Rate accepted places to make future recommendations more personal.")
        else:
            basis.append("Taste model has enough feedback to personalize with more confidence.")

        if local_share >= 0.45:
            basis.append("Local/authenticity guardrails have enough signal in this basket.")
        else:
            warnings.append("Local-authentic signal is still thinner than ideal for this run.")
            next_actions.append("Try Hidden gems scout style or widen the range for more local texture.")

        if len(members or []) > 1:
            if member_coverage is not None and member_coverage >= 1:
                basis.append("Friend blending found at least one strong match per traveler.")
            else:
                warnings.append("Friend blending may still need stronger coverage for one traveler.")
                next_actions.append("Try group-friendly scout style or add a swap for the underserved friend.")

        if exploration_count:
            basis.append(f"{exploration_count} guarded learning pick{'s' if exploration_count != 1 else ''} can test underexposed local options.")
        elif exploration_eligible_count:
            warnings.append("Exploration candidates existed, but guardrails held them out of this page.")
        if serendipity_score is not None and serendipity_score < 0.5:
            next_actions.append("Use Hidden gems scout style or widen the range to improve the discovery mix.")

        if learned_rerank.get("applied"):
            basis.append("Learned beta reranker is active behind Adventour guardrails.")
            if learned_guard_status == "constrained":
                warnings.append("Learned beta tried to move some risky picks, so guardrails constrained it.")
            elif learned_guard_status == "watch":
                warnings.append("Learned beta is active with watch-list guardrails.")
        elif learned_rerank.get("reason") == "no_model":
            next_actions.append("Load a promoted learned model before relying on learned beta ordering.")
        elif learned_rerank.get("reason") and learned_rerank.get("reason") != "not_enabled":
            warnings.append("Learned beta is blocked until its promotion checks pass.")

        if score >= 0.72:
            status = "ready"
            headline = "Model signal is strong enough to trust this basket."
        elif score >= 0.46:
            status = "learning"
            headline = "Model signal is usable, but Adventour is still learning."
        else:
            status = "cold_start"
            headline = "Model signal is still early; lean on local guardrails and exploration."

        return {
            "status": status,
            "headline": headline,
            "score": round(score, 3),
            "learning_status": learning_status,
            "average_preference_confidence": round(average_confidence, 3),
            "average_signal_count": round(average_signal_count, 3),
            "member_count": len(members or []),
            "local_feeling_share": round(_clamp(local_share), 3),
            "member_coverage_share": round(_clamp(member_coverage), 3) if member_coverage is not None else None,
            "exploration_count": exploration_count,
            "exploration_eligible_count": exploration_eligible_count,
            "serendipity_score": round(_clamp(serendipity_score), 3) if serendipity_score is not None else None,
            "learned_rerank": {
                "applied": bool(learned_rerank.get("applied")),
                "reason": learned_rerank.get("reason"),
                "model_type": learned_rerank.get("model_type"),
                "guard_status": learned_guard_status,
                "guard_headline": learned_guard.get("headline"),
            },
            "basis": basis[:5],
            "warnings": warnings[:4],
            "next_actions": list(dict.fromkeys(next_actions))[:4],
        }

    def _recommendation_decision_summary(
        self,
        status,
        metrics,
        members,
        group_fit_summary=None,
        provider_errors=None,
        repeated_decided=False,
        strengths=None,
        warnings=None,
    ):
        provider_errors = provider_errors or []
        strengths = strengths or []
        warnings = warnings or []
        dimensions = []

        def dimension(name, label, score, warn_at, fail_at, summary, action=None):
            score = round(_clamp(score), 3)
            if score < fail_at:
                dimension_status = "fail"
            elif score < warn_at:
                dimension_status = "warn"
            else:
                dimension_status = "pass"
            item = {
                "name": name,
                "label": label,
                "score": score,
                "status": dimension_status,
                "summary": summary,
            }
            if action:
                item["next_action"] = action
            dimensions.append(item)
            return item

        local_share = metrics.get("local_feeling_share") or 0
        authenticity = metrics.get("average_authenticity") or 0
        generic_share = metrics.get("generic_risk_share") or 0
        local_score = _clamp((local_share * 0.55) + (authenticity * 0.45) - (generic_share * 0.35))
        dimension(
            "local_texture",
            "Local texture",
            local_score,
            0.58,
            0.38,
            f"{round(local_share * 100)}% local-feeling with {round(generic_share * 100)}% generic risk.",
            "Prefer hidden gems, local-feeling places, or widen the range for less generic options.",
        )

        diversity_coverage = metrics.get("diversity_coverage")
        dominant_group_share = metrics.get("dominant_group_share") or 0
        missing_intent_count = metrics.get("missing_intent_count") or 0
        variety_base = 0.5 if diversity_coverage is None else diversity_coverage
        variety_score = _clamp((variety_base * 0.78) + ((1 - dominant_group_share) * 0.22) - (missing_intent_count * 0.08))
        dimension(
            "slate_variety",
            "Slate variety",
            variety_score,
            0.62,
            0.42,
            f"{round(variety_base * 100)}% category coverage; {missing_intent_count} requested mood{'s' if missing_intent_count != 1 else ''} missing.",
            "Try a broader tag mix or a larger search radius so the basket does not collapse into one mood.",
        )

        first_page_diversity_coverage = metrics.get("first_page_diversity_coverage")
        first_page_dominant_group_share = metrics.get("first_page_dominant_group_share") or 0
        first_page_missing_intent_count = metrics.get("first_page_missing_intent_count") or 0
        first_page_base = 0.5 if first_page_diversity_coverage is None else first_page_diversity_coverage
        first_page_score = _clamp(
            (first_page_base * 0.76)
            + ((1 - first_page_dominant_group_share) * 0.24)
            - (first_page_missing_intent_count * 0.06)
        )
        dimension(
            "first_swipes",
            "First swipes",
            first_page_score,
            0.62,
            0.42,
            f"{round(first_page_base * 100)}% opening variety; {round(first_page_dominant_group_share * 100)}% one-mood concentration.",
            "Refresh or broaden filters if the opening cards feel repetitive before the rest of the basket appears.",
        )

        exploration_count = metrics.get("exploration_count") or 0
        exploration_eligible_count = metrics.get("exploration_eligible_count") or 0
        if exploration_eligible_count:
            exploration_score = _clamp(0.45 + min(exploration_count, 2) * 0.25)
            exploration_summary = (
                f"{exploration_count} guarded learning pick{'s' if exploration_count != 1 else ''} "
                f"from {exploration_eligible_count} eligible option{'s' if exploration_eligible_count != 1 else ''}."
            )
            exploration_action = "Allow one guarded learning pick when friend taste or hidden-gem coverage is still sparse."
        else:
            exploration_score = 0.78
            exploration_summary = "No guarded learning pick was needed for this run."
            exploration_action = None
        dimension(
            "learning",
            "Learning",
            exploration_score,
            0.55,
            0.25,
            exploration_summary,
            exploration_action,
        )

        if len(members or []) > 1:
            coverage = metrics.get("member_coverage_share")
            coverage = 0 if coverage is None else coverage
            average_fit = metrics.get("average_group_fit") or 0
            fairness = (group_fit_summary or {}).get("fairness_score")
            fairness = 0.5 if fairness is None else fairness
            rescue_count = metrics.get("party_coverage_rescue_count") or 0
            rescued_members = metrics.get("party_coverage_rescued_members") or []
            rescued_member_phrase = f" for {', '.join(rescued_members[:2])}" if rescued_members else ""
            rescue_phrase = (
                f" Adventour rescued {rescue_count} match{'es' if rescue_count != 1 else ''}"
                f"{rescued_member_phrase}."
                if rescue_count
                else ""
            )
            friend_score = _clamp((coverage * 0.45) + (average_fit * 0.35) + (fairness * 0.20))
            dimension(
                "friend_fit",
                "Friend fit",
                friend_score,
                0.70,
                0.50,
                f"{round(coverage * 100)}% friend coverage with {round(average_fit * 100)}% average party fit.{rescue_phrase}",
                "Switch to a group-friendly scout style or refresh until every friend has at least one strong match.",
            )

        provider_error_count = len(provider_errors)
        provider_score = 1.0
        provider_summary = "Place providers returned cleanly."
        provider_action = None
        if provider_error_count:
            provider_score = 0.25
            provider_summary = f"{provider_error_count} provider issue{'s' if provider_error_count != 1 else ''} during this search."
            provider_action = "Retry the search or check provider credentials before judging recommendation quality."
        elif repeated_decided:
            provider_score = 0.65
            provider_summary = "Fresh options were exhausted, so Adventour repeated decided places."
            provider_action = "Broaden the range or clear strict filters to get fresher picks."
        dimension(
            "provider_health",
            "Provider health",
            provider_score,
            0.70,
            0.45,
            provider_summary,
            provider_action,
        )

        weights = {
            "local_texture": 0.34,
            "slate_variety": 0.17,
            "first_swipes": 0.10,
            "learning": 0.10,
            "friend_fit": 0.23,
            "provider_health": 0.06,
        }
        weighted = [
            (item["score"], weights.get(item["name"], 0.1))
            for item in dimensions
        ]
        weight_total = sum(weight for _, weight in weighted) or 1
        score = round(sum(score * weight for score, weight in weighted) / weight_total, 3)

        dimension_statuses = [item["status"] for item in dimensions]
        if "fail" in dimension_statuses or status == "needs_attention":
            decision_status = "needs_attention"
            headline = "This run needs tuning before it is a reliable friend test."
        elif "warn" in dimension_statuses or status == "watch":
            decision_status = "watch"
            headline = "This run is usable, with a few visible tradeoffs."
        else:
            decision_status = "ready"
            headline = "This run is strong enough to test with friends."

        dimension_strengths = [
            f"{item['label']} looks solid."
            for item in dimensions
            if item["status"] == "pass"
        ]
        dimension_warnings = [
            item["summary"]
            for item in dimensions
            if item["status"] in {"warn", "fail"}
        ]
        next_actions = [
            item["next_action"]
            for item in dimensions
            if item.get("next_action") and item["status"] in {"warn", "fail"}
        ]

        return {
            "status": decision_status,
            "headline": headline,
            "score": score,
            "dimensions": dimensions,
            "strengths": (dimension_strengths + strengths)[:4],
            "warnings": (dimension_warnings + warnings)[:4],
            "next_actions": next_actions[:3],
        }

    def _recommendation_diagnostic(
        self,
        status,
        metrics,
        filter_summary=None,
        model_confidence=None,
        group_fit_summary=None,
        provider_errors=None,
        repeated_decided=False,
        members=None,
        decision_summary=None,
    ):
        metrics = metrics or {}
        filter_summary = filter_summary or {}
        model_confidence = model_confidence or {}
        provider_errors = provider_errors or []
        members = members or []
        stages = []

        def stage(name, label, score, status_value, summary, action=None):
            item = {
                "name": name,
                "label": label,
                "score": round(_clamp(score), 3),
                "status": status_value,
                "summary": summary,
            }
            if action:
                item["next_action"] = action
            stages.append(item)
            return item

        raw_candidates = int(metrics.get("raw_candidates") or filter_summary.get("raw_candidates") or 0)
        returned = int(metrics.get("returned") or 0)
        skipped = filter_summary.get("skipped") or {}
        hard_skips = int(skipped.get("hard_constraints") or 0)
        distance_skips = int(skipped.get("distance") or 0)
        discoverability_skips = int(skipped.get("not_discoverable") or 0)
        duplicate_skips = int(skipped.get("duplicates") or 0)
        non_positive_skips = int(skipped.get("non_positive_score") or 0)
        total_skips = hard_skips + distance_skips + discoverability_skips + duplicate_skips + non_positive_skips

        provider_status = "pass"
        provider_score = 1.0
        provider_summary = f"Providers returned {raw_candidates} raw candidate{'s' if raw_candidates != 1 else ''}."
        provider_action = None
        if provider_errors:
            provider_status = "fail"
            provider_score = 0.15
            provider_summary = f"{len(provider_errors)} provider issue{'s' if len(provider_errors) != 1 else ''} happened during retrieval."
            provider_action = "Fix provider credentials/errors before judging recommendation quality."
        elif raw_candidates == 0:
            provider_status = "fail"
            provider_score = 0.2
            provider_summary = "No raw places came back for this launch point and query mix."
            provider_action = "Try a broader radius, a different launch point, or seed open/local provider data."
        elif raw_candidates < 10:
            provider_status = "warn"
            provider_score = 0.55
            provider_summary = f"Only {raw_candidates} raw candidates came back, so Adventour had little to rank."
            provider_action = "Broaden search tags or radius before trusting this as a city-quality test."
        stage("retrieval", "Retrieval supply", provider_score, provider_status, provider_summary, provider_action)

        depth_score = _clamp(returned / 8)
        depth_status = "pass" if returned >= 8 else "warn" if returned >= 5 else "fail"
        depth_action = None if depth_status == "pass" else "Widen range, relax filters, or add more provider/open-data sources for this area."
        stage(
            "candidate_depth",
            "Swipe depth",
            depth_score,
            depth_status,
            f"{returned} ranked pick{'s' if returned != 1 else ''} survived into the basket.",
            depth_action,
        )

        filter_status = "pass"
        filter_score = 1.0
        filter_summary_text = "Filters did not materially shrink the basket."
        filter_action = None
        if raw_candidates:
            skip_share = _clamp(total_skips / max(raw_candidates, 1))
            filter_score = _clamp(1 - skip_share)
            if hard_skips and returned < 5:
                filter_status = "fail"
                filter_action = "Clear strict tag skips or search a broader area before testing this basket."
            elif skip_share >= 0.45:
                filter_status = "warn"
                filter_action = "Review distance, tag skips, and discoverability filters for this location."
            filter_summary_text = (
                f"Filters skipped {total_skips} of {raw_candidates} raw candidates "
                f"({hard_skips} tag, {distance_skips} distance, {discoverability_skips} discoverability)."
            )
        elif provider_errors:
            filter_score = 0.5
            filter_summary_text = "Filtering could not be judged because provider retrieval failed."
        stage("filtering", "Filter pressure", filter_score, filter_status, filter_summary_text, filter_action)

        local_share = metrics.get("local_feeling_share") or 0
        hidden_gems = int(metrics.get("hidden_gem_count") or 0)
        generic_share = metrics.get("generic_risk_share") or 0
        authenticity_score = _clamp((local_share * 0.55) + min(hidden_gems, 2) * 0.16 + ((1 - generic_share) * 0.13))
        authenticity_status = "pass" if authenticity_score >= 0.62 else "warn" if authenticity_score >= 0.42 else "fail"
        stage(
            "authenticity",
            "Local authenticity",
            authenticity_score,
            authenticity_status,
            f"{round(local_share * 100)}% local-feeling, {hidden_gems} hidden gem{'s' if hidden_gems != 1 else ''}, {round(generic_share * 100)}% generic risk.",
            None if authenticity_status == "pass" else "Try authenticity-forward scout, widen the range, or seed more local gems.",
        )

        diversity = metrics.get("diversity_coverage")
        diversity = 0.5 if diversity is None else diversity
        missing_intents = int(metrics.get("missing_intent_count") or 0)
        dominant_share = metrics.get("dominant_group_share") or 0
        variety_score = _clamp((diversity * 0.75) + ((1 - dominant_share) * 0.25) - missing_intents * 0.08)
        variety_status = "pass" if variety_score >= 0.66 else "warn" if variety_score >= 0.44 else "fail"
        stage(
            "variety",
            "Experience variety",
            variety_score,
            variety_status,
            f"{round(diversity * 100)}% mood coverage with {missing_intents} requested mood{'s' if missing_intents != 1 else ''} missing.",
            None if variety_status == "pass" else "Boost missing friend/tag groups or broaden the query mix.",
        )

        if len(members) > 1:
            coverage = metrics.get("member_coverage_share")
            coverage = 0 if coverage is None else coverage
            average_fit = metrics.get("average_group_fit") or 0
            fairness = (group_fit_summary or {}).get("fairness_score")
            fairness = 0.5 if fairness is None else fairness
            friend_score = _clamp((coverage * 0.5) + (average_fit * 0.32) + (fairness * 0.18))
            friend_status = "pass" if friend_score >= 0.70 else "warn" if friend_score >= 0.50 else "fail"
            stage(
                "friend_blend",
                "Friend blend",
                friend_score,
                friend_status,
                f"{round(coverage * 100)}% friend coverage and {round(average_fit * 100)}% average party fit.",
                None if friend_status == "pass" else "Tap the friend suggestion chips or switch to group-friendly scout.",
            )

        model_score = model_confidence.get("score")
        model_score = 0 if model_score is None else model_score
        model_status = "pass" if model_score >= 0.70 else "warn" if model_score >= 0.45 else "fail"
        stage(
            "model_signal",
            "Taste model",
            model_score,
            model_status,
            model_confidence.get("headline") or "Taste model confidence was evaluated for this run.",
            None if model_status == "pass" else "Collect more accepts, rejects, and ratings before relying on heavy personalization.",
        )

        if repeated_decided:
            stage(
                "freshness",
                "Freshness",
                0.45,
                "warn",
                "Adventour repeated decided places because fresh options were exhausted.",
                "Broaden range or reset strict filters to get new places.",
            )

        priority = {
            "fail": 0,
            "warn": 1,
            "unknown": 2,
            "pass": 3,
        }
        issue_candidates = [
            item for item in stages
            if item["status"] in {"fail", "warn", "unknown"}
        ]
        issue_candidates.sort(key=lambda item: (priority.get(item["status"], 3), item["score"]))
        primary_issue = issue_candidates[0] if issue_candidates else None

        if primary_issue:
            headline = f"{primary_issue['label']} is the first thing to tune."
            next_actions = [
                item["next_action"]
                for item in issue_candidates
                if item.get("next_action")
            ]
        else:
            headline = "Recommendation pipeline looks healthy for this run."
            next_actions = []

        return {
            "status": "ready" if not primary_issue and status == "ready" else status,
            "headline": headline,
            "primary_issue": primary_issue,
            "stages": stages,
            "next_actions": list(dict.fromkeys(next_actions))[:4],
            "summary": {
                "raw_candidates": raw_candidates,
                "returned": returned,
                "total_skipped": total_skips,
                "provider_error_count": len(provider_errors),
            },
            "decision_status": (decision_summary or {}).get("status"),
        }

    def _place_history(self, user):
        since = datetime.utcnow() - timedelta(days=RECENT_HISTORY_DAYS)
        events = (
            UserPlaceEvent.query
            .filter(
                UserPlaceEvent.user_id == user.id,
                UserPlaceEvent.event_type.in_(["impression", "accept", "reject"]),
                UserPlaceEvent.occurred_at >= since,
            )
            .all()
        )
        history = {}
        for event in events:
            item = history.setdefault(event.place_id, {
                "impressions": 0,
                "accepted": False,
                "rejected": False,
                "last_event_at": None,
            })
            if event.event_type == "impression":
                item["impressions"] += 1
            elif event.event_type == "accept":
                item["accepted"] = True
            elif event.event_type == "reject":
                item["rejected"] = True
            if not item["last_event_at"] or event.occurred_at > item["last_event_at"]:
                item["last_event_at"] = event.occurred_at
        return history

    def _friend_place_history(self, friends):
        friends = list(friends or [])
        if not friends:
            return {}

        friend_ids = [friend.id for friend in friends]
        friend_names = {
            friend.id: friend.display_name or friend.username or "Traveler"
            for friend in friends
        }
        since = datetime.utcnow() - timedelta(days=PREFERENCE_EVENT_HALF_LIFE_DAYS)
        events = (
            UserPlaceEvent.query
            .filter(
                UserPlaceEvent.user_id.in_(friend_ids),
                UserPlaceEvent.event_type.in_(["accept", "reject", "navigate", "arrival", "rate", "save", "share"]),
                UserPlaceEvent.occurred_at >= since,
            )
            .order_by(UserPlaceEvent.occurred_at.asc())
            .all()
        )
        by_place = {}
        per_friend_scores = {}
        for event in events:
            weight = EVENT_WEIGHTS.get(event.event_type, 0)
            if event.event_type == "rate" and event.event_value is not None:
                weight = float(event.event_value) - 3.0
            if weight == 0:
                continue

            friend_scores = per_friend_scores.setdefault(event.place_id, {})
            friend_scores[event.user_id] = friend_scores.get(event.user_id, 0.0) + weight

        for place_id, friend_scores in per_friend_scores.items():
            liked_by = []
            rejected_by = []
            signed_scores = []
            for user_id, raw_score in friend_scores.items():
                normalized = _signed_clamp(raw_score / 5.0)
                signed_scores.append(normalized)
                if normalized >= 0.35:
                    liked_by.append(friend_names.get(user_id, "Traveler"))
                elif normalized <= -0.15:
                    rejected_by.append(friend_names.get(user_id, "Traveler"))

            score = sum(signed_scores) / len(signed_scores) if signed_scores else 0
            by_place[place_id] = {
                "score": round(_signed_clamp(score), 3),
                "liked_by": liked_by[:3],
                "rejected_by": rejected_by[:3],
                "signal_count": len(signed_scores),
            }

        return by_place

    def _session_context(self, user):
        since = datetime.utcnow() - timedelta(hours=SESSION_CONTEXT_HOURS)
        events = (
            UserPlaceEvent.query
            .filter(
                UserPlaceEvent.user_id == user.id,
                UserPlaceEvent.event_type.in_(["accept", "reject", "navigate", "arrival", "rate", "save", "share"]),
                UserPlaceEvent.occurred_at >= since,
            )
            .order_by(UserPlaceEvent.occurred_at.desc())
            .limit(30)
            .all()
        )
        context = {
            "status": "empty",
            "window_hours": SESSION_CONTEXT_HOURS,
            "signal_count": 0,
            "positive_signal_count": 0,
            "negative_signal_count": 0,
            "categories": {},
            "cuisines": {},
            "activities": {},
            "top_positive_tags": [],
            "top_negative_tags": [],
            "last_signal_at": None,
        }
        if not events:
            return context

        now = datetime.utcnow()
        for event in events:
            feature = PlaceFeature.query.filter_by(place_id=event.place_id).first()
            if not feature:
                continue
            weight = self._session_event_weight(event, now)
            if abs(weight) < 0.05:
                continue
            context["signal_count"] += 1
            if weight > 0:
                context["positive_signal_count"] += 1
            else:
                context["negative_signal_count"] += 1
            if not context["last_signal_at"] or event.occurred_at > context["last_signal_at"]:
                context["last_signal_at"] = event.occurred_at
            self._apply_weight(context["categories"], _json_loads(feature.category_vector), weight)
            self._apply_weight(context["cuisines"], _json_loads(feature.cuisine_vector), weight)
            self._apply_weight(context["activities"], _json_loads(feature.activity_vector), weight)

        self._normalize_vector(context["categories"])
        self._normalize_vector(context["cuisines"])
        self._normalize_vector(context["activities"])
        context["top_positive_tags"] = self._top_vector_entries(context["categories"], positive=True, limit=4)
        context["top_negative_tags"] = self._top_vector_entries(context["categories"], positive=False, limit=4)
        context["last_signal_at"] = context["last_signal_at"].isoformat() if context["last_signal_at"] else None
        context["status"] = "active" if context["signal_count"] else "empty"
        return context

    def _session_event_weight(self, event, now=None):
        now = now or datetime.utcnow()
        weight = EVENT_WEIGHTS.get(event.event_type, 0)
        if event.event_type == "rate" and event.event_value is not None:
            weight = (float(event.event_value) - 3.0) * 2.0
        age_hours = max(0, (now - event.occurred_at).total_seconds() / 3600)
        return weight * (0.5 ** (age_hours / SESSION_CONTEXT_HALF_LIFE_HOURS))

    def _session_context_fit(self, feature, session_context):
        if not session_context or not session_context.get("signal_count"):
            return 0.0
        dimension_scores = []
        for feature_vector, context_key, weight in [
            (_json_loads(feature.category_vector), "categories", 0.65),
            (_json_loads(feature.cuisine_vector), "cuisines", 0.20),
            (_json_loads(feature.activity_vector), "activities", 0.15),
        ]:
            context_vector = session_context.get(context_key, {})
            if not feature_vector or not context_vector:
                continue
            dimension_scores.append(((self._cosine_like(feature_vector, context_vector) - 0.5) * 2, weight))
        if not dimension_scores:
            return 0.0
        total_weight = sum(weight for _, weight in dimension_scores) or 1
        centered_fit = sum(score * weight for score, weight in dimension_scores) / total_weight
        # React quickly during a live swipe/search loop without replacing long-term taste.
        confidence = _clamp((session_context.get("signal_count") or 0) / 2.0)
        return _clamp(centered_fit * confidence, minimum=-1.0, maximum=1.0)

    def _decided_place_ids(self, user):
        return {
            place_id
            for place_id, history in self._place_history(user).items()
            if history.get("accepted") or history.get("rejected")
        }

    def _retrieval_context(self, query_tags, boost_query_tags=None):
        raw_boosts = list(dict.fromkeys(
            str(tag).strip()
            for tag in boost_query_tags or []
            if tag is not None and str(tag).strip()
        ))
        expanded_boosts = []
        for tag in raw_boosts:
            for expanded in _expand_preference_tag(tag):
                if expanded and expanded not in expanded_boosts:
                    expanded_boosts.append(expanded)

        return {
            "query_tags": list(query_tags or []),
            "boost_query_tags": raw_boosts,
            "boosted_query_tags": expanded_boosts,
            "friend_adjusted": bool(raw_boosts),
        }

    def _query_tags(self, vectors, fallback_user, boost_tags=None):
        vectors = list(vectors or [])
        boosted = []
        for tag in boost_tags or []:
            for expanded in _expand_preference_tag(str(tag).strip()):
                if expanded and expanded not in boosted:
                    boosted.append(expanded)
        scores = {}
        for vector in vectors:
            for tag, value in vector.get("categories", {}).items():
                scores[tag] = scores.get(tag, 0) + value

        positive_scores = {
            tag: score
            for tag, score in scores.items()
            if score > 0
        }

        if not positive_scores and fallback_user.preferences:
            expanded = []
            for tag in [tag.strip() for tag in fallback_user.preferences.split(",") if tag.strip()]:
                expanded.extend(_expand_preference_tag(tag))
            return list(dict.fromkeys([*boosted, *expanded]))[:7]

        per_member_tags = []
        if len(vectors) > 1:
            for vector in vectors:
                member_ranked = sorted(
                    (
                        (tag, value)
                        for tag, value in (vector.get("categories") or {}).items()
                        if value > 0 and positive_scores.get(tag, 0) > 0
                    ),
                    key=lambda item: item[1],
                    reverse=True,
                )
                for tag, _ in member_ranked[:2]:
                    if tag not in per_member_tags:
                        per_member_tags.append(tag)

        ranked = sorted(positive_scores.items(), key=lambda item: item[1], reverse=True)
        limit = 5 if len(vectors) <= 1 else min(8, max(6, (len(vectors) * 2) + 2))
        if boosted:
            limit = min(10, max(limit, len(boosted) + 4))
        query_tags = list(boosted)
        for tag in per_member_tags:
            if tag not in query_tags:
                query_tags.append(tag)
        for tag, _ in ranked:
            if tag not in query_tags:
                query_tags.append(tag)
            if len(query_tags) >= limit:
                break
        return query_tags[:limit] or ["restaurant", "tourist_attraction", "park"]

    def _top_vector_entries(self, values, positive=True, limit=5):
        if positive:
            ranked = sorted(
                ((tag, value) for tag, value in (values or {}).items() if value > 0),
                key=lambda item: item[1],
                reverse=True,
            )
        else:
            ranked = sorted(
                ((tag, value) for tag, value in (values or {}).items() if value < 0),
                key=lambda item: item[1],
            )
        return [
            {
                "tag": tag,
                "weight": round(abs(float(value)), 3),
                "label": tag.replace("_", " ").title(),
            }
            for tag, value in ranked[:limit]
        ]

    def _intent_target_groups(self, vectors, query_tags, constraints):
        category_scores = {}
        for vector in vectors:
            for tag, value in (vector.get("categories") or {}).items():
                for group in _intent_groups_for_tags([tag]):
                    category_scores[group] = category_scores.get(group, 0) + float(value or 0)

        for tag in query_tags or []:
            for group in _intent_groups_for_tags([tag]):
                category_scores[group] = category_scores.get(group, 0) + 0.25

        for tag in constraints.get("included_tag_groups") or []:
            for group in _intent_groups_for_tags([tag]):
                category_scores[group] = category_scores.get(group, 0) + 1.0

        for tag in constraints.get("required_types_any") or []:
            for group in _intent_groups_for_tags([tag]):
                category_scores[group] = category_scores.get(group, 0) + 1.0

        excluded_groups = set()
        for tag in list(constraints.get("excluded_tag_groups") or []) + list(constraints.get("avoid_types") or []):
            excluded_groups.update(_intent_groups_for_tags([tag]))

        ranked_groups = [
            group
            for group, _ in sorted(category_scores.items(), key=lambda item: item[1], reverse=True)
            if group not in excluded_groups
        ]
        return set(ranked_groups[:5])

    def _score_place(
        self,
        feature,
        candidate,
        members,
        member_vectors,
        constraints,
        distance_meters,
        radius_meters,
        mode,
        history=None,
        scoring_profile=None,
        session_context=None,
        allow_decided=False,
        local_event_match=None,
        friend_history=None,
    ):
        history = history or {}
        friend_history = friend_history or {}
        profile = scoring_profile or self.scoring_profile
        member_fit_details = []
        for member in members:
            fit = self._member_fit(feature, member_vectors.get(member.id, {}))
            member_fit_details.append({
                "user_id": member.id,
                "display_name": member.display_name or member.username or "Adventourer",
                "fit": round(fit, 3),
            })
        member_fits = [item["fit"] for item in member_fit_details]
        personal_fit = member_fits[0] if member_fits else 0
        group_average = sum(member_fits) / len(member_fits) if member_fits else personal_fit
        group_min_fit = min(member_fits) if member_fits else personal_fit
        disagreement = max(member_fits) - min(member_fits) if len(member_fits) > 1 else 0
        group_min_fit_weight = profile.group_min_fit_weight if len(member_fits) > 1 else 0
        group_consensus_fit = (
            group_average * (1 - group_min_fit_weight)
            + group_min_fit * group_min_fit_weight
        )
        group_fit = _clamp(group_consensus_fit - (profile.group_disagreement_penalty * disagreement))

        hidden_gem_affinity = _average_vector_value(member_vectors, "hidden_gem_affinity")
        chain_avoidance = _average_vector_value(member_vectors, "avoid_chains")
        hidden_gem_multiplier = _affinity_multiplier(hidden_gem_affinity)
        chain_avoidance_multiplier = _affinity_multiplier(chain_avoidance, minimum=0.75, maximum=1.2)

        authenticity = _clamp(
            (feature.authenticity_score or 0)
            + (feature.hidden_gem_score or 0) * profile.authenticity_hidden_gem_weight * hidden_gem_multiplier
            - (feature.chain_probability or 0) * profile.authenticity_chain_penalty_weight * chain_avoidance_multiplier
            - (feature.tourist_trap_score or 0) * profile.authenticity_tourist_trap_penalty_weight
        )
        quality = self._quality_score(feature, candidate)
        context_fit = self._context_fit(distance_meters, radius_meters, mode)
        time_fit = self._time_context_fit(feature, constraints)
        novelty = self._novelty_score(history)
        preference_signal = self._preference_signal_summary(member_vectors)
        session_fit = 0 if allow_decided else self._session_context_fit(feature, session_context)
        friend_history_fit = _signed_clamp(friend_history.get("score") or 0)
        exploration_uncertainty = self._exploration_uncertainty(member_vectors)
        exploration = self._exploration_score(feature, candidate, history, exploration_uncertainty)
        value_gem = self._value_gem_score(feature, constraints, authenticity, quality)
        local_event_fit = _clamp((local_event_match or {}).get("score") or 0)
        authenticity_confidence = self._authenticity_confidence(feature, candidate)

        chain_penalty = (
            profile.chain_penalty * chain_avoidance_multiplier
            if constraints.get("avoid_chains", True)
            and feature.chain_probability > profile.chain_penalty_threshold
            else 0
        )
        price_penalty = self._price_penalty(feature, constraints, member_vectors, profile)
        time_penalty = profile.time_mismatch_penalty if time_fit <= profile.time_mismatch_threshold else 0
        group_fairness_penalty = self._group_fairness_penalty(group_min_fit, len(member_fits), profile)
        repeat_penalty = self._repeat_penalty(history, profile)
        decision_penalty = self._decision_penalty(history, allow_decided, profile)

        score = (
            personal_fit * profile.personal_fit_weight
            + group_fit * profile.group_fit_weight
            + authenticity * profile.authenticity_weight
            + quality * profile.quality_weight
            + context_fit * profile.context_fit_weight
            + time_fit * profile.time_fit_weight
            + novelty * profile.novelty_weight
            + exploration * profile.exploration_weight
            + value_gem * profile.value_weight
            + local_event_fit * profile.local_event_weight
            + session_fit * profile.session_context_weight
            + friend_history_fit * profile.friend_history_weight
            - chain_penalty
            - price_penalty
            - time_penalty
            - group_fairness_penalty
            - repeat_penalty
            - decision_penalty
        )
        exploitation_score = score - (exploration * profile.exploration_weight)

        components = {
            "scoring_profile": profile.name,
            "personal_fit": round(personal_fit, 3),
            "group_average_fit": round(group_average, 3),
            "group_consensus_fit": round(group_consensus_fit, 3),
            "group_min_fit_weight": round(group_min_fit_weight, 3),
            "group_fit": round(group_fit, 3),
            "group_member_count": len(member_fits),
            "group_min_fit": round(group_min_fit, 3),
            "group_fairness_penalty": round(group_fairness_penalty, 3),
            "authenticity": round(authenticity, 3),
            "authenticity_confidence": round(authenticity_confidence["score"], 3),
            "authenticity_confidence_status": authenticity_confidence["status"],
            "quality": round(quality, 3),
            "context_fit": round(context_fit, 3),
            "time_fit": round(time_fit, 3),
            "novelty": round(novelty, 3),
            "exploration": round(exploration, 3),
            "exploration_applied": round(exploration, 3),
            "value_gem": round(value_gem, 3),
            "local_event_fit": round(local_event_fit, 3),
            "session_context_fit": round(session_fit, 3),
            "session_context_signal_count": int((session_context or {}).get("signal_count") or 0),
            "friend_history_fit": round(friend_history_fit, 3),
            "friend_history_signal_count": int(friend_history.get("signal_count") or 0),
            "exploration_uncertainty": round(exploration_uncertainty, 3),
            "preference_confidence": round(preference_signal["confidence"], 3),
            "average_member_signal_count": round(preference_signal["average_signal_count"], 3),
            "hidden_gem_affinity": round(hidden_gem_affinity, 3),
            "chain_avoidance": round(chain_avoidance, 3),
            "chain_penalty": round(chain_penalty, 3),
            "price_penalty": round(price_penalty, 3),
            "time_penalty": round(time_penalty, 3),
            "repeat_penalty": round(repeat_penalty, 3),
            "decision_penalty": round(decision_penalty, 3),
        }
        history_payload = {
            "recent_impressions": history.get("impressions", 0),
            "accepted": bool(history.get("accepted")),
            "rejected": bool(history.get("rejected")),
            "friend_liked_by": friend_history.get("liked_by", []),
            "friend_rejected_by": friend_history.get("rejected_by", []),
        }
        explanation_details = self._explanation_details(
            components,
            feature,
            candidate,
            member_fit_details,
            history_payload,
            allow_decided,
            constraints,
            local_event_match,
        )
        return {
            "score": _clamp(score),
            "ranking": {
                "scoring_profile": profile.name,
                "exploitation_score": round(_clamp(exploitation_score), 3),
                "pre_exploration_budget_score": round(_clamp(score), 3),
                "objective_breakdown": self._objective_breakdown(
                    components,
                    profile,
                    final_score=_clamp(score),
                ),
            },
            "components": components,
            "member_fit": member_fit_details,
            "party_fit_summary": self._party_fit_summary(member_fit_details, components),
            "history": history_payload,
            "explanation": self._explain(components, feature, history_payload, allow_decided, constraints),
            "explanation_details": explanation_details,
            "recommendation_story": self._recommendation_story(
                components,
                feature,
                candidate,
                member_fit_details,
                history_payload,
                allow_decided,
                constraints,
                explanation_details,
                local_event_match,
            ),
        }

    def _objective_breakdown(self, components, profile, final_score=None):
        components = components or {}
        positive_objectives = [
            ("personal_taste", "Personal taste", components.get("personal_fit", 0), profile.personal_fit_weight),
            ("travel_party", "Travel-party fit", components.get("group_fit", 0), profile.group_fit_weight),
            ("authenticity", "Local authenticity", components.get("authenticity", 0), profile.authenticity_weight),
            ("quality", "Place quality", components.get("quality", 0), profile.quality_weight),
            ("context", "Distance/context fit", components.get("context_fit", 0), profile.context_fit_weight),
            ("time", "Time fit", components.get("time_fit", 0), profile.time_fit_weight),
            ("novelty", "Novelty", components.get("novelty", 0), profile.novelty_weight),
            ("exploration", "Exploration", components.get("exploration_applied", components.get("exploration", 0)), profile.exploration_weight),
            ("value_gem", "Value gem", components.get("value_gem", 0), profile.value_weight),
            ("local_event", "Local event", components.get("local_event_fit", 0), profile.local_event_weight),
            ("session_momentum", "Current session", max(0, components.get("session_context_fit", 0)), profile.session_context_weight),
            ("friend_history", "Friend history", max(0, components.get("friend_history_fit", 0)), profile.friend_history_weight),
        ]
        penalties = [
            ("chain", "Chain/generic risk", components.get("chain_penalty", 0)),
            ("price", "Price mismatch", components.get("price_penalty", 0)),
            ("time_mismatch", "Time mismatch", components.get("time_penalty", 0)),
            ("group_fairness", "Low group coverage", components.get("group_fairness_penalty", 0)),
            ("repeat", "Recently shown", components.get("repeat_penalty", 0)),
            ("previous_decision", "Already decided", components.get("decision_penalty", 0)),
            ("session_mismatch", "Current-session mismatch", abs(min(0, components.get("session_context_fit", 0)) * profile.session_context_weight)),
            ("friend_history_conflict", "Friend passed here", abs(min(0, components.get("friend_history_fit", 0)) * profile.friend_history_weight)),
        ]
        positive_rows = [
            {
                "id": objective_id,
                "label": label,
                "component": round(_clamp(value or 0), 3),
                "weight": round(weight, 3),
                "contribution": round(_clamp(value or 0) * weight, 3),
            }
            for objective_id, label, value, weight in positive_objectives
        ]
        penalty_rows = [
            {
                "id": penalty_id,
                "label": label,
                "penalty": round(max(0, value or 0), 3),
            }
            for penalty_id, label, value in penalties
            if (value or 0) > 0
        ]
        positive_total = sum(row["contribution"] for row in positive_rows)
        penalty_total = sum(row["penalty"] for row in penalty_rows)
        return {
            "model_family": "hybrid_multi_objective",
            "positive": positive_rows,
            "penalties": penalty_rows,
            "positive_total": round(positive_total, 3),
            "penalty_total": round(penalty_total, 3),
            "net_score": round(_clamp(positive_total - penalty_total), 3),
            "final_score": round(_clamp(final_score if final_score is not None else positive_total - penalty_total), 3),
            "top_positive": [
                row["id"]
                for row in sorted(positive_rows, key=lambda item: item["contribution"], reverse=True)
                if row["contribution"] > 0
            ][:3],
            "top_penalty": penalty_rows[0]["id"] if penalty_rows else None,
        }

    def _member_fit(self, feature, vector):
        category_fit = self._cosine_like(_json_loads(feature.category_vector), vector.get("categories", {}))
        cuisine_fit = self._cosine_like(_json_loads(feature.cuisine_vector), vector.get("cuisines", {}))
        activity_fit = self._cosine_like(_json_loads(feature.activity_vector), vector.get("activities", {}))
        return _clamp((category_fit * 0.65) + (cuisine_fit * 0.20) + (activity_fit * 0.15))

    def _group_fairness_penalty(self, group_min_fit, member_count, profile):
        if member_count <= 1 or group_min_fit >= profile.group_low_fit_threshold:
            return 0
        shortage = profile.group_low_fit_threshold - group_min_fit
        return min(profile.group_low_fit_penalty, shortage * profile.group_low_fit_penalty * 2)

    def _price_preference_from_events(self, events):
        weighted_total = 0.0
        weight_total = 0.0
        now = datetime.utcnow()
        for event in events:
            feature = PlaceFeature.query.filter_by(place_id=event.place_id).first()
            if not feature or feature.price_band is None:
                continue

            weight = EVENT_WEIGHTS.get(event.event_type, 0)
            if event.event_type == "rate" and event.event_value is not None:
                weight = (float(event.event_value) - 3.0) * 2.0
            weight *= _event_recency_multiplier(event.occurred_at, now)
            if weight <= 0:
                continue

            weighted_total += feature.price_band * weight
            weight_total += weight

        if weight_total <= 0:
            return None
        return round(weighted_total / weight_total, 2)

    def _derive_features(self, candidate):
        types = candidate.get("types") or candidate.get("categories") or []
        if isinstance(types, str):
            types = [types]

        category_vector = {str(tag): 1.0 for tag in types}
        name = candidate.get("name", "")
        chain_probability = 1.0 if is_chain(name) else 0.0
        hidden_gem = 1.0 if is_hidden_gem(candidate) else 0.0
        sentiment = review_sentiment_score(candidate.get("reviews", []))
        rating = candidate.get("rating") or 0
        ratings_total = candidate.get("user_ratings_total") or 0
        quality = _clamp((float(rating) / 5.0) if rating else 0.5)
        popularity = _clamp(math.log10(ratings_total + 1) / 4.0)
        authenticity = _clamp(0.65 + hidden_gem * 0.25 + sentiment * 0.2 - chain_probability * 0.5 - popularity * 0.1)

        return {
            "category_vector": _json_dumps(category_vector),
            "cuisine_vector": _json_dumps({}),
            "activity_vector": _json_dumps({}),
            "price_band": candidate.get("price_level") or candidate.get("price"),
            "chain_probability": chain_probability,
            "authenticity_score": authenticity,
            "hidden_gem_score": hidden_gem,
            "tourist_trap_score": _clamp(popularity - 0.65),
            "quality_score_adventour": quality,
            "popularity_score_adventour": popularity,
            "feature_version": "phase1",
        }

    def _candidate_lat_lng(self, candidate):
        geometry = candidate.get("geometry") or {}
        location = geometry.get("location") or {}
        geocodes = candidate.get("geocodes") or {}
        main = geocodes.get("main") or {}
        return (
            location.get("lat") or main.get("latitude"),
            location.get("lng") or main.get("longitude"),
        )

    def _display_payload(self, candidate):
        photos = candidate.get("photos") or []
        return {
            "name": candidate.get("name"),
            "vicinity": candidate.get("vicinity") or (candidate.get("location") or {}).get("formatted_address"),
            "rating": candidate.get("rating"),
            "user_ratings_total": candidate.get("user_ratings_total"),
            "price_level": candidate.get("price_level") or candidate.get("price"),
            "business_status": candidate.get("business_status"),
            "types": candidate.get("types") or candidate.get("categories") or [],
            "photo_url": first_photo_url(photos),
            "photo_attributions": photos[0].get("author_attributions", []) if photos else [],
        }

    def _recommendation_category(self, candidate):
        return classify_recommendation_lane(
            candidate.get("name"),
            candidate.get("types") or candidate.get("categories") or [],
        )

    def _quality_score(self, feature, candidate):
        provider_rating = candidate.get("rating")
        if provider_rating:
            return _clamp(float(provider_rating) / 5.0)
        return _clamp(feature.quality_score_adventour or 0.5)

    def _authenticity_confidence(self, feature, candidate=None):
        candidate = candidate or {}
        authenticity = _clamp(feature.authenticity_score or 0)
        hidden_gem = _clamp(feature.hidden_gem_score or 0)
        chain_risk = _clamp(feature.chain_probability or 0)
        tourist_trap = _clamp(feature.tourist_trap_score or 0)
        rating = candidate.get("rating")
        rating_count = int(candidate.get("user_ratings_total") or 0)
        reviews = candidate.get("reviews") or []
        photos = candidate.get("photos") or []
        types = candidate.get("types") or candidate.get("categories") or []

        score = 0.28
        reasons = []
        if rating:
            score += 0.18
            reasons.append("provider rating")
        if rating_count >= 20:
            score += 0.24
            reasons.append("enough rating volume")
        elif rating_count >= 5:
            score += 0.14
            reasons.append("some rating volume")
        elif rating_count > 0:
            score += 0.06
            reasons.append("very light rating volume")
        if reviews:
            score += 0.12
            reasons.append("review text")
        if types:
            score += 0.10
            reasons.append("place category")
        if photos:
            score += 0.06
            reasons.append("photo signal")
        if chain_risk >= 0.7:
            score += 0.16
            reasons.append("known chain-name match")
        if tourist_trap >= 0.35:
            score += 0.06
            reasons.append("popularity risk signal")
        if rating_count < 5 and (hidden_gem >= 0.7 or authenticity >= 0.7) and chain_risk < 0.7:
            score -= 0.16
            reasons.append("thin local proof")

        score = _clamp(score)
        if score >= 0.72:
            status = "strong"
            label = "Strong evidence"
        elif score >= 0.5:
            status = "usable"
            label = "Usable evidence"
        else:
            status = "thin"
            label = "Thin evidence"
        return {
            "score": round(score, 3),
            "status": status,
            "label": label,
            "rating_count": rating_count,
            "signals": reasons[:4],
        }

    def _authenticity_evidence(self, feature, candidate=None):
        authenticity = _clamp(feature.authenticity_score or 0)
        hidden_gem = _clamp(feature.hidden_gem_score or 0)
        chain_risk = _clamp(feature.chain_probability or 0)
        tourist_trap = _clamp(feature.tourist_trap_score or 0)
        popularity = _clamp(feature.popularity_score_adventour or 0)
        confidence = self._authenticity_confidence(feature, candidate)

        reasons = []
        if hidden_gem >= 0.7:
            label = "Hidden gem"
            reasons.append("low-volume/high-quality signal")
        elif chain_risk >= 0.7:
            label = "Generic risk"
            reasons.append("known chain or chain-like name")
        elif tourist_trap >= 0.35:
            label = "Tourist-heavy"
            reasons.append("very high popularity can mean less local texture")
        elif authenticity >= 0.7:
            label = "Local-feeling"
            reasons.append("strong local/authentic score")
        else:
            label = "Popular local"
            reasons.append("balanced quality and local signal")

        if popularity < 0.45:
            reasons.append("not overexposed by rating volume")
        if chain_risk < 0.3:
            reasons.append("low chain signal")

        return {
            "label": label,
            "score": round(authenticity, 3),
            "hidden_gem_score": round(hidden_gem, 3),
            "chain_risk": round(chain_risk, 3),
            "tourist_trap_score": round(tourist_trap, 3),
            "popularity_score": round(popularity, 3),
            "confidence": confidence["score"],
            "confidence_status": confidence["status"],
            "confidence_label": confidence["label"],
            "rating_count": confidence["rating_count"],
            "evidence_signals": confidence["signals"],
            "reasons": reasons[:3],
        }

    def _context_fit(self, distance_meters, radius_meters, mode):
        if distance_meters is None or not radius_meters:
            return 0.5
        closeness = 1 - (distance_meters / radius_meters)
        if mode == "spontaneous":
            return _clamp(closeness)
        return _clamp(0.5 + closeness * 0.5)

    def _time_context_label(self, constraints):
        time_context = constraints.get("time_context") or {}
        raw_label = time_context.get("period")
        if raw_label in TIME_CONTEXT_TYPES:
            return raw_label

        raw_hour = time_context.get("local_hour", constraints.get("local_hour"))
        try:
            hour = int(raw_hour)
        except (TypeError, ValueError):
            return None

        if 5 <= hour < 11:
            return "morning"
        if 11 <= hour < 14:
            return "midday"
        if 14 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 22:
            return "evening"
        return "late_night"

    def _time_context_fit(self, feature, constraints):
        label = self._time_context_label(constraints)
        if not label:
            return 0.5

        types = set(_json_loads(feature.category_vector, default={}).keys())
        rules = TIME_CONTEXT_TYPES.get(label, {})
        preferred_matches = len(types.intersection(rules.get("preferred", set())))
        avoid_matches = len(types.intersection(rules.get("avoid", set())))
        if preferred_matches:
            return 0.86
        if avoid_matches:
            return 0.18
        return 0.5

    def _novelty_score(self, history):
        impressions = history.get("impressions", 0)
        if impressions <= 0:
            return 1.0
        if impressions == 1:
            return 0.65
        if impressions == 2:
            return 0.4
        return 0.18

    def _exploration_uncertainty(self, member_vectors):
        confidences = []
        for vector in (member_vectors or {}).values():
            if vector.get("confidence") is not None:
                confidences.append(_clamp(vector.get("confidence")))
            else:
                confidences.append(_clamp((vector.get("signal_count") or 0) / 12.0))
        if not confidences:
            return 1.0
        return _clamp(1 - (sum(confidences) / len(confidences)))

    def _preference_signal_summary(self, member_vectors):
        confidences = []
        signal_counts = []
        for vector in (member_vectors or {}).values():
            signal_count = vector.get("signal_count")
            if signal_count is not None:
                signal_counts.append(max(0.0, _safe_float(signal_count)))
            if vector.get("confidence") is not None:
                confidences.append(_clamp(vector.get("confidence")))
            elif signal_count is not None:
                confidences.append(_clamp(_safe_float(signal_count) / 12.0))

        return {
            "confidence": sum(confidences) / len(confidences) if confidences else 0.0,
            "average_signal_count": sum(signal_counts) / len(signal_counts) if signal_counts else 0.0,
        }

    def _exploration_score(self, feature, candidate, history, uncertainty=1.0):
        if history.get("impressions", 0) > 0 or history.get("accepted") or history.get("rejected"):
            return 0

        authenticity = _clamp(feature.authenticity_score or 0)
        hidden_gem = _clamp(feature.hidden_gem_score or 0)
        chain_probability = _clamp(feature.chain_probability or 0)
        tourist_trap = _clamp(feature.tourist_trap_score or 0)
        popularity = _clamp(feature.popularity_score_adventour or 0)
        quality = self._quality_score(feature, candidate)

        if quality < 0.70 or authenticity < 0.65 or chain_probability > 0.35 or tourist_trap > 0.45:
            return 0

        underexposed = _clamp(1 - popularity)
        local_signal = max(authenticity, (authenticity + hidden_gem) / 2)
        uncertainty_multiplier = 0.75 + (_clamp(uncertainty) * 0.35)
        return _clamp(((local_signal * 0.50) + (underexposed * 0.35) + (quality * 0.15)) * uncertainty_multiplier)

    def _repeat_penalty(self, history, scoring_profile=None):
        profile = scoring_profile or self.scoring_profile
        impressions = history.get("impressions", 0)
        return min(
            profile.repeat_penalty_max,
            impressions * profile.repeat_penalty_per_impression,
        )

    def _decision_penalty(self, history, allow_decided, scoring_profile=None):
        profile = scoring_profile or self.scoring_profile
        if not allow_decided:
            return 0
        if history.get("rejected"):
            return profile.rejected_repeat_penalty
        if history.get("accepted"):
            return profile.accepted_repeat_penalty
        return 0

    def _price_penalty(self, feature, constraints, member_vectors=None, scoring_profile=None):
        profile = scoring_profile or self.scoring_profile
        price_max = constraints.get("price_max")
        if feature.price_band is None:
            return 0
        if price_max is not None:
            return profile.price_penalty if feature.price_band > price_max else 0

        learned_preferences = [
            vector.get("price_preference")
            for vector in (member_vectors or {}).values()
            if vector.get("price_preference") is not None
        ]
        if not learned_preferences:
            return 0

        preferred_price = sum(learned_preferences) / len(learned_preferences)
        overage = feature.price_band - (preferred_price + 1)
        if overage <= 0:
            return 0
        return min(profile.price_penalty, overage * profile.price_penalty * 0.5)

    def _value_gem_score(self, feature, constraints, authenticity, quality):
        if feature.price_band is None:
            return 0

        try:
            price_band = int(feature.price_band)
        except (TypeError, ValueError):
            return 0

        price_max = constraints.get("price_max")
        if price_max is not None:
            try:
                if price_band > int(price_max):
                    return 0
            except (TypeError, ValueError):
                pass

        if price_band > 1:
            return 0

        chain_risk = _clamp(feature.chain_probability or 0)
        tourist_trap = _clamp(feature.tourist_trap_score or 0)
        if chain_risk >= 0.55 or tourist_trap >= 0.6:
            return 0

        hidden_gem = _clamp(feature.hidden_gem_score or 0)
        affordability = 1.0
        score = _clamp(
            affordability * 0.36
            + _clamp(authenticity) * 0.34
            + _clamp(quality) * 0.14
            + hidden_gem * 0.16
            - chain_risk * 0.18
            - tourist_trap * 0.10
        )
        return score if score >= 0.55 else 0

    def _explain(self, components, feature, history=None, allow_decided=False, constraints=None):
        history = history or {}
        constraints = constraints or {}
        reasons = []
        if components["personal_fit"] >= 0.7:
            reasons.append("strong match for your saved taste")
        if components["group_fit"] >= 0.7:
            reasons.append("good fit for the group")
        if (
            components.get("group_member_count", 1) > 1
            and components.get("group_min_fit", 1) >= 0.55
            and components.get("group_fairness_penalty", 0) == 0
        ):
            reasons.append("balanced fit across the group")
        elif components.get("group_fairness_penalty", 0) > 0:
            reasons.append("deprioritized because one traveler may not enjoy it")
        if components["authenticity"] >= 0.7:
            reasons.append("local/authentic signal is high")
        if feature.hidden_gem_score >= 0.7:
            reasons.append("hidden-gem candidate")
        if components.get("hidden_gem_affinity", 0.75) > 0.78 and feature.hidden_gem_score >= 0.6:
            reasons.append("lifted by your local-gem history")
        if components["chain_penalty"] > 0:
            if components.get("chain_avoidance", 0.75) > 0.78:
                reasons.append("deprioritized by your chain-avoidance history")
            else:
                reasons.append("chain penalty applied")
        if components["price_penalty"] > 0:
            if constraints.get("price_max") is not None:
                reasons.append("above your selected budget")
            else:
                reasons.append("above your usual price comfort zone")
        if components["novelty"] >= 0.9:
            reasons.append("fresh pick you have not seen recently")
        elif components["repeat_penalty"] > 0:
            reasons.append("shown recently, so it is lightly deprioritized")
        if components.get("exploration", 0) >= 0.75:
            reasons.append("promising underexposed local pick")
        if components.get("session_context_fit", 0) >= 0.35:
            reasons.append("matches what you are leaning toward right now")
        elif components.get("session_context_fit", 0) <= -0.35:
            reasons.append("lowered because it resembles places you just passed")
        if allow_decided and history.get("rejected"):
            reasons.append("previously rejected and only repeated because nearby options are exhausted")
        elif allow_decided and history.get("accepted"):
            reasons.append("previously accepted and only repeated because nearby options are exhausted")
        time_label = self._time_context_label(constraints)
        if time_label and components.get("time_fit", 0.5) >= 0.75:
            reasons.append(f"fits the {time_label.replace('_', ' ')} vibe")
        elif time_label and components.get("time_fit", 0.5) <= 0.25:
            reasons.append(f"less ideal for {time_label.replace('_', ' ')} timing")
        if components["context_fit"] >= 0.7:
            reasons.append("close enough for this Adventour")

        if not reasons:
            reasons.append("balanced recommendation across taste, quality, and context")
        return "; ".join(reasons) + "."

    def _explanation_details(self, components, feature, candidate=None, member_fit_details=None, history=None, allow_decided=False, constraints=None, local_event_match=None):
        history = history or {}
        constraints = constraints or {}
        member_fit_details = member_fit_details or []
        details = []

        hidden_gem = _clamp(feature.hidden_gem_score or 0)
        chain_risk = _clamp(feature.chain_probability or 0)
        authenticity = components.get("authenticity", 0)
        popularity = _clamp(feature.popularity_score_adventour or 0)
        authenticity_evidence = self._authenticity_evidence(feature, candidate)

        if hidden_gem >= 0.7:
            details.append({
                "kind": "authenticity",
                "label": "Hidden-gem signal",
                "value": "Strong quality with lower exposure, so it feels more discovery-worthy.",
                "strength": round(hidden_gem, 3),
            })
        elif authenticity >= 0.7:
            details.append({
                "kind": "authenticity",
                "label": "Local-feeling pick",
                "value": "Adventour sees strong authenticity and local texture.",
                "strength": round(authenticity, 3),
            })

        if popularity < 0.45 and chain_risk < 0.35:
            details.append({
                "kind": "local_texture",
                "label": "Less generic",
                "value": "Lower chain and overexposure signals help it stand apart from default tourist picks.",
                "strength": round(1 - max(popularity, chain_risk), 3),
            })

        if (
            authenticity_evidence.get("confidence_status") == "thin"
            and authenticity_evidence.get("label") in {"Hidden gem", "Local-feeling", "Popular local"}
        ):
            details.append({
                "kind": "authenticity_confidence",
                "label": "Thin local proof",
                "value": "Promising local signal, but Adventour has limited evidence and should keep learning from swipes.",
                "strength": authenticity_evidence.get("confidence"),
            })

        if components.get("chain_penalty", 0) > 0:
            details.append({
                "kind": "chain_guard",
                "label": "Chain guard active",
                "value": "Lowered because Adventour is protecting the route from generic chain-heavy recommendations.",
                "strength": round(components.get("chain_avoidance", 0.75), 3),
            })
        elif chain_risk < 0.3:
            details.append({
                "kind": "chain_guard",
                "label": "Low chain signal",
                "value": "It does not look like a major chain from the available place signals.",
                "strength": round(1 - chain_risk, 3),
            })

        if member_fit_details:
            sorted_members = sorted(member_fit_details, key=lambda item: item.get("fit", 0), reverse=True)
            best_members = [item.get("display_name", "Traveler") for item in sorted_members if item.get("fit", 0) >= 0.65]
            low_members = [item.get("display_name", "Traveler") for item in sorted_members if item.get("fit", 0) < 0.45]
            if len(member_fit_details) > 1 and components.get("group_fairness_penalty", 0) == 0:
                details.append({
                    "kind": "group_fit",
                    "label": "Travel-party fit",
                    "value": (
                        "Balanced for the group"
                        + (f", especially {', '.join(best_members[:2])}" if best_members else "")
                        + "."
                    ),
                    "strength": round(components.get("group_fit", 0), 3),
                })
            elif len(member_fit_details) > 1 and low_members:
                details.append({
                    "kind": "group_fit",
                    "label": "Mixed party fit",
                    "value": f"May be weaker for {', '.join(low_members[:2])}, so swaps can help rebalance.",
                    "strength": round(components.get("group_min_fit", 0), 3),
                })

        time_label = self._time_context_label(constraints)
        if time_label and components.get("time_fit", 0.5) >= 0.75:
            details.append({
                "kind": "timing",
                "label": "Good timing",
                "value": f"Fits the {time_label.replace('_', ' ')} vibe for this search.",
                "strength": round(components.get("time_fit", 0.5), 3),
            })

        if components.get("price_penalty", 0) > 0:
            details.append({
                "kind": "budget",
                "label": "Budget caution",
                "value": "Kept in consideration, but nudged down because it may be above the selected or learned comfort zone.",
                "strength": round(1 - components.get("price_penalty", 0), 3),
            })
        elif components.get("value_gem", 0) >= 0.6:
            details.append({
                "kind": "value_gem",
                "label": "Value gem",
                "value": "Lifted because it looks affordable without giving up local texture.",
                "strength": round(components.get("value_gem", 0), 3),
            })

        if components.get("novelty", 0) >= 0.9:
            details.append({
                "kind": "freshness",
                "label": "Fresh pick",
                "value": "You have not seen this place recently in Adventour.",
                "strength": round(components.get("novelty", 0), 3),
            })
        elif components.get("repeat_penalty", 0) > 0:
            details.append({
                "kind": "freshness",
                "label": "Seen recently",
                "value": "Still eligible, but lightly lowered to keep the basket varied.",
                "strength": round(components.get("novelty", 0), 3),
            })

        if components.get("exploration_applied", 0) > 0:
            details.append({
                "kind": "exploration",
                "label": "Learning pick",
                "value": "Adventour is safely testing this underexposed local option because quality and authenticity cleared the guardrails.",
                "strength": round(components.get("exploration_applied", 0), 3),
            })

        if components.get("session_context_fit", 0) >= 0.25:
            details.append({
                "kind": "session_context",
                "label": "Current-session match",
                "value": "Boosted because it resembles what you are accepting or rating well in this live Adventour search.",
                "strength": round(components.get("session_context_fit", 0), 3),
            })
        elif components.get("session_context_fit", 0) <= -0.25:
            details.append({
                "kind": "session_context",
                "label": "Current-session mismatch",
                "value": "Lowered because it resembles places you recently passed in this live Adventour search.",
                "strength": round(abs(components.get("session_context_fit", 0)), 3),
            })

        if components.get("friend_history_fit", 0) >= 0.25 and history.get("friend_liked_by"):
            names = ", ".join(history.get("friend_liked_by", [])[:2])
            details.append({
                "kind": "friend_history",
                "label": "Friend liked this",
                "value": f"Boosted because {names} already showed positive Adventour signal here.",
                "strength": round(components.get("friend_history_fit", 0), 3),
            })
        elif components.get("friend_history_fit", 0) <= -0.15 and history.get("friend_rejected_by"):
            names = ", ".join(history.get("friend_rejected_by", [])[:2])
            details.append({
                "kind": "friend_history",
                "label": "Friend passed here",
                "value": f"Lowered because {names} passed on this place before.",
                "strength": round(abs(components.get("friend_history_fit", 0)), 3),
            })

        if local_event_match and components.get("local_event_fit", 0) >= 0.5:
            title = local_event_match.get("title") or "a nearby local event"
            distance = local_event_match.get("distance_to_place_meters")
            distance_label = (
                f"{round(distance)}m away"
                if distance is not None and distance < 1000
                else f"{distance / 1609.344:.1f} mi away"
                if distance is not None
                else "nearby"
            )
            details.append({
                "kind": "local_event",
                "label": "Event nearby",
                "value": f"Pairs with {title}, {distance_label}, so it can anchor a more social Adventour.",
                "strength": round(components.get("local_event_fit", 0), 3),
            })

        if allow_decided and (history.get("rejected") or history.get("accepted")):
            details.append({
                "kind": "history",
                "label": "Exhausted-area repeat",
                "value": "Repeated only because stronger nearby options were exhausted.",
                "strength": 0.5,
            })

        return details[:6]

    def _recommendation_story(
        self,
        components,
        feature,
        candidate=None,
        member_fit_details=None,
        history=None,
        allow_decided=False,
        constraints=None,
        explanation_details=None,
        local_event_match=None,
    ):
        history = history or {}
        constraints = constraints or {}
        member_fit_details = member_fit_details or []
        explanation_details = explanation_details or []
        authenticity = self._authenticity_evidence(feature, candidate)
        reasons = []
        cautions = []
        metrics = [
            {
                "id": "match",
                "label": "Taste match",
                "value": round(components.get("personal_fit", 0), 3),
                "display": f"{round(components.get('personal_fit', 0) * 100)}%",
            },
            {
                "id": "local_signal",
                "label": "Local signal",
                "value": round(components.get("authenticity", 0), 3),
                "display": f"{round(components.get('authenticity', 0) * 100)}%",
            },
            {
                "id": "hidden_gem",
                "label": "Hidden-gem",
                "value": round(_clamp(feature.hidden_gem_score or 0), 3),
                "display": f"{round(_clamp(feature.hidden_gem_score or 0) * 100)}%",
            },
            {
                "id": "local_proof",
                "label": "Proof",
                "value": authenticity.get("confidence"),
                "display": authenticity.get("confidence_label"),
            },
        ]

        if member_fit_details:
            sorted_members = sorted(member_fit_details, key=lambda item: item.get("fit", 0), reverse=True)
            low_members = [item for item in sorted_members if item.get("fit", 0) < 0.45]
            strong_members = [item for item in sorted_members if item.get("fit", 0) >= 0.65]
            metrics.append({
                "id": "party_fit",
                "label": "Party fit",
                "value": round(components.get("group_fit", 0), 3),
                "display": f"{round(components.get('group_fit', 0) * 100)}%",
            })
            if len(member_fit_details) > 1 and not low_members:
                names = ", ".join(item.get("display_name", "Traveler") for item in strong_members[:2])
                reasons.append(f"Works across the travel party{f', especially {names}' if names else ''}.")
            elif len(member_fit_details) > 1 and low_members:
                names = ", ".join(item.get("display_name", "Traveler") for item in low_members[:2])
                cautions.append(f"May be weaker for {names}; group-friendly swaps can rebalance it.")
            elif components.get("personal_fit", 0) >= 0.65:
                reasons.append("Strong match for your learned Adventour taste.")

        if components.get("exploration_applied", 0) > 0:
            metrics.append({
                "id": "learning",
                "label": "Learning",
                "value": round(components.get("exploration_applied", 0), 3),
                "display": f"{round(components.get('exploration_applied', 0) * 100)}%",
            })
        if components.get("session_context_signal_count", 0) > 0:
            metrics.append({
                "id": "session_context",
                "label": "Now",
                "value": round(components.get("session_context_fit", 0), 3),
                "display": f"{round(components.get('session_context_fit', 0) * 100)}%",
            })
        if components.get("friend_history_signal_count", 0) > 0:
            metrics.append({
                "id": "friend_history",
                "label": "Friend",
                "value": round(components.get("friend_history_fit", 0), 3),
                "display": f"{round(components.get('friend_history_fit', 0) * 100)}%",
            })
        if components.get("value_gem", 0) > 0:
            metrics.append({
                "id": "value_gem",
                "label": "Value",
                "value": round(components.get("value_gem", 0), 3),
                "display": f"{round(components.get('value_gem', 0) * 100)}%",
            })
        if local_event_match and components.get("local_event_fit", 0) > 0:
            metrics.append({
                "id": "local_event",
                "label": "Event fit",
                "value": round(components.get("local_event_fit", 0), 3),
                "display": f"{round(components.get('local_event_fit', 0) * 100)}%",
            })

        if authenticity.get("label") == "Hidden gem":
            reasons.append("Looks like a hidden-gem candidate with stronger local texture than exposure.")
        elif authenticity.get("label") == "Local-feeling":
            reasons.append("Has a local-feeling signal, not just broad popularity.")
        elif authenticity.get("label") == "Generic risk":
            cautions.append("Generic or chain-like signals are present, so Adventour lowered the score.")
        if components.get("value_gem", 0) >= 0.6:
            reasons.append("Affordable without losing the local Adventour feel.")
        if (
            authenticity.get("confidence_status") == "thin"
            and authenticity.get("label") in {"Hidden gem", "Local-feeling", "Popular local"}
        ):
            cautions.append("Local proof is still thin, so Adventour should learn from your swipe here.")

        for detail in explanation_details:
            value = detail.get("value")
            if value and len(reasons) < 4 and detail.get("kind") not in {"chain_guard", "budget", "history"}:
                reasons.append(value)

        if local_event_match and len(reasons) < 4:
            title = local_event_match.get("title") or "a nearby local event"
            reasons.append(f"Can pair with {title} to make the stop feel more current and social.")

        if components.get("exploration_applied", 0) > 0:
            reasons.append("Included as guarded exploration because it is underexposed but still quality-filtered.")
        if components.get("session_context_fit", 0) >= 0.25:
            reasons.append("Matches the direction of your current swipe session.")
        if components.get("friend_history_fit", 0) >= 0.25 and history.get("friend_liked_by"):
            reasons.append(f"{', '.join(history.get('friend_liked_by', [])[:2])} already liked this place.")
        if components.get("time_fit", 0.5) >= 0.75:
            time_label = self._time_context_label(constraints)
            if time_label:
                reasons.append(f"Fits the {time_label.replace('_', ' ')} timing for this search.")
        if components.get("price_penalty", 0) > 0:
            cautions.append("May be above the selected or learned price comfort zone.")
        if components.get("repeat_penalty", 0) > 0:
            cautions.append("You saw this recently, so Adventour lightly lowered it.")
        if components.get("session_context_fit", 0) <= -0.25:
            cautions.append("Similar to places you recently passed in this session.")
        if components.get("friend_history_fit", 0) <= -0.15 and history.get("friend_rejected_by"):
            cautions.append(f"{', '.join(history.get('friend_rejected_by', [])[:2])} passed on this before.")
        if allow_decided and history.get("rejected"):
            cautions.append("Previously passed; repeated only because this area is running low on fresh options.")
        elif allow_decided and history.get("accepted"):
            cautions.append("Previously accepted; repeated only because this area is running low on fresh options.")

        if not reasons:
            reasons.append("Balanced recommendation across taste, quality, local signal, and distance.")

        headline = self._recommendation_story_headline(components, authenticity, member_fit_details, cautions)
        return {
            "headline": headline,
            "reasons": reasons[:4],
            "cautions": cautions[:3],
            "metrics": metrics,
            "authenticity_label": authenticity.get("label"),
            "authenticity_confidence_label": authenticity.get("confidence_label"),
            "confidence": round(_clamp(components.get("score", 0) or components.get("personal_fit", 0)), 3),
        }

    def _recommendation_story_headline(self, components, authenticity, member_fit_details, cautions):
        if components.get("group_member_count", 1) > 1 and components.get("group_min_fit", 0) >= 0.55:
            return "A balanced pick for this travel party."
        if authenticity.get("label") == "Hidden gem":
            return "A local-gem leaning pick Adventour wants you to see."
        if components.get("exploration_applied", 0) > 0:
            return "A promising local discovery Adventour is learning from."
        if components.get("personal_fit", 0) >= 0.7:
            return "A strong match for your Adventour taste."
        if cautions:
            return "A useful option with a few tradeoffs."
        return "A balanced pick for this launch point."

    def _apply_weight(self, target, source, weight):
        for key, value in source.items():
            target[key] = target.get(key, 0) + (float(value) * weight)

    def _normalize_vector(self, vector):
        if not vector:
            return
        max_abs = max(abs(value) for value in vector.values()) or 1
        for key in list(vector.keys()):
            normalized = vector[key] / max_abs
            if abs(normalized) < 0.05:
                del vector[key]
            else:
                vector[key] = round(normalized, 4)

    def _cosine_like(self, left, right):
        if not left or not right:
            return 0.0
        numerator = sum(float(left.get(key, 0)) * float(right.get(key, 0)) for key in left.keys())
        left_norm = math.sqrt(sum(float(value) ** 2 for value in left.values()))
        right_norm = math.sqrt(sum(float(value) ** 2 for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        return _clamp((numerator / (left_norm * right_norm) + 1) / 2)
