import importlib


def candidate(name, place_id, types, rating=4.7, ratings_total=80, price_level=2):
    return {
        "provider": "compare-test",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": 37.422, "lng": -122.084}},
        "business_status": "OPERATIONAL",
    }


class FakeItineraryService:
    def __init__(self):
        self.calls = []

    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        self.calls.append({
            "profile": profile,
            "learned_rerank": constraints.get("learned_rerank"),
            "record_impressions": constraints.get("record_impressions"),
        })
        score = {
            "phase1_balanced": 0.72,
            "authenticity_forward": 0.86,
        }.get(profile, 0.5)
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": score,
                "label": "Strong route" if score >= 0.85 else "Ready to test",
                "planned_stop_count": 4 if score >= 0.7 else 2,
                "expected_stop_count": 4,
                "warnings": [],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": score,
                                "diversity_groups": ["food_drink"],
                                "components": {
                                    "authenticity": 0.82 if profile == "authenticity_forward" else 0.68,
                                },
                                "authenticity_evidence": {
                                    "score": 0.82 if profile == "authenticity_forward" else 0.68,
                                    "hidden_gem_score": 0.7 if profile == "authenticity_forward" else 0.45,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 20,
                    "total_known_high": 50,
                },
            },
            "recommendation_quality": {
                "diagnostic": {
                    "status": "ready" if profile == "authenticity_forward" else "watch",
                    "headline": "Recommendation pipeline looks healthy for this route." if profile == "authenticity_forward" else "Swipe depth is the first thing to tune.",
                    "primary_issue": None if profile == "authenticity_forward" else {
                        "name": "candidate_depth",
                        "label": "Swipe depth",
                        "status": "warn",
                        "score": 0.52,
                        "summary": "The route had enough stops, but too few alternates for confident swaps.",
                        "next_action": "Widen range or compare scout styles to fill route alternates.",
                    },
                },
            },
        }


class DestinationCompareItineraryService:
    def __init__(self):
        self.calls = []

    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        self.calls.append({
            "destination_label": destination_label,
            "location": location,
            "radius_meters": radius_meters,
            "profile": constraints.get("scoring_profile"),
            "member_ids": member_ids,
            "party_size": party_size,
            "days": days,
        })
        strong = destination_label == "Austin, TX"
        score = 0.84 if strong else 0.79
        authenticity = 0.86 if strong else 0.48
        hidden_gem = 0.72 if strong else 0.18
        chain_risk = 0.08 if strong else 0.44
        return {
            "scoring_profile": constraints.get("scoring_profile"),
            "destination": destination_label,
            "route_readiness": {
                "score": score,
                "label": "Vacation-ready route" if strong else "Usable route",
                "planned_stop_count": 5 if strong else 3,
                "expected_stop_count": 5,
                "stop_coverage": 1.0 if strong else 0.6,
                "event_score": 0.78 if strong else 0.28,
                "event_social_score": 0.55 if strong else 0.08,
                "booking_score": 0.88 if strong else 0.42,
                "party_score": 0.82 if strong else 0.6,
                "warnings": [] if strong else ["Route needs more authentic local depth before sharing."],
                "strengths": ["Local events and booking handoff are ready."] if strong else [],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0 if strong else 1,
                "warning_count": 0 if strong else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": "Local night market" if strong else "Generic downtown stop",
                                "score": score,
                                "diversity_groups": ["local_events" if strong else "sights_landmarks"],
                                "components": {"authenticity": authenticity},
                                "authenticity_evidence": {
                                    "score": authenticity,
                                    "hidden_gem_score": hidden_gem,
                                    "chain_risk": chain_risk,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 80 if strong else 55,
                    "total_known_high": 160 if strong else 130,
                },
            },
            "booking_plan": {
                "summary": {
                    "readiness_score": 0.88 if strong else 0.42,
                    "message": "Booking handoff is ready." if strong else "Booking details need more setup.",
                },
            },
            "local_events": {
                "status": "ready" if strong else "manual",
                "summary": {
                    "event_count": 2 if strong else 0,
                    "route_match_count": 1 if strong else 0,
                    "route_actionable_event_count": 1 if strong else 0,
                    "route_reservation_ready_count": 1 if strong else 0,
                    "route_social_anchor_count": 1 if strong else 0,
                },
            },
        }


class InactiveLearnedItineraryService(FakeItineraryService):
    learned_reason = "no_model"
    training_data_health = None

    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        result = super().recommend_itinerary(
            user,
            location,
            radius_meters,
            member_ids,
            constraints,
            party_size,
            days,
            destination_label,
        )
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


class ThinDataLearnedItineraryService(InactiveLearnedItineraryService):
    learned_reason = "training_data_needs_data"
    training_data_health = {
        "status": "needs_data",
        "summary": "Training data is too thin to trust beyond a smoke test.",
        "counts": {"labeled": 6, "requests": 3, "event_friend_signal": 1},
    }


class TieBreakItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        event_score = 0.92 if profile == "event_ready" else 0.58
        warnings = [] if profile == "event_ready" else ["Local events found, but they may need manual source or reservation research."]
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.8,
                "label": "Ready to test",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": event_score,
                "booking_score": 0.9,
                "party_score": 0.85,
                "warnings": warnings,
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": len(warnings),
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.8,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.74},
                                "authenticity_evidence": {
                                    "score": 0.74,
                                    "hidden_gem_score": 0.52,
                                    "chain_risk": 0.16,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 35,
                    "total_known_high": 75,
                },
            },
        }


class SocialEventTieBreakItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        social_ready = profile == "social_event_ready"
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.8,
                "label": "Ready to test",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.78,
                "event_social_score": 0.64 if social_ready else 0.16,
                "event_summary": {
                    "route_social_anchor_count": 1 if social_ready else 0,
                    "route_friend_signal_count": 1 if social_ready else 0,
                    "top_route_social_event_title": "Riverside Night Market" if social_ready else None,
                },
                "booking_score": 0.8,
                "party_score": 0.82,
                "warnings": [] if social_ready else ["Local events are paired, but they need social signal before meetup testing."],
                "strengths": ["Friend-backed local events are paired with this route."] if social_ready else ["Local events are available near this Adventour."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if social_ready else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.8,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.68},
                                "authenticity_evidence": {
                                    "score": 0.68,
                                    "hidden_gem_score": 0.45,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 35,
                    "total_known_high": 75,
                },
            },
        }


class EventActionabilityTieBreakItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        actionable = profile == "event_actionable_route"
        event_summary = {
            "event_count": 1,
            "route_match_count": 1,
            "route_actionable_event_count": 1 if actionable else 0,
            "route_reservation_ready_count": 1 if actionable else 0,
            "route_social_anchor_count": 1 if actionable else 0,
            "route_friend_signal_count": 1 if actionable else 0,
            "route_social_anchor": {
                "title": "Riverside Night Market",
                "score": 0.88 if actionable else 0.0,
                "reservation_ready": actionable,
                "action_url": "https://events.example.com/riverside/rsvp" if actionable else None,
            } if actionable else None,
            "top_route_event_title": "Riverside Night Market",
            "top_route_social_event_title": "Riverside Night Market" if actionable else None,
        }
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.79 if actionable else 0.81,
                "label": "Actionable event route" if actionable else "Higher raw event route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.78,
                "event_social_score": 0.50 if actionable else 0.10,
                "event_summary": event_summary,
                "booking_score": 0.8,
                "party_score": 0.82,
                "warnings": [] if actionable else ["Local events found, but they may need manual source or reservation research."],
                "strengths": ["Reservation-ready local events are paired with this route."] if actionable else ["Local events are available near this Adventour."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if actionable else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.79 if actionable else 0.81,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.68},
                                "authenticity_evidence": {
                                    "score": 0.68,
                                    "hidden_gem_score": 0.45,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 35,
                    "total_known_high": 75,
                },
            },
        }


class LaunchChecklistItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        can_start = profile == "lower_score_ready"
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.72 if can_start else 0.91,
                "label": "Ready to test" if can_start else "Strong route",
                "planned_stop_count": 3 if can_start else 4,
                "expected_stop_count": 4,
                "stop_coverage": 0.75 if can_start else 1.0,
                "warnings": [] if can_start else ["Route needs one launch-blocking fix."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": can_start,
                "headline": "Ready to launch." if can_start else "Fix route before launch.",
                "blocking_count": 0 if can_start else 1,
                "action_count": 0 if can_start else 1,
                "warning_count": 0,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.72 if can_start else 0.91,
                                "diversity_groups": ["food_drink"],
                                "components": {"authenticity": 0.7},
                                "authenticity_evidence": {
                                    "score": 0.7,
                                    "hidden_gem_score": 0.5,
                                    "chain_risk": 0.18,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 25,
                    "total_known_high": 55,
                },
            },
        }


class AuthenticityTieBreakItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        local_forward = profile == "local_forward"
        authenticity = 0.86 if local_forward else 0.54
        hidden_gem = 0.72 if local_forward else 0.2
        chain_risk = 0.08 if local_forward else 0.42
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.82,
                "label": "Ready to test",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.65,
                "booking_score": 0.75,
                "party_score": 0.72,
                "warnings": [] if local_forward else ["This route leans generic."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if local_forward else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.82,
                                "diversity_groups": ["shops_markets"],
                                "components": {"authenticity": authenticity},
                                "authenticity_evidence": {
                                    "score": authenticity,
                                    "hidden_gem_score": hidden_gem,
                                    "chain_risk": chain_risk,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 30,
                    "total_known_high": 70,
                },
            },
        }


class GroupFitTieBreakItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        balanced = profile == "balanced_group"
        members = [
            {"user_id": 1, "display_name": "Wanyea", "average_fit": 0.76 if balanced else 0.92, "matched_stops": 4},
            {"user_id": 2, "display_name": "Maya", "average_fit": 0.74 if balanced else 0.38, "matched_stops": 4},
        ]
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.82,
                "label": "Ready to test",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.65,
                "booking_score": 0.75,
                "party_score": 0.98 if balanced else 0.46,
                "warnings": [] if balanced else ["Friend fit is uneven; try group-friendly scout style or swap a stop."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if balanced else 1,
            },
            "days": [
                {
                    "party_fit": {
                        "members": members,
                        "lowest_average_fit": min(member["average_fit"] for member in members),
                        "highest_average_fit": max(member["average_fit"] for member in members),
                        "fairness_score": 0.98 if balanced else 0.46,
                        "message": "Strongly balanced for this travel party." if balanced else "One traveler may love this route more than the others; use swaps to rebalance it.",
                    },
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.82,
                                "diversity_groups": ["food_drink"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.48,
                                    "chain_risk": 0.14,
                                },
                            },
                        },
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 40,
                    "total_known_high": 90,
                },
            },
        }


class TripReadinessItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        easy_party_route = profile == "party_low_friction"
        members = [
            {"user_id": 1, "display_name": "Wanyea", "average_fit": 0.82 if easy_party_route else 0.91, "matched_stops": 4},
            {"user_id": 2, "display_name": "Maya", "average_fit": 0.78 if easy_party_route else 0.42, "matched_stops": 4},
        ]
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.82 if easy_party_route else 0.91,
                "label": "Ready to test" if easy_party_route else "Strong route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.72 if easy_party_route else 0.9,
                "party_score": 0.92 if easy_party_route else 0.48,
                "warnings": [] if easy_party_route else ["This route has several pieces to book manually."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if easy_party_route else 1,
            },
            "days": [
                {
                    "party_fit": {
                        "members": members,
                        "lowest_average_fit": min(member["average_fit"] for member in members),
                        "highest_average_fit": max(member["average_fit"] for member in members),
                        "fairness_score": 0.94 if easy_party_route else 0.5,
                        "message": "Strongly balanced for this travel party." if easy_party_route else "One traveler may need better matches.",
                    },
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.82 if easy_party_route else 0.91,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.55,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "low" if easy_party_route else "high",
                    "score": 0.12 if easy_party_route else 0.82,
                    "action_needed_count": 0 if easy_party_route else 3,
                    "manual_count": 0 if easy_party_route else 2,
                    "setup_count": 1 if easy_party_route else 3,
                    "provider_action_count": 1 if easy_party_route else 5,
                },
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 45 if easy_party_route else 35,
                    "total_known_high": 95 if easy_party_route else 85,
                },
            },
        }


class SwapSafetyItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        safe_swaps = profile == "swap_flexible_route"
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.82 if safe_swaps else 0.88,
                "label": "Flexible route" if safe_swaps else "Higher raw score route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.76,
                "party_score": 0.78,
                "warnings": [] if safe_swaps else ["Some swaps add friction or cost."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if safe_swaps else 1,
            },
            "swap_guide": {
                "stop_count": 4,
                "swappable_stop_count": 4 if safe_swaps else 2,
                "swap_coverage": 1.0 if safe_swaps else 0.5,
                "alternative_count": 6,
                "recommended_swap_count": 3 if safe_swaps else 0,
                "low_friction_count": 3 if safe_swaps else 1,
                "route_risk_count": 0 if safe_swaps else 3,
                "cost_caution_count": 0 if safe_swaps else 2,
                "cost_saving_count": 2 if safe_swaps else 0,
                "best_swaps": [
                    {
                        "from_name": "Current stop",
                        "to_name": "Neighborhood alternative",
                        "confidence": 0.84,
                        "cost_impact_status": "saves" if safe_swaps else "pricier",
                    }
                ],
            },
            "days": [
                {
                    "stops": [
                        {
                            "alternatives": [{"name": f"{profile} swap"}] if safe_swaps else [],
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.82 if safe_swaps else 0.88,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.55,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "medium",
                    "score": 0.36,
                    "action_needed_count": 1,
                    "manual_count": 1,
                    "setup_count": 1,
                    "provider_action_count": 1,
                },
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 42 if safe_swaps else 38,
                    "total_known_high": 90 if safe_swaps else 86,
                },
            },
        }


class FriendCoverageItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        friend_ready = profile == "friend_covered"
        owner_fit = 0.8 if friend_ready else 0.94
        friend_fit = 0.78 if friend_ready else 0.42
        return {
            "scoring_profile": profile,
            "member_count": 2,
            "route_readiness": {
                "score": 0.84 if friend_ready else 0.9,
                "label": "Ready to test" if friend_ready else "Strong route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.7,
                "booking_score": 0.76,
                "party_score": 0.88 if friend_ready else 0.5,
                "warnings": [] if friend_ready else ["One friend may need stronger route matches."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if friend_ready else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "alternatives": [{"name": f"{profile} swap"}],
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.84 if friend_ready else 0.9,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.56,
                                    "chain_risk": 0.12,
                                },
                                "member_fit": [
                                    {"user_id": 1, "display_name": "Wanyea", "fit": owner_fit},
                                    {"user_id": 2, "display_name": "Maya", "fit": friend_fit},
                                ],
                                "ranking": {
                                    "party_coverage_rescue": friend_ready,
                                    "rescued_member": "Maya" if friend_ready else None,
                                    "rescued_member_fit": friend_fit if friend_ready else None,
                                    "replaced_pick": "raw_score_friend_gap first stop" if friend_ready else None,
                                },
                            },
                            "party_fit_summary": {
                                "coverage_rescue": {
                                    "member": "Maya",
                                    "fit": friend_fit,
                                    "replaced_pick": "raw_score_friend_gap first stop",
                                } if friend_ready else None,
                            },
                        }
                    ],
                },
            ],
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 38,
                    "total_known_high": 86,
                },
            },
        }


class BookingActionCoverageItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        bookable = profile == "bookable_route"
        booking_links = [
            {"label": "Reserve dinner", "url": "https://example.com/dinner"},
            {"label": "Book stay", "url": "https://example.com/stay"},
            {"label": "Transit pass", "url": "https://example.com/transit"},
        ] if bookable else []
        booking_timeline = {
            "items": [
                {"label": "Dinner reservation", "stores_reservation": True},
                {"label": "Hotel confirmation", "stores_reservation": True},
            ] if bookable else [
                {"label": "Research reservations", "stores_reservation": False},
            ],
        }
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.84 if bookable else 0.91,
                "label": "Ready to book" if bookable else "Strong route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.72,
                "booking_score": 0.76 if bookable else 0.9,
                "booking_action_link_count": len(booking_links),
                "booking_saveable_item_count": 2 if bookable else 0,
                "party_score": 0.82,
                "warnings": [] if bookable else ["Booking options need manual follow-up."],
                "strengths": ["Booking links are ready."] if bookable else ["Route shape is strong."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if bookable else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.84 if bookable else 0.91,
                                "diversity_groups": ["food_drink"],
                                "components": {"authenticity": 0.74},
                                "authenticity_evidence": {
                                    "score": 0.74,
                                    "hidden_gem_score": 0.58,
                                    "chain_risk": 0.1,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "booking_action_links": booking_links,
                "booking_timeline": booking_timeline,
                "planning_burden": {
                    "level": "low",
                    "score": 0.1,
                    "action_needed_count": 0,
                    "manual_count": 0,
                    "setup_count": 1,
                    "provider_action_count": 1,
                },
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 50,
                    "total_known_high": 120,
                },
            },
        }


class SavedBookingCoverageItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        saved = profile == "saved_booking_route"
        booking_links = [
            {"label": "Reserve dinner", "url": "https://example.com/dinner"},
            {"label": "Book stay", "url": "https://example.com/stay"},
        ]
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.87 if saved else 0.88,
                "label": "Ready with saved details" if saved else "Ready with links",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.72,
                "booking_score": 0.78 if saved else 0.9,
                "booking_action_link_count": 2,
                "booking_saveable_item_count": 2,
                "party_score": 0.82,
                "warnings": [],
                "strengths": ["Booking details are ready."] if saved else ["Booking links are ready."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.87 if saved else 0.88,
                                "diversity_groups": ["food_drink"],
                                "components": {"authenticity": 0.74},
                                "authenticity_evidence": {
                                    "score": 0.74,
                                    "hidden_gem_score": 0.58,
                                    "chain_risk": 0.1,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "booking_action_links": booking_links,
                "booking_timeline": {
                    "items": [
                        {"label": "Dinner reservation", "stores_reservation": True},
                        {"label": "Hotel confirmation", "stores_reservation": True},
                    ],
                },
                "planning_burden": {
                    "level": "low",
                    "score": 0.1,
                    "action_needed_count": 0,
                    "manual_count": 0,
                    "setup_count": 1,
                    "provider_action_count": 1,
                },
            },
            "trip_packet": {
                "reservation_coverage": {
                    "required_count": 2,
                    "saved_count": 2 if saved else 0,
                    "confirmed_count": 2 if saved else 0,
                    "missing_labels": [] if saved else ["Dinner", "Stay"],
                },
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 50,
                    "total_known_high": 120,
                },
            },
        }


class BookingHandoffItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        handoff_ready = profile == "handoff_ready_route"
        commands = [
            {
                "phase": "book",
                "label": "Book stay",
                "status": "ready",
                "source_url": "https://example.com/stay",
                "can_open": True,
                "can_save": True,
            },
            {
                "phase": "book",
                "label": "Book flight",
                "status": "ready",
                "source_url": "https://example.com/flight",
                "can_open": True,
                "can_save": True,
            },
            {
                "phase": "setup",
                "label": "Transit pass",
                "status": "ready",
                "source_url": "https://example.com/transit",
                "can_open": True,
                "can_save": False,
            },
        ] if handoff_ready else [
            {
                "phase": "prep",
                "label": "Research booking steps",
                "status": "action_needed",
                "can_open": False,
                "can_save": False,
            },
        ]
        return {
            "scoring_profile": profile,
            "route_readiness": {
                "score": 0.84 if handoff_ready else 0.89,
                "label": "Ready to hand off" if handoff_ready else "Strong route shell",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.72,
                "booking_score": 0.8 if handoff_ready else 0.86,
                "booking_action_link_count": 3 if handoff_ready else 0,
                "booking_saveable_item_count": 2 if handoff_ready else 0,
                "party_score": 0.82,
                "warnings": [] if handoff_ready else ["Booking handoff needs manual work."],
                "strengths": ["Booking handoff is ready."] if handoff_ready else ["Route shape is strong."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if handoff_ready else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.84 if handoff_ready else 0.89,
                                "diversity_groups": ["food_drink"],
                                "components": {"authenticity": 0.74},
                                "authenticity_evidence": {
                                    "score": 0.74,
                                    "hidden_gem_score": 0.58,
                                    "chain_risk": 0.1,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "booking_action_links": [
                    {"label": "Book stay", "url": "https://example.com/stay"},
                    {"label": "Book flight", "url": "https://example.com/flight"},
                    {"label": "Transit pass", "url": "https://example.com/transit"},
                ] if handoff_ready else [],
                "booking_timeline": {
                    "items": [
                        {"label": "Stay confirmation", "stores_reservation": True},
                        {"label": "Flight confirmation", "stores_reservation": True},
                    ] if handoff_ready else [
                        {"label": "Research reservations", "stores_reservation": False},
                    ],
                },
                "planning_burden": {
                    "level": "low" if handoff_ready else "high",
                    "score": 0.08 if handoff_ready else 0.72,
                    "action_needed_count": 0 if handoff_ready else 2,
                    "manual_count": 0 if handoff_ready else 3,
                    "setup_count": 1 if handoff_ready else 0,
                    "provider_action_count": 3 if handoff_ready else 0,
                },
            },
            "trip_logistics_readiness": {
                "status": "ready" if handoff_ready else "manual",
                "score": 0.86 if handoff_ready else 0.38,
                "missing_input_count": 0 if handoff_ready else 2,
                "blocking_count": 0 if handoff_ready else 1,
                "provider_link_count": 3 if handoff_ready else 0,
                "quote_ready_count": 2 if handoff_ready else 0,
                "save_ready_count": 2 if handoff_ready else 0,
                "setup_ready_count": 1 if handoff_ready else 0,
                "reservation_storage_ready": handoff_ready,
            },
            "trip_packet": {
                "booking_command_center": {
                    "status": "ready" if handoff_ready else "action_needed",
                    "primary_action": commands[0],
                    "commands": commands,
                    "command_count": len(commands),
                    "ready_count": 3 if handoff_ready else 0,
                    "action_needed_count": 0 if handoff_ready else 1,
                    "open_link_count": 3 if handoff_ready else 0,
                    "save_prompt_count": 2 if handoff_ready else 0,
                },
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 50,
                    "total_known_high": 120,
                },
            },
        }


class RouteModelConfidenceItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        trusted = profile == "trusted_model_route"
        route_model_confidence = {
            "score": 0.92 if trusted else 0.32,
            "status": "strong" if trusted else "thin",
            "learning_status": "learned_signal" if trusted else "cold_start",
            "stop_coverage": 1.0 if trusted else 0.5,
            "authenticity_score": 0.78 if trusted else 0.46,
            "party_score": 0.82 if trusted else 0.52,
            "booking_score": 0.72 if trusted else 0.44,
            "swap_coverage": 0.75 if trusted else 0.25,
            "basis": ["profile", "route_coverage", "local_signal"] if trusted else ["route_coverage"],
            "warnings": [] if trusted else ["Not enough learned preference signal for this route."],
            "learned_rerank": {
                "guard_status": "active" if trusted else "constrained",
            },
        }
        return {
            "scoring_profile": profile,
            "route_model_confidence": route_model_confidence,
            "route_readiness": {
                "score": 0.80 if trusted else 0.83,
                "label": "Trustworthy model route" if trusted else "Higher raw score route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.74,
                "party_score": 0.78,
                "warnings": [] if trusted else ["Model confidence is thin for this route."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if trusted else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.80 if trusted else 0.83,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.7},
                                "authenticity_evidence": {
                                    "score": 0.7,
                                    "hidden_gem_score": 0.54,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "medium",
                    "score": 0.38,
                    "action_needed_count": 1,
                    "manual_count": 1,
                    "setup_count": 1,
                    "provider_action_count": 2,
                },
            },
            "trip_packet": {
                "route_model_confidence": route_model_confidence,
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 40,
                    "total_known_high": 95,
                },
            },
        }


class LogisticsReadinessItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        logistics_ready = profile == "logistics_ready_route"
        logistics_readiness = {
            "status": "ready" if logistics_ready else "needs_details",
            "headline": "Trip logistics are ready enough to share and book." if logistics_ready else "Trip logistics need basics.",
            "score": 0.88 if logistics_ready else 0.34,
            "provider_link_count": 3 if logistics_ready else 0,
            "quote_ready_count": 2 if logistics_ready else 0,
            "save_ready_count": 3 if logistics_ready else 0,
            "setup_ready_count": 1 if logistics_ready else 0,
            "blocking_count": 0 if logistics_ready else 1,
            "missing_input_count": 0 if logistics_ready else 3,
            "local_transport_status": "estimated" if logistics_ready else "manual",
            "reservation_storage_ready": logistics_ready,
        }
        return {
            "scoring_profile": profile,
            "trip_logistics_readiness": logistics_readiness,
            "route_readiness": {
                "score": 0.80 if logistics_ready else 0.84,
                "label": "Shareable logistics route" if logistics_ready else "Higher raw route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.64,
                "party_score": 0.78,
                "warnings": [] if logistics_ready else ["Trip basics are missing."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0 if logistics_ready else 1,
                "warning_count": 0 if logistics_ready else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.80 if logistics_ready else 0.84,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.7},
                                "authenticity_evidence": {
                                    "score": 0.7,
                                    "hidden_gem_score": 0.54,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "medium",
                    "score": 0.38,
                    "action_needed_count": 1,
                    "manual_count": 1,
                    "setup_count": 1,
                    "provider_action_count": 2,
                },
            },
            "trip_packet": {
                "trip_logistics_readiness": logistics_readiness,
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 42,
                    "total_known_high": 98,
                },
            },
        }


class TravelQuoteReadinessItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        quotes_ready = profile == "quote_ready_route"
        quote_plan = {
            "status": "ready_to_quote" if quotes_ready else "needs_details",
            "headline": "Known local costs are estimated; travel quotes are ready to compare." if quotes_ready else "Add trip basics before Adventour can prepare reliable travel quotes.",
            "required_count": 2,
            "ready_count": 2 if quotes_ready else 0,
            "missing_inputs": [] if quotes_ready else ["origin", "start_date"],
            "items": [
                {
                    "type": "flight",
                    "label": "Flight or train",
                    "quote_required": True,
                    "quote_status": "ready_to_quote" if quotes_ready else "needs_details",
                    "primary_url": "https://www.google.com/travel/flights?q=Orlando+to+Austin" if quotes_ready else None,
                },
                {
                    "type": "stay",
                    "label": "Stay",
                    "quote_required": True,
                    "quote_status": "ready_to_quote" if quotes_ready else "needs_details",
                    "primary_url": "https://www.google.com/travel/hotels?q=Austin" if quotes_ready else None,
                },
            ],
        }
        logistics_readiness = {
            "status": "ready",
            "headline": "Trip logistics are ready enough to share and book.",
            "score": 0.82,
            "provider_link_count": 2 if quotes_ready else 0,
            "quote_ready_count": 2 if quotes_ready else 0,
            "save_ready_count": 2,
            "setup_ready_count": 1,
            "blocking_count": 0,
            "missing_input_count": 0,
            "local_transport_status": "estimated",
            "reservation_storage_ready": True,
        }
        return {
            "scoring_profile": profile,
            "trip_logistics_readiness": logistics_readiness,
            "route_readiness": {
                "score": 0.82 if quotes_ready else 0.85,
                "label": "Quote ready route" if quotes_ready else "Higher raw route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.72,
                "party_score": 0.78,
                "warnings": [] if quotes_ready else ["Travel quote details are missing."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if quotes_ready else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.82 if quotes_ready else 0.85,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.54,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "medium",
                    "score": 0.35,
                    "action_needed_count": 1 if not quotes_ready else 0,
                    "manual_count": 1 if not quotes_ready else 0,
                    "setup_count": 1,
                    "provider_action_count": 2,
                },
            },
            "trip_packet": {
                "trip_logistics_readiness": logistics_readiness,
                "quote_plan": quote_plan,
            },
            "price_breakdown": {
                "quote_plan": quote_plan,
                "per_person": {
                    "total_known_low": 60,
                    "total_known_high": 140,
                    "flight_low": None,
                    "flight_high": None,
                    "stay_low": None,
                    "stay_high": None,
                },
            },
        }


class TripStyleFitItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        style_fit = profile == "style_fit_weekend"
        trip_style_fit = {
            "status": "ready" if style_fit else "needs_attention",
            "score": 0.92 if style_fit else 0.32,
            "trip_style": "weekend",
            "suggested_style": "weekend" if style_fit else "day",
            "duration_fit": 0.94 if style_fit else 0.28,
            "quote_coverage": 1.0 if style_fit else 0.0,
            "event_density": 0.55 if style_fit else 0.05,
            "route_days": 2 if style_fit else 1,
            "nights": 1 if style_fit else 0,
        }
        return {
            "scoring_profile": profile,
            "trip_style": "weekend",
            "trip_style_fit": trip_style_fit,
            "route_readiness": {
                "score": 0.84 if style_fit else 0.85,
                "label": "Weekend fit" if style_fit else "Higher raw route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.64 if style_fit else 0.56,
                "booking_score": 0.72,
                "party_score": 0.78,
                "warnings": [] if style_fit else ["This route is too thin for a weekend plan."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 0 if style_fit else 1,
            },
            "days": [
                {
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.84 if style_fit else 0.85,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.54,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "booking_plan": {
                "planning_burden": {
                    "level": "medium",
                    "score": 0.32,
                    "action_needed_count": 1,
                    "manual_count": 1,
                    "setup_count": 1,
                    "provider_action_count": 2,
                },
            },
            "trip_packet": {
                "trip_style_fit": trip_style_fit,
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 75,
                    "total_known_high": 180,
                    "nights": 1 if style_fit else 0,
                },
            },
        }


class GroupSwapCoverageItineraryService:
    def recommend_itinerary(self, user, location, radius_meters, member_ids, constraints, party_size, days, destination_label):
        profile = constraints.get("scoring_profile")
        swap_ready = profile == "group_swap_ready"
        party_coverage_plan = {
            "status": "actionable" if swap_ready else "needs_options",
            "headline": "Swaps can help Maya feel more covered." if swap_ready else "Maya still needs stronger swap options.",
            "next_action": "Preview the suggested swap for Maya before sharing this route." if swap_ready else "Try a group-friendly scout style or widen the search radius.",
            "member_count": 2,
            "underserved_member_count": 1,
            "actionable_member_count": 1 if swap_ready else 0,
            "members": [
                {
                    "user_id": 1,
                    "display_name": "Owner",
                    "average_fit": 0.82,
                    "coverage_status": "covered",
                    "strong_match_count": 1,
                    "suggested_swaps": [],
                },
                {
                    "user_id": 2,
                    "display_name": "Maya",
                    "average_fit": 0.48,
                    "coverage_status": "needs_match",
                    "strong_match_count": 0,
                    "suggested_swaps": [
                        {
                            "day": 1,
                            "slot_id": "afternoon_gem",
                            "slot_label": "Afternoon gem",
                            "from_name": "Owner Favorite",
                            "to_name": "Maya Market",
                            "confidence": 0.86,
                            "low_friction_score": 0.82,
                            "replacement_fit": 0.78,
                            "fit_delta": 0.30,
                            "coverage_status": "covered_by_swap",
                            "tradeoff": "Small route tradeoff.",
                        },
                    ] if swap_ready else [],
                },
            ],
        }
        swap_guide = {
            "status": "ready" if swap_ready else "watch",
            "headline": "This route is flexible enough to customize.",
            "next_action": party_coverage_plan["next_action"],
            "stop_count": 4,
            "swappable_stop_count": 4,
            "swap_coverage": 1.0,
            "alternative_count": 6 if swap_ready else 3,
            "recommended_swap_count": 2 if swap_ready else 0,
            "low_friction_count": 3 if swap_ready else 1,
            "authenticity_upgrade_count": 1,
            "party_upgrade_count": 1 if swap_ready else 0,
            "consensus_upgrade_count": 1 if swap_ready else 0,
            "route_risk_count": 0,
            "cost_caution_count": 0,
            "cost_saving_count": 0,
            "party_coverage_plan": party_coverage_plan,
            "best_swaps": [
                {
                    "from_name": "Owner Favorite",
                    "to_name": "Maya Market",
                    "should_swap": True,
                    "confidence": 0.86,
                    "group_consensus_delta": 0.08,
                    "group_consensus_gap_delta": 0.11,
                    "target_members": [{"display_name": "Maya", "coverage_status": "covered_by_swap"}],
                },
            ] if swap_ready else [],
        }
        return {
            "scoring_profile": profile,
            "scenario_readiness": {
                "friend_readiness": {
                    "status": "needs_attention",
                    "member_count": 2,
                    "coverage_share": 0.5,
                    "average_group_fit": 0.64,
                    "underserved_count": 1,
                    "covered_member_count": 1,
                    "underserved_members": [{"user_id": 2, "display_name": "Maya", "average_fit": 0.48}],
                },
            },
            "route_readiness": {
                "score": 0.83 if swap_ready else 0.84,
                "label": "Group adjustable route" if swap_ready else "Higher raw route",
                "planned_stop_count": 4,
                "expected_stop_count": 4,
                "stop_coverage": 1.0,
                "event_score": 0.62,
                "booking_score": 0.72,
                "party_score": 0.64,
                "warnings": ["One friend may need stronger route matches."],
                "strengths": ["Most route slots are filled."],
            },
            "launch_checklist": {
                "can_start": True,
                "headline": "Ready to launch.",
                "blocking_count": 0,
                "action_count": 0,
                "warning_count": 1,
            },
            "swap_guide": swap_guide,
            "days": [
                {
                    "party_fit": {
                        "members": [
                            {"user_id": 1, "display_name": "Owner", "average_fit": 0.82, "coverage_status": "covered"},
                            {"user_id": 2, "display_name": "Maya", "average_fit": 0.48, "coverage_status": "needs_match"},
                        ],
                        "fairness_score": 0.66,
                        "coverage_share": 0.5,
                        "underserved_count": 1,
                    },
                    "stops": [
                        {
                            "recommendation": {
                                "name": f"{profile} first stop",
                                "score": 0.83 if swap_ready else 0.84,
                                "diversity_groups": ["arts_culture"],
                                "components": {"authenticity": 0.72},
                                "authenticity_evidence": {
                                    "score": 0.72,
                                    "hidden_gem_score": 0.54,
                                    "chain_risk": 0.12,
                                },
                            },
                        },
                    ],
                },
            ],
            "trip_packet": {
                "swap_guide": swap_guide,
            },
            "price_breakdown": {
                "per_person": {
                    "total_known_low": 70,
                    "total_known_high": 150,
                },
            },
        }


class CountingProviderRegistry:
    def __init__(self):
        self.calls = 0

    def search(self, tags, location, radius_meters=3200, constraints=None):
        self.calls += 1
        return [
            candidate("Corner Coffee", "coffee-1", ["cafe", "coffee_shop"], price_level=1),
            candidate("City Art Walk", "art-1", ["art_gallery"], price_level=1),
            candidate("Local Taco Stand", "taco-1", ["restaurant", "mexican_restaurant"], price_level=1),
            candidate("Late Night Jazz", "jazz-1", ["bar", "concert_hall"], price_level=2),
        ], []


def test_itinerary_compare_endpoint_returns_sorted_profile_summaries(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", FakeItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:compare@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["phase1_balanced", "authenticity_forward"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "authenticity_forward",
        "phase1_balanced",
    ]
    assert payload["comparisons"][0]["first_stop"]["name"] == "authenticity_forward first stop"
    assert payload["comparisons"][0]["launch_checklist"]["can_start"] is True
    assert payload["comparisons"][0]["scenario_readiness"]["mode"] == "planned_itinerary"
    assert payload["comparisons"][0]["scenario_readiness"]["beta_testable"] is False
    assert payload["comparisons"][0]["comparison_rank"]["can_start"] is True
    assert payload["comparisons"][0]["comparison_rank"]["authenticity_score"] == 0.82
    assert payload["comparisons"][0]["authenticity_summary"]["label"] == "Strong local signal"
    assert payload["comparisons"][0]["comparison_explanation"]["tradeoffs"][0]["label"] == "Launch"
    weaker = payload["comparisons"][1]
    assert weaker["pipeline_diagnostic"]["name"] == "candidate_depth"
    assert weaker["comparison_rank"]["pipeline_issue_status"] == "warn"
    assert any(tradeoff["label"] == "Pipeline" for tradeoff in weaker["comparison_explanation"]["tradeoffs"])
    assert "Widen range" in weaker["comparison_explanation"]["cautions"][0]
    assert "plan" not in payload["comparisons"][0]


def test_itinerary_compare_endpoint_can_include_adoptable_plans(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", FakeItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:compare-plans@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["phase1_balanced", "authenticity_forward"],
            "include_plans": True,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    recommended = payload["comparisons"][0]
    assert payload["recommended_profile"] == "authenticity_forward"
    assert recommended["scoring_profile"] == "authenticity_forward"
    assert recommended["plan"]["scoring_profile"] == "authenticity_forward"
    assert recommended["plan"]["scenario_readiness"]["mode"] == "planned_itinerary"
    assert recommended["plan"]["days"][0]["stops"][0]["recommendation"]["name"] == "authenticity_forward first stop"
    assert recommended["plan"]["trip_packet"]["friend_test_packet"]["status"] in {"ready", "watch", "needs_attention"}
    assert any(
        stat["id"] == "friend_test_packet"
        for stat in recommended["plan"]["trip_packet"]["quick_stats"]
    )


def test_itinerary_compare_endpoint_supports_learned_beta_variant(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    fake_service = FakeItineraryService()
    monkeypatch.setattr(server_app, "itinerary_service", fake_service)

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:compare-learned@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["learned_beta"],
            "include_plans": True,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    comparison = payload["comparisons"][0]
    assert payload["recommended_profile"] == "learned_beta"
    assert comparison["scoring_profile"] == "learned_beta"
    assert comparison["plan"]["comparison_profile"] == "learned_beta"
    assert comparison["plan"]["scoring_profile"] == "phase1_balanced"
    assert fake_service.calls[0]["profile"] == "phase1_balanced"
    assert fake_service.calls[0]["learned_rerank"] is True
    assert fake_service.calls[0]["record_impressions"] is False


def test_itinerary_compare_demotes_inactive_learned_beta(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    fake_service = InactiveLearnedItineraryService()
    monkeypatch.setattr(server_app, "itinerary_service", fake_service)

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:compare-inactive-learned@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["learned_beta", "authenticity_forward"],
            "include_plans": True,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    learned = next(item for item in payload["comparisons"] if item["scoring_profile"] == "learned_beta")
    assert learned["comparison_rank"]["learned_inactive"] is True
    assert learned["comparison_rank"]["learned_reason"] == "no_model"
    assert learned["comparison_explanation"]["tradeoffs"][2]["label"] == "Learning"
    assert "loaded model" in learned["comparison_explanation"]["cautions"][0]


def test_itinerary_compare_explains_thin_learned_training_data(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    fake_service = ThinDataLearnedItineraryService()
    monkeypatch.setattr(server_app, "itinerary_service", fake_service)

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:compare-thin-learned@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["learned_beta", "authenticity_forward"],
            "include_plans": True,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "authenticity_forward"
    learned = next(item for item in payload["comparisons"] if item["scoring_profile"] == "learned_beta")
    assert learned["comparison_rank"]["learned_inactive"] is True
    assert learned["comparison_rank"]["learned_reason"] == "training_data_needs_data"
    assert learned["comparison_rank"]["learned_training_data_status"] == "needs_data"
    assert "too thin" in learned["comparison_explanation"]["cautions"][0]


def test_itinerary_compare_endpoint_uses_readiness_tie_breakers(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", TieBreakItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:tiebreak@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["event_weak", "event_ready"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "event_ready"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == ["event_ready", "event_weak"]
    assert payload["comparisons"][0]["comparison_rank"]["event_score"] == 0.92
    assert payload["comparisons"][1]["comparison_rank"]["warning_count"] == 1


def test_itinerary_compare_endpoint_prefers_social_event_anchor(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", SocialEventTieBreakItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:social-event@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["quiet_event_route", "social_event_ready"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "social_event_ready"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "social_event_ready",
        "quiet_event_route",
    ]
    rank = payload["comparisons"][0]["comparison_rank"]
    assert rank["event_social_score"] == 0.64
    assert rank["event_friend_signal_count"] == 1
    assert rank["event_top_social_title"] == "Riverside Night Market"
    assert any(
        tradeoff["kind"] == "event_social" and tradeoff["label"] == "Social"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_actionable_event_anchor(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", EventActionabilityTieBreakItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:actionable-event@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["higher_raw_event_route", "event_actionable_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "event_actionable_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "event_actionable_route",
        "higher_raw_event_route",
    ]
    rank = payload["comparisons"][0]["comparison_rank"]
    weaker_rank = payload["comparisons"][1]["comparison_rank"]
    assert rank["route_score"] == 0.79
    assert weaker_rank["route_score"] == 0.81
    assert rank["event_actionability_score"] >= 0.8
    assert rank["event_route_match_count"] == 1
    assert rank["event_actionable_count"] == 1
    assert rank["event_reservation_ready_count"] == 1
    assert rank["event_route_anchor_title"] == "Riverside Night Market"
    assert rank["event_route_anchor_reservation_ready"] is True
    assert rank["event_route_anchor_action_url"].endswith("/rsvp")
    assert rank["trip_readiness_score"] > weaker_rank["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with an actionable local-event anchor."
    assert any(
        tradeoff["kind"] == "event_actionability" and tradeoff["label"] == "Event plan" and tradeoff["value"] == "1 RSVP"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prioritizes_launchable_routes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", LaunchChecklistItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:launchable@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["higher_score_blocked", "lower_score_ready"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "lower_score_ready"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "lower_score_ready",
        "higher_score_blocked",
    ]
    assert payload["comparisons"][0]["launch_checklist"]["can_start"] is True
    assert payload["comparisons"][1]["comparison_rank"]["blocking_count"] == 1


def test_itinerary_compare_endpoint_uses_authenticity_tie_breaker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", AuthenticityTieBreakItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:authenticity-tiebreak@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["generic_ready", "local_forward"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "local_forward"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "local_forward",
        "generic_ready",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["authenticity_score"] == 0.86
    assert payload["comparisons"][0]["comparison_rank"]["hidden_gem_count"] == 1
    assert payload["comparisons"][0]["authenticity_summary"]["chain_risk"] == 0.08
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best launchable route with strong local texture."


def test_itinerary_compare_endpoint_uses_group_fairness_tie_breaker(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", GroupFitTieBreakItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:group-tiebreak@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["uneven_group", "balanced_group"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "balanced_group"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "balanced_group",
        "uneven_group",
    ]
    assert payload["comparisons"][0]["group_fit_summary"]["fairness_score"] == 0.98
    assert payload["comparisons"][1]["group_fit_summary"]["underserved_count"] == 1
    assert payload["comparisons"][0]["group_compromise_brief"]["status"] == "balanced"
    assert payload["comparisons"][1]["group_compromise_brief"]["status"] == "needs_coverage"
    assert payload["comparisons"][1]["group_compromise_brief"]["most_compromised_member"]["display_name"] == "Maya"
    assert payload["comparisons"][0]["comparison_rank"]["group_lowest_fit"] == 0.74
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best launchable route for the whole travel party."


def test_itinerary_compare_endpoint_prefers_trip_readiness_over_raw_route_score(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", TripReadinessItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:trip-readiness@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["raw_score_high_friction", "party_low_friction"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "party_low_friction"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "party_low_friction",
        "raw_score_high_friction",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["route_score"] == 0.82
    assert payload["comparisons"][1]["comparison_rank"]["route_score"] == 0.91
    assert payload["comparisons"][0]["comparison_rank"]["trip_readiness_score"] > payload["comparisons"][1]["comparison_rank"]["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_rank"]["planning_burden_level"] == "low"
    assert payload["comparisons"][1]["comparison_rank"]["planning_action_needed_count"] == 3
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best low-friction route for the whole travel party."
    assert payload["comparisons"][0]["comparison_explanation"]["tradeoffs"][0]["label"] == "Launch"
    assert any(
        tradeoff["label"] == "Planning" and tradeoff["value"] == "Low"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_swap_safe_routes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", SwapSafetyItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:swap-safety@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["raw_score_risky_swaps", "swap_flexible_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "swap_flexible_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "swap_flexible_route",
        "raw_score_risky_swaps",
    ]
    ready_rank = payload["comparisons"][0]["comparison_rank"]
    risky_rank = payload["comparisons"][1]["comparison_rank"]
    assert ready_rank["route_score"] == 0.82
    assert risky_rank["route_score"] == 0.88
    assert ready_rank["swap_safety_score"] > risky_rank["swap_safety_score"]
    assert ready_rank["swap_low_friction_count"] == 3
    assert ready_rank["swap_cost_saving_count"] == 2
    assert risky_rank["swap_route_risk_count"] == 3
    assert risky_rank["swap_cost_caution_count"] == 2
    assert ready_rank["trip_readiness_score"] > risky_rank["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with safer swap flexibility."
    assert any(
        tradeoff["label"] == "Swap safety" and tradeoff["value"] == "3/4 easy"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )
    assert any(
        tradeoff["label"] == "Cheaper swaps" and tradeoff["value"] == "2"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_trustworthy_route_model_signal(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", RouteModelConfidenceItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:route-model-confidence@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["raw_route_thin_model", "trusted_model_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "trusted_model_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "trusted_model_route",
        "raw_route_thin_model",
    ]
    trusted_rank = payload["comparisons"][0]["comparison_rank"]
    thin_rank = payload["comparisons"][1]["comparison_rank"]
    assert trusted_rank["route_score"] == 0.8
    assert thin_rank["route_score"] == 0.83
    assert trusted_rank["route_model_confidence_score"] == 0.92
    assert trusted_rank["route_model_status"] == "strong"
    assert trusted_rank["route_model_basis_count"] == 3
    assert trusted_rank["route_model_warning_count"] == 0
    assert trusted_rank["route_model_learned_guard_status"] == "active"
    assert thin_rank["route_model_warning_count"] == 1
    assert trusted_rank["trip_readiness_score"] > thin_rank["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with a trustworthy model signal."
    assert any(
        tradeoff["label"] == "Model signal" and tradeoff["value"] == "92%"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_destination_compare_endpoint_ranks_candidate_destinations(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    fake_service = DestinationCompareItineraryService()
    monkeypatch.setattr(server_app, "itinerary_service", fake_service)

    response = server_app.app.test_client().post(
        "/api/recommendations/destinations/compare",
        headers={"Authorization": "Bearer dev:destination-compare@example.com"},
        json={
            "destinations": [
                {
                    "id": "orlando",
                    "label": "Orlando, FL",
                    "location": {"latitude": 28.5384, "longitude": -81.3789},
                    "radius_meters": 8000,
                },
                {
                    "id": "austin",
                    "label": "Austin, TX",
                    "location": {"latitude": 30.2672, "longitude": -97.7431},
                    "radius_meters": 10000,
                },
            ],
            "days": 3,
            "party_size": 2,
            "member_ids": [7],
            "scoring_profiles": ["phase1_balanced"],
            "constraints": {"trip_style": "vacation", "avoid_chains": True},
            "include_plans": True,
            "include_profile_comparisons": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_destination_label"] == "Austin, TX"
    assert payload["recommended_destination"]["id"] == "austin"
    assert payload["recommended_profile"] == "phase1_balanced"
    assert [item["destination_label"] for item in payload["comparisons"]] == [
        "Austin, TX",
        "Orlando, FL",
    ]
    assert payload["comparisons"][0]["comparison_mode"] == "destination"
    assert payload["comparisons"][0]["destination_rank"]["route_score"] == 0.84
    assert payload["comparisons"][1]["destination_rank"]["route_score"] == 0.79
    assert payload["comparisons"][0]["destination_rank"]["trip_readiness_score"] > payload["comparisons"][1]["destination_rank"]["trip_readiness_score"]
    assert payload["comparisons"][0]["plan"]["comparison_destination"]["id"] == "austin"
    assert payload["comparisons"][0]["plan"]["comparison_destination_rank"]["route_score"] == 0.84
    assert payload["comparisons"][0]["plan"]["comparison_destination_explanation"]["headline"]
    assert payload["comparisons"][0]["profile_comparisons"][0]["destination_label"] == "Austin, TX"
    assert [call["destination_label"] for call in fake_service.calls] == ["Orlando, FL", "Austin, TX"]
    assert fake_service.calls[1]["location"] == {"latitude": 30.2672, "longitude": -97.7431}
    assert fake_service.calls[1]["radius_meters"] == 10000
    assert fake_service.calls[1]["member_ids"] == [7]
    assert fake_service.calls[1]["party_size"] == 2
    assert fake_service.calls[1]["days"] == 3


def test_itinerary_compare_endpoint_prefers_shareable_trip_logistics(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", LogisticsReadinessItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:trip-logistics@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["raw_route_missing_logistics", "logistics_ready_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "logistics_ready_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "logistics_ready_route",
        "raw_route_missing_logistics",
    ]
    ready_rank = payload["comparisons"][0]["comparison_rank"]
    missing_rank = payload["comparisons"][1]["comparison_rank"]
    assert ready_rank["route_score"] == 0.8
    assert missing_rank["route_score"] == 0.84
    assert ready_rank["logistics_readiness_score"] == 0.88
    assert ready_rank["logistics_provider_link_count"] == 3
    assert ready_rank["logistics_quote_ready_count"] == 2
    assert ready_rank["logistics_save_ready_count"] == 3
    assert ready_rank["logistics_reservation_storage_ready"] is True
    assert missing_rank["logistics_missing_input_count"] == 3
    assert ready_rank["trip_readiness_score"] > missing_rank["trip_readiness_score"]
    assert any(
        tradeoff["label"] == "Trip logistics" and tradeoff["value"] == "88%"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_routes_with_travel_quotes_ready(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", TravelQuoteReadinessItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:travel-quotes@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 2,
            "scoring_profiles": ["raw_route_missing_quotes", "quote_ready_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "quote_ready_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "quote_ready_route",
        "raw_route_missing_quotes",
    ]
    ready_rank = payload["comparisons"][0]["comparison_rank"]
    missing_rank = payload["comparisons"][1]["comparison_rank"]
    assert ready_rank["route_score"] == 0.82
    assert missing_rank["route_score"] == 0.85
    assert ready_rank["travel_quote_required_count"] == 2
    assert ready_rank["travel_quote_ready_count"] == 2
    assert ready_rank["travel_quote_readiness_score"] == 1
    assert missing_rank["travel_quote_missing_input_count"] == 2
    assert ready_rank["trip_readiness_score"] > missing_rank["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with travel quotes ready to compare."
    assert any(
        tradeoff["label"] == "Travel quotes" and tradeoff["value"] == "2/2 ready"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_routes_matching_trip_style(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", TripStyleFitItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:trip-style-fit@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 2,
            "scoring_profiles": ["raw_route_day_shape", "style_fit_weekend"],
            "constraints": {"trip_style": "weekend", "avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "style_fit_weekend"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "style_fit_weekend",
        "raw_route_day_shape",
    ]
    ready_rank = payload["comparisons"][0]["comparison_rank"]
    mismatch_rank = payload["comparisons"][1]["comparison_rank"]
    assert ready_rank["route_score"] == 0.84
    assert mismatch_rank["route_score"] == 0.85
    assert ready_rank["trip_style_fit_score"] == 0.92
    assert ready_rank["trip_style_fit_status"] == "ready"
    assert ready_rank["trip_style"] == "weekend"
    assert ready_rank["trip_style_suggested"] == "weekend"
    assert ready_rank["trip_style_route_days"] == 2
    assert mismatch_rank["trip_style_fit_status"] == "needs_attention"
    assert ready_rank["trip_readiness_score"] > mismatch_rank["trip_readiness_score"]
    assert any(
        tradeoff["label"] == "Style fit" and tradeoff["value"] == "92%"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prefers_group_actionable_swap_routes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", GroupSwapCoverageItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:group-swap-compare@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["raw_group_gap", "group_swap_ready"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "group_swap_ready"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "group_swap_ready",
        "raw_group_gap",
    ]
    ready_rank = payload["comparisons"][0]["comparison_rank"]
    gap_rank = payload["comparisons"][1]["comparison_rank"]
    assert ready_rank["route_score"] == 0.83
    assert gap_rank["route_score"] == 0.84
    assert ready_rank["swap_party_actionable_member_count"] == 1
    assert ready_rank["swap_party_underserved_member_count"] == 1
    assert ready_rank["swap_party_coverage_score"] == 1
    assert ready_rank["effective_underserved_count"] == 0
    assert ready_rank["swap_consensus_upgrade_count"] == 1
    assert gap_rank["effective_underserved_count"] == 1
    assert ready_rank["trip_readiness_score"] > gap_rank["trip_readiness_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with group swaps ready for weaker friend fits."
    assert any(
        tradeoff["label"] == "Group swaps" and tradeoff["value"] == "1 ready"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prioritizes_friend_route_coverage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", FriendCoverageItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:friend-route-coverage@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["raw_score_friend_gap", "friend_covered"],
            "include_plans": True,
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "friend_covered"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "friend_covered",
        "raw_score_friend_gap",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["route_score"] == 0.84
    assert payload["comparisons"][1]["comparison_rank"]["route_score"] == 0.9
    assert payload["comparisons"][0]["comparison_rank"]["friend_coverage_share"] == 1.0
    assert payload["comparisons"][0]["comparison_rank"]["friend_testable"] is True
    assert payload["comparisons"][0]["comparison_rank"]["friend_test_status"] == "ready"
    assert payload["comparisons"][0]["comparison_rank"]["friend_test_blocker_count"] == 0
    assert payload["comparisons"][1]["comparison_rank"]["friend_underserved_count"] == 1
    assert payload["comparisons"][0]["comparison_rank"]["friend_rescue_count"] == 1
    assert payload["comparisons"][0]["comparison_rank"]["friend_rescued_members"] == ["Maya"]
    assert payload["comparisons"][0]["scenario_readiness"]["friend_readiness"]["status"] == "ready"
    assert payload["comparisons"][0]["friend_test_packet"]["friend_readiness_status"] == "ready"
    assert payload["comparisons"][0]["friend_test_packet"]["friend_testable"] is True
    assert payload["comparisons"][0]["friend_test_packet"]["coverage_share"] == 1.0
    assert payload["comparisons"][0]["plan"]["trip_packet"]["friend_test_packet"]["friend_readiness_status"] == "ready"
    assert payload["comparisons"][0]["plan"]["trip_packet"]["friend_test_packet"]["coverage_share"] == 1.0
    assert payload["comparisons"][0]["plan"]["trip_packet"]["friend_test_packet"]["compromise_brief"]["status"] == "balanced"
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route that made room for Maya."
    assert any(
        tradeoff["label"] == "Friend test" and tradeoff["value"] == "Ready"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )
    assert any(
        tradeoff["label"] == "Friend coverage" and tradeoff["value"] == "100%"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )
    assert any(
        tradeoff["label"] == "Made room" and tradeoff["value"] == "Maya"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_summary_includes_friend_test_packet_without_full_plan(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", FriendCoverageItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:friend-route-summary@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "member_ids": [2],
            "scoring_profiles": ["raw_score_friend_gap", "friend_covered"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    recommended = payload["comparisons"][0]
    assert recommended["scoring_profile"] == "friend_covered"
    assert "plan" not in recommended
    assert recommended["friend_test_packet"]["friend_readiness_status"] == "ready"
    assert recommended["friend_test_packet"]["friend_testable"] is True
    assert recommended["friend_test_packet"]["compromise_brief"]["status"] == "balanced"
    assert recommended["comparison_rank"]["friend_testable"] is True
    assert recommended["comparison_rank"]["friend_test_status"] == "ready"
    assert any(
        tradeoff["kind"] == "friend_test" and tradeoff["value"] == "Ready"
        for tradeoff in recommended["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prioritizes_booking_action_coverage(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", BookingActionCoverageItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:booking-action-coverage@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["raw_score_no_links", "bookable_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "bookable_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "bookable_route",
        "raw_score_no_links",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["route_score"] == 0.84
    assert payload["comparisons"][1]["comparison_rank"]["route_score"] == 0.91
    assert payload["comparisons"][0]["comparison_rank"]["booking_action_link_count"] == 3
    assert payload["comparisons"][0]["comparison_rank"]["booking_saveable_item_count"] == 2
    assert payload["comparisons"][0]["comparison_rank"]["booking_actionable_score"] > payload["comparisons"][1]["comparison_rank"]["booking_actionable_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route to book and launch with less planning."
    assert any(
        tradeoff["label"] == "Booking links" and tradeoff["value"] == "3 ready"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prioritizes_saved_booking_details(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", SavedBookingCoverageItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:saved-booking-coverage@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["linked_booking_route", "saved_booking_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "saved_booking_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "saved_booking_route",
        "linked_booking_route",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["route_score"] == 0.87
    assert payload["comparisons"][1]["comparison_rank"]["route_score"] == 0.88
    assert payload["comparisons"][0]["comparison_rank"]["booking_saved_coverage"] == 1.0
    assert payload["comparisons"][1]["comparison_rank"]["booking_saved_coverage"] == 0
    assert payload["comparisons"][0]["comparison_rank"]["booking_actionable_score"] > payload["comparisons"][1]["comparison_rank"]["booking_actionable_score"]
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with booking details already saved."
    assert any(
        tradeoff["label"] == "Saved details" and tradeoff["value"] == "2/2 saved"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_prioritizes_booking_handoff_readiness(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    monkeypatch.setattr(server_app, "itinerary_service", BookingHandoffItineraryService())

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:booking-handoff@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["raw_score_manual_handoff", "handoff_ready_route"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["recommended_profile"] == "handoff_ready_route"
    assert [item["scoring_profile"] for item in payload["comparisons"]] == [
        "handoff_ready_route",
        "raw_score_manual_handoff",
    ]
    assert payload["comparisons"][0]["comparison_rank"]["route_score"] == 0.84
    assert payload["comparisons"][1]["comparison_rank"]["route_score"] == 0.89
    assert payload["comparisons"][0]["comparison_rank"]["booking_handoff_score"] > 0.72
    assert payload["comparisons"][0]["comparison_rank"]["booking_command_open_link_count"] == 3
    assert payload["comparisons"][0]["comparison_rank"]["booking_command_save_prompt_count"] == 2
    assert payload["comparisons"][0]["comparison_explanation"]["headline"] == "Best route with booking handoff ready."
    assert any(
        tradeoff["label"] == "Trip handoff" and tradeoff["value"] == "3 open / 2 save"
        for tradeoff in payload["comparisons"][0]["comparison_explanation"]["tradeoffs"]
    )


def test_itinerary_compare_endpoint_reuses_provider_candidates(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ADVENTOUR_DEV_AUTH", "true")

    server_app = importlib.import_module("app")
    counting_registry = CountingProviderRegistry()
    service = server_app.ItineraryRecommendationService(
        server_app.RecommendationService(counting_registry),
        local_event_service=None,
        travel_logistics_service=server_app.TravelLogisticsService(),
    )
    monkeypatch.setattr(server_app, "itinerary_service", service)

    response = server_app.app.test_client().post(
        "/api/recommendations/itinerary/compare",
        headers={"Authorization": "Bearer dev:cached-compare@example.com"},
        json={
            "location": {"latitude": 37.422, "longitude": -122.084},
            "radius_meters": 3200,
            "days": 1,
            "scoring_profiles": ["phase1_balanced", "authenticity_forward", "group_friendly"],
            "constraints": {"avoid_chains": True},
        },
    )

    assert response.status_code == 200
    assert counting_registry.calls == 1
    payload = response.get_json()
    assert len(payload["comparisons"]) == 3
    assert payload["provider_usage"]["search_count"] == 3
    assert payload["provider_usage"]["provider_fetch_count"] == 1
    assert payload["provider_usage"]["cache_hit_count"] == 2
    assert payload["provider_usage"]["saved_fetch_count"] == 2

    with server_app.app.app_context():
        user = server_app.User.query.filter_by(email="cached-compare@example.com").first()
        assert user is not None
        assert server_app.UserPlaceEvent.query.filter_by(
            user_id=user.id,
            event_type="impression",
        ).count() == 0
