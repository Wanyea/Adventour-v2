from copy import deepcopy
from datetime import datetime
import math


ROUTE_DISTANCE_PENALTY_START_METERS = 1200
ROUTE_DISTANCE_PENALTY_FULL_METERS = 8000
ROUTE_DISTANCE_PENALTY_MAX = 0.45
ROUTE_MEMBER_REBALANCE_THRESHOLD = 0.12
ROUTE_MEMBER_REBALANCE_BONUS_MAX = 0.24
ROUTE_MEMBER_STRONG_FIT_THRESHOLD = 0.65
MAX_ITINERARY_DAYS = 7


SLOT_DEFINITIONS = [
    {
        "id": "morning_anchor",
        "label": "Morning launch",
        "time_window": "9:00 AM - 10:30 AM",
        "preferred_types": {"cafe", "coffee_shop", "bakery", "breakfast_restaurant", "brunch_restaurant"},
        "role": "Start with something easy, local, and low-friction.",
    },
    {
        "id": "late_morning_discovery",
        "label": "Local discovery",
        "time_window": "10:45 AM - 12:30 PM",
        "preferred_types": {"museum", "art_gallery", "park", "garden", "historical_landmark", "book_store", "market"},
        "role": "Give the route a memorable neighborhood or culture stop.",
    },
    {
        "id": "lunch",
        "label": "Lunch stop",
        "time_window": "12:45 PM - 2:00 PM",
        "preferred_types": {"restaurant", "lunch_restaurant", "mexican_restaurant", "seafood_restaurant", "sandwich_shop"},
        "role": "Choose a real meal spot instead of a generic chain.",
    },
    {
        "id": "afternoon_gem",
        "label": "Afternoon gem",
        "time_window": "2:15 PM - 4:30 PM",
        "preferred_types": {"tourist_attraction", "park", "art_gallery", "market", "museum", "shopping_mall", "clothing_store"},
        "role": "Add the place that makes the Adventour feel specific to the city.",
    },
    {
        "id": "evening_finish",
        "label": "Evening finish",
        "time_window": "5:30 PM - 8:00 PM",
        "preferred_types": {"restaurant", "bar", "night_club", "concert_hall", "performing_arts_theater", "comedy_club"},
        "role": "End with dinner, nightlife, or a social local experience.",
    },
]

SLOTS_BY_PACE = {
    "relaxed": {"morning_anchor", "lunch", "afternoon_gem"},
    "balanced": {"morning_anchor", "late_morning_discovery", "lunch", "evening_finish"},
    "full": {slot["id"] for slot in SLOT_DEFINITIONS},
}

BUDGET_PROFILES = {
    "budget": {"price_max": 1, "label": "Budget-conscious"},
    "flexible": {"price_max": 2, "label": "Flexible"},
    "splurge": {"price_max": 4, "label": "Splurge-friendly"},
}


PRICE_LEVEL_ESTIMATES = {
    0: (0, 10),
    1: (10, 20),
    2: (20, 45),
    3: (45, 85),
    4: (85, 150),
}


TYPE_DIVERSITY_GROUPS = {
    "food_drink": {
        "restaurant",
        "lunch_restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "mexican_restaurant",
        "seafood_restaurant",
        "sandwich_shop",
        "cafe",
        "coffee_shop",
        "bakery",
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
        "garden",
        "zoo",
        "aquarium",
        "hiking_area",
    },
    "shopping_market": {
        "market",
        "book_store",
        "clothing_store",
        "shopping_mall",
    },
    "nightlife": {
        "bar",
        "night_club",
        "concert_hall",
        "comedy_club",
    },
}

EVENT_CATEGORY_SLOT_HINTS = {
    "market": {"late_morning_discovery", "afternoon_gem"},
    "makers": {"late_morning_discovery", "afternoon_gem"},
    "popup": {"lunch", "afternoon_gem", "evening_finish"},
    "food": {"lunch", "evening_finish"},
    "music": {"evening_finish"},
    "concert": {"evening_finish"},
    "art": {"late_morning_discovery", "afternoon_gem"},
    "gallery": {"late_morning_discovery", "afternoon_gem"},
    "theater": {"evening_finish"},
    "comedy": {"evening_finish"},
    "outdoor": {"late_morning_discovery", "afternoon_gem"},
    "community": {"late_morning_discovery", "afternoon_gem", "evening_finish"},
}

EVENT_HOUR_SLOT_HINTS = [
    (6, 11, {"morning_anchor", "late_morning_discovery"}),
    (11, 14, {"lunch"}),
    (14, 17, {"afternoon_gem"}),
    (17, 24, {"evening_finish"}),
    (0, 3, {"evening_finish"}),
]


def _display_types(recommendation):
    return set(recommendation.get("display", {}).get("types") or [])


def _display_name(recommendation):
    return recommendation.get("name") or recommendation.get("display", {}).get("name") or "this stop"


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _optional_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _slot_match(slot, recommendation):
    types = _display_types(recommendation)
    if not types:
        return 0
    return len(types.intersection(slot["preferred_types"]))


def _clone_recommendation(recommendation):
    payload = deepcopy(recommendation)
    payload.pop("repeat_after_exhaustion", None)
    return payload


def _clone_route_recommendation(recommendation):
    payload = _clone_recommendation(recommendation)
    payload["diversity_groups"] = sorted(_diversity_groups(payload))
    return payload


def _diversity_groups(recommendation):
    types = _display_types(recommendation)
    groups = {
        group
        for group, group_types in TYPE_DIVERSITY_GROUPS.items()
        if types.intersection(group_types)
    }
    return groups or {"other"}


def _same_point(first, second, tolerance=0.000001):
    return (
        abs(float(first[0]) - float(second[0])) <= tolerance
        and abs(float(first[1]) - float(second[1])) <= tolerance
    )


def _haversine_meters(start, end):
    lat1, lon1 = start
    lat2, lon2 = end
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


def _parse_event_start(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


class ItineraryRecommendationService:
    """Build planned Adventour routes from ranked place recommendations.

    This is intentionally deterministic and transparent for the beta. It keeps
    the trusted recommender as the ranking engine, then adds route slots,
    alternatives, and cost/logistics assumptions around those ranked places.
    """

    def __init__(self, recommendation_service, local_event_service=None, travel_logistics_service=None):
        self.recommendation_service = recommendation_service
        self.local_event_service = local_event_service
        self.travel_logistics_service = travel_logistics_service

    def recommend_itinerary(
        self,
        user,
        location,
        radius_meters=8000,
        member_ids=None,
        constraints=None,
        party_size=1,
        days=1,
        destination_label=None,
    ):
        raw_constraints = constraints or {}
        days = self._resolve_days(days, raw_constraints)
        constraints = {
            "limit": 60,
            "avoid_chains": True,
            **raw_constraints,
        }
        party_size = max(1, int(party_size or 1))
        trip_style = constraints.get("trip_style") or ("day" if days == 1 else "vacation")
        pace = constraints.get("pace") if constraints.get("pace") in SLOTS_BY_PACE else "balanced"
        budget_profile = constraints.get("budget_profile") if constraints.get("budget_profile") in BUDGET_PROFILES else "flexible"
        constraints["limit"] = max(
            int(constraints.get("limit") or 60),
            days * len(self._slots_for_pace(pace)) * 3,
        )
        if constraints.get("price_max") is None:
            constraints["price_max"] = BUDGET_PROFILES[budget_profile]["price_max"]

        recommendation_result = self.recommendation_service.recommend(
            user=user,
            location=location,
            radius_meters=radius_meters,
            member_ids=member_ids or [],
            constraints=constraints,
            mode="planned",
        )
        party_size = max(party_size, int(recommendation_result.get("member_count") or 1))
        candidates = recommendation_result.get("recommendations", [])
        route_days = []
        used_place_ids = set()

        for day_number in range(1, days + 1):
            day_stops = []
            day_slots = self._slots_for_pace(pace)
            day_context = {
                "groups": {},
                "types": {},
                "member_totals": {},
                "member_counts": {},
                "slot_ids": [slot["id"] for slot in day_slots],
                "points": [],
                "last_point": None,
            }
            for slot in day_slots:
                selected = self._pick_for_slot(slot, candidates, used_place_ids, day_context)
                if not selected:
                    continue
                selected_route_components = self._slot_score_components(slot, selected, day_context)
                stop_reasoning = self._stop_reasoning(slot, selected, day_context, selected_route_components)
                used_place_ids.add(selected["place_id"])
                self._update_route_context(day_context, selected)
                alternatives = self._alternatives_for_slot(slot, candidates, used_place_ids, selected, day_context)
                day_stops.append({
                    "slot_id": slot["id"],
                    "label": slot["label"],
                    "time_window": slot["time_window"],
                    "role": slot["role"],
                    "recommendation": _clone_route_recommendation(selected),
                    "party_fit_summary": self._stop_party_fit_summary(selected),
                    "why_this_stop": stop_reasoning,
                    "alternatives": [
                        self._clone_swap_alternative(slot, selected, item, day_context)
                        for item in alternatives
                    ],
                    "diversity_groups": sorted(_diversity_groups(selected)),
                    "swap_hint": "Swap with an alternative to keep the same time slot and route shape.",
                })

            route_days.append({
                "day": day_number,
                "title": f"Day {day_number}: {destination_label or 'Adventour'} local route",
                "summary": self._day_summary(day_stops),
                "route_balance": self._route_balance(day_context),
                "party_fit": self._party_fit(day_stops),
                "stops": day_stops,
            })

        local_events = self._local_events(
            user,
            location,
            radius_meters,
            destination_label,
            constraints,
            recommendation_result.get("query_tags", []),
            member_ids or [],
        )
        local_events = self._route_aware_local_events(local_events, route_days)
        booking_plan = self._booking_plan(route_days, party_size, destination_label, constraints)
        route_readiness = self._route_readiness(
            route_days=route_days,
            expected_stop_count=days * len(self._slots_for_pace(pace)),
            filter_summary=recommendation_result.get("filter_summary"),
            provider_errors=recommendation_result.get("provider_errors", []),
            booking_plan=booking_plan,
            local_events=local_events,
        )
        price_breakdown = self._price_breakdown(
            route_days,
            party_size,
            budget_profile,
            recommendation_result.get("members", []),
            constraints,
            booking_plan,
        )
        trip_logistics_readiness = self._trip_logistics_readiness(booking_plan, price_breakdown)
        trip_style_fit = self._trip_style_fit(
            trip_style=trip_style,
            route_days=route_days,
            route_readiness=route_readiness,
            price_breakdown=price_breakdown,
            booking_plan=booking_plan,
            local_events=local_events,
            trip_logistics_readiness=trip_logistics_readiness,
        )
        route_explanation = self._route_explanation(
            route_days=route_days,
            route_readiness=route_readiness,
            price_breakdown=price_breakdown,
            booking_plan=booking_plan,
            local_events=local_events,
            member_count=recommendation_result.get("member_count", 1),
            scoring_profile=recommendation_result.get("scoring_profile"),
        )
        launch_checklist = self._launch_checklist(
            route_days=route_days,
            route_readiness=route_readiness,
            booking_plan=booking_plan,
            local_events=local_events,
        )
        itinerary_story = self._itinerary_story(
            destination_label=destination_label,
            trip_style=trip_style,
            pace=pace,
            budget_profile=budget_profile,
            route_days=route_days,
            route_readiness=route_readiness,
            route_explanation=route_explanation,
            price_breakdown=price_breakdown,
            booking_plan=booking_plan,
            local_events=local_events,
            member_count=recommendation_result.get("member_count", 1),
        )
        swap_guide = self._swap_guide(route_days)
        route_model_confidence = self._route_model_confidence(
            route_days=route_days,
            recommendation_result=recommendation_result,
            route_readiness=route_readiness,
        )
        trip_packet = self._trip_packet(
            route_days=route_days,
            route_readiness=route_readiness,
            price_breakdown=price_breakdown,
            booking_plan=booking_plan,
            launch_checklist=launch_checklist,
            local_events=local_events,
            trip_logistics_readiness=trip_logistics_readiness,
            trip_style_fit=trip_style_fit,
        )
        self._attach_swap_guide_to_trip_packet(trip_packet, swap_guide)
        self._attach_route_model_confidence_to_trip_packet(trip_packet, route_model_confidence)
        self._attach_beta_readiness_to_trip_packet(trip_packet, route_readiness)

        return {
            "mode": "planned_itinerary",
            "request_id": recommendation_result.get("request_id"),
            "scoring_profile": recommendation_result.get("scoring_profile"),
            "available_scoring_profiles": recommendation_result.get("available_scoring_profiles", []),
            "title": self._title(destination_label, days, trip_style),
            "destination": destination_label,
            "trip_style": trip_style,
            "pace": pace,
            "budget_profile": budget_profile,
            "nights": self._lodging_nights(days, constraints),
            "member_count": recommendation_result.get("member_count", 1),
            "members": recommendation_result.get("members", []),
            "query_tags": recommendation_result.get("query_tags", []),
            "retrieval_context": recommendation_result.get("retrieval_context", {}),
            "provider_errors": recommendation_result.get("provider_errors", []),
            "filter_summary": recommendation_result.get("filter_summary"),
            "learned_rerank": recommendation_result.get("learned_rerank"),
            "preference_insights": recommendation_result.get("preference_insights", []),
            "recommendation_quality": recommendation_result.get("recommendation_quality"),
            "days": route_days,
            "price_breakdown": price_breakdown,
            "logistics": self._logistics(route_days),
            "booking_plan": booking_plan,
            "trip_logistics_readiness": trip_logistics_readiness,
            "trip_style_fit": trip_style_fit,
            "local_events": local_events,
            "route_readiness": route_readiness,
            "route_authenticity": route_readiness.get("authenticity_summary"),
            "route_explanation": route_explanation,
            "launch_checklist": launch_checklist,
            "itinerary_story": itinerary_story,
            "trip_packet": trip_packet,
            "swap_guide": swap_guide,
            "route_model_confidence": route_model_confidence,
            "swap_model": {
                "strategy": "slot_locked_alternatives",
                "description": "Each stop includes alternatives chosen for the same time slot so users can swap without rebuilding the whole Adventour.",
            },
        }

    def _resolve_days(self, requested_days, constraints):
        resolved = max(1, min(int(requested_days or 1), MAX_ITINERARY_DAYS))
        if (constraints or {}).get("trip_style") != "vacation":
            return resolved

        travel_dates = (constraints or {}).get("travel_dates") or {}
        start = _parse_event_start(travel_dates.get("start"))
        end = _parse_event_start(travel_dates.get("end"))
        if start and end and end >= start:
            resolved = (end.date() - start.date()).days + 1
        return max(1, min(resolved, MAX_ITINERARY_DAYS))

    def _slots_for_pace(self, pace):
        allowed_ids = SLOTS_BY_PACE.get(pace, SLOTS_BY_PACE["balanced"])
        return [slot for slot in SLOT_DEFINITIONS if slot["id"] in allowed_ids]

    def _pick_for_slot(self, slot, candidates, used_place_ids, route_context=None):
        unused = [item for item in candidates if item["place_id"] not in used_place_ids]
        if not unused:
            return None
        ranked = sorted(
            unused,
            key=lambda item: self._slot_route_score(slot, item, route_context or {}),
            reverse=True,
        )
        return ranked[0]

    def _alternatives_for_slot(self, slot, candidates, used_place_ids, selected_recommendation, route_context=None):
        selected_place_id = selected_recommendation["place_id"]
        swap_context = self._route_context_without(route_context or {}, selected_recommendation)
        alternatives = [
            item for item in candidates
            if item["place_id"] != selected_place_id and item["place_id"] not in used_place_ids
        ]
        alternatives.sort(
            key=lambda item: self._slot_route_score(slot, item, swap_context),
            reverse=True,
        )
        return alternatives[:3]

    def _clone_swap_alternative(self, slot, selected_recommendation, alternative, route_context):
        swap_context = self._route_context_without(route_context or {}, selected_recommendation)
        payload = _clone_route_recommendation(alternative)
        payload["swap_impact"] = self._swap_impact(slot, selected_recommendation, alternative, swap_context)
        return payload

    def _route_context_without(self, route_context, recommendation):
        context = deepcopy(route_context or {})
        context["groups"] = dict(context.get("groups") or {})
        context["types"] = dict(context.get("types") or {})
        context["member_totals"] = dict(context.get("member_totals") or {})
        context["member_counts"] = dict(context.get("member_counts") or {})
        context["slot_ids"] = list(context.get("slot_ids") or [])
        context["points"] = list(context.get("points") or [])

        for group in _diversity_groups(recommendation):
            next_count = context["groups"].get(group, 0) - 1
            if next_count > 0:
                context["groups"][group] = next_count
            else:
                context["groups"].pop(group, None)
        for place_type in _display_types(recommendation):
            next_count = context["types"].get(place_type, 0) - 1
            if next_count > 0:
                context["types"][place_type] = next_count
            else:
                context["types"].pop(place_type, None)
        for member in recommendation.get("member_fit") or []:
            user_id = member.get("user_id")
            fit = member.get("fit")
            if user_id is None or fit is None:
                continue
            next_total = context["member_totals"].get(user_id, 0) - float(fit)
            next_count = context["member_counts"].get(user_id, 0) - 1
            if next_count > 0:
                context["member_totals"][user_id] = next_total
                context["member_counts"][user_id] = next_count
            else:
                context["member_totals"].pop(user_id, None)
                context["member_counts"].pop(user_id, None)
        recommendation_point = self._coordinates(recommendation)
        if recommendation_point and context["points"]:
            if _same_point(context["points"][-1], recommendation_point):
                context["points"].pop()
            else:
                context["points"] = [
                    point for point in context["points"]
                    if not _same_point(point, recommendation_point)
                ]
        context["last_point"] = context["points"][-1] if context["points"] else None
        return context

    def _slot_route_score(self, slot, recommendation, route_context):
        return self._slot_score_components(slot, recommendation, route_context)["route_score"]

    def _slot_score_components(self, slot, recommendation, route_context):
        slot_fit = min(_slot_match(slot, recommendation), 3) * 0.35
        base_score = recommendation.get("score", 0) or 0
        components = recommendation.get("components") or {}
        authenticity = components.get("authenticity", 0) or 0
        quality = components.get("quality", 0) or 0
        diversity_penalty = self._diversity_penalty(recommendation, route_context)
        travel_penalty = self._travel_penalty(recommendation, route_context)
        member_rebalance_bonus = self._member_rebalance_bonus(recommendation, route_context)
        route_score = (
            base_score
            + slot_fit
            + authenticity * 0.08
            + quality * 0.04
            + member_rebalance_bonus
            - diversity_penalty
            - travel_penalty
        )
        return {
            "route_score": route_score,
            "base_score": base_score,
            "slot_fit": slot_fit,
            "slot_matches": _slot_match(slot, recommendation),
            "authenticity": authenticity,
            "quality": quality,
            "friend_history_fit": _optional_float(components.get("friend_history_fit"), 0),
            "diversity_penalty": diversity_penalty,
            "travel_penalty": travel_penalty,
            "member_rebalance_bonus": member_rebalance_bonus,
            "travel_distance_meters": self._travel_distance_meters(recommendation, route_context),
            "member_fit": self._average_member_fit(recommendation),
        }

    def _swap_impact(self, slot, selected_recommendation, alternative, swap_context):
        current = self._slot_score_components(slot, selected_recommendation, swap_context)
        replacement = self._slot_score_components(slot, alternative, swap_context)
        cost_impact = self._swap_cost_impact(selected_recommendation, alternative)
        score_delta = replacement["route_score"] - current["route_score"]
        authenticity_delta = replacement["authenticity"] - current["authenticity"]
        member_fit_delta = replacement["member_fit"] - current["member_fit"]
        current_consensus_fit = self._group_consensus_fit(selected_recommendation)
        replacement_consensus_fit = self._group_consensus_fit(alternative)
        consensus_delta = replacement_consensus_fit - current_consensus_fit
        current_consensus_gap = self._group_consensus_gap(selected_recommendation)
        replacement_consensus_gap = self._group_consensus_gap(alternative)
        consensus_gap_delta = current_consensus_gap - replacement_consensus_gap
        diversity_delta = current["diversity_penalty"] - replacement["diversity_penalty"]
        travel_delta = current["travel_penalty"] - replacement["travel_penalty"]
        rebalance_delta = replacement["member_rebalance_bonus"] - current["member_rebalance_bonus"]
        slot_fit_delta = replacement["slot_fit"] - current["slot_fit"]
        friend_history_delta = replacement["friend_history_fit"] - current["friend_history_fit"]
        friend_signal = self._swap_friend_signal(selected_recommendation, alternative, friend_history_delta)
        member_fit_changes = self._swap_member_fit_changes(selected_recommendation, alternative)
        target_members = [
            item for item in member_fit_changes
            if item.get("coverage_status") == "covered_by_swap" or item.get("delta", 0) >= 0.12
        ]
        weakened_members = [
            item for item in member_fit_changes
            if item.get("delta", 0) <= -0.12
        ]
        low_friction = self._swap_low_friction(
            score_delta=score_delta,
            travel_delta=travel_delta,
            slot_fit_delta=slot_fit_delta,
            replacement=replacement,
            cost_impact=cost_impact,
        )

        reasons = []
        if rebalance_delta >= 0.05:
            reasons.append("Helps rebalance the party")
        if member_fit_delta >= 0.05:
            reasons.append("Improves party fit")
        if target_members:
            names = ", ".join(item["display_name"] for item in target_members[:2])
            reasons.append(f"Gives {names} a stronger match")
        if consensus_delta >= 0.05:
            reasons.append("Improves group consensus")
        if consensus_gap_delta >= 0.04:
            reasons.append("Narrows the group fit gap")
        if travel_delta >= 0.05:
            reasons.append("Keeps the route tighter")
        if diversity_delta >= 0.05:
            reasons.append("Adds more route variety")
        if authenticity_delta >= 0.05:
            reasons.append("More local-authentic")
        if friend_history_delta >= 0.15 and friend_signal.get("replacement_liked_by"):
            reasons.append("Adds friend-backed social proof")
        if cost_impact["status"] == "saves":
            reasons.append(f"May save about {cost_impact['delta_label']} per person")
        if replacement["slot_matches"] >= current["slot_matches"] and replacement["slot_matches"] > 0:
            reasons.append("Keeps the time slot natural")
        if not reasons:
            reasons.append("Similar fit with a different vibe" if score_delta >= -0.15 else "Bigger change to the route")
        readiness = self._swap_readiness(
            score_delta=score_delta,
            authenticity_delta=authenticity_delta,
            member_fit_delta=member_fit_delta,
            diversity_delta=diversity_delta,
            travel_delta=travel_delta,
            rebalance_delta=rebalance_delta,
            friend_history_delta=friend_history_delta,
            replacement=replacement,
            low_friction=low_friction,
            cost_impact=cost_impact,
        )
        decision = self._swap_decision(
            readiness=readiness,
            reasons=reasons,
            score_delta=score_delta,
            authenticity_delta=authenticity_delta,
            member_fit_delta=member_fit_delta,
            diversity_delta=diversity_delta,
            travel_delta=travel_delta,
            rebalance_delta=rebalance_delta,
            friend_history_delta=friend_history_delta,
            friend_signal=friend_signal,
            replacement=replacement,
            low_friction=low_friction,
            cost_impact=cost_impact,
        )

        return {
            "route_score_delta": round(score_delta, 3),
            "authenticity_delta": round(authenticity_delta, 3),
            "member_fit_delta": round(member_fit_delta, 3),
            "group_consensus_delta": round(consensus_delta, 3),
            "group_consensus_gap_delta": round(consensus_gap_delta, 3),
            "current_group_consensus_fit": round(current_consensus_fit, 3),
            "replacement_group_consensus_fit": round(replacement_consensus_fit, 3),
            "current_group_consensus_gap": round(current_consensus_gap, 3),
            "replacement_group_consensus_gap": round(replacement_consensus_gap, 3),
            "target_members": target_members[:3],
            "weakened_members": weakened_members[:3],
            "variety_delta": round(diversity_delta, 3),
            "travel_efficiency_delta": round(travel_delta, 3),
            "member_rebalance_delta": round(rebalance_delta, 3),
            "friend_history_delta": round(friend_history_delta, 3),
            "current_friend_history_fit": round(current["friend_history_fit"], 3),
            "replacement_friend_history_fit": round(replacement["friend_history_fit"], 3),
            "friend_signal": friend_signal,
            "travel_distance_meters": replacement["travel_distance_meters"],
            "slot_fit_delta": round(slot_fit_delta, 3),
            "price_level_delta": cost_impact["price_level_delta"],
            "known_cost_delta_low": cost_impact["delta_low"],
            "known_cost_delta_high": cost_impact["delta_high"],
            "cost_impact_status": cost_impact["status"],
            "cost_impact_label": cost_impact["label"],
            "cost_impact_detail": cost_impact["detail"],
            "low_friction_score": low_friction["score"],
            "low_friction_label": low_friction["label"],
            "reasons": reasons[:3],
            "swap_readiness": readiness,
            "swap_decision": decision,
        }

    def _swap_member_fit_changes(self, selected_recommendation, alternative):
        current = self._member_fit_by_id(selected_recommendation)
        replacement = self._member_fit_by_id(alternative)
        user_ids = sorted(set(current.keys()).union(replacement.keys()), key=lambda value: str(value))
        changes = []
        for user_id in user_ids:
            current_member = current.get(user_id) or {}
            replacement_member = replacement.get(user_id) or {}
            current_fit = current_member.get("fit")
            replacement_fit = replacement_member.get("fit")
            if current_fit is None or replacement_fit is None:
                continue
            delta = replacement_fit - current_fit
            if current_fit < ROUTE_MEMBER_STRONG_FIT_THRESHOLD <= replacement_fit:
                coverage_status = "covered_by_swap"
            elif replacement_fit >= ROUTE_MEMBER_STRONG_FIT_THRESHOLD:
                coverage_status = "covered"
            elif delta > 0:
                coverage_status = "improved"
            else:
                coverage_status = "watch"
            changes.append({
                "user_id": user_id,
                "display_name": replacement_member.get("display_name") or current_member.get("display_name") or "Traveler",
                "current_fit": round(current_fit, 3),
                "replacement_fit": round(replacement_fit, 3),
                "delta": round(delta, 3),
                "coverage_status": coverage_status,
            })
        changes.sort(
            key=lambda item: (
                1 if item["coverage_status"] == "covered_by_swap" else 0,
                item["delta"],
                item["replacement_fit"],
            ),
            reverse=True,
        )
        return changes

    def _member_fit_by_id(self, recommendation):
        members = {}
        for member in recommendation.get("member_fit") or []:
            user_id = member.get("user_id")
            fit = member.get("fit")
            if user_id is None or fit is None:
                continue
            members[user_id] = {
                "display_name": member.get("display_name") or "Traveler",
                "fit": float(fit),
            }
        return members

    def _recommendation_price_estimate(self, recommendation):
        display = recommendation.get("display") or {}
        raw_level = display.get("price_level", recommendation.get("price_level"))
        try:
            price_level = int(raw_level)
        except (TypeError, ValueError):
            price_level = None

        known = price_level in PRICE_LEVEL_ESTIMATES
        estimate_level = price_level if known else 2
        low, high = PRICE_LEVEL_ESTIMATES.get(estimate_level, PRICE_LEVEL_ESTIMATES[2])
        return {
            "known": known,
            "price_level": price_level,
            "estimate_level": estimate_level,
            "low": low,
            "high": high,
        }

    def _format_cost_delta(self, delta_low, delta_high):
        low = abs(int(round(delta_low)))
        high = abs(int(round(delta_high)))
        if low == high:
            return f"${high}"
        return f"${low}-${high}"

    def _swap_cost_impact(self, selected_recommendation, alternative):
        current = self._recommendation_price_estimate(selected_recommendation)
        replacement = self._recommendation_price_estimate(alternative)
        known = current["known"] and replacement["known"]
        delta_low = replacement["low"] - current["low"]
        delta_high = replacement["high"] - current["high"]
        price_level_delta = (
            replacement["price_level"] - current["price_level"]
            if known else None
        )

        if not known:
            status = "unknown"
            label = "Cost unknown"
            detail = "Live cost check needed"
        elif delta_high >= 25 or (price_level_delta is not None and price_level_delta >= 2):
            status = "pricier"
            label = "Pricier swap"
            detail = f"+{self._format_cost_delta(delta_low, delta_high)}"
        elif delta_high <= -15 or (price_level_delta is not None and price_level_delta <= -2):
            status = "saves"
            label = "May save money"
            detail = f"-{self._format_cost_delta(delta_low, delta_high)}"
        else:
            status = "similar"
            label = "Similar cost"
            detail = "about the same"

        return {
            "status": status,
            "label": label,
            "detail": detail,
            "known": known,
            "price_level_delta": price_level_delta,
            "delta_low": int(round(delta_low)) if known else None,
            "delta_high": int(round(delta_high)) if known else None,
            "delta_label": self._format_cost_delta(delta_low, delta_high) if known else None,
            "current": current,
            "replacement": replacement,
        }

    def _swap_low_friction(self, score_delta, travel_delta, slot_fit_delta, replacement, cost_impact=None):
        travel_distance = replacement.get("travel_distance_meters")
        if travel_distance is None:
            distance_score = 0.74
        elif travel_distance <= ROUTE_DISTANCE_PENALTY_START_METERS:
            distance_score = 1.0
        elif travel_distance >= ROUTE_DISTANCE_PENALTY_FULL_METERS:
            distance_score = 0.24
        else:
            distance_score = 1 - (
                (travel_distance - ROUTE_DISTANCE_PENALTY_START_METERS)
                / max(1, ROUTE_DISTANCE_PENALTY_FULL_METERS - ROUTE_DISTANCE_PENALTY_START_METERS)
            )

        route_hold_score = _clamp(0.72 + min(0.18, score_delta) - min(0.32, abs(min(0, score_delta))))
        slot_hold_score = 1.0 if slot_fit_delta >= 0 else max(0.35, 1 + slot_fit_delta)
        travel_hold_score = _clamp(0.72 + min(0.18, travel_delta) - min(0.28, abs(min(0, travel_delta))))
        cost_status = (cost_impact or {}).get("status")
        cost_delta_high = _optional_float((cost_impact or {}).get("delta_high"))
        if cost_status == "saves":
            cost_hold_score = 1.0
        elif cost_status == "pricier" and cost_delta_high >= 60:
            cost_hold_score = 0.42
        elif cost_status == "pricier":
            cost_hold_score = 0.62
        elif cost_status == "similar":
            cost_hold_score = 0.88
        else:
            cost_hold_score = 0.74
        score = _clamp(
            distance_score * 0.31
            + route_hold_score * 0.26
            + slot_hold_score * 0.19
            + travel_hold_score * 0.16
            + cost_hold_score * 0.08
        )
        if score >= 0.78:
            label = "Low-friction swap"
        elif score >= 0.58:
            label = "Manageable swap"
        else:
            label = "High-friction swap"
        return {
            "score": round(score, 3),
            "label": label,
        }

    def _swap_readiness(
        self,
        score_delta,
        authenticity_delta,
        member_fit_delta,
        diversity_delta,
        travel_delta,
        rebalance_delta,
        friend_history_delta,
        replacement,
        low_friction,
        cost_impact=None,
    ):
        positive_signal = sum(
            max(0, value)
            for value in [
                score_delta,
                authenticity_delta,
                member_fit_delta,
                diversity_delta,
                travel_delta,
                rebalance_delta,
                friend_history_delta * 0.6,
            ]
        )
        negative_signal = sum(
            abs(min(0, value))
            for value in [
                score_delta,
                authenticity_delta,
                member_fit_delta,
                diversity_delta,
                travel_delta,
                friend_history_delta * 0.6,
            ]
        )
        score = _clamp(0.52 + positive_signal * 0.55 - negative_signal * 0.45)
        travel_distance = replacement.get("travel_distance_meters")
        if travel_distance is not None and travel_distance >= ROUTE_DISTANCE_PENALTY_FULL_METERS:
            score = max(0, score - 0.18)
        cost_status = (cost_impact or {}).get("status")
        cost_delta_high = _optional_float((cost_impact or {}).get("delta_high"))
        if cost_status == "pricier" and cost_delta_high >= 60:
            score = max(0, score - 0.10)
        elif cost_status == "pricier":
            score = max(0, score - 0.05)

        if score_delta >= 0.04 and travel_delta >= -0.04 and low_friction["score"] >= 0.58 and cost_delta_high < 60:
            status = "safe_upgrade"
            label = "Safe upgrade"
            next_action = "Swap this in; it improves the route without adding much travel friction."
        elif rebalance_delta >= 0.05 or member_fit_delta >= 0.05:
            status = "party_rebalance"
            label = "Party rebalance" if low_friction["score"] >= 0.5 else "Party rebalance, travel check"
            next_action = "Use this if the group fit matters more than keeping the current stop."
        elif score_delta >= -0.08 and travel_delta >= -0.10:
            status = "balanced_tradeoff"
            label = "Balanced tradeoff"
            next_action = "Swap if this vibe feels better; the route should still hold together."
        else:
            status = "route_risk"
            label = "Route risk"
            next_action = "Preview the travel jump before swapping this into the route."

        return {
            "status": status,
            "label": label,
            "score": round(score, 3),
            "low_friction_score": low_friction["score"],
            "low_friction_label": low_friction["label"],
            "next_action": next_action,
        }

    def _swap_decision(
        self,
        readiness,
        reasons,
        score_delta,
        authenticity_delta,
        member_fit_delta,
        diversity_delta,
        travel_delta,
        rebalance_delta,
        friend_history_delta,
        friend_signal,
        replacement,
        low_friction,
        cost_impact=None,
    ):
        status = readiness.get("status")
        travel_distance = replacement.get("travel_distance_meters")
        score = readiness.get("score", 0)
        should_swap = (
            (status in {"safe_upgrade", "party_rebalance"} and low_friction["score"] >= 0.5)
            or (status == "balanced_tradeoff" and score >= 0.58)
        )

        if status == "safe_upgrade":
            headline = "Worth swapping in."
            best_when = "Choose this when you want a stronger route without losing the shape of the day."
        elif status == "party_rebalance":
            headline = "Best for the group."
            best_when = "Choose this when one traveler needs a better fit."
        elif status == "balanced_tradeoff":
            headline = "Taste call."
            best_when = "Choose this if the vibe feels more interesting than the current stop."
        else:
            headline = "Preview before swapping."
            best_when = "Choose this only if you are comfortable changing the route more aggressively."

        tradeoffs = []
        if score_delta < -0.08:
            tradeoffs.append("lower route fit")
        if travel_delta < -0.08:
            tradeoffs.append("more travel friction")
        if diversity_delta < -0.05:
            tradeoffs.append("less route variety")
        if member_fit_delta < -0.05:
            tradeoffs.append("weaker party fit")
        if authenticity_delta < -0.05:
            tradeoffs.append("less local-authentic")
        if (cost_impact or {}).get("status") == "pricier":
            detail = (cost_impact or {}).get("detail")
            tradeoffs.append(f"higher estimated cost{f' ({detail})' if detail else ''}")
        if friend_history_delta <= -0.15:
            tradeoffs.append("weaker friend signal")
        if not tradeoffs:
            if travel_distance is not None and travel_distance <= ROUTE_DISTANCE_PENALTY_START_METERS:
                tradeoff = "Low travel tradeoff."
            elif score_delta >= 0:
                tradeoff = "No major tradeoff detected."
            else:
                tradeoff = "Small route tradeoff."
        else:
            tradeoff = "Tradeoff: " + ", ".join(tradeoffs[:3]) + "."

        badges = []
        if score_delta >= 0.04:
            badges.append({"label": "Route", "detail": "upgrade", "tone": "positive"})
        elif score_delta <= -0.08:
            badges.append({"label": "Route", "detail": "risk", "tone": "caution"})
        else:
            badges.append({"label": "Route", "detail": "similar", "tone": "neutral"})

        cost_status = (cost_impact or {}).get("status")
        if cost_status == "saves":
            badges.append({"label": "Cost", "detail": (cost_impact or {}).get("detail"), "tone": "positive"})
        elif cost_status == "pricier":
            badges.append({"label": "Cost", "detail": (cost_impact or {}).get("detail"), "tone": "caution"})

        if authenticity_delta >= 0.05:
            badges.append({"label": "Local", "detail": "better", "tone": "positive"})
        elif authenticity_delta <= -0.05:
            badges.append({"label": "Local", "detail": "lower", "tone": "caution"})

        if rebalance_delta >= 0.05 or member_fit_delta >= 0.05:
            badges.append({"label": "Party", "detail": "better", "tone": "positive"})
        elif member_fit_delta <= -0.05:
            badges.append({"label": "Party", "detail": "weaker", "tone": "caution"})

        if friend_history_delta >= 0.15 and friend_signal.get("replacement_liked_by"):
            liked_names = friend_signal.get("replacement_liked_by", [])[:2]
            badges.append({
                "label": "Friend",
                "detail": f"{liked_names[0]} liked" if len(liked_names) == 1 else f"{liked_names[0]} +{len(liked_names) - 1} liked",
                "tone": "positive",
                "names": liked_names,
            })
        elif friend_history_delta <= -0.15 or friend_signal.get("replacement_rejected_by"):
            rejected_names = friend_signal.get("replacement_rejected_by", [])[:2]
            badges.append({
                "label": "Friend",
                "detail": f"{rejected_names[0]} passed" if len(rejected_names) == 1 else "check",
                "tone": "caution",
                "names": rejected_names,
            })

        if low_friction["score"] >= 0.78:
            badges.append({"label": "Friction", "detail": "low", "tone": "positive"})
        elif low_friction["score"] < 0.58:
            badges.append({"label": "Friction", "detail": "check", "tone": "caution"})

        if travel_delta >= 0.05:
            badges.append({"label": "Travel", "detail": "tighter", "tone": "positive"})
        elif travel_delta <= -0.08:
            badges.append({"label": "Travel", "detail": "farther", "tone": "caution"})

        if diversity_delta >= 0.05:
            badges.append({"label": "Mix", "detail": "fresher", "tone": "positive"})

        return {
            "headline": headline,
            "should_swap": should_swap,
            "best_when": best_when,
            "tradeoff": tradeoff,
            "primary_reason": reasons[0] if reasons else readiness.get("label"),
            "confidence": round(score, 3),
            "low_friction_score": low_friction["score"],
            "low_friction_label": low_friction["label"],
            "badges": badges[:4],
        }

    def _swap_friend_signal(self, selected_recommendation, alternative, friend_history_delta):
        selected_history = selected_recommendation.get("history") or {}
        alternative_history = alternative.get("history") or {}
        replacement_liked_by = list(alternative_history.get("friend_liked_by") or [])
        replacement_rejected_by = list(alternative_history.get("friend_rejected_by") or [])
        current_liked_by = list(selected_history.get("friend_liked_by") or [])
        current_rejected_by = list(selected_history.get("friend_rejected_by") or [])

        if friend_history_delta >= 0.15 and replacement_liked_by:
            label = "Friend-backed swap"
            message = f"{', '.join(replacement_liked_by[:2])} already liked the replacement."
            status = "positive"
        elif replacement_rejected_by:
            label = "Friend caution"
            message = f"{', '.join(replacement_rejected_by[:2])} passed on the replacement before."
            status = "caution"
        elif friend_history_delta <= -0.15 and current_liked_by:
            label = "Loses friend proof"
            message = f"The current stop had friend support from {', '.join(current_liked_by[:2])}."
            status = "caution"
        else:
            label = "No strong friend swap signal"
            message = None
            status = "neutral"

        return {
            "status": status,
            "label": label,
            "message": message,
            "current_liked_by": current_liked_by[:3],
            "current_rejected_by": current_rejected_by[:3],
            "replacement_liked_by": replacement_liked_by[:3],
            "replacement_rejected_by": replacement_rejected_by[:3],
        }

    def _swap_guide(self, route_days):
        stops = [
            (day, stop)
            for day in route_days
            for stop in day.get("stops", [])
        ]
        stop_count = len(stops)
        alternatives = []

        for day, stop in stops:
            current = stop.get("recommendation") or {}
            for alternative in stop.get("alternatives") or []:
                impact = alternative.get("swap_impact") or {}
                decision = impact.get("swap_decision") or {}
                readiness = impact.get("swap_readiness") or {}
                alternatives.append({
                    "day": day.get("day"),
                    "slot_id": stop.get("slot_id"),
                    "slot_label": stop.get("label"),
                    "from_place_id": current.get("place_id"),
                    "from_name": current.get("name") or (current.get("display") or {}).get("name"),
                    "to_place_id": alternative.get("place_id"),
                    "to_name": alternative.get("name") or (alternative.get("display") or {}).get("name"),
                    "headline": decision.get("headline") or readiness.get("label"),
                    "best_when": decision.get("best_when") or readiness.get("next_action"),
                    "tradeoff": decision.get("tradeoff"),
                    "should_swap": bool(decision.get("should_swap")),
                    "confidence": decision.get("confidence") or readiness.get("score"),
                    "low_friction_score": impact.get("low_friction_score"),
                    "low_friction_label": impact.get("low_friction_label"),
                    "route_score_delta": impact.get("route_score_delta"),
                    "authenticity_delta": impact.get("authenticity_delta"),
                    "member_fit_delta": impact.get("member_fit_delta"),
                    "member_rebalance_delta": impact.get("member_rebalance_delta"),
                    "group_consensus_delta": impact.get("group_consensus_delta"),
                    "group_consensus_gap_delta": impact.get("group_consensus_gap_delta"),
                    "target_members": impact.get("target_members") or [],
                    "weakened_members": impact.get("weakened_members") or [],
                    "travel_efficiency_delta": impact.get("travel_efficiency_delta"),
                    "travel_distance_meters": impact.get("travel_distance_meters"),
                    "price_level_delta": impact.get("price_level_delta"),
                    "known_cost_delta_low": impact.get("known_cost_delta_low"),
                    "known_cost_delta_high": impact.get("known_cost_delta_high"),
                    "cost_impact_status": impact.get("cost_impact_status"),
                    "cost_impact_label": impact.get("cost_impact_label"),
                    "cost_impact_detail": impact.get("cost_impact_detail"),
                    "status": readiness.get("status"),
                    "reasons": impact.get("reasons") or [],
                    "badges": decision.get("badges") or [],
                })

        swappable_stop_count = sum(1 for _, stop in stops if stop.get("alternatives"))
        alternative_count = len(alternatives)
        recommended_swaps = [item for item in alternatives if item.get("should_swap")]
        low_friction_swaps = [
            item
            for item in alternatives
            if _optional_float(item.get("low_friction_score")) >= 0.78
        ]
        authenticity_upgrades = [
            item
            for item in alternatives
            if _optional_float(item.get("authenticity_delta")) >= 0.05
        ]
        party_upgrades = [
            item
            for item in alternatives
            if max(
                _optional_float(item.get("member_fit_delta")),
                _optional_float(item.get("member_rebalance_delta")),
            ) >= 0.05
        ]
        consensus_upgrades = [
            item
            for item in alternatives
            if max(
                _optional_float(item.get("group_consensus_delta")),
                _optional_float(item.get("group_consensus_gap_delta")),
            ) >= 0.04
        ]
        route_risks = [
            item
            for item in alternatives
            if item.get("status") == "route_risk" or _optional_float(item.get("travel_efficiency_delta")) <= -0.12
        ]
        cost_cautions = [
            item
            for item in alternatives
            if item.get("cost_impact_status") == "pricier"
        ]
        cost_savings = [
            item
            for item in alternatives
            if item.get("cost_impact_status") == "saves"
        ]
        swap_coverage = swappable_stop_count / stop_count if stop_count else 0

        def sort_key(item):
            return (
                1 if item.get("should_swap") else 0,
                _optional_float(item.get("confidence")),
                max(
                    _optional_float(item.get("group_consensus_delta")),
                    _optional_float(item.get("group_consensus_gap_delta")),
                ),
                _optional_float(item.get("low_friction_score")),
                0.05 if item.get("cost_impact_status") == "saves" else 0,
                _optional_float(item.get("member_rebalance_delta")),
                _optional_float(item.get("authenticity_delta")),
                _optional_float(item.get("route_score_delta")),
            )

        best_swaps = sorted(alternatives, key=sort_key, reverse=True)[:4]

        if not stop_count:
            status = "needs_route"
            headline = "Build a route before Adventour can suggest safe swaps."
            next_action = "Plan an Adventour first, then compare alternatives for each stop."
        elif swap_coverage >= 0.8 and recommended_swaps:
            status = "ready"
            headline = "This route is flexible enough to customize."
            next_action = "Use the highlighted swaps when a stop does not fit the group or vibe."
        elif swap_coverage >= 0.5:
            status = "watch"
            headline = "This route has some flexibility, but not every stop has a strong swap."
            next_action = "Rebuild or widen the range if you want more swap safety before sharing."
        else:
            status = "needs_attention"
            headline = "This route may feel brittle if someone dislikes a stop."
            next_action = "Compare scout styles or widen the search to add more alternatives."

        party_coverage_plan = self._swap_party_coverage_plan(route_days, alternatives)
        if party_coverage_plan.get("status") == "actionable" and status != "needs_route":
            next_action = party_coverage_plan.get("next_action") or "Use group-balance swaps when one friend is quietly getting a weaker route."
        elif consensus_upgrades and status != "needs_route":
            next_action = "Use group-balance swaps when one friend is quietly getting a weaker route."
        elif party_upgrades and status != "needs_route":
            next_action = "Use party-friendly swaps when a friend looks underserved."
        elif authenticity_upgrades and status != "needs_route":
            next_action = "Swap in a local-feeling alternative if the route starts feeling too generic."

        return {
            "status": status,
            "headline": headline,
            "next_action": next_action,
            "stop_count": stop_count,
            "swappable_stop_count": swappable_stop_count,
            "swap_coverage": round(swap_coverage, 3),
            "alternative_count": alternative_count,
            "recommended_swap_count": len(recommended_swaps),
            "low_friction_count": len(low_friction_swaps),
            "authenticity_upgrade_count": len(authenticity_upgrades),
            "party_upgrade_count": len(party_upgrades),
            "consensus_upgrade_count": len(consensus_upgrades),
            "route_risk_count": len(route_risks),
            "cost_caution_count": len(cost_cautions),
            "cost_saving_count": len(cost_savings),
            "party_coverage_plan": party_coverage_plan,
            "best_swaps": best_swaps,
        }

    def _swap_party_coverage_plan(self, route_days, alternatives):
        members = {}
        for day in route_days:
            party_fit = day.get("party_fit") or {}
            for member in party_fit.get("members") or []:
                user_id = member.get("user_id")
                if user_id is None:
                    continue
                current = members.setdefault(user_id, {
                    "user_id": user_id,
                    "display_name": member.get("display_name") or "Traveler",
                    "average_fit": member.get("average_fit"),
                    "coverage_status": member.get("coverage_status"),
                    "best_match": member.get("best_match"),
                    "strong_match_count": 0,
                    "suggested_swaps": [],
                })
                current["strong_match_count"] += int(member.get("strong_match_count") or 0)
                if current.get("average_fit") is None or (
                    member.get("average_fit") is not None
                    and float(member.get("average_fit")) < float(current.get("average_fit") or 0)
                ):
                    current["average_fit"] = member.get("average_fit")
                    current["coverage_status"] = member.get("coverage_status")
                    current["best_match"] = member.get("best_match")

        if not members:
            return {
                "status": "unknown",
                "headline": "Group swap coverage will appear after Adventour has friend-fit data.",
                "next_action": "Add friends or collect taste signals before relying on group-balance swaps.",
                "members": [],
                "actionable_member_count": 0,
            }

        for item in alternatives:
            if item.get("status") == "route_risk":
                continue
            for target in item.get("target_members") or []:
                user_id = target.get("user_id")
                if user_id not in members:
                    continue
                suggested = {
                    "day": item.get("day"),
                    "slot_id": item.get("slot_id"),
                    "slot_label": item.get("slot_label"),
                    "from_name": item.get("from_name"),
                    "to_name": item.get("to_name"),
                    "to_place_id": item.get("to_place_id"),
                    "confidence": item.get("confidence"),
                    "low_friction_score": item.get("low_friction_score"),
                    "replacement_fit": target.get("replacement_fit"),
                    "fit_delta": target.get("delta"),
                    "coverage_status": target.get("coverage_status"),
                    "tradeoff": item.get("tradeoff"),
                }
                members[user_id]["suggested_swaps"].append(suggested)

        for member in members.values():
            member["suggested_swaps"].sort(
                key=lambda item: (
                    1 if item.get("coverage_status") == "covered_by_swap" else 0,
                    _optional_float(item.get("confidence")),
                    _optional_float(item.get("low_friction_score")),
                    _optional_float(item.get("fit_delta")),
                ),
                reverse=True,
            )
            member["suggested_swaps"] = member["suggested_swaps"][:2]

        ordered_members = sorted(
            members.values(),
            key=lambda item: (
                1 if item.get("coverage_status") != "covered" else 0,
                -_optional_float(item.get("average_fit"), 1),
            ),
            reverse=True,
        )
        underserved = [member for member in ordered_members if member.get("coverage_status") != "covered"]
        actionable = [member for member in ordered_members if member.get("suggested_swaps")]

        if underserved and actionable:
            names = ", ".join(member["display_name"] for member in actionable[:2])
            status = "actionable"
            headline = f"Swaps can help {names} feel more covered."
            next_action = f"Preview the suggested swap for {actionable[0]['display_name']} before sharing this route."
        elif underserved:
            names = ", ".join(member["display_name"] for member in underserved[:2])
            status = "needs_options"
            headline = f"{names} still need stronger swap options."
            next_action = "Try a group-friendly scout style or widen the search radius."
        else:
            status = "covered"
            headline = "Every traveler has at least one strong route fit."
            next_action = "Keep swaps optional unless the group wants a different vibe."

        return {
            "status": status,
            "headline": headline,
            "next_action": next_action,
            "member_count": len(ordered_members),
            "underserved_member_count": len(underserved),
            "actionable_member_count": len(actionable),
            "members": ordered_members,
        }

    def _attach_swap_guide_to_trip_packet(self, trip_packet, swap_guide):
        if not trip_packet or not swap_guide:
            return

        quick_stats = [
            stat
            for stat in trip_packet.get("quick_stats") or []
            if stat.get("id") != "swap_guide"
        ]
        quick_stats.append({
            "id": "swap_guide",
            "label": "Swap safety",
            "value": f"{swap_guide.get('swappable_stop_count', 0)}/{swap_guide.get('stop_count', 0)} stops",
            "status": "ready" if swap_guide.get("status") == "ready" else "manual",
        })
        trip_packet["swap_guide"] = swap_guide
        trip_packet["quick_stats"] = quick_stats

    def _route_model_confidence(self, route_days, recommendation_result, route_readiness):
        basket_quality = recommendation_result.get("recommendation_quality") or {}
        basket_confidence = basket_quality.get("model_confidence") or {}
        route_readiness = route_readiness or {}
        stops = [
            stop
            for day in route_days
            for stop in day.get("stops", [])
        ]
        stop_count = len(stops)
        model_score = _optional_float(basket_confidence.get("score"))
        stop_coverage = _optional_float(route_readiness.get("stop_coverage"))
        authenticity_score = _optional_float(route_readiness.get("authenticity_score"))
        party_score = _optional_float(route_readiness.get("party_score"))
        booking_score = _optional_float(route_readiness.get("booking_score"))
        swap_coverage = _optional_float(self._swap_guide(route_days).get("swap_coverage"))
        local_share = _optional_float(basket_confidence.get("local_feeling_share"))
        learned_rerank = recommendation_result.get("learned_rerank") or {}
        learned_guard = (learned_rerank.get("runtime_guard") or {}).get("status")
        learned_penalty = 0.08 if learned_guard == "constrained" else 0.04 if learned_guard == "watch" else 0

        route_score = _clamp(
            model_score * 0.34
            + stop_coverage * 0.18
            + authenticity_score * 0.16
            + party_score * 0.12
            + booking_score * 0.10
            + swap_coverage * 0.10
            - learned_penalty
        )

        warnings = list(basket_confidence.get("warnings") or [])[:3]
        next_actions = list(basket_confidence.get("next_actions") or [])[:3]
        basis = list(basket_confidence.get("basis") or [])[:4]

        if stop_count and stop_coverage >= 0.8:
            basis.append("The planned route kept enough slots filled to trust the itinerary shape.")
        elif stop_count:
            warnings.append("The route has fewer filled stops than ideal, so model confidence is capped.")
            next_actions.append("Widen the range or compare scout styles to fill the route.")

        if authenticity_score >= 0.65:
            basis.append("Local/authenticity guardrails stayed strong after building the route.")
        else:
            warnings.append("Route-level local/authenticity signal is weaker than Adventour prefers.")
            next_actions.append("Swap in a stronger local-feeling stop before sharing.")

        if party_score >= 0.7 and (recommendation_result.get("member_count") or 1) > 1:
            basis.append("Friend blending still looks balanced across planned stops.")
        elif (recommendation_result.get("member_count") or 1) > 1:
            warnings.append("Friend blending may need stronger route coverage.")
            next_actions.append("Use group-friendly scout style or party-friendly swaps.")

        if swap_coverage >= 0.75:
            basis.append("Most planned stops have swap options, so testers can tune the route.")
        elif stop_count:
            warnings.append("Some stops have limited swap flexibility.")

        if route_score >= 0.72:
            status = "ready"
            headline = "Route model signal is strong enough to test."
        elif route_score >= 0.46:
            status = "learning"
            headline = "Route model signal is usable, but keep tuning."
        else:
            status = "cold_start"
            headline = "Route model signal is early; rely on local guardrails and swaps."

        return {
            "status": status,
            "headline": headline,
            "score": round(route_score, 3),
            "learning_status": basket_confidence.get("learning_status"),
            "average_preference_confidence": basket_confidence.get("average_preference_confidence"),
            "average_signal_count": basket_confidence.get("average_signal_count"),
            "member_count": recommendation_result.get("member_count", 1),
            "local_feeling_share": round(local_share, 3),
            "stop_coverage": round(stop_coverage, 3),
            "authenticity_score": round(authenticity_score, 3),
            "party_score": round(party_score, 3),
            "booking_score": round(booking_score, 3),
            "swap_coverage": round(swap_coverage, 3),
            "learned_rerank": basket_confidence.get("learned_rerank") or {
                "applied": bool(learned_rerank.get("applied")),
                "reason": learned_rerank.get("reason"),
                "model_type": learned_rerank.get("model_type"),
                "guard_status": learned_guard,
                "guard_headline": (learned_rerank.get("runtime_guard") or {}).get("headline"),
            },
            "basis": list(dict.fromkeys(basis))[:6],
            "warnings": list(dict.fromkeys(warnings))[:5],
            "next_actions": list(dict.fromkeys(next_actions))[:5],
        }

    def _attach_route_model_confidence_to_trip_packet(self, trip_packet, route_model_confidence):
        if not trip_packet or not route_model_confidence:
            return

        quick_stats = [
            stat
            for stat in trip_packet.get("quick_stats") or []
            if stat.get("id") != "route_model_confidence"
        ]
        quick_stats.append({
            "id": "route_model_confidence",
            "label": "Model signal",
            "value": f"{round(_optional_float(route_model_confidence.get('score')) * 100)}%",
            "status": "ready" if route_model_confidence.get("status") == "ready" else "manual",
        })
        trip_packet["route_model_confidence"] = route_model_confidence
        trip_packet["quick_stats"] = quick_stats

    def _attach_beta_readiness_to_trip_packet(self, trip_packet, route_readiness):
        if not trip_packet:
            return

        beta_readiness = self._trip_packet_beta_readiness(trip_packet, route_readiness)
        quick_stats = [
            stat
            for stat in trip_packet.get("quick_stats") or []
            if stat.get("id") != "beta_readiness"
        ]
        quick_stats.insert(0, {
            "id": "beta_readiness",
            "label": "Beta ready",
            "value": f"{round(_optional_float(beta_readiness.get('score')) * 100)}%",
            "status": "ready" if beta_readiness.get("ready_for_friend_testing") else "action_needed",
        })
        trip_packet["beta_readiness"] = beta_readiness
        trip_packet["quick_stats"] = quick_stats

    def _trip_packet_beta_readiness(self, trip_packet, route_readiness):
        route_readiness = route_readiness or {}
        route_model_confidence = trip_packet.get("route_model_confidence") or {}
        authenticity_packet = trip_packet.get("authenticity_packet") or {}
        trip_logistics = trip_packet.get("trip_logistics_readiness") or {}
        event_packet = trip_packet.get("event_packet") or {}
        swap_guide = trip_packet.get("swap_guide") or {}

        member_count = int(route_model_confidence.get("member_count") or trip_packet.get("party_size") or 1)
        event_status = event_packet.get("status")
        event_score = (
            1.0
            if event_status == "ready"
            else 0.68
            if event_status == "needs_confirmation"
            else 0.52
            if event_status == "needs_scouting"
            else _optional_float(route_readiness.get("event_score"), 0.5)
        )
        dimensions = [
            self._beta_readiness_dimension(
                "route",
                "Route shape",
                route_readiness.get("score"),
                0.18,
                "Route has enough complete, varied stops to test.",
                "Fill route gaps or compare scout styles.",
                pass_min=0.70,
                watch_min=0.55,
            ),
            self._beta_readiness_dimension(
                "model",
                "Model confidence",
                route_model_confidence.get("score"),
                0.16,
                "Recommendation model signal is strong enough for a beta run.",
                "Collect more accepts/rejects or use safer local-first guardrails.",
                pass_min=0.66,
                watch_min=0.48,
            ),
            self._beta_readiness_dimension(
                "local_promise",
                "Local promise",
                authenticity_packet.get("score") or route_readiness.get("authenticity_score"),
                0.17,
                "The route keeps Adventour's local-first promise.",
                "Swap out generic-risk stops for local-feeling alternatives.",
                pass_min=0.68,
                watch_min=0.52,
            ),
            self._beta_readiness_dimension(
                "booking",
                "Planning handoff",
                trip_logistics.get("score") or trip_packet.get("booking_score") or route_readiness.get("booking_score"),
                0.16,
                "Booking links, setup steps, and reservation storage are usable.",
                "Add missing trip details or provider links before sharing.",
                pass_min=0.72,
                watch_min=0.55,
            ),
            self._beta_readiness_dimension(
                "friend_fit",
                "Friend fit",
                route_readiness.get("party_score") if member_count > 1 else 1.0,
                0.14 if member_count > 1 else 0.06,
                "The route is balanced enough for the selected travelers.",
                "Use group-friendly swaps for any underserved friend.",
                pass_min=0.70,
                watch_min=0.55,
                optional=member_count <= 1,
            ),
            self._beta_readiness_dimension(
                "swap_safety",
                "Swap safety",
                swap_guide.get("swap_coverage"),
                0.10,
                "Most stops have safe alternatives if a tester dislikes one.",
                "Widen range or rebuild to add more alternatives.",
                pass_min=0.70,
                watch_min=0.45,
            ),
            self._beta_readiness_dimension(
                "local_events",
                "Local events",
                event_score,
                0.09,
                "Local event or scouting guidance is ready enough for social testing.",
                "Scout current local calendars or add a meetup anchor.",
                pass_min=0.70,
                watch_min=0.48,
            ),
        ]

        total_weight = sum(item["weight"] for item in dimensions)
        score = _clamp(sum(item["score"] * item["weight"] for item in dimensions) / max(0.001, total_weight))
        blocking_dimensions = [
            item for item in dimensions
            if item["status"] == "fail" and not item.get("optional")
        ]
        watch_dimensions = [
            item for item in dimensions
            if item["status"] == "watch" and not item.get("optional")
        ]
        strongest_dimensions = [
            item for item in dimensions
            if item["status"] == "pass"
        ][:3]
        weakest_dimension = min(dimensions, key=lambda item: item["score"]) if dimensions else None

        ready_for_friend_testing = score >= 0.74 and not blocking_dimensions
        if ready_for_friend_testing and not watch_dimensions:
            status = "ready"
            headline = "Ready for close-friend testing."
            next_action = "Share this Adventour with a trusted tester or start it yourself."
        elif ready_for_friend_testing:
            status = "beta_ready_with_notes"
            headline = "Ready to test, with a few notes."
            next_action = watch_dimensions[0]["action"] if watch_dimensions else "Share with a trusted tester and watch feedback."
        elif score >= 0.58:
            status = "needs_tuning"
            headline = "Promising, but tune before friend testing."
            next_action = (blocking_dimensions or watch_dimensions or dimensions)[0]["action"]
        else:
            status = "not_ready"
            headline = "Not ready for friend testing yet."
            next_action = (blocking_dimensions or watch_dimensions or dimensions)[0]["action"]

        return {
            "status": status,
            "headline": headline,
            "score": round(score, 3),
            "ready_for_friend_testing": ready_for_friend_testing,
            "member_count": member_count,
            "weakest_dimension": weakest_dimension,
            "blocking_count": len(blocking_dimensions),
            "watch_count": len(watch_dimensions),
            "dimensions": dimensions,
            "strengths": [item["evidence"] for item in strongest_dimensions][:3],
            "required_actions": [item["action"] for item in blocking_dimensions][:3],
            "watchouts": [item["action"] for item in watch_dimensions][:3],
            "next_action": next_action,
        }

    def _beta_readiness_dimension(
        self,
        dimension_id,
        label,
        score,
        weight,
        evidence,
        action,
        pass_min=0.70,
        watch_min=0.50,
        optional=False,
    ):
        numeric_score = _clamp(_optional_float(score, 0))
        status = "pass" if numeric_score >= pass_min else "watch" if numeric_score >= watch_min else "fail"
        return {
            "id": dimension_id,
            "label": label,
            "score": round(numeric_score, 3),
            "weight": round(weight, 3),
            "status": status,
            "optional": bool(optional),
            "evidence": evidence,
            "action": action,
        }

    def _average_member_fit(self, recommendation):
        member_fit = recommendation.get("member_fit") or []
        fits = [
            float(item.get("fit"))
            for item in member_fit
            if item.get("fit") is not None
        ]
        return sum(fits) / len(fits) if fits else 0

    def _member_fit_values(self, recommendation):
        return [
            _optional_float(item.get("fit"))
            for item in recommendation.get("member_fit") or []
            if item.get("fit") is not None
        ]

    def _group_consensus_fit(self, recommendation):
        values = self._member_fit_values(recommendation)
        if len(values) <= 1:
            return self._average_member_fit(recommendation)
        group_average_fit = sum(values) / len(values)
        group_min_fit = min(values)
        min_fit_weight = _optional_float((recommendation.get("components") or {}).get("group_min_fit_weight"), default=0.14)
        return group_average_fit * (1 - min_fit_weight) + group_min_fit * min_fit_weight

    def _group_consensus_gap(self, recommendation):
        values = self._member_fit_values(recommendation)
        if len(values) <= 1:
            return 0
        group_average_fit = sum(values) / len(values)
        consensus_fit = self._group_consensus_fit(recommendation)
        return max(0, group_average_fit - consensus_fit)

    def _party_coverage_rescue(self, recommendation):
        ranking = recommendation.get("ranking") or {}
        if not ranking.get("party_coverage_rescue"):
            return None

        rescued_member = ranking.get("rescued_member") or "a traveler"
        rescued_fit = ranking.get("rescued_member_fit")
        try:
            rescued_fit = round(float(rescued_fit), 3)
        except (TypeError, ValueError):
            rescued_fit = None

        return {
            "member": rescued_member,
            "fit": rescued_fit,
            "replaced_pick": ranking.get("replaced_pick"),
            "reason": ranking.get("rescue_reason"),
            "score_gap": ranking.get("score_gap"),
        }

    def _stop_reasoning(self, slot, recommendation, route_context, route_components=None):
        route_components = route_components or self._slot_score_components(slot, recommendation, route_context)
        components = recommendation.get("components") or {}
        evidence = recommendation.get("authenticity_evidence") or {}
        display_types = sorted(_display_types(recommendation))
        matched_types = sorted(set(display_types).intersection(slot.get("preferred_types") or set()))
        travel_distance = route_components.get("travel_distance_meters")
        coverage_rescue = self._party_coverage_rescue(recommendation)

        reasons = []
        cautions = []

        if coverage_rescue:
            rescued_member = coverage_rescue["member"]
            fit = coverage_rescue.get("fit")
            reasons.append(
                f"Adventour made room for this stop because it gives {rescued_member} "
                + (f"a {round(fit * 100)}% personal match." if fit is not None else "a strong personal match.")
            )

        if matched_types:
            reasons.append(
                f"Fits {slot['label'].lower()} with {', '.join(matched_types[:3]).replace('_', ' ')} signals."
            )
        elif display_types:
            reasons.append(f"Adds a different route texture with {display_types[0].replace('_', ' ')} signals.")

        evidence_label = evidence.get("label")
        evidence_reasons = evidence.get("reasons") or []
        hidden_gem = evidence.get("hidden_gem_score")
        authenticity = components.get("authenticity", evidence.get("score", 0)) or 0
        if hidden_gem is not None and hidden_gem >= 0.7:
            evidence_detail = ", ".join(evidence_reasons[:2])
            reasons.append(
                "Hidden-gem signal is strong"
                + (f": {evidence_detail}." if evidence_detail else ".")
            )
        elif authenticity >= 0.7:
            reasons.append(
                f"Local-authentic signal is strong{f' ({evidence_label})' if evidence_label else ''}."
            )
        elif evidence_label:
            reasons.append(f"Local signal reads as {str(evidence_label).lower()}.")

        if components.get("group_member_count", 1) > 1:
            group_fit = components.get("group_fit", 0) or 0
            group_min_fit = components.get("group_min_fit", 0) or 0
            if group_min_fit >= 0.55:
                reasons.append(f"Keeps the travel party above {round(group_min_fit * 100)}% minimum fit.")
            elif group_fit:
                cautions.append(f"Party fit is mixed; lowest traveler fit is {round(group_min_fit * 100)}%.")

        friend_history_fit = components.get("friend_history_fit", 0) or 0
        history = recommendation.get("history") or {}
        friend_liked_by = history.get("friend_liked_by") or []
        friend_rejected_by = history.get("friend_rejected_by") or []
        if friend_history_fit >= 0.25 and friend_liked_by:
            reasons.append(
                f"{', '.join(friend_liked_by[:2])} already liked this place, so it has group social proof."
            )
        elif friend_history_fit <= -0.15 and friend_rejected_by:
            cautions.append(
                f"{', '.join(friend_rejected_by[:2])} passed on this before; keep it swappable."
            )

        if travel_distance is None:
            reasons.append("Starts this part of the route cleanly.")
        elif travel_distance <= ROUTE_DISTANCE_PENALTY_START_METERS:
            reasons.append("Keeps the route tight from the previous stop.")
        elif travel_distance >= ROUTE_DISTANCE_PENALTY_FULL_METERS:
            cautions.append("This creates a larger travel jump than ideal for the route.")

        if route_components.get("member_rebalance_bonus", 0) >= 0.05:
            reasons.append("Helps rebalance the route for a previously underserved traveler.")
        if route_components.get("diversity_penalty", 0) == 0:
            reasons.append("Avoids repeating the same route category too heavily.")

        if components.get("chain_penalty", 0) > 0:
            cautions.append("Chain-like signal is present, so Adventour down-ranked it.")
        if components.get("price_penalty", 0) > 0:
            cautions.append("May be above the selected or learned price comfort zone.")
        if not cautions and evidence.get("tourist_trap_score", 0) >= 0.35:
            cautions.append("Popularity suggests it may feel more tourist-heavy than hidden.")

        return {
            "headline": f"Picked for {slot['label'].lower()} because it fits the route and taste signals.",
            "reasons": reasons[:4],
            "cautions": cautions[:3],
            "stats": {
                "route_score": round(route_components.get("route_score", 0), 3),
                "slot_matches": route_components.get("slot_matches", 0),
                "authenticity": round(authenticity, 3),
                "hidden_gem_score": evidence.get("hidden_gem_score"),
                "chain_risk": evidence.get("chain_risk"),
                "travel_distance_meters": travel_distance,
                "member_fit": round(route_components.get("member_fit", 0), 3),
                "rescued_member_fit": coverage_rescue.get("fit") if coverage_rescue else None,
                "friend_history_fit": round(friend_history_fit, 3),
            },
        }

    def _stop_party_fit_summary(self, recommendation):
        coverage_rescue = self._party_coverage_rescue(recommendation)
        member_fit = [
            {
                "user_id": member.get("user_id"),
                "display_name": member.get("display_name") or "Traveler",
                "fit": float(member.get("fit")),
            }
            for member in recommendation.get("member_fit") or []
            if member.get("user_id") is not None and member.get("fit") is not None
        ]
        if not member_fit:
            return {
                "headline": "Preference fit will improve as Adventour learns this travel party.",
                "top_members": [],
                "weak_members": [],
                "average_fit": None,
                "lowest_fit": None,
                "highest_fit": None,
                "coverage_rescue": coverage_rescue,
            }

        member_fit.sort(key=lambda item: item["fit"], reverse=True)
        average_fit = sum(item["fit"] for item in member_fit) / len(member_fit)
        top_members = [item for item in member_fit if item["fit"] >= 0.65][:2]
        weak_members = [item for item in member_fit if item["fit"] < 0.45][:2]

        if coverage_rescue:
            rescued_member = coverage_rescue["member"]
            fit = coverage_rescue.get("fit")
            headline = (
                f"Made room for {rescued_member}"
                + (f" at {round(fit * 100)}% fit." if fit is not None else ".")
            )
        elif len(member_fit) == 1:
            headline = f"Best signal for {member_fit[0]['display_name']} at {round(member_fit[0]['fit'] * 100)}% fit."
        elif weak_members:
            names = ", ".join(item["display_name"] for item in weak_members)
            headline = f"Mixed party fit; {names} may prefer a swap."
        elif top_members:
            names = ", ".join(item["display_name"] for item in top_members)
            headline = f"Strong group signal, especially for {names}."
        else:
            headline = "Moderate group fit; this stop keeps the route balanced."

        return {
            "headline": headline,
            "top_members": [
                {
                    "user_id": item["user_id"],
                    "display_name": item["display_name"],
                    "fit": round(item["fit"], 3),
                }
                for item in top_members
            ],
            "weak_members": [
                {
                    "user_id": item["user_id"],
                    "display_name": item["display_name"],
                    "fit": round(item["fit"], 3),
                }
                for item in weak_members
            ],
            "average_fit": round(average_fit, 3),
            "lowest_fit": round(member_fit[-1]["fit"], 3),
            "highest_fit": round(member_fit[0]["fit"], 3),
            "coverage_rescue": coverage_rescue,
        }

    def _member_rebalance_bonus(self, recommendation, route_context):
        member_totals = route_context.get("member_totals") or {}
        member_counts = route_context.get("member_counts") or {}
        if len(member_totals) <= 1:
            return 0

        averages = {
            user_id: member_totals[user_id] / member_counts[user_id]
            for user_id in member_totals
            if member_counts.get(user_id)
        }
        if len(averages) <= 1:
            return 0

        highest_average = max(averages.values())
        underserved_ids = {
            user_id
            for user_id, average in averages.items()
            if highest_average - average >= ROUTE_MEMBER_REBALANCE_THRESHOLD
        }
        if not underserved_ids:
            return 0

        candidate_fits = {
            member.get("user_id"): float(member.get("fit"))
            for member in recommendation.get("member_fit") or []
            if member.get("user_id") is not None and member.get("fit") is not None
        }
        underserved_fit = [
            candidate_fits[user_id]
            for user_id in underserved_ids
            if user_id in candidate_fits
        ]
        if not underserved_fit:
            return 0

        average_underserved_fit = sum(underserved_fit) / len(underserved_fit)
        all_fit = sum(candidate_fits.values()) / len(candidate_fits) if candidate_fits else 0
        lift = max(0, average_underserved_fit - all_fit)
        return min(ROUTE_MEMBER_REBALANCE_BONUS_MAX, lift * 0.8)

    def _diversity_penalty(self, recommendation, route_context):
        groups = _diversity_groups(recommendation)
        types = _display_types(recommendation)
        group_counts = route_context.get("groups", {})
        type_counts = route_context.get("types", {})
        repeated_group_penalty = sum(group_counts.get(group, 0) for group in groups) * 0.28
        repeated_type_penalty = sum(type_counts.get(place_type, 0) for place_type in types) * 0.08
        new_group_credit = len([group for group in groups if group_counts.get(group, 0) == 0]) * 0.25
        return min(0.7, max(0, repeated_group_penalty + repeated_type_penalty - new_group_credit))

    def _travel_penalty(self, recommendation, route_context):
        distance = self._travel_distance_meters(recommendation, route_context)
        if distance is None or distance <= ROUTE_DISTANCE_PENALTY_START_METERS:
            return 0
        scaled = (
            (distance - ROUTE_DISTANCE_PENALTY_START_METERS)
            / max(1, ROUTE_DISTANCE_PENALTY_FULL_METERS - ROUTE_DISTANCE_PENALTY_START_METERS)
        )
        return min(ROUTE_DISTANCE_PENALTY_MAX, max(0, scaled) * ROUTE_DISTANCE_PENALTY_MAX)

    def _travel_distance_meters(self, recommendation, route_context):
        last_point = route_context.get("last_point")
        current_point = self._coordinates(recommendation)
        if not last_point or not current_point:
            return None
        return round(_haversine_meters(last_point, current_point))

    def _update_route_context(self, route_context, recommendation):
        route_context.setdefault("member_totals", {})
        route_context.setdefault("member_counts", {})
        for group in _diversity_groups(recommendation):
            route_context["groups"][group] = route_context["groups"].get(group, 0) + 1
        for place_type in _display_types(recommendation):
            route_context["types"][place_type] = route_context["types"].get(place_type, 0) + 1
        for member in recommendation.get("member_fit") or []:
            user_id = member.get("user_id")
            fit = member.get("fit")
            if user_id is None or fit is None:
                continue
            route_context["member_totals"][user_id] = route_context["member_totals"].get(user_id, 0) + float(fit)
            route_context["member_counts"][user_id] = route_context["member_counts"].get(user_id, 0) + 1
        point = self._coordinates(recommendation)
        if point:
            route_context.setdefault("points", []).append(point)
            route_context["last_point"] = point

    def _coordinates(self, recommendation):
        lat = recommendation.get("latitude")
        lng = recommendation.get("longitude")
        if lat is None:
            lat = recommendation.get("display", {}).get("latitude")
        if lng is None:
            lng = recommendation.get("display", {}).get("longitude")
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)

    def _route_balance(self, route_context):
        group_counts = route_context.get("groups", {})
        return {
            "unique_groups": sorted(group_counts.keys()),
            "group_counts": group_counts,
            "variety_score": round(len(group_counts) / max(1, len(route_context.get("slot_ids", SLOT_DEFINITIONS))), 3),
        }

    def _party_compromise_brief(self, members, underserved_members, fairness_score, coverage_share):
        if not members:
            return {
                "status": "unknown",
                "headline": "Party fit needs preference data.",
                "message": "Adventour needs a few taste signals before it can explain who this route serves best.",
                "next_action": "Have each traveler swipe on a few places before trusting a group route.",
                "balance_chips": [
                    {"label": "Coverage", "value": "learning", "tone": "neutral"},
                ],
            }

        ordered = sorted(members, key=lambda item: item.get("average_fit", 0))
        most_compromised = ordered[0]
        dominant = ordered[-1]
        fit_gap = max(0, float(dominant.get("average_fit", 0)) - float(most_compromised.get("average_fit", 0)))
        coverage_percent = round((coverage_share or 0) * 100)
        gap_percent = round(fit_gap * 100)
        underserved_names = ", ".join(member["display_name"] for member in underserved_members[:2])

        if len(members) == 1:
            status = "solo"
            headline = f"Built around {dominant['display_name']}."
            message = "This Adventour is personalized for one traveler right now."
            next_action = "Add friends to blend preferences before planning a group route."
        elif underserved_members:
            status = "needs_coverage"
            headline = f"{underserved_names} need a stronger match."
            message = "The route has a favorite, but at least one traveler does not have a strong personal stop yet."
            next_action = f"Swap in a stop that better matches {underserved_names}."
        elif coverage_share >= 1 and fairness_score is not None and fairness_score >= 0.85 and fit_gap <= 0.18:
            status = "balanced"
            headline = "Balanced for the whole party."
            message = "Every traveler has a strong stop and the route is not leaning too hard toward one person."
            next_action = "This is a strong route to start or share with friends."
        elif coverage_share >= 1:
            status = "covered_but_uneven"
            headline = f"{dominant['display_name']} may love this most."
            message = "Everyone has a strong stop, but one traveler is carrying more of the route fit."
            next_action = f"Use a swap if you want {most_compromised['display_name']} to feel more centered."
        elif fairness_score is not None and fairness_score < 0.7:
            status = "uneven"
            headline = "This route needs a fairer blend."
            message = f"{dominant['display_name']} is better served than {most_compromised['display_name']}."
            next_action = "Try a different scout style or swap the weakest match before sharing."
        else:
            status = "watch"
            headline = "Good blend, worth checking."
            message = "The route looks usable, but Adventour should keep watching for better personal coverage."
            next_action = "Review the weakest traveler fit before starting."

        chips = [
            {"label": "Coverage", "value": f"{coverage_percent}%", "tone": "positive" if coverage_share >= 1 else "caution"},
            {"label": "Gap", "value": f"{gap_percent} pts", "tone": "positive" if fit_gap <= 0.18 else "caution"},
            {
                "label": "Needs match",
                "value": str(len(underserved_members)),
                "tone": "positive" if not underserved_members else "caution",
            },
        ]

        return {
            "status": status,
            "headline": headline,
            "message": message,
            "dominant_member": {
                "user_id": dominant.get("user_id"),
                "display_name": dominant.get("display_name"),
                "average_fit": dominant.get("average_fit"),
            },
            "most_compromised_member": {
                "user_id": most_compromised.get("user_id"),
                "display_name": most_compromised.get("display_name"),
                "average_fit": most_compromised.get("average_fit"),
            },
            "fit_gap": round(fit_gap, 3),
            "coverage_share": round(coverage_share or 0, 3),
            "fairness_score": fairness_score,
            "next_action": next_action,
            "balance_chips": chips,
        }

    def _party_fit(self, stops):
        member_totals = {}
        member_counts = {}
        member_names = {}
        member_strong_counts = {}
        member_best_matches = {}

        for stop_index, stop in enumerate(stops, start=1):
            recommendation = stop.get("recommendation", {}) or {}
            stop_name = recommendation.get("name") or recommendation.get("display", {}).get("name") or stop.get("label")
            for member in stop.get("recommendation", {}).get("member_fit") or []:
                user_id = member.get("user_id")
                if user_id is None:
                    continue
                fit = member.get("fit")
                if fit is None:
                    continue
                member_totals[user_id] = member_totals.get(user_id, 0) + float(fit)
                member_counts[user_id] = member_counts.get(user_id, 0) + 1
                member_names[user_id] = member.get("display_name") or "Traveler"
                if float(fit) >= ROUTE_MEMBER_STRONG_FIT_THRESHOLD:
                    member_strong_counts[user_id] = member_strong_counts.get(user_id, 0) + 1
                best = member_best_matches.get(user_id)
                if not best or float(fit) > best.get("fit", 0):
                    member_best_matches[user_id] = {
                        "day_stop_index": stop_index,
                        "slot_id": stop.get("slot_id"),
                        "slot_label": stop.get("label"),
                        "place_id": recommendation.get("place_id"),
                        "name": stop_name,
                        "fit": round(float(fit), 3),
                    }

        members = [
            {
                "user_id": user_id,
                "display_name": member_names[user_id],
                "average_fit": round(member_totals[user_id] / member_counts[user_id], 3),
                "matched_stops": member_counts[user_id],
                "strong_match_count": member_strong_counts.get(user_id, 0),
                "coverage_status": (
                    "covered"
                    if member_strong_counts.get(user_id, 0) > 0
                    else "needs_match"
                ),
                "best_match": member_best_matches.get(user_id),
            }
            for user_id in member_totals
            if member_counts.get(user_id)
        ]
        members.sort(key=lambda item: item["user_id"])

        if not members:
            return {
                "members": [],
                "fairness_score": None,
                "message": "Party fit will appear after Adventour has preference data for this route.",
                "coverage_share": None,
                "covered_member_count": 0,
                "underserved_count": 0,
                "underserved_members": [],
                "ready_for_friend_testing": False,
                "compromise_brief": self._party_compromise_brief([], [], None, None),
            }

        fits = [member["average_fit"] for member in members]
        lowest = min(fits)
        highest = max(fits)
        fairness_score = round(max(0, 1 - (highest - lowest)), 3)
        covered_members = [member for member in members if member["coverage_status"] == "covered"]
        underserved_members = [member for member in members if member["coverage_status"] != "covered"]
        coverage_share = len(covered_members) / len(members) if members else 0
        if len(members) == 1:
            message = f"Built around {members[0]['display_name']}'s Adventour taste."
        elif coverage_share >= 1 and fairness_score >= 0.85:
            message = "Every traveler has a strong route stop and party balance is high."
        elif coverage_share >= 1:
            message = "Every traveler has at least one strong route stop."
        elif underserved_members:
            names = ", ".join(member["display_name"] for member in underserved_members[:2])
            message = f"{names} may need a stronger route stop; use swaps to rebalance."
        elif fairness_score >= 0.85:
            message = "Strongly balanced for this travel party."
        elif fairness_score >= 0.7:
            message = "Good party balance with a few stronger personal matches."
        else:
            message = "One traveler may love this route more than the others; use swaps to rebalance it."

        return {
            "members": members,
            "lowest_average_fit": lowest,
            "highest_average_fit": highest,
            "fairness_score": fairness_score,
            "coverage_share": round(coverage_share, 3),
            "covered_member_count": len(covered_members),
            "underserved_count": len(underserved_members),
            "underserved_members": underserved_members,
            "ready_for_friend_testing": coverage_share >= 1 and fairness_score >= 0.7,
            "coverage_plan": {
                "status": (
                    "ready"
                    if coverage_share >= 1 and fairness_score >= 0.7
                    else "needs_member_coverage"
                    if underserved_members
                    else "watch"
                ),
                "coverage_share": round(coverage_share, 3),
                "covered_member_count": len(covered_members),
                "underserved_count": len(underserved_members),
                "next_actions": (
                    ["Keep this route or start the Adventour with the group."]
                    if coverage_share >= 1 and fairness_score >= 0.7
                    else [
                        "Use group-friendly scout style or swap in a stronger stop for "
                        + ", ".join(member["display_name"] for member in underserved_members[:2])
                        + "."
                    ]
                    if underserved_members
                    else ["Review group fit before sharing this route."]
                ),
            },
            "compromise_brief": self._party_compromise_brief(
                members,
                underserved_members,
                fairness_score,
                coverage_share,
            ),
            "message": message,
        }

    def _route_aware_local_events(self, local_events, route_days):
        if not local_events or not local_events.get("events"):
            return local_events

        enriched = deepcopy(local_events)
        route_event_count = 0
        route_actionable_event_count = 0
        route_reservation_ready_count = 0
        route_social_anchor_count = 0
        route_friend_signal_count = 0
        route_community_signal_count = 0
        top_route_social_event_title = None
        route_social_anchor = None
        route_social_anchor_score = -1
        for event in enriched.get("events", []):
            context = self._best_event_route_context(event, route_days)
            if not context:
                continue
            event["route_context"] = context
            event["route_anchor_score"] = self._route_social_anchor_score(event, context)
            self._attach_event_to_route_stop(event, context, route_days)
            event.setdefault("explanation", [])
            event["explanation"] = [
                *event["explanation"],
                *[reason for reason in context["reasons"] if reason not in event["explanation"]],
            ][:5]
            route_event_count += 1
            if event.get("source_url") or event.get("reservation_url"):
                route_actionable_event_count += 1
            if event.get("reservation_url"):
                route_reservation_ready_count += 1
            social = event.get("social") or {}
            friend_signal = int(social.get("friend_going_count") or 0) + int(social.get("friend_interested_count") or 0)
            community_signal = int(social.get("going_count") or 0) + int(social.get("interested_count") or 0)
            route_friend_signal_count += friend_signal
            route_community_signal_count += community_signal
            if friend_signal or community_signal or (event.get("event_story") or {}).get("social_ready"):
                route_social_anchor_count += 1
                if not top_route_social_event_title:
                    top_route_social_event_title = event.get("title")
            if event["route_anchor_score"] > route_social_anchor_score:
                route_social_anchor = event
                route_social_anchor_score = event["route_anchor_score"]

        summary = enriched.setdefault("summary", {})
        summary["route_match_count"] = route_event_count
        summary["route_actionable_event_count"] = route_actionable_event_count
        summary["route_reservation_ready_count"] = route_reservation_ready_count
        summary["route_social_anchor_count"] = route_social_anchor_count
        summary["route_friend_signal_count"] = route_friend_signal_count
        summary["route_community_signal_count"] = route_community_signal_count
        if route_event_count:
            first_matched = next(
                (event for event in enriched.get("events", []) if event.get("route_context")),
                None,
            )
            summary["top_route_event_title"] = first_matched.get("title") if first_matched else None
            summary["top_route_social_event_title"] = top_route_social_event_title
            summary["route_social_anchor"] = self._route_social_anchor_payload(route_social_anchor) if route_social_anchor else None
            if route_reservation_ready_count:
                summary["route_context_message"] = "Local events are paired with route stops and reservation links."
            elif route_actionable_event_count:
                summary["route_context_message"] = "Local events are paired with route stops and source links."
            else:
                summary["route_context_message"] = "Local events are paired with nearby route stops."
        else:
            summary["route_context_message"] = "Events are nearby, but Adventour could not pair them to a route stop yet."
        return enriched

    def _route_social_anchor_score(self, event, context):
        social = event.get("social") or {}
        friend_signal = int(social.get("friend_going_count") or 0) + int(social.get("friend_interested_count") or 0)
        community_signal = int(social.get("going_count") or 0) + int(social.get("interested_count") or 0)
        source = event.get("source") or {}
        source_quality = _optional_float((event.get("score_components") or {}).get("source_quality"), _optional_float(source.get("trust_score"), 0.35))
        reservation_ready = 1.0 if event.get("reservation_url") else 0.45 if event.get("source_url") else 0.15
        return round(_clamp(
            _optional_float(context.get("route_fit")) * 0.34
            + _optional_float(event.get("score")) * 0.20
            + min(1.0, friend_signal / 2) * 0.22
            + min(1.0, community_signal / 5) * 0.08
            + reservation_ready * 0.10
            + source_quality * 0.06
        ), 3)

    def _route_social_anchor_payload(self, event):
        if not event:
            return None
        context = event.get("route_context") or {}
        social = event.get("social") or {}
        friend_signal = int(social.get("friend_going_count") or 0) + int(social.get("friend_interested_count") or 0)
        community_signal = int(social.get("going_count") or 0) + int(social.get("interested_count") or 0)
        source = event.get("source") or {}
        action_url = event.get("reservation_url") or event.get("source_url")
        if friend_signal:
            reason = f"{friend_signal} selected friend signal{'s' if friend_signal != 1 else ''} and {context.get('fit_label', 'a route fit')} make this the best meetup anchor."
        elif event.get("reservation_url"):
            reason = f"Reservation-ready event paired with {context.get('fit_label', 'the route')}."
        elif community_signal:
            reason = f"{community_signal} community signal{'s' if community_signal != 1 else ''} make this a social route candidate."
        else:
            reason = f"Best route-paired local event near {context.get('stop_name') or 'a planned stop'}."

        return {
            "id": event.get("id"),
            "title": event.get("title"),
            "category": event.get("category"),
            "score": event.get("route_anchor_score"),
            "event_score": event.get("score"),
            "reason": reason,
            "action_url": action_url,
            "reservation_url": event.get("reservation_url"),
            "source_url": event.get("source_url"),
            "reservation_ready": bool(event.get("reservation_url")),
            "friend_signal_count": friend_signal,
            "community_signal_count": community_signal,
            "source_badge": source.get("badge"),
            "route_context": {
                "day": context.get("day"),
                "slot_id": context.get("slot_id"),
                "slot_label": context.get("slot_label"),
                "time_window": context.get("time_window"),
                "stop_name": context.get("stop_name"),
                "fit_label": context.get("fit_label"),
                "distance_to_stop_meters": context.get("distance_to_stop_meters"),
                "route_fit": context.get("route_fit"),
            } if context else None,
        }

    def _attach_event_to_route_stop(self, event, context, route_days):
        for day in route_days:
            if int(day.get("day") or 0) != int(context.get("day") or 0):
                continue
            for stop in day.get("stops", []):
                if stop.get("slot_id") != context.get("slot_id"):
                    continue
                matches = stop.setdefault("local_event_matches", [])
                matches.append(self._stop_event_preview(event, context))
                matches.sort(key=lambda item: item.get("route_fit") or 0, reverse=True)
                del matches[2:]
                return

    def _stop_event_preview(self, event, context):
        source = event.get("source") or {}
        readiness = event.get("event_readiness") or {}
        return {
            "id": event.get("id"),
            "title": event.get("title"),
            "category": event.get("category"),
            "starts_at": event.get("starts_at").isoformat() if hasattr(event.get("starts_at"), "isoformat") else event.get("starts_at"),
            "fit_label": context.get("fit_label"),
            "distance_to_stop_meters": context.get("distance_to_stop_meters"),
            "route_fit": context.get("route_fit"),
            "reasons": (context.get("reasons") or [])[:2],
            "source_badge": source.get("badge") or readiness.get("source_badge"),
            "source_url": event.get("source_url"),
            "reservation_url": event.get("reservation_url"),
            "reservation_ready": bool(event.get("reservation_url")),
            "readiness_status": readiness.get("status"),
        }

    def _best_event_route_context(self, event, route_days):
        stop_matches = []
        for day in route_days:
            for stop in day.get("stops", []):
                recommendation = stop.get("recommendation") or {}
                match = self._event_stop_match(event, day, stop, recommendation)
                if match:
                    stop_matches.append(match)

        if not stop_matches:
            return None

        best = max(stop_matches, key=lambda item: item["route_fit"])
        distance = best.get("distance_to_stop_meters")
        if distance is not None and distance <= 700:
            fit_label = f"Near {best['slot_label']}"
        elif best.get("slot_time_match") or best.get("category_match"):
            fit_label = f"Pairs with {best['slot_label']}"
        else:
            fit_label = f"Route idea near {best['slot_label']}"

        reasons = []
        if distance is not None:
            if distance <= 700:
                reasons.append(f"{round(distance)}m from {_display_name(best['recommendation'])}")
            elif distance <= 1600:
                reasons.append(f"Near {_display_name(best['recommendation'])}")
        if best.get("category_match"):
            reasons.append("Event category fits this route slot")
        if best.get("slot_time_match"):
            reasons.append("Timing lines up with the route")
        if not reasons:
            reasons.append("Adds a local happening near the route")

        return {
            "day": best["day"],
            "slot_id": best["slot_id"],
            "slot_label": best["slot_label"],
            "time_window": best["time_window"],
            "stop_name": _display_name(best["recommendation"]),
            "distance_to_stop_meters": round(distance) if distance is not None else None,
            "route_fit": round(best["route_fit"], 3),
            "fit_label": fit_label,
            "reasons": reasons[:3],
        }

    def _event_stop_match(self, event, day, stop, recommendation):
        event_point = self._event_coordinates(event)
        stop_point = self._coordinates(recommendation)
        distance = _haversine_meters(event_point, stop_point) if event_point and stop_point else None
        distance_fit = 0.45 if distance is None else _clamp(1 - (distance / 1800))
        category_match = stop.get("slot_id") in self._event_category_slot_hints(event)
        slot_time_match = stop.get("slot_id") in self._event_time_slot_hints(event)
        event_score = event.get("score") or 0

        route_fit = (
            distance_fit * 0.42
            + (0.24 if category_match else 0)
            + (0.18 if slot_time_match else 0)
            + event_score * 0.16
        )

        if distance is not None and distance > 2500 and not category_match and not slot_time_match:
            return None

        return {
            "day": day.get("day"),
            "slot_id": stop.get("slot_id"),
            "slot_label": stop.get("label"),
            "time_window": stop.get("time_window"),
            "recommendation": recommendation,
            "distance_to_stop_meters": distance,
            "category_match": category_match,
            "slot_time_match": slot_time_match,
            "route_fit": route_fit,
        }

    def _event_coordinates(self, event):
        lat = event.get("latitude")
        lng = event.get("longitude")
        if lat is None or lng is None:
            return None
        return float(lat), float(lng)

    def _event_category_slot_hints(self, event):
        category = (event.get("category") or "").strip().lower()
        hints = set()
        if category in EVENT_CATEGORY_SLOT_HINTS:
            hints.update(EVENT_CATEGORY_SLOT_HINTS[category])
        for key, slot_ids in EVENT_CATEGORY_SLOT_HINTS.items():
            if key and key in category:
                hints.update(slot_ids)
        return hints

    def _event_time_slot_hints(self, event):
        starts_at = _parse_event_start(event.get("starts_at"))
        if not starts_at:
            return set()
        hour = starts_at.hour
        hints = set()
        for start_hour, end_hour, slot_ids in EVENT_HOUR_SLOT_HINTS:
            if start_hour <= hour < end_hour:
                hints.update(slot_ids)
        return hints

    def _route_readiness(self, route_days, expected_stop_count, filter_summary=None, provider_errors=None, booking_plan=None, local_events=None):
        stops = [stop for day in route_days for stop in day.get("stops", [])]
        planned_stop_count = len(stops)
        stop_coverage = _clamp(planned_stop_count / max(1, expected_stop_count))
        variety_scores = [
            day.get("route_balance", {}).get("variety_score")
            for day in route_days
            if day.get("route_balance", {}).get("variety_score") is not None
        ]
        variety_score = sum(variety_scores) / len(variety_scores) if variety_scores else 0
        party_scores = [
            day.get("party_fit", {}).get("fairness_score")
            for day in route_days
            if day.get("party_fit", {}).get("fairness_score") is not None
        ]
        party_coverage_scores = [
            day.get("party_fit", {}).get("coverage_share")
            for day in route_days
            if day.get("party_fit", {}).get("coverage_share") is not None
        ]
        party_fairness_score = sum(party_scores) / len(party_scores) if party_scores else 0.75
        party_coverage_score = (
            sum(party_coverage_scores) / len(party_coverage_scores)
            if party_coverage_scores
            else 1.0 if not party_scores else party_fairness_score
        )
        party_score = _clamp((party_fairness_score * 0.52) + (party_coverage_score * 0.48))
        missing_inputs = (booking_plan or {}).get("missing_inputs") or []
        booking_summary = (booking_plan or {}).get("summary") or {}
        booking_score = self._route_booking_score(booking_plan)
        local_event_summary = (local_events or {}).get("summary") or {}
        event_score = self._route_event_score(local_events)
        event_social_summary = local_event_summary.get("social_readiness") or {}
        event_social_score = self._route_event_social_score(local_event_summary, local_events)
        authenticity_packet = self._route_authenticity_packet(route_days)
        authenticity_score = authenticity_packet.get("score", 0)

        score = _clamp(
            stop_coverage * 0.30
            + variety_score * 0.17
            + party_score * 0.17
            + authenticity_score * 0.16
            + booking_score * 0.12
            + event_score * 0.08
        )

        warnings = []
        strengths = []
        filter_summary = filter_summary or {}
        skipped = filter_summary.get("skipped") or {}

        if stop_coverage < 0.55:
            warnings.append("Route is missing several planned stops.")
        elif stop_coverage >= 0.9:
            strengths.append("Most route slots are filled.")

        if variety_score < 0.45 and planned_stop_count > 1:
            warnings.append("Route variety is low; try a different scout style or widen the range.")
        elif variety_score >= 0.7:
            strengths.append("Good mix of local categories.")

        if party_coverage_scores and party_coverage_score < 1:
            warnings.append("At least one traveler lacks a strong route stop.")
        if party_score < 0.7:
            warnings.append("Friend fit is uneven; try group-friendly scout style or swap a stop.")
        elif party_score >= 0.85:
            strengths.append("Balanced for this travel party.")

        if authenticity_packet.get("status") == "needs_attention":
            warnings.append(authenticity_packet.get("headline") or "Route needs stronger local-authentic picks.")
        elif authenticity_packet.get("status") == "watch":
            warnings.append(authenticity_packet.get("headline") or "Route authenticity is usable but could improve.")
        elif authenticity_packet.get("status") == "ready":
            strengths.append(authenticity_packet.get("headline") or "Route has strong local-authentic texture.")

        if skipped.get("hard_constraints", 0) > 0:
            warnings.append("Skip filters removed some route candidates.")
        if provider_errors:
            warnings.append("A provider lookup had issues, so route coverage may be thinner.")
        booking_action_link_count = len((booking_plan or {}).get("booking_action_links") or [])
        booking_timeline_items = ((booking_plan or {}).get("booking_timeline") or {}).get("items") or []
        saveable_timeline_count = sum(1 for item in booking_timeline_items if item.get("stores_reservation"))
        if missing_inputs:
            warnings.append("Add trip dates or origin to prepare booking steps.")
        elif booking_action_link_count == 0:
            warnings.append("Booking steps need provider links before this route feels bookable.")
        local_event_status = (local_events or {}).get("status")
        if local_event_status == "ready":
            if (
                local_event_summary.get("route_friend_signal_count", 0) > 0
                and local_event_summary.get("route_match_count", 0) > 0
                and event_social_score >= 0.5
            ):
                strengths.append("Friend-backed local events are paired with this route.")
            elif (
                local_event_summary.get("route_social_anchor_count", 0) > 0
                and local_event_summary.get("route_match_count", 0) > 0
                and event_social_score >= 0.38
            ):
                strengths.append("Social local events can anchor this Adventour.")
            if local_event_summary.get("route_reservation_ready_count", 0) > 0 and event_score >= 0.82:
                strengths.append("Reservation-ready local events are paired with this route.")
            elif local_event_summary.get("route_actionable_event_count", 0) > 0 and event_score >= 0.78:
                strengths.append("Source-backed local events are paired with this route.")
            elif event_score >= 0.82:
                strengths.append("Actionable local events are ready near this Adventour.")
            else:
                strengths.append("Local events are available near this Adventour.")
            if local_event_summary.get("route_match_count", 0) == 0:
                warnings.append("Local events found, but they are not paired to the route yet.")
            elif event_score < 0.7:
                warnings.append("Local events found, but they may need manual source or reservation research.")
            if (
                local_event_summary.get("route_match_count", 0) > 0
                and not local_event_summary.get("route_friend_signal_count", 0)
                and not local_event_summary.get("route_community_signal_count", 0)
            ):
                warnings.append("Local events are paired, but they need social signal before meetup testing.")
        elif local_event_status == "empty":
            warnings.append("No local events matched this launch point yet.")

        if not missing_inputs and booking_score >= 0.85 and saveable_timeline_count:
            strengths.append("Booking links and reservation storage are ready.")
        elif not missing_inputs and booking_score >= 0.85:
            strengths.append("Booking steps are ready to prepare.")
        elif (booking_plan or {}).get("status") == "provider_not_connected":
            warnings.append("Booking logistics are not connected yet.")
        elif not missing_inputs and booking_summary.get("blocked_component_count", 0) > 0:
            warnings.append("Some booking steps still need provider setup.")

        if score >= 0.85:
            label = "Strong route"
        elif score >= 0.7:
            label = "Ready to test"
        elif score >= 0.45:
            label = "Needs tuning"
        else:
            label = "Not ready yet"

        return {
            "score": round(score, 3),
            "label": label,
            "planned_stop_count": planned_stop_count,
            "expected_stop_count": expected_stop_count,
            "stop_coverage": round(stop_coverage, 3),
            "variety_score": round(variety_score, 3),
            "party_score": round(party_score, 3),
            "party_fairness_score": round(party_fairness_score, 3),
            "party_coverage_score": round(party_coverage_score, 3),
            "authenticity_score": round(authenticity_score, 3),
            "authenticity_summary": authenticity_packet,
            "booking_score": round(booking_score, 3),
            "booking_summary": booking_summary,
            "booking_action_link_count": booking_action_link_count,
            "booking_saveable_item_count": saveable_timeline_count,
            "event_score": round(event_score, 3),
            "event_social_score": round(event_social_score, 3),
            "event_social_summary": event_social_summary,
            "event_summary": local_event_summary,
            "warnings": warnings[:5],
            "strengths": strengths[:6],
        }

    def _route_authenticity_packet(self, route_days):
        stops = [stop for day in route_days for stop in day.get("stops", [])]
        count = len(stops)
        if not count:
            return {
                "status": "needs_attention",
                "headline": "No stops are ready to prove local authenticity yet.",
                "score": 0,
                "stop_count": 0,
                "local_feeling_count": 0,
                "hidden_gem_count": 0,
                "generic_risk_count": 0,
                "chain_risk_count": 0,
                "tourist_trap_risk_count": 0,
                "thin_local_evidence_count": 0,
                "average_authenticity_confidence": 0,
                "local_feeling_share": 0,
                "hidden_gem_share": 0,
                "generic_risk_share": 0,
                "highlights": [],
                "warnings": ["Build a route before judging authenticity."],
                "next_actions": ["Seed more local places or widen the route search."],
            }

        total_authenticity = 0.0
        local_feeling = []
        hidden_gems = []
        generic_risks = []
        chain_risks = []
        tourist_risks = []
        thin_local_evidence = []
        confidence_values = []
        for stop in stops:
            recommendation = stop.get("recommendation") or {}
            evidence = recommendation.get("authenticity_evidence") or {}
            components = recommendation.get("components") or {}
            authenticity = float(components.get("authenticity", evidence.get("score", 0)) or 0)
            total_authenticity += authenticity
            label = evidence.get("label")
            hidden_gem_score = float(evidence.get("hidden_gem_score") or 0)
            chain_risk = float(evidence.get("chain_risk") or components.get("chain_penalty") or 0)
            tourist_trap = float(evidence.get("tourist_trap_score") or 0)
            confidence = evidence.get("confidence")
            if confidence is None:
                confidence = components.get("authenticity_confidence")
            confidence = float(confidence) if confidence is not None else None
            confidence_status = evidence.get("confidence_status") or components.get("authenticity_confidence_status")
            if confidence is not None:
                confidence_values.append(confidence)
            stop_payload = {
                "slot_id": stop.get("slot_id"),
                "label": stop.get("label"),
                "name": recommendation.get("name") or (recommendation.get("display") or {}).get("name"),
                "authenticity": round(authenticity, 3),
                "authenticity_label": label,
                "hidden_gem_score": round(hidden_gem_score, 3),
                "chain_risk": round(chain_risk, 3),
                "tourist_trap_score": round(tourist_trap, 3),
                "authenticity_confidence": round(confidence, 3) if confidence is not None else None,
                "authenticity_confidence_status": confidence_status,
            }

            if label in {"Hidden gem", "Local-feeling"} or authenticity >= 0.64:
                local_feeling.append(stop_payload)
            if label == "Hidden gem" or hidden_gem_score >= 0.58:
                hidden_gems.append(stop_payload)
            if confidence_status == "thin" and (label in {"Hidden gem", "Local-feeling", "Popular local"} or authenticity >= 0.64):
                thin_local_evidence.append(stop_payload)
            if label == "Generic risk" or chain_risk >= 0.3 or tourist_trap >= 0.35:
                generic_risks.append(stop_payload)
            if chain_risk >= 0.3:
                chain_risks.append(stop_payload)
            if tourist_trap >= 0.35:
                tourist_risks.append(stop_payload)

        average_authenticity = total_authenticity / count
        local_share = len(local_feeling) / count
        hidden_share = len(hidden_gems) / count
        generic_share = len(generic_risks) / count
        thin_local_share = len(thin_local_evidence) / count
        average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0
        score = _clamp(
            average_authenticity * 0.42
            + local_share * 0.30
            + hidden_share * 0.18
            - generic_share * 0.24
            - thin_local_share * 0.12
        )

        if generic_share >= 0.45 or score < 0.42:
            status = "needs_attention"
            headline = "Route may feel too generic for Adventour."
        elif thin_local_evidence or local_share < 0.45 or score < 0.62:
            status = "watch"
            headline = (
                "Route has local texture, but some proof is thin."
                if thin_local_evidence
                else "Route has some local texture, but needs stronger hidden-gem coverage."
            )
        else:
            status = "ready"
            headline = "Route has a local-first backbone."

        highlights = []
        warnings = []
        next_actions = []
        if local_feeling:
            highlights.append(f"{len(local_feeling)} local-feeling stop{'s' if len(local_feeling) != 1 else ''} anchor the route.")
        if hidden_gems:
            highlights.append(f"{len(hidden_gems)} hidden-gem style pick{'s' if len(hidden_gems) != 1 else ''} keep it from feeling generic.")
        if generic_risks:
            warnings.append(f"{len(generic_risks)} stop{'s' if len(generic_risks) != 1 else ''} carry generic, chain, or tourist-trap risk.")
            next_actions.append("Swap the riskiest stop for a local-feeling alternative before sharing this route.")
        if thin_local_evidence:
            warnings.append(f"{len(thin_local_evidence)} local-feeling stop{'s' if len(thin_local_evidence) != 1 else ''} need more proof before Adventour should fully trust the route.")
            next_actions.append("Swipe, rate, or swap thin-proof local stops before sharing this route.")
        if local_share < 0.45:
            warnings.append("Less than half the route has strong local/authenticity signal.")
            next_actions.append("Try Hidden gems scout style or widen the range for more local texture.")
        if not hidden_gems:
            warnings.append("No hidden-gem style stop made the route yet.")
            next_actions.append("Use the swap suggestions to add at least one underexposed local stop.")

        return {
            "status": status,
            "headline": headline,
            "score": round(score, 3),
            "stop_count": count,
            "average_authenticity": round(average_authenticity, 3),
            "local_feeling_count": len(local_feeling),
            "hidden_gem_count": len(hidden_gems),
            "generic_risk_count": len(generic_risks),
            "chain_risk_count": len(chain_risks),
            "tourist_trap_risk_count": len(tourist_risks),
            "thin_local_evidence_count": len(thin_local_evidence),
            "average_authenticity_confidence": round(average_confidence, 3),
            "local_feeling_share": round(local_share, 3),
            "hidden_gem_share": round(hidden_share, 3),
            "generic_risk_share": round(generic_share, 3),
            "thin_local_evidence_share": round(thin_local_share, 3),
            "strongest_local_stops": sorted(
                local_feeling,
                key=lambda item: (item["authenticity"], item["hidden_gem_score"]),
                reverse=True,
            )[:3],
            "risk_stops": sorted(
                generic_risks,
                key=lambda item: (item["chain_risk"], item["tourist_trap_score"]),
                reverse=True,
            )[:3],
            "highlights": highlights[:3],
            "warnings": warnings[:3],
            "next_actions": list(dict.fromkeys(next_actions))[:3],
        }

    def _route_booking_score(self, booking_plan):
        if not booking_plan:
            return 0.35

        missing_inputs = booking_plan.get("missing_inputs") or []
        summary = booking_plan.get("summary") or {}
        if summary.get("readiness_score") is not None:
            base_score = float(summary["readiness_score"] or 0)
        elif booking_plan.get("status") == "provider_not_connected":
            base_score = 0.35
        else:
            base_score = 1.0 if not missing_inputs else max(0.45, 1 - len(missing_inputs) * 0.18)

        action_links = booking_plan.get("booking_action_links") or []
        timeline_items = (booking_plan.get("booking_timeline") or {}).get("items") or []
        saveable_count = sum(1 for item in timeline_items if item.get("stores_reservation"))
        storage_ready = bool((booking_plan.get("reservation_storage") or {}).get("status") == "ready")
        planning_burden = booking_plan.get("planning_burden") or {}
        planning_burden_score = float(planning_burden.get("score") or 0)

        action_link_score = min(1.0, len(action_links) / 3) if action_links else 0.0
        saveable_score = min(1.0, saveable_count / 2) if saveable_count else 0.0
        storage_score = 1.0 if storage_ready else 0.0
        missing_penalty = min(0.36, len(missing_inputs) * 0.12)

        score = _clamp(
            base_score * 0.54
            + action_link_score * 0.16
            + saveable_score * 0.12
            + storage_score * 0.08
            + (1 - planning_burden_score) * 0.10
            - missing_penalty
        )
        if missing_inputs:
            return min(score, 0.49)
        if not action_links:
            return min(score, 0.68)
        return score

    def _route_event_score(self, local_events):
        summary = (local_events or {}).get("summary") or {}
        status = (local_events or {}).get("status")
        base_score = (
            summary.get("readiness_score")
            if summary.get("readiness_score") is not None
            else 0.55
            if status == "empty"
            else 0.75
        )
        base_score = float(base_score or 0)
        event_count = int(summary.get("event_count") or len((local_events or {}).get("events") or []) or 0)
        if not event_count:
            return _clamp(base_score)

        route_match_count = int(summary.get("route_match_count") or 0)
        route_actionable_count = int(summary.get("route_actionable_event_count") or 0)
        route_reservation_count = int(summary.get("route_reservation_ready_count") or 0)
        route_social_anchor_count = int(summary.get("route_social_anchor_count") or 0)
        route_friend_signal_count = int(summary.get("route_friend_signal_count") or 0)
        source_summary = summary.get("source_summary") or {}
        trusted_source_count = int(source_summary.get("trusted_source_count") or 0)

        route_match_share = route_match_count / max(1, event_count)
        route_actionable_share = route_actionable_count / max(1, event_count)
        route_reservation_share = route_reservation_count / max(1, event_count)
        route_social_score = self._route_event_social_score(summary, local_events)
        trusted_source_share = trusted_source_count / max(1, event_count)

        route_score = _clamp(
            base_score * 0.56
            + route_match_share * 0.14
            + route_actionable_share * 0.07
            + route_reservation_share * 0.07
            + route_social_score * 0.12
            + min(1.0, trusted_source_share) * 0.04
        )

        if route_match_count == 0:
            return min(route_score, 0.68)
        if route_friend_signal_count:
            return max(route_score, min(0.96, base_score + 0.06))
        if route_social_anchor_count:
            return max(route_score, min(0.9, base_score + 0.03))
        if route_reservation_count:
            return max(route_score, min(0.94, base_score + 0.04))
        if route_actionable_count:
            return max(route_score, min(0.86, base_score + 0.02))
        return route_score

    def _route_event_social_score(self, summary, local_events=None):
        summary = summary or {}
        social_readiness = summary.get("social_readiness") or {}
        social_score = _clamp(float(social_readiness.get("score") or 0))
        event_count = int(summary.get("event_count") or len((local_events or {}).get("events") or []) or 0)
        if not event_count:
            return social_score

        route_social_anchor_count = int(summary.get("route_social_anchor_count") or 0)
        route_friend_signal_count = int(summary.get("route_friend_signal_count") or 0)
        route_community_signal_count = int(summary.get("route_community_signal_count") or 0)
        route_social_anchor_share = route_social_anchor_count / max(1, event_count)
        route_social_signal_share = _clamp(
            route_social_anchor_share * 0.5
            + min(1.0, route_friend_signal_count / max(1, event_count)) * 0.35
            + min(1.0, route_community_signal_count / max(1, event_count)) * 0.15
        )
        return _clamp(social_score * 0.55 + route_social_signal_share * 0.45)

    def _route_explanation(
        self,
        route_days,
        route_readiness,
        price_breakdown,
        booking_plan,
        local_events,
        member_count=1,
        scoring_profile=None,
    ):
        stops = [stop for day in route_days for stop in day.get("stops", [])]
        unique_groups = sorted({
            group
            for day in route_days
            for group in (day.get("route_balance", {}).get("unique_groups") or [])
        })
        party_fit_scores = [
            day.get("party_fit", {}).get("fairness_score")
            for day in route_days
            if day.get("party_fit", {}).get("fairness_score") is not None
        ]
        party_fit = sum(party_fit_scores) / len(party_fit_scores) if party_fit_scores else None
        per_person = (price_breakdown or {}).get("per_person") or {}
        booking_summary = (booking_plan or {}).get("summary") or {}
        event_summary = (local_events or {}).get("summary") or {}
        route_event_count = event_summary.get("route_match_count") or 0

        reasons = []
        if stops:
            reasons.append(
                f"Built {len(stops)} stop{'s' if len(stops) != 1 else ''} around the {scoring_profile or 'selected'} scout style."
            )
        if unique_groups:
            reasons.append(
                f"Mixes {', '.join(group.replace('_', ' ') for group in unique_groups[:3])}"
                f"{' and more' if len(unique_groups) > 3 else ''}."
            )
        if member_count and member_count > 1 and party_fit is not None:
            reasons.append(
                f"Balances {member_count} travelers with {round(party_fit * 100)}% route fairness."
            )
        elif member_count and member_count > 1:
            reasons.append(f"Blends preferences across {member_count} travelers.")
        if route_event_count:
            event_title = event_summary.get("top_route_event_title") or event_summary.get("top_event_title")
            reasons.append(
                f"Pairs {route_event_count} local event{'s' if route_event_count != 1 else ''}"
                f"{f' including {event_title}' if event_title else ''} with route stops."
            )
        elif (local_events or {}).get("status") == "ready":
            reasons.append("Includes local events near the launch point.")
        if booking_summary:
            reasons.append(booking_summary.get("message") or "Booking details can be saved with this route.")

        known_low = per_person.get("total_known_low")
        known_high = per_person.get("total_known_high")
        if known_low is not None and known_high is not None:
            reasons.append(f"Known local estimate is ${known_low}-${known_high} per person before live flight or stay pricing.")

        if (route_readiness or {}).get("score", 0) >= 0.85:
            headline = "This route is strong enough to test."
        elif (route_readiness or {}).get("score", 0) >= 0.7:
            headline = "This route is ready for a beta Adventour."
        elif stops:
            headline = "This route has a good shell, but needs tuning."
        else:
            headline = "This route needs more candidates before it feels ready."

        return {
            "headline": headline,
            "reasons": reasons[:5],
            "cautions": (route_readiness or {}).get("warnings", [])[:3],
            "stats": {
                "stop_count": len(stops),
                "day_count": len(route_days),
                "unique_group_count": len(unique_groups),
                "variety_score": (route_readiness or {}).get("variety_score"),
                "party_score": (route_readiness or {}).get("party_score"),
                "authenticity_score": (route_readiness or {}).get("authenticity_score"),
                "booking_score": (route_readiness or {}).get("booking_score"),
                "event_score": (route_readiness or {}).get("event_score"),
                "route_event_count": route_event_count,
                "known_per_person_low": known_low,
                "known_per_person_high": known_high,
            },
        }

    def _itinerary_story(
        self,
        destination_label,
        trip_style,
        pace,
        budget_profile,
        route_days,
        route_readiness,
        route_explanation,
        price_breakdown,
        booking_plan,
        local_events,
        member_count=1,
    ):
        stops = [stop for day in route_days for stop in day.get("stops", [])]
        unique_groups = sorted({
            group
            for day in route_days
            for group in (day.get("route_balance", {}).get("unique_groups") or [])
        })
        display_groups = [group.replace("_", " ") for group in unique_groups[:3]]
        readiness_score = float((route_readiness or {}).get("score") or 0)
        booking_summary = (booking_plan or {}).get("summary") or {}
        booking_timeline = (booking_plan or {}).get("booking_timeline") or {}
        event_summary = (local_events or {}).get("summary") or {}
        per_person = (price_breakdown or {}).get("per_person") or {}
        known_low = per_person.get("total_known_low")
        known_high = per_person.get("total_known_high")

        local_first_count = 0
        hidden_gem_count = 0
        for stop in stops:
            evidence = stop.get("recommendation", {}).get("authenticity_evidence") or {}
            if float(evidence.get("score") or 0) >= 0.62:
                local_first_count += 1
            if float(evidence.get("hidden_gem_score") or 0) >= 0.58:
                hidden_gem_count += 1

        if readiness_score >= 0.85:
            headline = "A ready-to-launch Adventour with a local-first backbone."
        elif readiness_score >= 0.7 and local_first_count:
            headline = "A beta-ready local-first Adventour with clear next steps."
        elif readiness_score >= 0.7:
            headline = "A beta-ready Adventour with clear next steps."
        elif stops:
            headline = "A promising Adventour shell that needs one more pass."
        else:
            headline = "Adventour needs more local candidates before this becomes a trip."

        destination = destination_label or "this launch point"
        group_phrase = ", ".join(display_groups) if display_groups else "local texture"
        pace_phrase = (pace or "balanced").replace("_", " ")
        style_phrase = "vacation" if trip_style == "vacation" else "route"
        narrative = (
            f"This {pace_phrase} {style_phrase} in {destination} is shaped around {group_phrase}, "
            "then checked for friend fit, booking readiness, and local-event energy."
        )

        highlights = []
        if stops:
            highlights.append(
                f"{len(stops)} stop{'s' if len(stops) != 1 else ''} across {len(route_days)} day{'s' if len(route_days) != 1 else ''}."
            )
        if unique_groups:
            highlights.append(
                f"Route mix covers {', '.join(display_groups)}{' and more' if len(unique_groups) > 3 else ''}."
            )
        if local_first_count:
            highlights.append(
                f"{local_first_count} stop{'s' if local_first_count != 1 else ''} carry strong local/authenticity signals."
            )
        if hidden_gem_count:
            highlights.append(
                f"{hidden_gem_count} hidden-gem style pick{'s' if hidden_gem_count != 1 else ''} help it avoid a generic checklist."
            )
        if member_count and member_count > 1:
            party_score = (route_readiness or {}).get("party_score")
            if party_score is not None:
                highlights.append(f"Group blend is at {round(float(party_score) * 100)}% fairness for {member_count} travelers.")
            else:
                highlights.append(f"Preferences are blended across {member_count} travelers.")
        if event_summary.get("route_match_count"):
            event_title = event_summary.get("top_route_event_title") or event_summary.get("top_event_title")
            highlights.append(
                f"{event_summary.get('route_match_count')} local event{'s' if event_summary.get('route_match_count') != 1 else ''}"
                f"{f' including {event_title}' if event_title else ''} line up with the route."
            )
        elif (local_events or {}).get("status") == "ready":
            highlights.append("Local events are available near the route for a social anchor.")
        if known_low is not None and known_high is not None:
            highlights.append(f"Known local spend is estimated at ${known_low}-${known_high} per person before live flight or stay pricing.")

        planning_steps = []
        if booking_timeline.get("headline"):
            planning_steps.append(booking_timeline["headline"])
        elif booking_summary.get("message"):
            planning_steps.append(booking_summary["message"])
        if (route_readiness or {}).get("warnings"):
            planning_steps.extend((route_readiness or {}).get("warnings", [])[:2])
        if (booking_plan or {}).get("next_best_actions"):
            planning_steps.extend(
                action.get("label")
                for action in (booking_plan or {}).get("next_best_actions", [])[:2]
                if action.get("label")
            )
        if not planning_steps and (route_explanation or {}).get("reasons"):
            planning_steps.extend((route_explanation or {}).get("reasons", [])[:2])

        badges = [
            {
                "label": (route_readiness or {}).get("label") or "Route",
                "detail": f"{round(readiness_score * 100)}% ready",
                "tone": "ready" if readiness_score >= 0.7 else "watch",
            },
            {
                "label": "Local-first",
                "detail": f"{local_first_count}/{len(stops)} stops" if stops else "Needs candidates",
                "tone": "ready" if local_first_count else "watch",
            },
            {
                "label": "Planning",
                "detail": (booking_timeline.get("status") or booking_summary.get("status") or "draft").replace("_", " "),
                "tone": "ready" if (route_readiness or {}).get("booking_score", 0) >= 0.75 else "watch",
            },
        ]
        if member_count and member_count > 1:
            badges.append({
                "label": "Party",
                "detail": f"{member_count} travelers",
                "tone": "ready" if (route_readiness or {}).get("party_score", 0) >= 0.7 else "watch",
            })
        if event_summary.get("event_count") is not None:
            badges.append({
                "label": "Events",
                "detail": f"{event_summary.get('route_match_count') or 0} paired",
                "tone": "ready" if event_summary.get("route_match_count") else "watch",
            })

        return {
            "headline": headline,
            "narrative": narrative,
            "highlights": highlights[:5],
            "planning_steps": planning_steps[:4],
            "badges": badges[:5],
            "stats": {
                "local_first_stop_count": local_first_count,
                "hidden_gem_stop_count": hidden_gem_count,
                "stop_count": len(stops),
                "day_count": len(route_days),
                "unique_group_count": len(unique_groups),
                "readiness_score": round(readiness_score, 3),
                "booking_timeline_status": booking_timeline.get("status"),
                "budget_profile": budget_profile,
            },
        }

    def _launch_checklist(self, route_days, route_readiness, booking_plan=None, local_events=None):
        stops = [stop for day in route_days for stop in day.get("stops", [])]
        planned_stop_count = len(stops)
        expected_stop_count = (route_readiness or {}).get("expected_stop_count") or planned_stop_count
        booking_summary = (booking_plan or {}).get("summary") or {}
        booking_missing = (booking_plan or {}).get("missing_inputs") or []
        local_event_summary = (local_events or {}).get("summary") or {}
        local_event_status = (local_events or {}).get("status")
        party_score = (route_readiness or {}).get("party_score")
        variety_score = (route_readiness or {}).get("variety_score")

        items = []
        if planned_stop_count > 0:
            stop_status = "ready" if planned_stop_count >= expected_stop_count else "warning"
            items.append({
                "id": "route_stops",
                "label": "Route stops",
                "status": stop_status,
                "detail": f"{planned_stop_count}/{expected_stop_count} planned stops are filled.",
                "action": "Widen the range or try another scout style if you want fuller coverage." if stop_status == "warning" else "Start with the first stop when ready.",
                "blocking": False,
            })
        else:
            items.append({
                "id": "route_stops",
                "label": "Route stops",
                "status": "action_needed",
                "detail": "No route stops are ready yet.",
                "action": "Rebuild with a broader range, fewer skip filters, or another scout style.",
                "blocking": True,
            })

        if variety_score is not None:
            variety_ready = variety_score >= 0.45 or planned_stop_count <= 1
            items.append({
                "id": "route_variety",
                "label": "Route variety",
                "status": "ready" if variety_ready else "warning",
                "detail": f"Route variety is {round(float(variety_score) * 100)}%.",
                "action": "Swap a repeated category or compare scout styles." if not variety_ready else "Good mix for a beta route.",
                "blocking": False,
            })

        if party_score is not None:
            party_ready = party_score >= 0.7
            items.append({
                "id": "party_fit",
                "label": "Party fit",
                "status": "ready" if party_ready else "warning",
                "detail": f"Travel-party fairness is {round(float(party_score) * 100)}%.",
                "action": "Use group-friendly scout style or swap a stop." if not party_ready else "Balanced enough to test with this group.",
                "blocking": False,
            })

        if booking_missing:
            items.append({
                "id": "booking_details",
                "label": "Booking details",
                "status": "action_needed",
                "detail": "Missing " + ", ".join(booking_missing).replace("_", " ") + ".",
                "action": "Add origin and trip dates before relying on flight or stay steps.",
                "blocking": False,
            })
        elif booking_summary:
            booking_ready = float(booking_summary.get("readiness_score", 0)) >= 0.75
            items.append({
                "id": "booking_details",
                "label": "Booking details",
                "status": "ready" if booking_ready else "warning",
                "detail": booking_summary.get("message") or "Booking details can be saved with this route.",
                "action": "Open provider links and save confirmations as you book." if booking_ready else "Review provider steps before starting.",
                "blocking": False,
            })

        if local_event_status == "ready":
            reservation_count = local_event_summary.get("reservation_ready_count") or 0
            items.append({
                "id": "local_events",
                "label": "Local events",
                "status": "ready" if reservation_count else "warning",
                "detail": f"{local_event_summary.get('event_count', 0)} nearby event picks found.",
                "action": "Open event or reservation links before starting." if reservation_count else "Review source links for event details.",
                "blocking": False,
            })
        else:
            items.append({
                "id": "local_events",
                "label": "Local events",
                "status": "optional",
                "detail": "No matched local events yet.",
                "action": "Use source searches or add an event manually if this trip needs a social anchor.",
                "blocking": False,
            })

        blocking_count = sum(1 for item in items if item.get("blocking"))
        action_count = sum(1 for item in items if item.get("status") == "action_needed")
        warning_count = sum(1 for item in items if item.get("status") == "warning")
        can_start = planned_stop_count > 0 and blocking_count == 0
        if not can_start:
            headline = "Finish the route shell before starting."
        elif action_count or warning_count:
            headline = "Startable, with a few things to review."
        else:
            headline = "Ready to launch."

        return {
            "can_start": can_start,
            "headline": headline,
            "blocking_count": blocking_count,
            "action_count": action_count,
            "warning_count": warning_count,
            "items": items,
        }

    def _day_summary(self, stops):
        if not stops:
            return "No route could be assembled yet. Try widening the search distance or seeding more local places."
        labels = [stop["label"].lower() for stop in stops]
        return f"{len(stops)} planned stops covering " + ", ".join(labels) + "."

    def _title(self, destination_label, days, trip_style="day"):
        destination = destination_label or "your launch point"
        if trip_style == "weekend":
            return f"Weekend Adventour in {destination}"
        if trip_style == "vacation":
            return f"{days}-day Adventour vacation in {destination}"
        return f"{days}-day Adventour in {destination}" if days > 1 else f"One-day Adventour in {destination}"

    def _price_breakdown(self, route_days, party_size, budget_profile="flexible", members=None, constraints=None, booking_plan=None):
        place_low = 0
        place_high = 0
        stop_count = 0
        for day in route_days:
            for stop in day["stops"]:
                stop_count += 1
                price_level = stop["recommendation"].get("display", {}).get("price_level")
                low, high = PRICE_LEVEL_ESTIMATES.get(price_level if price_level is not None else 2, PRICE_LEVEL_ESTIMATES[2])
                place_low += low
                place_high += high

        local_transit_low, local_transit_high = self._local_transport_price_range(route_days, booking_plan)
        per_person = {
            "places_low": place_low,
            "places_high": place_high,
            "local_transit_low": local_transit_low,
            "local_transit_high": local_transit_high,
            "flight_low": None,
            "flight_high": None,
            "stay_low": None,
            "stay_high": None,
            "total_known_low": place_low + local_transit_low,
            "total_known_high": place_high + local_transit_high,
        }
        quote_plan = self._cost_quote_plan(per_person, booking_plan)
        return {
            "currency": "USD",
            "party_size": party_size,
            "budget_profile": budget_profile,
            "budget_label": BUDGET_PROFILES.get(budget_profile, BUDGET_PROFILES["flexible"])["label"],
            "days": len(route_days),
            "nights": self._lodging_nights(len(route_days), constraints or {}),
            "per_person": per_person,
            "travelers": self._traveler_cost_breakdown(members or [], party_size, per_person),
            "quote_plan": quote_plan,
            "unknown_cost_components": [
                item["type"]
                for item in quote_plan.get("items", [])
                if item.get("quote_required")
            ],
            "party_total_known": {
                "low": (place_low + local_transit_low) * party_size,
                "high": (place_high + local_transit_high) * party_size,
            },
            "assumptions": [
                "Place costs are estimated from provider price levels when available.",
                "Flight and stay prices require booking providers and are intentionally not guessed yet.",
                "Local travel uses Adventour's route logistics estimate, not a fare quote.",
            ],
        }

    def _local_transport_price_range(self, route_days, booking_plan=None):
        for component in (booking_plan or {}).get("components") or []:
            if component.get("type") != "local_transport":
                continue
            estimate = component.get("estimate") or {}
            low = estimate.get("per_person_low")
            high = estimate.get("per_person_high")
            if low is not None and high is not None:
                return low, high

        return 8 * max(1, len(route_days)), 35 * max(1, len(route_days))

    def _cost_quote_plan(self, per_person, booking_plan=None):
        components = {
            component.get("type"): component
            for component in (booking_plan or {}).get("components") or []
        }
        action_links = {
            link.get("component_type"): link
            for link in (booking_plan or {}).get("booking_action_links") or []
        }
        quote_items = []
        for component_type, label, low_key, high_key in [
            ("flight", "Flight or train", "flight_low", "flight_high"),
            ("stay", "Stay", "stay_low", "stay_high"),
        ]:
            component = components.get(component_type) or {}
            status = component.get("status")
            quote_required = per_person.get(low_key) is None or per_person.get(high_key) is None
            if status in {"optional_for_day_trip", "not_needed_for_day_trip"} and quote_required:
                quote_required = False
            if not quote_required and not component:
                continue
            link = action_links.get(component_type) or {}
            missing_inputs = component.get("missing_inputs") or []
            provider_options = [
                {
                    "label": option.get("label"),
                    "url": option.get("url"),
                    "note": option.get("note"),
                }
                for option in (component.get("provider_options") or [])[:3]
            ]
            quote_items.append({
                "type": component_type,
                "label": label,
                "status": status or "not_configured",
                "quote_required": quote_required,
                "quote_status": (
                    "ready_to_quote"
                    if quote_required and link.get("url") and not missing_inputs
                    else "needs_details"
                    if quote_required and missing_inputs
                    else "not_needed"
                    if not quote_required
                    else "manual"
                ),
                "missing_inputs": missing_inputs,
                "search_hint": component.get("search_hint"),
                "provider_options": provider_options,
                "primary_provider_label": link.get("provider_label") or (provider_options[0].get("label") if provider_options else None),
                "primary_url": link.get("url") or (provider_options[0].get("url") if provider_options else None),
                "next_steps": (component.get("next_steps") or [])[:3],
            })

        required_items = [item for item in quote_items if item.get("quote_required")]
        ready_items = [item for item in required_items if item.get("quote_status") == "ready_to_quote"]
        missing_input_labels = sorted({
            str(missing)
            for item in required_items
            for missing in item.get("missing_inputs") or []
        })
        if not required_items:
            status = "local_estimate_only"
            headline = "No travel quotes are required for this route yet."
        elif len(ready_items) == len(required_items):
            status = "ready_to_quote"
            headline = "Known local costs are estimated; travel quotes are ready to compare."
        elif missing_input_labels:
            status = "needs_details"
            headline = "Add trip basics before Adventour can prepare reliable travel quotes."
        else:
            status = "manual"
            headline = "Some travel quote links need manual provider research."

        return {
            "status": status,
            "headline": headline,
            "items": quote_items,
            "required_count": len(required_items),
            "ready_count": len(ready_items),
            "missing_inputs": missing_input_labels,
            "message": self._cost_quote_plan_message(status, required_items, ready_items, missing_input_labels),
        }

    def _cost_quote_plan_message(self, status, required_items, ready_items, missing_inputs):
        if status == "local_estimate_only":
            return "Adventour is only tracking local place and transport estimates for this route."
        labels = ", ".join(item.get("label") or item.get("type") for item in required_items)
        if status == "ready_to_quote":
            return f"{labels} still need live prices, and provider links are ready to open."
        if missing_inputs:
            readable = ", ".join(str(item).replace("_", " ") for item in missing_inputs[:3])
            return f"{labels} still need live prices; add {readable} to unlock reliable quotes."
        if ready_items:
            return f"{len(ready_items)}/{len(required_items)} travel quotes are ready to open."
        return f"{labels} still need live provider quotes."

    def _lodging_nights(self, route_days_count, constraints):
        travel_dates = (constraints or {}).get("travel_dates") or {}
        start = _parse_event_start(travel_dates.get("start"))
        end = _parse_event_start(travel_dates.get("end"))
        if start and end and end > start:
            return max(0, (end.date() - start.date()).days)
        return max(0, int(route_days_count or 1) - 1)

    def _traveler_cost_breakdown(self, members, party_size, per_person):
        traveler_count = max(1, int(party_size or 1))
        traveler_rows = []
        for index in range(traveler_count):
            member = members[index] if index < len(members) else {}
            display_name = member.get("display_name") or ("You" if index == 0 else f"Traveler {index + 1}")
            traveler_rows.append({
                "user_id": member.get("id"),
                "display_name": display_name,
                "known_low": per_person["total_known_low"],
                "known_high": per_person["total_known_high"],
                "components": [
                    {
                        "type": "places",
                        "label": "Places",
                        "low": per_person["places_low"],
                        "high": per_person["places_high"],
                        "status": "estimated",
                    },
                    {
                        "type": "local_transport",
                        "label": "Local travel",
                        "low": per_person["local_transit_low"],
                        "high": per_person["local_transit_high"],
                        "status": "estimated",
                    },
                    {
                        "type": "flight",
                        "label": "Flight or train",
                        "low": per_person["flight_low"],
                        "high": per_person["flight_high"],
                        "status": "provider_needed",
                    },
                    {
                        "type": "stay",
                        "label": "Stay",
                        "low": per_person["stay_low"],
                        "high": per_person["stay_high"],
                        "status": "provider_needed",
                    },
                ],
            })
        return traveler_rows

    def _trip_logistics_readiness(self, booking_plan, price_breakdown):
        booking_plan = booking_plan or {}
        price_breakdown = price_breakdown or {}
        summary = booking_plan.get("summary") or {}
        booking_handoff = booking_plan.get("booking_handoff") or {}
        booking_checklist = booking_plan.get("booking_checklist") or {}
        components = {
            component.get("type"): component
            for component in booking_plan.get("components") or []
        }
        action_links = booking_plan.get("booking_action_links") or []
        timeline_items = ((booking_plan.get("booking_timeline") or {}).get("items") or [])
        missing_inputs = booking_plan.get("missing_inputs") or summary.get("missing_inputs") or []
        checklist_items = booking_checklist.get("items") or []
        ready_count = int(booking_checklist.get("ready_count") or 0)
        blocking_count = int(booking_checklist.get("blocking_count") or 0)
        action_count = int(booking_checklist.get("action_count") or 0)
        checklist_ready_share = ready_count / len(checklist_items) if checklist_items else 0
        provider_link_count = len([link for link in action_links if link.get("url")])
        quote_ready_count = int(booking_handoff.get("ready_to_quote_count") or 0)
        save_ready_count = int(booking_handoff.get("ready_to_save_count") or 0)
        saveable_count = sum(1 for item in timeline_items if item.get("stores_reservation"))
        setup_ready_count = len(booking_handoff.get("setup_ready") or [])
        reservation_storage_ready = (booking_plan.get("reservation_storage") or {}).get("status") == "ready"
        local_transport = components.get("local_transport") or {}
        local_transport_ready = local_transport.get("status") == "estimated"
        per_person = price_breakdown.get("per_person") or {}
        quote_plan = price_breakdown.get("quote_plan") or self._cost_quote_plan(per_person, booking_plan)
        known_low = per_person.get("total_known_low")
        known_high = per_person.get("total_known_high")
        known_cost_ready = known_low is not None and known_high is not None
        unknown_cost_components = [
            label
            for label, low_key, high_key in [
                ("flight", "flight_low", "flight_high"),
                ("stay", "stay_low", "stay_high"),
            ]
            if per_person.get(low_key) is None or per_person.get(high_key) is None
        ]

        base_score = _optional_float(summary.get("readiness_score"))
        quote_score = min(1.0, quote_ready_count / 2)
        save_score = min(1.0, max(save_ready_count, saveable_count) / 3)
        provider_link_score = min(1.0, provider_link_count / 3)
        local_transport_score = 1.0 if local_transport_ready else 0.35 if local_transport else 0.0
        reservation_score = 1.0 if reservation_storage_ready else 0.0
        known_cost_score = 0.72 if known_cost_ready else 0.25
        score = _clamp(
            base_score * 0.28
            + quote_score * 0.16
            + save_score * 0.15
            + provider_link_score * 0.10
            + checklist_ready_share * 0.12
            + local_transport_score * 0.09
            + reservation_score * 0.06
            + known_cost_score * 0.04
            - min(0.24, len(missing_inputs) * 0.08)
            - min(0.16, blocking_count * 0.08)
        )

        strengths = []
        warnings = []
        next_actions = []
        if quote_ready_count:
            strengths.append(f"{quote_ready_count} travel quote link{'s' if quote_ready_count != 1 else ''} ready.")
        elif any((components.get(kind) or {}).get("status") == "needs_provider" for kind in ["flight", "stay"]):
            warnings.append("Flight or stay searches still need trip basics before they feel bookable.")
        if save_ready_count or saveable_count:
            strengths.append("Reservation wallet can save confirmation details after checkout.")
        elif reservation_storage_ready:
            warnings.append("Reservation storage is ready, but few booking pieces are save-ready yet.")
        if local_transport_ready:
            strengths.append("Local transport setup is estimated and ready to review.")
        else:
            warnings.append("Local transport setup needs a manual check.")
        if missing_inputs:
            readable = ", ".join(str(item).replace("_", " ") for item in missing_inputs[:3])
            warnings.append(f"Missing {readable} for reliable booking setup.")
            next_actions.append(f"Add {readable} before sharing this trip packet.")
        if unknown_cost_components:
            warnings.append(
                quote_plan.get("message")
                or f"{', '.join(unknown_cost_components[:2]).title()} costs need live provider quotes."
            )
        if booking_checklist.get("next_action"):
            next_actions.append(booking_checklist["next_action"])
        if booking_handoff.get("next_step"):
            next_actions.append(booking_handoff["next_step"])

        if blocking_count or missing_inputs:
            status = "needs_details"
            headline = "Trip logistics need a few basics before booking feels reliable."
        elif score >= 0.78:
            status = "ready"
            headline = "Trip logistics are ready enough to share and book."
        elif score >= 0.52:
            status = "action_needed"
            headline = "Trip logistics are usable, with manual pieces clearly marked."
        else:
            status = "manual"
            headline = "Trip logistics still need manual provider work."

        return {
            "status": status,
            "headline": headline,
            "score": round(score, 3),
            "booking_readiness_score": round(base_score, 3),
            "booking_handoff_status": booking_handoff.get("status"),
            "booking_checklist_status": booking_checklist.get("status"),
            "provider_link_count": provider_link_count,
            "quote_ready_count": quote_ready_count,
            "save_ready_count": save_ready_count,
            "saveable_timeline_count": saveable_count,
            "setup_ready_count": setup_ready_count,
            "blocking_count": blocking_count,
            "action_count": action_count,
            "missing_input_count": len(missing_inputs),
            "missing_inputs": missing_inputs,
            "checklist_ready_share": round(checklist_ready_share, 3),
            "reservation_storage_ready": reservation_storage_ready,
            "local_transport_status": local_transport.get("status"),
            "local_transport_mode": local_transport.get("mode"),
            "local_transport_provider": local_transport.get("setup_provider"),
            "flight_status": (components.get("flight") or {}).get("status"),
            "stay_status": (components.get("stay") or {}).get("status"),
            "known_cost_ready": known_cost_ready,
            "known_per_person_low": known_low,
            "known_per_person_high": known_high,
            "unknown_cost_components": unknown_cost_components,
            "quote_status": quote_plan.get("status"),
            "quote_required_count": quote_plan.get("required_count", 0),
            "quote_ready_count": quote_plan.get("ready_count", 0),
            "quote_missing_inputs": quote_plan.get("missing_inputs", []),
            "strengths": list(dict.fromkeys(strengths))[:4],
            "warnings": list(dict.fromkeys(warnings))[:4],
            "next_actions": list(dict.fromkeys(next_actions))[:4],
        }

    def _cost_confidence(self, price_breakdown, booking_plan):
        price_breakdown = price_breakdown or {}
        booking_plan = booking_plan or {}
        per_person = price_breakdown.get("per_person") or {}
        quote_plan = price_breakdown.get("quote_plan") or self._cost_quote_plan(per_person, booking_plan)
        known_low = per_person.get("total_known_low")
        known_high = per_person.get("total_known_high")
        currency = price_breakdown.get("currency", "USD")
        unknown_components = [
            label
            for label, low_key, high_key in [
                ("flight", "flight_low", "flight_high"),
                ("stay", "stay_low", "stay_high"),
            ]
            if per_person.get(low_key) is None or per_person.get(high_key) is None
        ]
        if known_low is not None and known_high is not None:
            combined_label = f"${known_low}-${known_high} known per person"
            message = (
                "Places and local transport are estimated; "
                f"{', '.join(unknown_components)} still need provider quotes."
                if unknown_components
                else "Known per-person route costs are estimated and ready to track."
            )
        else:
            combined_label = None
            message = "Cost confidence is manual until route estimates are available."

        return {
            "status": "estimated",
            "tracked_total": 0,
            "estimate_add_on_total": 0,
            "estimate_add_on_per_person": 0,
            "combined_known_low": known_low,
            "combined_known_high": known_high,
            "combined_label": combined_label,
            "currency": currency,
            "add_on_types": [],
            "unknown_types": unknown_components,
            "quote_status": quote_plan.get("status"),
            "quote_required_count": quote_plan.get("required_count", 0),
            "quote_ready_count": quote_plan.get("ready_count", 0),
            "quote_plan": quote_plan,
            "message": message,
        }

    def _trip_style_fit(
        self,
        trip_style,
        route_days,
        route_readiness,
        price_breakdown,
        booking_plan,
        local_events=None,
        trip_logistics_readiness=None,
    ):
        route_days = route_days or []
        route_readiness = route_readiness or {}
        price_breakdown = price_breakdown or {}
        booking_plan = booking_plan or {}
        local_event_summary = (local_events or {}).get("summary") or {}
        per_person = price_breakdown.get("per_person") or {}
        route_day_count = len(route_days)
        nights = int(price_breakdown.get("nights") if price_breakdown.get("nights") is not None else booking_plan.get("nights") or 0)
        planned_stop_count = int(route_readiness.get("planned_stop_count") or sum(len(day.get("stops", [])) for day in route_days))
        expected_stop_count = int(route_readiness.get("expected_stop_count") or planned_stop_count or 1)
        stop_coverage = _optional_float(route_readiness.get("stop_coverage"))
        booking_score = _optional_float(route_readiness.get("booking_score"))
        route_score = _optional_float(route_readiness.get("score"))
        event_route_match_count = int(local_event_summary.get("route_match_count") or 0)
        quote_plan = price_breakdown.get("quote_plan") or self._cost_quote_plan(per_person, booking_plan)
        quote_required_count = int(quote_plan.get("required_count") or 0)
        quote_ready_count = int(quote_plan.get("ready_count") or 0)
        quote_coverage = (
            quote_ready_count / quote_required_count
            if quote_required_count
            else 1.0 if trip_style == "day" else 0.65
        )

        if route_day_count <= 1 and nights <= 0:
            suggested_style = "day"
        elif route_day_count <= 3 and nights <= 3:
            suggested_style = "weekend"
        else:
            suggested_style = "vacation"

        if trip_style == "day":
            duration_fit = 1.0 if route_day_count == 1 and nights == 0 else 0.42
            style_label = "Day trip"
            ideal = "Best when the route is one day, low-lodging, and easy to launch now."
        elif trip_style == "weekend":
            duration_fit = 1.0 if 2 <= route_day_count <= 3 and 1 <= nights <= 3 else 0.58 if route_day_count <= 3 else 0.38
            style_label = "Weekend"
            ideal = "Best when the route has two or three days, one to three nights, and ready travel handoffs."
        else:
            duration_fit = 1.0 if route_day_count >= 3 and nights >= 2 else 0.58 if route_day_count >= 2 else 0.32
            style_label = "Vacation"
            ideal = "Best when Adventour can plan multiple days plus flight, stay, and local transport handoffs."

        route_depth = _clamp((stop_coverage * 0.62) + (min(1, planned_stop_count / max(1, expected_stop_count)) * 0.38))
        logistics_score = _optional_float((trip_logistics_readiness or {}).get("score"), booking_score)
        event_density = _clamp(event_route_match_count / max(1, route_day_count))
        score = _clamp(
            duration_fit * 0.38
            + route_depth * 0.22
            + booking_score * 0.16
            + quote_coverage * 0.14
            + event_density * 0.06
            + logistics_score * 0.04
        )

        reasons = []
        cautions = []
        if duration_fit >= 0.85:
            reasons.append(f"{style_label} length matches the route shape.")
        else:
            cautions.append(f"{style_label} length does not fully match the current route.")
        if route_depth >= 0.85:
            reasons.append("Route has enough stops for the selected trip style.")
        elif route_depth < 0.6:
            cautions.append("Route depth is thin for this trip style.")
        if quote_required_count and quote_ready_count >= quote_required_count:
            reasons.append("Flight and stay quote links are ready.")
        elif quote_required_count:
            cautions.append("Travel quote links still need origin, dates, or stay details.")
        if event_route_match_count:
            reasons.append(f"{event_route_match_count} local event{'s' if event_route_match_count != 1 else ''} can anchor the trip.")
        if booking_score < 0.55:
            cautions.append("Booking handoffs are not ready enough for this trip style.")

        if score >= 0.78 and not cautions:
            status = "ready"
            headline = f"{style_label} is a strong fit."
            next_action = "Start from this route style or compare scout styles before sharing."
        elif score >= 0.58:
            status = "watch"
            headline = f"{style_label} can work, but review the tradeoffs."
            next_action = cautions[0] if cautions else "Review booking and event details before sharing."
        else:
            status = "needs_attention"
            headline = f"{style_label} is not the best fit yet."
            next_action = (
                f"Consider switching to {suggested_style}."
                if suggested_style != trip_style
                else "Add route depth, trip dates, or booking details before sharing."
            )

        return {
            "status": status,
            "headline": headline,
            "message": ideal,
            "score": round(score, 3),
            "trip_style": trip_style,
            "suggested_style": suggested_style,
            "style_label": style_label,
            "route_days": route_day_count,
            "nights": nights,
            "duration_fit": round(duration_fit, 3),
            "route_depth_score": round(route_depth, 3),
            "booking_score": round(booking_score, 3),
            "quote_coverage": round(quote_coverage, 3),
            "quote_required_count": quote_required_count,
            "quote_ready_count": quote_ready_count,
            "event_density": round(event_density, 3),
            "event_route_match_count": event_route_match_count,
            "reasons": reasons[:4],
            "cautions": cautions[:4],
            "next_action": next_action,
        }

    def _trip_packet(self, route_days, route_readiness, price_breakdown, booking_plan, launch_checklist, local_events=None, trip_logistics_readiness=None, trip_style_fit=None):
        booking_plan = booking_plan or {}
        price_breakdown = price_breakdown or {}
        trip_logistics_readiness = trip_logistics_readiness or self._trip_logistics_readiness(booking_plan, price_breakdown)
        trip_style_fit = trip_style_fit or {}
        per_person = price_breakdown.get("per_person") or {}
        booking_summary = booking_plan.get("summary") or {}
        booking_timeline = booking_plan.get("booking_timeline") or {}
        booking_checklist = booking_plan.get("booking_checklist") or {}
        launch_checklist = launch_checklist or {}
        authenticity_packet = (route_readiness or {}).get("authenticity_summary") or {}
        local_event_summary = (local_events or {}).get("summary") or {}
        action_links = booking_plan.get("booking_action_links") or []
        timeline_items = booking_timeline.get("items") or []
        local_transport = next(
            (
                component
                for component in booking_plan.get("components") or []
                if component.get("type") == "local_transport"
            ),
            {},
        )
        mobility_setup = self._trip_packet_mobility_setup(local_transport)
        saveable_items = [
            item
            for item in timeline_items
            if item.get("stores_reservation")
        ]
        missing_inputs = booking_plan.get("missing_inputs") or booking_summary.get("missing_inputs") or []
        known_low = per_person.get("total_known_low")
        known_high = per_person.get("total_known_high")
        booking_score = (route_readiness or {}).get("booking_score")
        if booking_score is None:
            booking_score = booking_summary.get("readiness_score", 0)
        booking_score = float(booking_score or 0)
        can_start = bool(launch_checklist.get("can_start", True))
        event_reservation_count = local_event_summary.get("route_reservation_ready_count") or local_event_summary.get("reservation_ready_count") or 0
        quote_plan = price_breakdown.get("quote_plan") or self._cost_quote_plan(per_person, booking_plan)

        if missing_inputs:
            status = "needs_details"
            headline = "Add a few trip details before this Adventour is booking-ready."
        elif booking_score >= 0.85 and can_start:
            status = "ready"
            headline = "This Adventour has a clear booking packet."
        elif can_start:
            status = "action_needed"
            headline = "This Adventour is usable, but a few booking pieces still need attention."
        else:
            status = "blocked"
            headline = launch_checklist.get("headline") or "Finish route setup before launching this Adventour."

        cost_label = None
        if known_low is not None and known_high is not None:
            cost_label = f"${known_low}-${known_high} known per person"

        quick_stats = [
            {
                "id": "known_cost",
                "label": "Known cost",
                "value": cost_label or "Manual pricing",
                "status": "ready" if cost_label else "manual",
            },
            {
                "id": "booking_links",
                "label": "Booking links",
                "value": len(action_links),
                "status": "ready" if action_links else "manual",
            },
            {
                "id": "saveable_items",
                "label": "Saveable pieces",
                "value": len(saveable_items),
                "status": "ready" if saveable_items else "manual",
            },
            {
                "id": "event_reservations",
                "label": "Event RSVPs",
                "value": event_reservation_count,
                "status": "ready" if event_reservation_count else "optional",
            },
            {
                "id": "mobility",
                "label": "Mobility",
                "value": mobility_setup.get("label") if mobility_setup else "Manual",
                "status": "ready" if mobility_setup else "manual",
            },
        ]
        if booking_checklist:
            checklist_items = booking_checklist.get("items") or []
            quick_stats.append({
                "id": "booking_checklist",
                "label": "Checklist",
                "value": f"{booking_checklist.get('ready_count', 0)}/{len(checklist_items)} ready",
                "status": "ready" if not booking_checklist.get("blocking_count") else "action_needed",
            })
        if authenticity_packet:
            quick_stats.append({
                "id": "authenticity_packet",
                "label": "Local promise",
                "value": f"{authenticity_packet.get('local_feeling_count', 0)}/{authenticity_packet.get('stop_count', 0)} local",
                "status": "ready" if authenticity_packet.get("status") == "ready" else "manual",
            })
        if trip_logistics_readiness:
            quick_stats.append({
                "id": "trip_logistics",
                "label": "Trip logistics",
                "value": f"{round(_optional_float(trip_logistics_readiness.get('score')) * 100)}%",
                "status": "ready" if trip_logistics_readiness.get("status") == "ready" else "action_needed",
            })
        if trip_style_fit:
            quick_stats.append({
                "id": "trip_style_fit",
                "label": "Trip style",
                "value": f"{round(_optional_float(trip_style_fit.get('score')) * 100)}%",
                "status": "ready" if trip_style_fit.get("status") == "ready" else "action_needed",
            })
        if quote_plan.get("required_count"):
            quick_stats.append({
                "id": "travel_quotes",
                "label": "Travel quotes",
                "value": f"{quote_plan.get('ready_count', 0)}/{quote_plan.get('required_count', 0)} ready",
                "status": "ready" if quote_plan.get("status") == "ready_to_quote" else "action_needed",
            })

        required_actions = []
        for missing in missing_inputs:
            required_actions.append({
                "id": f"missing_{missing}",
                "label": f"Add {str(missing).replace('_', ' ')}",
                "detail": "Needed before Adventour can prepare reliable flight, stay, or date-specific booking steps.",
                "status": "action_needed",
            })
        for action in (booking_plan.get("next_best_actions") or [])[:3]:
            required_actions.append({
                "id": f"next_{action.get('type') or action.get('label')}",
                "label": action.get("label") or "Review booking step",
                "detail": action.get("detail"),
                "status": "action_needed",
            })

        save_prompts = [
            {
                "id": item.get("component_type") or item.get("phase") or item.get("label"),
                "label": item.get("label") or "Save booking details",
                "detail": item.get("action") or item.get("detail"),
                "reservation_type": item.get("reservation_type"),
                "provider": item.get("provider"),
                "source_url": item.get("source_url"),
            }
            for item in saveable_items[:4]
        ]
        event_prompts = self._trip_packet_event_reservation_prompts(local_events)
        if event_prompts:
            save_prompt_ids = {item.get("id") for item in save_prompts}
            save_prompts.extend([
                item
                for item in event_prompts
                if item.get("id") not in save_prompt_ids
            ])

        event_booking_links = [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "provider_label": item.get("provider"),
                "url": item.get("reservation_url") or item.get("source_url"),
                "stores_reservation": True,
                "reservation_type": "event",
            }
            for item in event_prompts
            if item.get("reservation_url") or item.get("source_url")
        ]
        booking_links = [
            {
                "id": link.get("id"),
                "label": link.get("label"),
                "provider_label": link.get("provider_label"),
                "url": link.get("url"),
                "stores_reservation": bool(link.get("stores_reservation")),
                "reservation_type": link.get("reservation_type"),
            }
            for link in action_links
        ]
        if event_booking_links:
            booking_link_ids = {item.get("id") for item in booking_links}
            prioritized_links = []
            prioritized_links.extend(booking_links[:2])
            prioritized_links.extend([
                item
                for item in event_booking_links
                if item.get("id") not in booking_link_ids
            ][:2])
            prioritized_links.extend(booking_links[2:])
            booking_links = prioritized_links
        event_packet = self._trip_packet_event_packet(local_events)
        if event_packet:
            quick_stats.append({
                "id": "event_packet",
                "label": "Event anchor",
                "value": event_packet.get("short_label"),
                "status": "ready" if event_packet.get("status") == "ready" else "manual",
            })
        booking_command_center = self._trip_packet_booking_command_center(
            status=status,
            headline=headline,
            trip_logistics_readiness=trip_logistics_readiness,
            required_actions=required_actions,
            booking_links=booking_links,
            save_prompts=save_prompts,
            mobility_setup=mobility_setup,
            booking_checklist=booking_checklist,
            booking_plan=booking_plan,
        )

        return {
            "status": status,
            "headline": headline,
            "can_start": can_start,
            "booking_score": round(booking_score, 3),
            "currency": price_breakdown.get("currency", "USD"),
            "party_size": price_breakdown.get("party_size") or booking_plan.get("party_size"),
            "known_per_person": {
                "low": known_low,
                "high": known_high,
                "label": cost_label,
            },
            "cost_confidence": self._cost_confidence(price_breakdown, booking_plan),
            "quote_plan": quote_plan,
            "trip_logistics_readiness": trip_logistics_readiness,
            "trip_style_fit": trip_style_fit,
            "missing_inputs": missing_inputs,
            "quick_stats": quick_stats,
            "required_actions": required_actions[:5],
            "booking_links": booking_links[:4],
            "save_prompts": save_prompts[:6],
            "booking_command_center": booking_command_center,
            "mobility_setup": mobility_setup,
            "booking_checklist": booking_checklist,
            "authenticity_packet": authenticity_packet,
            "event_packet": event_packet,
            "next_step": (
                booking_command_center.get("primary_action", {}).get("label")
                if booking_command_center.get("primary_action")
                else None
            ) or (
                booking_checklist.get("next_action")
                if booking_checklist and booking_checklist.get("blocking_count")
                else None
            ) or (
                required_actions[0]["label"]
                if required_actions
                else mobility_setup.get("next_step")
                if mobility_setup and mobility_setup.get("next_step")
                else "Open booking links and save confirmations in Adventour."
            ),
            "reservation_storage_ready": bool((booking_plan.get("reservation_storage") or {}).get("status") == "ready"),
        }

    def _trip_packet_booking_command_center(
        self,
        status,
        headline,
        trip_logistics_readiness,
        required_actions,
        booking_links,
        save_prompts,
        mobility_setup,
        booking_checklist,
        booking_plan,
    ):
        commands = []

        for action in required_actions or []:
            is_missing_input = str(action.get("id") or "").startswith("missing_")
            commands.append({
                "id": action.get("id"),
                "phase": "unlock" if is_missing_input else "prep",
                "label": action.get("label") or "Finish trip detail",
                "detail": action.get("detail"),
                "status": action.get("status") or "action_needed",
                "action": action.get("label") or action.get("detail"),
                "component_type": "missing_input" if is_missing_input else "booking_action",
                "priority": 1 if is_missing_input else 8,
                "can_open": False,
                "can_save": False,
            })

        for index, link in enumerate(booking_links or [], start=1):
            reservation_type = link.get("reservation_type")
            phase = "reserve" if reservation_type in {"event", "place"} else "book"
            commands.append({
                "id": link.get("id"),
                "phase": phase,
                "label": link.get("label") or link.get("provider_label") or "Open booking link",
                "detail": (
                    f"Open {link.get('provider_label')} and save the confirmation in Adventour."
                    if link.get("provider_label")
                    else "Open provider link, compare options, then save confirmation details."
                ),
                "status": "ready" if link.get("url") else "manual",
                "action": "Open booking link" if link.get("url") else "Review provider manually",
                "component_type": reservation_type or "booking",
                "reservation_type": reservation_type,
                "provider_label": link.get("provider_label"),
                "source_url": link.get("url"),
                "priority": 10 + index,
                "can_open": bool(link.get("url")),
                "can_save": bool(link.get("stores_reservation")),
            })

        if mobility_setup:
            commands.append({
                "id": "mobility_setup",
                "phase": "setup",
                "label": mobility_setup.get("provider_label") or mobility_setup.get("label") or "Local travel setup",
                "detail": mobility_setup.get("next_step") or (mobility_setup.get("setup_steps") or [None])[0],
                "status": "ready" if mobility_setup.get("status") == "estimated" else "manual",
                "action": mobility_setup.get("next_step") or "Review local travel setup",
                "component_type": "local_transport",
                "provider_label": mobility_setup.get("provider") or mobility_setup.get("provider_label"),
                "source_url": mobility_setup.get("source_url"),
                "priority": 30,
                "can_open": bool(mobility_setup.get("source_url")),
                "can_save": False,
            })

        for index, prompt in enumerate(save_prompts or [], start=1):
            commands.append({
                "id": prompt.get("id"),
                "phase": "save",
                "label": prompt.get("label") or "Save confirmation",
                "detail": prompt.get("detail"),
                "status": "manual",
                "action": "Save booking details in Adventour",
                "component_type": prompt.get("reservation_type") or "reservation",
                "reservation_type": prompt.get("reservation_type"),
                "provider_label": prompt.get("provider"),
                "source_url": prompt.get("reservation_url") or prompt.get("source_url"),
                "priority": 40 + index,
                "can_open": bool(prompt.get("reservation_url") or prompt.get("source_url")),
                "can_save": True,
            })

        commands = self._dedupe_trip_packet_commands(commands)
        commands.sort(key=lambda item: (item.get("priority", 99), item.get("label") or ""))
        visible_commands = commands[:6]
        primary_action = visible_commands[0] if visible_commands else None
        ready_count = sum(1 for item in visible_commands if item.get("status") == "ready")
        action_count = sum(1 for item in visible_commands if item.get("status") == "action_needed")
        missing_detail_count = sum(1 for item in visible_commands if item.get("component_type") == "missing_input")
        save_count = sum(1 for item in visible_commands if item.get("can_save"))
        open_count = sum(1 for item in visible_commands if item.get("can_open"))
        checklist_status = (booking_checklist or {}).get("status")
        logistics_status = (trip_logistics_readiness or {}).get("status")
        center_status = (
            "needs_details"
            if missing_detail_count or status in {"blocked", "needs_details"}
            else "ready"
            if logistics_status == "ready" and open_count and save_count
            else "action_needed"
            if visible_commands
            else "manual"
        )

        return {
            "status": center_status,
            "headline": self._trip_packet_command_headline(center_status, primary_action, headline),
            "primary_action": primary_action,
            "commands": visible_commands,
            "command_count": len(commands),
            "ready_count": ready_count,
            "action_needed_count": action_count,
            "open_link_count": open_count,
            "save_prompt_count": save_count,
            "checklist_status": checklist_status,
            "trip_logistics_status": logistics_status,
            "booking_handoff_status": ((booking_plan or {}).get("booking_handoff") or {}).get("status"),
        }

    def _dedupe_trip_packet_commands(self, commands):
        seen = set()
        deduped = []
        for command in commands:
            key = (
                command.get("phase"),
                command.get("component_type"),
                command.get("reservation_type"),
                command.get("source_url"),
                command.get("label"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(command)
        return deduped

    def _trip_packet_command_headline(self, status, primary_action, fallback_headline):
        if status == "needs_details":
            return "Unlock the trip packet by finishing the required details."
        if status == "ready":
            return "Book, setup, and save confirmations from one ordered list."
        if status == "action_needed" and primary_action:
            return f"Next best move: {primary_action.get('label')}."
        return fallback_headline or "Review the booking packet before sharing this Adventour."

    def _trip_packet_event_packet(self, local_events):
        if not local_events:
            return {}

        summary = local_events.get("summary") or {}
        social_readiness = summary.get("social_readiness") or {}
        event_plan = local_events.get("event_plan") or {}
        event_plan_items = event_plan.get("items") or []
        route_match_count = int(summary.get("route_match_count") or 0)
        event_count = int(summary.get("event_count") or len(local_events.get("events") or []) or 0)
        reservation_ready_count = int(
            summary.get("route_reservation_ready_count")
            or summary.get("reservation_ready_count")
            or 0
        )
        friend_signal_count = int(
            summary.get("route_friend_signal_count")
            or social_readiness.get("friend_signal_count")
            or 0
        )
        source_summary = summary.get("source_summary") or {}
        recommended_source = source_summary.get("recommended_external_source") or {}
        route_social_anchor = summary.get("route_social_anchor") or {}
        top_event_title = (
            route_social_anchor.get("title") or
            summary.get("top_route_event_title")
            or summary.get("top_event_title")
            or ((social_readiness.get("top_social_event") or {}).get("title"))
        )
        meetup_anchor = self._trip_packet_meetup_anchor(local_events, social_readiness)

        if social_readiness.get("status") == "ready":
            status = "ready"
            headline = social_readiness.get("headline") or "A local event can anchor this Adventour socially."
        elif route_match_count and reservation_ready_count:
            status = "ready"
            headline = f"{top_event_title or 'A local event'} is paired with the route and ready to reserve."
        elif event_count:
            status = "needs_confirmation"
            headline = "Local event leads found; confirm source, RSVP, or friend interest."
        else:
            status = "needs_scouting"
            headline = "No saved local event anchor yet; scout current calendars before relying on this route socially."

        top_plan_item = next(
            (item for item in event_plan_items if item.get("id") in {"top_event", "recommended_external_source", "external_scouting"}),
            event_plan_items[0] if event_plan_items else {},
        )
        next_action = (
            social_readiness.get("next_action")
            or top_plan_item.get("action")
            or recommended_source.get("reason")
            or "Scout current local calendars or add a local event."
        )

        return {
            "status": status,
            "headline": headline,
            "score": summary.get("readiness_score"),
            "social_status": social_readiness.get("status"),
            "social_score": social_readiness.get("score"),
            "event_plan_status": event_plan.get("status"),
            "short_label": (
                "Social ready"
                if status == "ready" and friend_signal_count
                else f"{route_match_count} paired"
                if route_match_count
                else f"{event_count} leads"
                if event_count
                else "Scout"
            ),
            "event_count": event_count,
            "route_match_count": route_match_count,
            "reservation_ready_count": reservation_ready_count,
            "friend_signal_count": friend_signal_count,
            "community_signal_count": social_readiness.get("community_signal_count", 0),
            "top_event_title": top_event_title,
            "top_event": social_readiness.get("top_social_event"),
            "route_social_anchor": route_social_anchor or None,
            "meetup_anchor": meetup_anchor,
            "next_action": next_action,
            "meetup_checklist": social_readiness.get("meetup_checklist") or [],
            "blocking_count": social_readiness.get("blocking_count", 0),
            "recommended_source": recommended_source,
            "event_plan_items": event_plan_items[:4],
        }

    def _trip_packet_meetup_anchor(self, local_events, social_readiness=None):
        events = (local_events or {}).get("events") or []
        if not events:
            return None

        social_readiness = social_readiness or {}
        top_social_event = social_readiness.get("top_social_event") or {}
        top_social_id = top_social_event.get("id")
        top_social_title = top_social_event.get("title")
        summary_anchor = ((local_events or {}).get("summary") or {}).get("route_social_anchor") or {}
        summary_anchor_id = summary_anchor.get("id")

        def anchor_score(event):
            social = event.get("social") or {}
            context = event.get("route_context") or {}
            friend_signal = int(social.get("friend_going_count") or 0) + int(social.get("friend_interested_count") or 0)
            community_signal = int(social.get("going_count") or 0) + int(social.get("interested_count") or 0)
            score = _optional_float(event.get("score")) * 0.32
            score += _optional_float(context.get("route_fit")) * 0.26
            score += min(1.0, friend_signal / 2) * 0.22
            score += min(1.0, community_signal / 5) * 0.08
            if event.get("reservation_url"):
                score += 0.08
            elif event.get("source_url"):
                score += 0.04
            if context:
                score += 0.08
            if (top_social_id and event.get("id") == top_social_id) or (top_social_title and event.get("title") == top_social_title):
                score += 0.08
            if summary_anchor_id and event.get("id") == summary_anchor_id:
                score += 0.12
            return score

        anchor = max(events, key=anchor_score)
        social = anchor.get("social") or {}
        context = anchor.get("route_context") or {}
        source = anchor.get("source") or {}
        starts_at = anchor.get("starts_at")
        if hasattr(starts_at, "isoformat"):
            starts_at = starts_at.isoformat()
        friend_signal = int(social.get("friend_going_count") or 0) + int(social.get("friend_interested_count") or 0)
        community_signal = int(social.get("going_count") or 0) + int(social.get("interested_count") or 0)
        action_url = anchor.get("reservation_url") or anchor.get("source_url")

        if friend_signal:
            reason = f"{friend_signal} friend signal{'s' if friend_signal != 1 else ''} make this the strongest meetup anchor."
        elif community_signal:
            reason = f"{community_signal} Adventourer signal{'s' if community_signal != 1 else ''} make this worth watching."
        elif context:
            reason = f"Best event fit for {context.get('fit_label') or 'this route'}."
        elif action_url:
            reason = "Best actionable local event lead for this Adventour."
        else:
            reason = "Best local event lead to validate before this route becomes social."

        if anchor.get("reservation_url"):
            next_action = "Open the RSVP or ticket page, then save the confirmation in Adventour."
        elif anchor.get("source_url"):
            next_action = "Open the event source, confirm it is current, then save it if your group wants to go."
        elif friend_signal or community_signal:
            next_action = "Coordinate who wants to go before making this the meetup anchor."
        else:
            next_action = "Mark Interested or invite friends to test whether this should anchor the route."

        return {
            "id": anchor.get("id"),
            "title": anchor.get("title"),
            "category": anchor.get("category"),
            "starts_at": starts_at,
            "source_name": anchor.get("source_name") or source.get("name") or source.get("badge"),
            "source_badge": source.get("badge"),
            "source_url": anchor.get("source_url"),
            "reservation_url": anchor.get("reservation_url"),
            "action_url": action_url,
            "reservation_ready": bool(anchor.get("reservation_url")),
            "friend_signal_count": friend_signal,
            "community_signal_count": community_signal,
            "score": round(anchor_score(anchor), 3),
            "reason": reason,
            "next_action": next_action,
            "route_context": {
                "day": context.get("day"),
                "slot_id": context.get("slot_id"),
                "slot_label": context.get("slot_label"),
                "time_window": context.get("time_window"),
                "stop_name": context.get("stop_name"),
                "fit_label": context.get("fit_label"),
                "distance_to_stop_meters": context.get("distance_to_stop_meters"),
                "route_fit": context.get("route_fit"),
            } if context else None,
        }

    def _trip_packet_event_reservation_prompts(self, local_events):
        events = (local_events or {}).get("events") or []
        route_events = [
            event
            for event in events
            if event.get("route_context") and (event.get("reservation_url") or event.get("source_url"))
        ]
        fallback_events = [
            event
            for event in events
            if not event.get("route_context") and event.get("reservation_url")
        ]
        ordered_events = route_events + fallback_events
        prompts = []
        seen = set()
        for event in ordered_events:
            event_id = event.get("id") or event.get("title") or event.get("reservation_url") or event.get("source_url")
            prompt_id = f"event_{event_id}"
            if prompt_id in seen:
                continue
            seen.add(prompt_id)
            context = event.get("route_context") or {}
            source = event.get("source") or {}
            starts_at = event.get("starts_at")
            if hasattr(starts_at, "isoformat"):
                starts_at = starts_at.isoformat()
            if event.get("reservation_url"):
                label = f"RSVP: {event.get('title') or 'Local event'}"
                detail = "Open the event RSVP, then save the confirmation in Adventour."
            else:
                label = f"Check event: {event.get('title') or 'Local event'}"
                detail = "Open the event source and confirm details before relying on it."
            route_label = context.get("fit_label")
            if route_label:
                detail = f"{detail} Paired with {route_label.lower()}."
            prompts.append({
                "id": prompt_id,
                "label": label,
                "detail": detail,
                "reservation_type": "event",
                "provider": event.get("source_name") or source.get("name") or source.get("badge"),
                "source_url": event.get("source_url"),
                "reservation_url": event.get("reservation_url"),
                "starts_at": starts_at,
                "route_context": {
                    "day": context.get("day"),
                    "slot_id": context.get("slot_id"),
                    "fit_label": context.get("fit_label"),
                    "distance_to_stop_meters": context.get("distance_to_stop_meters"),
                } if context else None,
            })
        return prompts[:4]

    def _trip_packet_mobility_setup(self, local_transport):
        if not local_transport:
            return None
        estimate = local_transport.get("estimate") or {}
        recommended_option = next(
            (option for option in local_transport.get("options") or [] if option.get("recommended")),
            None,
        )
        setup_steps = local_transport.get("setup_steps") or local_transport.get("next_steps") or []
        label = local_transport.get("label") or (recommended_option or {}).get("label") or "Local travel"
        provider = local_transport.get("setup_provider")
        provider_label = f"{provider} setup" if provider else "Local travel setup"
        return {
            "status": local_transport.get("status") or "manual",
            "mode": local_transport.get("mode"),
            "label": label,
            "provider": provider,
            "provider_label": provider_label,
            "source_url": local_transport.get("setup_source_url"),
            "can_save": True,
            "reservation_type": "local_transport",
            "draft_title": provider_label,
            "draft_provider": provider or "",
            "draft_booking_url": local_transport.get("setup_source_url"),
            "route_distance_meters": local_transport.get("route_distance_meters"),
            "estimate": {
                "currency": estimate.get("currency", "USD"),
                "per_person_low": estimate.get("per_person_low"),
                "per_person_high": estimate.get("per_person_high"),
            } if estimate else None,
            "recommended_option": {
                "id": recommended_option.get("id"),
                "label": recommended_option.get("label"),
                "why": recommended_option.get("why"),
            } if recommended_option else None,
            "setup_steps": setup_steps[:3],
            "next_step": setup_steps[0] if setup_steps else local_transport.get("action"),
            "draft_notes": "\n".join([
                step
                for step in [
                    setup_steps[0] if setup_steps else local_transport.get("action"),
                    (recommended_option or {}).get("why"),
                    f"Route distance estimate: {round(local_transport.get('route_distance_meters') or 0)} meters"
                    if local_transport.get("route_distance_meters") else None,
                ]
                if step
            ]),
        }

    def _logistics(self, route_days):
        stop_count = sum(len(day["stops"]) for day in route_days)
        return {
            "local_transport": {
                "recommendation": "Use walking, rideshare, or public transit depending on the city and weather.",
                "estimated_segments": max(0, stop_count - 1),
                "booking_status": "directions_ready_booking_provider_not_connected",
            },
            "booking_checklist": [
                "Open directions for each accepted stop from Adventour.",
                "Book timed-entry tickets or reservations for stops that require them.",
                "Add flight and stay providers before Adventour can quote or store reservation numbers.",
            ],
        }

    def _booking_plan(self, route_days, party_size, destination_label, constraints):
        if not self.travel_logistics_service:
            return {
                "status": "provider_not_connected",
                "message": "Booking logistics are not connected yet.",
            }
        return self.travel_logistics_service.build_booking_plan(
            route_days=route_days,
            party_size=party_size,
            destination_label=destination_label,
            origin_label=constraints.get("origin_label"),
            travel_dates=constraints.get("travel_dates"),
            trip_style=constraints.get("trip_style"),
            lodging_type=constraints.get("lodging_type"),
            stay_neighborhood=constraints.get("stay_neighborhood"),
            preferred_local_transport=constraints.get("preferred_local_transport"),
        )

    def _local_events_placeholder(self, destination_label):
        return {
            "status": "provider_not_connected",
            "destination": destination_label,
            "message": "Local event recommendations will use dedicated event/community providers so markets, pop-ups, and meetups do not get mixed into normal place search.",
            "planned_sources": ["Adventour community events", "official city calendars", "event providers", "local blogs with outbound links"],
        }

    def _local_events(self, user, location, radius_meters, destination_label, constraints=None, preference_tags=None, friend_user_ids=None):
        if self.local_event_service:
            return self.local_event_service.recommend_events(
                location=location,
                radius_meters=radius_meters,
                destination_label=destination_label,
                limit=4,
                date_window=(constraints or {}).get("travel_dates"),
                preference_tags=preference_tags or [],
                viewer_user_id=user.id if user else None,
                friend_user_ids=friend_user_ids or [],
            )
        return self._local_events_placeholder(destination_label)
