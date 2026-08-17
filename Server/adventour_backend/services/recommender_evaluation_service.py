import json
import math
from collections import defaultdict

from adventour_backend.services.recommender_model_service import LearningToRankBaselineService


DEFAULT_K_VALUES = (1, 3, 5)
MIN_PROMOTION_REQUESTS = 20

GUARDRAIL_THRESHOLDS = {
    "local_quality_min": {"warn": 0.5, "fail": 0.4},
    "authenticity_min": {"warn": 0.55, "fail": 0.45},
    "hidden_gem_min": {"warn": 0.2, "fail": 0.1},
    "chain_probability_max": {"warn": 0.45, "fail": 0.65},
    "group_min_fit_min": {"warn": 0.5, "fail": 0.4},
    "group_consensus_fit_min": {"warn": 0.68, "fail": 0.55},
    "group_fairness_penalty_max": {"warn": 0.22, "fail": 0.35},
    "group_consensus_gap_max": {"warn": 0.06, "fail": 0.12},
    "group_underserved_rate_max": {"warn": 0.3, "fail": 0.5},
    "event_anchor_score_min": {"warn": 0.5, "fail": 0.35},
    "event_reservation_ready_rate_min": {"warn": 0.35, "fail": 0.15},
}

SCENARIO_TYPE_GROUPS = {
    "food_drink": {
        "restaurant",
        "lunch_restaurant",
        "breakfast_restaurant",
        "brunch_restaurant",
        "cafe",
        "coffee_shop",
        "bakery",
        "bar",
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
        "tourist_attraction",
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


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round_metric(value):
    return round(float(value), 4)


def _dcg(labels):
    return sum(label / math.log2(index + 2) for index, label in enumerate(labels))


class RecommendationEvaluationService:
    """Evaluate ranked Adventour outcomes from exported training examples."""

    def evaluate_examples(self, examples, k_values=DEFAULT_K_VALUES, positive_threshold=0.75):
        normalized_k_values = tuple(sorted({int(k) for k in k_values if int(k) > 0}))
        if not normalized_k_values:
            normalized_k_values = DEFAULT_K_VALUES

        grouped = defaultdict(list)
        labeled_example_count = 0
        skipped_without_request = 0
        skipped_without_rank = 0

        for example in examples:
            if example.get("label") is None:
                continue

            labeled_example_count += 1
            request_id = example.get("request_id")
            rank_position = _safe_int(example.get("rank_position"))

            if not request_id:
                skipped_without_request += 1
                continue
            if rank_position is None:
                skipped_without_rank += 1
                continue

            grouped[str(request_id)].append({
                **example,
                "rank_position": rank_position,
                "label": _safe_float(example.get("label")),
                "outcome_weight": _safe_float(example.get("outcome_weight"), 1.0),
            })

        request_summaries = [
            self._request_summary(request_id, rows, normalized_k_values, positive_threshold)
            for request_id, rows in grouped.items()
        ]

        return {
            "overall": self._overall_summary(
                request_summaries,
                labeled_example_count,
                skipped_without_request,
                skipped_without_rank,
                normalized_k_values,
            ),
            "by_scoring_profile": self._profile_summaries(request_summaries, normalized_k_values),
            "by_segment": self._segment_summaries(request_summaries, normalized_k_values),
            "requests": request_summaries,
        }

    def compare_with_learned_model(self, examples, model, k_values=DEFAULT_K_VALUES, positive_threshold=0.75):
        baseline = self.evaluate_examples(
            examples,
            k_values=k_values,
            positive_threshold=positive_threshold,
        )
        reranked_examples = self._learned_reranked_examples(examples, model)
        learned = self.evaluate_examples(
            reranked_examples,
            k_values=k_values,
            positive_threshold=positive_threshold,
        )
        delta = self._comparison_delta(
            baseline.get("overall") or {},
            learned.get("overall") or {},
        )
        segment_delta = self._segment_comparison_delta(
            baseline.get("by_segment") or {},
            learned.get("by_segment") or {},
        )

        return {
            "baseline": baseline,
            "learned": learned,
            "delta": delta,
            "segment_delta": segment_delta,
            "promotion_gate": self._promotion_gate(
                baseline.get("overall") or {},
                learned.get("overall") or {},
                delta,
                segment_delta,
                baseline.get("by_segment") or {},
                learned.get("by_segment") or {},
            ),
        }

    def load_jsonl(self, path):
        examples = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    examples.append(json.loads(stripped))
        return examples

    def scenario_readiness_report(self, result):
        """Summarize whether a live or lab recommendation result is beta-ready.

        Offline evaluation tells us whether past ranking behavior improved.
        This report answers a different product question: does the current
        basket or itinerary look trustworthy enough to test with real people?
        """

        if (result or {}).get("mode") == "planned_itinerary" or (result or {}).get("route_readiness"):
            return self._planned_scenario_readiness(result or {})
        return self._basket_scenario_readiness(result or {})

    def _learned_reranked_examples(self, examples, model):
        model_service = LearningToRankBaselineService()
        learned_rows = model_service.rerank_examples(examples, model)
        return [
            {
                **row,
                "original_rank_position": row.get("rank_position"),
                "rank_position": row.get("learned_rank_position"),
                "model_score": row.get("learned_score", row.get("model_score")),
                "ranking_strategy": "learned_baseline",
            }
            for row in learned_rows
        ]

    def _basket_scenario_readiness(self, result):
        recommendations = result.get("recommendations") or []
        quality = result.get("recommendation_quality") or {}
        quality_metrics = quality.get("metrics") or {}
        model_confidence = quality.get("model_confidence") or result.get("model_confidence") or {}
        group_fit_summary = result.get("group_fit_summary") or {}
        slate_summary = result.get("slate_summary") or {}
        slate_metrics = slate_summary.get("metrics") or {}
        provider_errors = result.get("provider_errors") or []
        member_count = max(1, int(result.get("member_count") or len(result.get("members") or []) or 1))
        returned_count = int(quality_metrics.get("returned") or len(recommendations))
        local_share = _optional_float(quality_metrics.get("local_feeling_share"))
        hidden_gem_count = int(quality_metrics.get("hidden_gem_count") or 0)
        generic_share = _optional_float(quality_metrics.get("generic_risk_share"))
        local_event_backed_count = int(quality_metrics.get("local_event_backed_count") or 0)
        local_event_social_score = _optional_float(quality_metrics.get("local_event_social_score"))
        local_event_friend_signal_count = int(quality_metrics.get("local_event_friend_signal_count") or 0)
        local_event_reservation_ready_count = int(quality_metrics.get("local_event_reservation_ready_count") or 0)
        average_group_fit = _optional_float(quality_metrics.get("average_group_fit"))
        consensus_group_fit = _optional_float(
            quality_metrics.get("average_consensus_fit", group_fit_summary.get("average_consensus_fit"))
        )
        consensus_gap = _optional_float(
            quality_metrics.get("group_consensus_gap", group_fit_summary.get("consensus_gap"))
        )
        explanation_coverage = self._explanation_coverage(recommendations)
        variety_group_count = len(self._result_variety_groups(recommendations))
        diversity_coverage = _optional_float(
            slate_metrics.get("diversity_coverage", quality_metrics.get("diversity_coverage"))
        )
        member_coverage_share = _optional_float(
            slate_metrics.get("member_coverage_share", quality_metrics.get("member_coverage_share"))
        )
        friend_readiness = self._friend_readiness_summary(
            member_count=member_count,
            average_group_fit=average_group_fit,
            consensus_group_fit=consensus_group_fit,
            consensus_gap=consensus_gap,
            member_coverage_share=member_coverage_share,
            group_fit_summary=group_fit_summary,
            slate_summary=slate_summary,
        ) if member_count > 1 else None
        missing_intent_count = int(
            slate_metrics.get("missing_intent_count", quality_metrics.get("missing_intent_count") or 0) or 0
        )
        first_page_diversity = _optional_float(
            slate_metrics.get("first_page_diversity_coverage", quality_metrics.get("first_page_diversity_coverage"))
        )
        first_page_dominant_share = _optional_float(
            slate_metrics.get("first_page_dominant_group_share", quality_metrics.get("first_page_dominant_group_share"))
        )
        first_page_missing_intents = int(
            slate_metrics.get("first_page_missing_intent_count", quality_metrics.get("first_page_missing_intent_count") or 0) or 0
        )
        first_page_score = self._basket_first_page_score(
            first_page_diversity,
            first_page_dominant_share,
            first_page_missing_intents,
        )
        model_confidence_score = _optional_float(model_confidence.get("score"))

        checks = [
            self._readiness_check(
                "candidate_depth",
                "Enough picks to swipe",
                "pass" if returned_count >= 8 else "warn" if returned_count >= 5 else "fail",
                returned_count,
                "8+ picks preferred, 5 minimum",
                "Widen the search radius, relax filters, or seed more local places before friend testing.",
            ),
            self._readiness_check(
                "provider_health",
                "Place provider response was healthy",
                "pass" if not provider_errors else "fail",
                len(provider_errors),
                "0 provider errors",
                "Fix provider/API errors before judging recommendation quality.",
            ),
            self._readiness_check(
                "local_authentic_mix",
                "Local-authentic mix is visible",
                self._threshold_status(local_share, pass_min=0.35, warn_min=0.2),
                local_share,
                "35%+ local-feeling picks",
                "Tune authenticity weights, widen the radius, or add more local data for this launch point.",
            ),
            self._readiness_check(
                "hidden_gem_presence",
                "At least one hidden gem surfaced",
                "pass" if hidden_gem_count >= 1 else "warn" if returned_count else "fail",
                hidden_gem_count,
                "1+ hidden-gem pick",
                "Keep testing, but treat this area as thin until a true hidden-gem candidate appears.",
            ),
            self._readiness_check(
                "generic_risk",
                "Generic or chain risk is controlled",
                self._max_threshold_status(generic_share, pass_max=0.25, warn_max=0.45),
                generic_share,
                "25% or less generic-risk picks",
                "Increase chain penalties or reduce fallback repeats for this scenario.",
            ),
            self._readiness_check(
                "explanation_coverage",
                "Cards explain why they were picked",
                self._threshold_status(explanation_coverage, pass_min=0.9, warn_min=0.75),
                explanation_coverage,
                "90%+ cards with recommendation story",
                "Fill missing recommendation stories before giving this to testers.",
            ),
            self._readiness_check(
                "variety",
                "Basket covers enough kinds of experience",
                self._threshold_status(diversity_coverage, pass_min=0.8, warn_min=0.5)
                if diversity_coverage is not None
                else "pass" if variety_group_count >= 3 else "warn" if variety_group_count >= 2 else "fail",
                diversity_coverage if diversity_coverage is not None else variety_group_count,
                "80%+ slate variety coverage, or 3+ experience groups",
                "Improve diversification or adjust selected tag groups for this destination.",
            ),
            self._readiness_check(
                "intent_coverage",
                "Requested trip moods are represented",
                "pass" if missing_intent_count == 0 else "warn" if missing_intent_count <= 1 else "fail",
                missing_intent_count,
                "0 missing requested groups",
                "Relax filters, widen the radius, or add candidates for the missing trip mood.",
            ),
            self._readiness_check(
                "first_swipe_variety",
                "Opening cards feel varied",
                self._threshold_status(first_page_score, pass_min=0.72, warn_min=0.52),
                first_page_score,
                "72%+ first-swipe variety",
                "Diversify the first few cards so the basket does not feel repetitive right away.",
            ),
            self._readiness_check(
                "model_confidence",
                "Model signal is trustworthy",
                self._threshold_status(model_confidence_score, pass_min=0.7, warn_min=0.45),
                model_confidence_score,
                "70%+ model confidence",
                "Collect more accepts, rejects, and ratings before treating this basket as personalized.",
            ),
        ]
        event_actionable_score = None
        if local_event_backed_count:
            event_actionable_score = self._average_available([
                local_event_social_score,
                min(1.0, local_event_reservation_ready_count / max(1, local_event_backed_count)),
                min(1.0, local_event_friend_signal_count / max(1, local_event_backed_count)),
            ])
            checks.append(self._readiness_check(
                "event_social_anchor",
                "Event-backed picks are social and actionable",
                self._threshold_status(event_actionable_score, pass_min=0.5, warn_min=0.28),
                event_actionable_score,
                "50%+ event social/actionable readiness",
                "Ask friends to mark Interested/Going or add event picks with RSVP/source links.",
            ))
        if member_count > 1:
            checks.append(self._readiness_check(
                "group_fit",
                "Friend blend is balanced",
                self._threshold_status(average_group_fit, pass_min=0.7, warn_min=0.55),
                average_group_fit,
                "70%+ average group fit",
                "Try the group-friendly scout style or add stronger shared-interest candidates.",
            ))
            checks.append(self._readiness_check(
                "friend_coverage",
                "Every traveler has a strong slate match",
                self._threshold_status(member_coverage_share, pass_min=1.0, warn_min=0.75),
                member_coverage_share,
                "100% of travelers covered",
                "Try the group-friendly scout style or add more candidates for the underserved traveler.",
            ))
            if consensus_group_fit is not None or consensus_gap is not None:
                checks.append(self._readiness_check(
                    "group_consensus",
                    "Friend blend protects the lowest-fit traveler",
                    self._consensus_status(consensus_group_fit, consensus_gap),
                    consensus_group_fit,
                    "68%+ consensus fit and no large average-to-consensus gap",
                    "Use group-friendly scout style or add candidates that raise the lowest-fit traveler, not just the group average.",
                ))

        friend_warnings = []
        if friend_readiness and friend_readiness.get("status") == "needs_attention":
            friend_warnings.append(friend_readiness.get("headline"))
        elif friend_readiness and friend_readiness.get("status") == "watch":
            friend_warnings.extend(friend_readiness.get("watchouts") or [])
        status = self._scenario_status(checks)
        if status == "ready" and friend_readiness and friend_readiness.get("status") == "watch":
            status = "watch"

        report = self._scenario_report(
            mode="basket",
            status=status,
            headline=self._scenario_headline(status, "Recommendation basket"),
            metrics={
                "returned": returned_count,
                "local_feeling_share": self._rounded_optional(local_share),
                "hidden_gem_count": hidden_gem_count,
                "generic_risk_share": self._rounded_optional(generic_share),
                "explanation_coverage": self._rounded_optional(explanation_coverage),
                "variety_group_count": variety_group_count,
                "diversity_coverage": self._rounded_optional(diversity_coverage),
                "missing_intent_count": missing_intent_count,
                "member_coverage_share": self._rounded_optional(member_coverage_share),
                "average_consensus_fit": self._rounded_optional(consensus_group_fit),
                "group_consensus_gap": self._rounded_optional(consensus_gap),
                "first_page_diversity_coverage": self._rounded_optional(first_page_diversity),
                "first_page_dominant_group_share": self._rounded_optional(first_page_dominant_share),
                "first_page_missing_intent_count": first_page_missing_intents,
                "first_page_score": self._rounded_optional(first_page_score),
                "model_confidence_score": self._rounded_optional(model_confidence_score),
                "model_confidence_status": model_confidence.get("status"),
                "learning_status": model_confidence.get("learning_status"),
                "local_event_backed_count": local_event_backed_count,
                "local_event_social_score": self._rounded_optional(local_event_social_score),
                "local_event_friend_signal_count": local_event_friend_signal_count,
                "local_event_reservation_ready_count": local_event_reservation_ready_count,
                "event_actionable_score": self._rounded_optional(event_actionable_score),
                "member_count": member_count,
            },
            checks=checks,
            strengths=(quality.get("strengths") or [])[:4],
            warnings=list(dict.fromkeys(friend_warnings + (quality.get("warnings") or [])))[:5],
        )
        report["test_verdict"] = self._basket_friend_test_verdict(
            status=status,
            returned_count=returned_count,
            local_share=local_share,
            hidden_gem_count=hidden_gem_count,
            generic_share=generic_share,
            explanation_coverage=explanation_coverage,
            first_page_score=first_page_score,
            friend_readiness=friend_readiness,
            member_count=member_count,
            average_group_fit=average_group_fit,
            model_confidence=model_confidence,
            event_actionable_score=event_actionable_score,
            local_event_backed_count=local_event_backed_count,
            local_event_friend_signal_count=local_event_friend_signal_count,
            checks=checks,
        )
        if friend_readiness:
            report["friend_readiness"] = friend_readiness
        report["remediation_plan"] = self._scenario_remediation_plan(
            checks,
            test_verdict=report["test_verdict"],
            friend_readiness=friend_readiness,
            model_confidence=model_confidence,
        )
        return report

    def _friend_readiness_summary(
        self,
        member_count,
        average_group_fit,
        member_coverage_share,
        consensus_group_fit=None,
        consensus_gap=None,
        group_fit_summary=None,
        slate_summary=None,
    ):
        group_fit_summary = group_fit_summary or {}
        slate_summary = slate_summary or {}
        coverage_rows = slate_summary.get("member_coverage") or []
        group_rows = {
            member.get("user_id"): member
            for member in group_fit_summary.get("members") or []
            if member.get("user_id") is not None
        }
        underserved_ids = {
            member.get("user_id")
            for member in (slate_summary.get("underserved_members") or group_fit_summary.get("underserved_members") or [])
            if member.get("user_id") is not None
        }

        member_rows = []
        covered_count = 0
        for row in coverage_rows:
            user_id = row.get("user_id")
            group_row = group_rows.get(user_id, {})
            strong_match_count = int(row.get("strong_match_count") or group_row.get("matched_count") or 0)
            if strong_match_count > 0:
                covered_count += 1
            best_match = row.get("best_match") or {}
            best_fit = _optional_float(row.get("best_fit", group_row.get("average_fit")))
            status = "covered" if strong_match_count > 0 and user_id not in underserved_ids else "needs_match"
            member_rows.append({
                "user_id": user_id,
                "display_name": row.get("display_name") or group_row.get("display_name") or "Traveler",
                "status": status,
                "average_fit": self._rounded_optional(_optional_float(group_row.get("average_fit"))),
                "best_fit": self._rounded_optional(best_fit),
                "strong_match_count": strong_match_count,
                "best_match": best_match or None,
                "preferred_groups": row.get("preferred_groups") or group_row.get("preferred_groups") or [],
                "suggested_query_tags": row.get("suggested_query_tags") or group_row.get("suggested_query_tags") or [],
                "learning_status": row.get("learning_status") or group_row.get("learning_status"),
                "signal_count": row.get("signal_count") if row.get("signal_count") is not None else group_row.get("signal_count"),
                "confidence": self._rounded_optional(_optional_float(
                    row.get("confidence") if row.get("confidence") is not None else group_row.get("confidence")
                )),
                "suggested_swaps": (row.get("suggested_swaps") or [])[:3],
            })

        if not member_rows and group_rows:
            for row in group_rows.values():
                strong_match_count = int(row.get("matched_count") or 0)
                if strong_match_count > 0:
                    covered_count += 1
                status = "covered" if strong_match_count > 0 and row.get("user_id") not in underserved_ids else "needs_match"
                member_rows.append({
                    "user_id": row.get("user_id"),
                    "display_name": row.get("display_name") or "Traveler",
                    "status": status,
                    "average_fit": self._rounded_optional(_optional_float(row.get("average_fit"))),
                    "best_fit": self._rounded_optional(_optional_float(row.get("average_fit"))),
                    "strong_match_count": strong_match_count,
                    "best_match": None,
                    "preferred_groups": row.get("preferred_groups") or [],
                    "suggested_query_tags": row.get("suggested_query_tags") or [],
                    "learning_status": row.get("learning_status"),
                    "signal_count": row.get("signal_count"),
                    "confidence": self._rounded_optional(_optional_float(row.get("confidence"))),
                })

        if member_rows:
            covered_count = sum(1 for row in member_rows if row.get("status") == "covered")
            underserved = [row for row in member_rows if row.get("status") != "covered"]
            resolved_coverage = covered_count / len(member_rows)
        else:
            underserved = []
            resolved_coverage = member_coverage_share
            if member_coverage_share is not None:
                covered_count = int(round(member_coverage_share * member_count))

        coverage = member_coverage_share if member_coverage_share is not None else resolved_coverage
        fit = average_group_fit if average_group_fit is not None else _optional_float(group_fit_summary.get("average_fit"))
        consensus_fit = (
            consensus_group_fit
            if consensus_group_fit is not None
            else _optional_float(group_fit_summary.get("average_consensus_fit"))
        )
        consensus_fit_gap = (
            consensus_gap
            if consensus_gap is not None
            else _optional_float(group_fit_summary.get("consensus_gap"))
        )
        consensus_status = self._consensus_status(consensus_fit, consensus_fit_gap)
        cold_start_members = [
            member
            for member in member_rows
            if member.get("learning_status") == "cold_start"
            or (member.get("signal_count") is not None and int(member.get("signal_count") or 0) < 3)
        ]
        if consensus_status == "fail":
            status = "needs_attention"
            headline = "The group average is hiding a low-fit traveler."
        elif coverage is not None and coverage >= 1.0 and (fit is None or fit >= 0.7) and consensus_status != "warn" and not cold_start_members:
            status = "ready"
            headline = "Every traveler has at least one strong basket match."
        elif coverage is not None and coverage >= 0.75 and (fit is None or fit >= 0.55):
            status = "watch"
            headline = (
                "Every traveler has coverage, but Adventour is still learning this party."
                if cold_start_members
                else
                "Every traveler has coverage, but consensus fit needs a quick look."
                if consensus_status == "warn"
                else "Most travelers are covered, but the group blend needs a quick look."
            )
        else:
            status = "needs_attention"
            names = ", ".join(member.get("display_name") for member in underserved[:2])
            headline = f"{names or 'A traveler'} needs a stronger match before friend testing."

        next_actions = []
        consensus_swap_pool = [
            suggestion
            for member in member_rows
            for suggestion in (member.get("suggested_swaps") or [])[:1]
        ]
        consensus_swap_pool.sort(
            key=lambda item: (
                _safe_float(item.get("group_consensus_delta")),
                _safe_float(item.get("group_consensus_gap_delta")),
                _safe_float(item.get("member_fit_delta")),
            ),
            reverse=True,
        )
        for member in cold_start_members[:2]:
            next_actions.append(
                f"Ask {member.get('display_name')} to swipe or rate a few picks so Adventour can learn their taste."
            )
        for member in underserved[:3]:
            if len(next_actions) >= 3:
                break
            suggested_swap = (member.get("suggested_swaps") or [None])[0]
            if suggested_swap:
                fit = suggested_swap.get("fit")
                next_actions.append(
                    f"Swap {suggested_swap.get('from_stop')} for {suggested_swap.get('to_stop')} "
                    f"to give {member.get('display_name')} "
                    + (f"a {round(fit * 100)}% route match." if fit is not None else "a stronger route match.")
                )
                continue
            best_match = (member.get("best_match") or {}).get("name")
            if best_match:
                next_actions.append(
                    f"Find a stronger pick for {member.get('display_name')} than {best_match}, or switch to Group fit scout."
                )
            else:
                next_actions.append(
                    f"Find at least one strong pick for {member.get('display_name')}, or switch to Group fit scout."
                )
        if consensus_status in {"warn", "fail"}:
            consensus_swap = (consensus_swap_pool or [None])[0]
            if consensus_swap and not next_actions:
                next_actions.append(
                    f"Swap {consensus_swap.get('from_stop')} for {consensus_swap.get('to_stop')} "
                    "to narrow the group consensus gap."
                )
            next_actions.append("Run Group fit scout or add picks that raise the lowest-fit traveler, not just the group average.")
        if not next_actions and status == "watch":
            next_actions.append("Review the lowest-fit traveler before sending this basket to friends.")

        return {
            "status": status,
            "headline": headline,
            "member_count": member_count,
            "covered_member_count": covered_count,
            "underserved_count": len(underserved),
            "coverage_share": self._rounded_optional(coverage),
            "average_group_fit": self._rounded_optional(fit),
            "average_consensus_fit": self._rounded_optional(consensus_fit),
            "consensus_gap": self._rounded_optional(consensus_fit_gap),
            "cold_start_member_count": len(cold_start_members),
            "members": member_rows,
            "underserved_members": underserved,
            "suggested_swaps": [
                suggestion
                for member in underserved
                for suggestion in (member.get("suggested_swaps") or [])[:1]
            ][:3] or consensus_swap_pool[:3],
            "watchouts": next_actions[:3],
            "next_actions": next_actions[:3],
        }

    def _planned_scenario_readiness(self, result):
        route_readiness = result.get("route_readiness") or {}
        provider_errors = result.get("provider_errors") or []
        days = result.get("days") or []
        stops = [
            stop
            for day in days
            for stop in day.get("stops", [])
        ]
        member_count = max(1, int(result.get("member_count") or len(result.get("members") or []) or 1))
        route_score = _optional_float(route_readiness.get("score"))
        stop_coverage = _optional_float(route_readiness.get("stop_coverage"))
        variety_score = _optional_float(route_readiness.get("variety_score"))
        party_score = _optional_float(route_readiness.get("party_score"))
        booking_score = _optional_float(route_readiness.get("booking_score"))
        event_score = _optional_float(route_readiness.get("event_score"))
        route_model_confidence = result.get("route_model_confidence") or (result.get("trip_packet") or {}).get("route_model_confidence") or {}
        trip_logistics_readiness = (
            result.get("trip_logistics_readiness")
            or (result.get("trip_packet") or {}).get("trip_logistics_readiness")
            or {}
        )
        duration_alignment = self._planned_duration_alignment(result)
        quote_readiness = self._travel_quote_readiness(result)
        route_model_confidence_score = _optional_float(route_model_confidence.get("score"))
        trip_logistics_score = _optional_float(trip_logistics_readiness.get("score"))
        swap_coverage = self._swap_coverage(stops)
        price_ready = self._price_estimate_ready(result.get("price_breakdown") or {})
        local_authenticity_score = self._planned_local_authenticity_score(stops)
        booking_actionable_score = self._planned_booking_actionable_score(result, route_readiness, booking_score)
        event_pairing_score = self._planned_event_pairing_score(result, stops, event_score)
        event_social_score = self._planned_event_social_score(result, route_readiness)
        friend_readiness = self._planned_friend_readiness_summary(
            member_count=member_count,
            days=days,
        ) if member_count > 1 else None
        route_friend_coverage = _optional_float(
            (friend_readiness or {}).get("coverage_share")
        )
        route_average_fit = _optional_float(
            (friend_readiness or {}).get("average_group_fit")
        )
        route_consensus_fit = _optional_float(
            (friend_readiness or {}).get("average_consensus_fit")
        )
        route_consensus_gap = _optional_float(
            (friend_readiness or {}).get("consensus_gap")
        )

        checks = [
            self._readiness_check(
                "route_score",
                "Route readiness is beta-testable",
                self._threshold_status(route_score, pass_min=0.7, warn_min=0.45),
                route_score,
                "70%+ route readiness",
                "Tune route slots, filters, or scout style before handing this route to friends.",
            ),
            self._readiness_check(
                "stop_coverage",
                "Enough itinerary slots are filled",
                self._threshold_status(stop_coverage, pass_min=0.8, warn_min=0.55),
                stop_coverage,
                "80%+ slots filled",
                "Widen the range or add more candidate types for this destination.",
            ),
            self._readiness_check(
                "route_variety",
                "Route has a healthy mix of experiences",
                self._threshold_status(variety_score, pass_min=0.65, warn_min=0.45),
                variety_score,
                "65%+ variety score",
                "Swap or rerank stops so the day does not collapse into one category.",
            ),
            self._readiness_check(
                "provider_health",
                "Place provider response was healthy",
                "pass" if not provider_errors else "fail",
                len(provider_errors),
                "0 provider errors",
                "Fix provider/API errors before judging route quality.",
            ),
            self._readiness_check(
                "swap_options",
                "Most stops have swap options",
                self._threshold_status(swap_coverage, pass_min=0.8, warn_min=0.5),
                swap_coverage,
                "80%+ stops with alternatives",
                "Fetch more candidates or loosen slot matching so testers can swap weak stops.",
            ),
            self._readiness_check(
                "booking_readiness",
                "Booking and logistics plan is useful",
                self._threshold_status(booking_score, pass_min=0.7, warn_min=0.45),
                booking_score,
                "70%+ booking readiness",
                "Collect missing origin/date inputs or connect provider actions for this trip.",
            ),
            self._readiness_check(
                "local_events",
                "Local-event layer is useful",
                self._threshold_status(event_score, pass_min=0.7, warn_min=0.45),
                event_score,
                "70%+ event readiness",
                "Add community events or external event sources for this area.",
            ),
            self._readiness_check(
                "social_events",
                "Local events can support a meetup",
                self._threshold_status(event_social_score, pass_min=0.5, warn_min=0.28),
                event_social_score,
                "50%+ social-event readiness",
                "Ask friends to mark Interested/Going or add a community event with social signal.",
            ),
            self._readiness_check(
                "price_estimate",
                "Per-person estimate is present",
                "pass" if price_ready else "warn",
                bool(price_ready),
                "known low/high estimate",
                "Keep the route testable, but add clearer cost coverage before broader beta.",
            ),
            self._readiness_check(
                "route_model_confidence",
                "Route model signal is trustworthy",
                self._threshold_status(route_model_confidence_score, pass_min=0.7, warn_min=0.45),
                route_model_confidence_score,
                "70%+ route model confidence",
                "Collect more taste signal or keep the transparent route ranking before sharing this itinerary.",
            ),
            self._readiness_check(
                "trip_logistics",
                "Trip logistics are shareable",
                self._threshold_status(trip_logistics_score, pass_min=0.72, warn_min=0.5),
                trip_logistics_score,
                "72%+ trip logistics readiness",
                "Add missing origin, dates, booking handoffs, or local transport setup before friend testing.",
            ),
            self._readiness_check(
                "duration_alignment",
                "Trip duration matches the itinerary",
                self._duration_alignment_check_status(duration_alignment),
                (duration_alignment or {}).get("status"),
                "trip style, route days, and dates agree",
                (duration_alignment or {}).get("message") or "Confirm whether this should be a day, weekend, or vacation plan.",
            ),
        ]
        if quote_readiness.get("required_count"):
            checks.append(self._readiness_check(
                "travel_quotes",
                "Flight/stay quote links are ready",
                "pass" if quote_readiness.get("status") == "ready_to_quote"
                else self._threshold_status(quote_readiness.get("ready_coverage"), pass_min=1.0, warn_min=0.5),
                quote_readiness.get("ready_coverage"),
                "100% required quote links ready",
                quote_readiness.get("message") or "Add origin, dates, and stay details so flight/stay quote links are ready.",
            ))
        if member_count > 1:
            checks.append(self._readiness_check(
                "party_fit",
                "Friend route fit is balanced",
                self._threshold_status(party_score, pass_min=0.7, warn_min=0.55),
                party_score,
                "70%+ party score",
                "Try group-friendly scout style or swap stops that underserve a traveler.",
            ))
            checks.append(self._readiness_check(
                "friend_route_coverage",
                "Every traveler has a strong route stop",
                self._threshold_status(route_friend_coverage, pass_min=1.0, warn_min=0.75),
                route_friend_coverage,
                "100% of travelers covered",
                "Swap in stops that give the underserved traveler at least one strong route match.",
            ))
            checks.append(self._readiness_check(
                "friend_route_fit",
                "Route has enough average traveler fit",
                self._threshold_status(route_average_fit, pass_min=0.7, warn_min=0.55),
                route_average_fit,
                "70%+ average traveler fit",
                "Use group-friendly scout style or rebuild with broader candidate coverage.",
            ))
            if route_consensus_fit is not None or route_consensus_gap is not None:
                checks.append(self._readiness_check(
                    "route_group_consensus",
                    "Route protects the lowest-fit traveler",
                    self._consensus_status(route_consensus_fit, route_consensus_gap),
                    route_consensus_fit,
                    "68%+ route consensus fit and no large average-to-consensus gap",
                    "Swap in stops that raise the lowest-fit traveler, not just the route average.",
                ))

        friend_warnings = []
        if friend_readiness and friend_readiness.get("status") == "needs_attention":
            friend_warnings.append(friend_readiness.get("headline"))
        elif friend_readiness and friend_readiness.get("status") == "watch":
            friend_warnings.extend(friend_readiness.get("watchouts") or [])
        status = self._scenario_status(checks)
        if status == "ready" and friend_readiness and friend_readiness.get("status") == "watch":
            status = "watch"

        test_verdict = self._planned_friend_test_verdict(
            status=status,
            route_score=route_score,
            stop_coverage=stop_coverage,
            local_authenticity_score=local_authenticity_score,
            friend_readiness=friend_readiness,
            member_count=member_count,
            party_score=party_score,
            booking_actionable_score=booking_actionable_score,
            event_pairing_score=event_pairing_score,
            event_social_score=event_social_score,
            swap_coverage=swap_coverage,
            price_ready=price_ready,
            route_model_confidence=route_model_confidence,
            trip_logistics_readiness=trip_logistics_readiness,
            checks=checks,
        )

        report = self._scenario_report(
            mode="planned_itinerary",
            status=status,
            headline=self._scenario_headline(status, "Planned Adventour"),
            metrics={
                "route_score": self._rounded_optional(route_score),
                "planned_stop_count": route_readiness.get("planned_stop_count") or len(stops),
                "expected_stop_count": route_readiness.get("expected_stop_count"),
                "stop_coverage": self._rounded_optional(stop_coverage),
                "variety_score": self._rounded_optional(variety_score),
                "party_score": self._rounded_optional(party_score),
                "booking_score": self._rounded_optional(booking_score),
                "booking_actionable_score": self._rounded_optional(booking_actionable_score),
                "event_score": self._rounded_optional(event_score),
                "event_pairing_score": self._rounded_optional(event_pairing_score),
                "event_social_score": self._rounded_optional(event_social_score),
                "swap_coverage": self._rounded_optional(swap_coverage),
                "local_authenticity_score": self._rounded_optional(local_authenticity_score),
                "route_model_confidence_score": self._rounded_optional(route_model_confidence_score),
                "route_model_confidence_status": route_model_confidence.get("status"),
                "trip_logistics_score": self._rounded_optional(trip_logistics_score),
                "trip_logistics_status": trip_logistics_readiness.get("status"),
                "trip_logistics_missing_input_count": trip_logistics_readiness.get("missing_input_count"),
                "trip_logistics_blocking_count": trip_logistics_readiness.get("blocking_count"),
                "duration_alignment_status": duration_alignment.get("status"),
                "duration_alignment_trip_style": duration_alignment.get("trip_style"),
                "duration_alignment_route_days": duration_alignment.get("route_days"),
                "duration_alignment_calendar_nights": duration_alignment.get("calendar_nights"),
                "travel_quote_status": quote_readiness.get("status"),
                "travel_quote_required_count": quote_readiness.get("required_count"),
                "travel_quote_ready_count": quote_readiness.get("ready_count"),
                "travel_quote_missing_input_count": quote_readiness.get("missing_input_count"),
                "travel_quote_ready_coverage": self._rounded_optional(quote_readiness.get("ready_coverage")),
                "member_count": member_count,
                "member_coverage_share": self._rounded_optional(route_friend_coverage),
                "average_group_fit": self._rounded_optional(route_average_fit),
                "average_consensus_fit": self._rounded_optional(route_consensus_fit),
                "group_consensus_gap": self._rounded_optional(route_consensus_gap),
            },
            checks=checks,
            strengths=(route_readiness.get("strengths") or [])[:4],
            warnings=list(dict.fromkeys(
                friend_warnings
                + ([duration_alignment.get("headline")] if duration_alignment.get("status") in {"watch", "needs_attention"} else [])
                + (route_readiness.get("warnings") or [])
            ))[:5],
        )
        report["test_verdict"] = test_verdict
        if friend_readiness:
            report["friend_readiness"] = friend_readiness
        report["remediation_plan"] = self._scenario_remediation_plan(
            checks,
            test_verdict=test_verdict,
            friend_readiness=friend_readiness,
            quote_readiness=quote_readiness,
            model_confidence=route_model_confidence,
            trip_logistics_readiness=trip_logistics_readiness,
            duration_alignment=duration_alignment,
        )
        return report

    def _basket_friend_test_verdict(
        self,
        status,
        returned_count,
        local_share,
        hidden_gem_count,
        generic_share,
        explanation_coverage,
        first_page_score,
        friend_readiness,
        member_count,
        average_group_fit,
        model_confidence,
        event_actionable_score,
        local_event_backed_count,
        local_event_friend_signal_count,
        checks,
    ):
        model_confidence = model_confidence or {}
        model_score = _optional_float(model_confidence.get("score"))
        local_score = None
        if local_share is not None:
            generic_penalty = generic_share if generic_share is not None else 0
            hidden_bonus = min(0.18, max(0, hidden_gem_count or 0) * 0.08)
            local_score = max(0, min(1, local_share + hidden_bonus - generic_penalty * 0.3))

        if member_count > 1 and friend_readiness:
            coverage = _optional_float(friend_readiness.get("coverage_share"))
            fit = _optional_float(friend_readiness.get("average_group_fit"))
            consensus_fit = _optional_float(friend_readiness.get("average_consensus_fit"))
            friend_score = self._average_available([coverage, fit, consensus_fit])
        else:
            friend_score = average_group_fit

        dimensions = [
            self._verdict_dimension("depth", "Swipe depth", min(1, returned_count / 8) if returned_count else 0, 0.9, 0.62),
            self._verdict_dimension("local", "Local texture", local_score, 0.7, 0.5),
            self._friend_verdict_dimension(friend_score, friend_readiness),
            self._verdict_dimension("first_swipes", "Opening cards", first_page_score, 0.72, 0.52),
            self._verdict_dimension("model_signal", "Model signal", model_score, 0.7, 0.45),
            self._basket_event_verdict_dimension(
                event_actionable_score,
                local_event_backed_count,
                local_event_friend_signal_count,
            ),
            self._verdict_dimension("explanations", "Score explanations", explanation_coverage, 0.9, 0.75),
        ]
        weighted_score = self._weighted_verdict_score(dimensions)
        failing_checks = [
            check
            for check in checks
            if check.get("status") == "fail"
        ]
        caution_dimensions = [
            item
            for item in dimensions
            if item.get("status") in {"warn", "fail"}
        ]

        if status == "needs_attention" or failing_checks:
            verdict_status = "needs_attention"
            headline = "Basket is not friend-test ready yet."
        elif (friend_readiness or {}).get("status") == "watch":
            verdict_status = "watch"
            headline = "Basket is testable with friend-fit watchouts."
        elif weighted_score >= 0.74 and not any(item.get("status") == "fail" for item in dimensions):
            verdict_status = "ready"
            headline = "Basket is ready to send to trusted friends."
        elif weighted_score >= 0.56:
            verdict_status = "watch"
            headline = "Basket is testable with watchouts."
        else:
            verdict_status = "needs_attention"
            headline = "Basket needs more recommendation work first."

        blockers = [
            check.get("message")
            for check in failing_checks
            if check.get("message")
        ][:3]
        next_actions = [
            item.get("summary")
            for item in caution_dimensions
            if item.get("summary")
        ][:3]
        if model_confidence.get("next_actions"):
            next_actions.extend(model_confidence.get("next_actions")[:2])

        return {
            "status": verdict_status,
            "headline": headline,
            "score": self._rounded_optional(weighted_score),
            "friend_testable": verdict_status == "ready",
            "dimensions": dimensions,
            "blockers": blockers,
            "next_actions": list(dict.fromkeys(next_actions))[:4],
        }

    def _basket_event_verdict_dimension(self, score, event_count, friend_signal_count):
        if not event_count:
            return {
                "name": "events",
                "label": "Event anchors",
                "score": None,
                "status": "warn",
                "summary": "No event-backed picks surfaced in this basket yet.",
            }
        dimension = self._verdict_dimension("events", "Event anchors", score, 0.5, 0.28)
        if friend_signal_count:
            dimension["summary"] = f"{friend_signal_count} selected-friend event signal{'s' if friend_signal_count != 1 else ''} make this basket more social."
        return dimension

    def _basket_first_page_score(self, first_page_diversity, first_page_dominant_share, first_page_missing_intents):
        if first_page_diversity is None and first_page_dominant_share is None and not first_page_missing_intents:
            return None

        diversity = first_page_diversity if first_page_diversity is not None else 0.5
        dominant_share = first_page_dominant_share if first_page_dominant_share is not None else 0.5
        return max(0, min(1, diversity * 0.74 + (1 - dominant_share) * 0.26 - first_page_missing_intents * 0.08))

    def _planned_friend_test_verdict(
        self,
        status,
        route_score,
        stop_coverage,
        local_authenticity_score,
        friend_readiness,
        member_count,
        party_score,
        booking_actionable_score,
        event_pairing_score,
        event_social_score,
        swap_coverage,
        price_ready,
        route_model_confidence,
        trip_logistics_readiness,
        checks,
    ):
        route_model_confidence = route_model_confidence or {}
        trip_logistics_readiness = trip_logistics_readiness or {}
        friend_score = None
        if member_count > 1 and friend_readiness:
            coverage = _optional_float(friend_readiness.get("coverage_share"))
            fit = _optional_float(friend_readiness.get("average_group_fit"))
            consensus_fit = _optional_float(friend_readiness.get("average_consensus_fit"))
            friend_score = self._average_available([coverage, fit, consensus_fit])
        else:
            friend_score = party_score

        route_foundation = self._average_available([route_score, stop_coverage])
        dimensions = [
            self._verdict_dimension("route", "Route shape", route_foundation, 0.72, 0.55),
            self._verdict_dimension("local", "Local texture", local_authenticity_score, 0.7, 0.5),
            self._friend_verdict_dimension(friend_score, friend_readiness),
            self._verdict_dimension("booking", "Bookable steps", booking_actionable_score, 0.72, 0.5),
            self._verdict_dimension(
                "model_signal",
                "Route model signal",
                _optional_float(route_model_confidence.get("score")),
                0.7,
                0.45,
            ),
            self._verdict_dimension(
                "trip_logistics",
                "Trip logistics",
                _optional_float(trip_logistics_readiness.get("score")),
                0.72,
                0.5,
            ),
            self._verdict_dimension("events", "Event pairing", event_pairing_score, 0.7, 0.45),
            self._verdict_dimension("social_events", "Social event anchor", event_social_score, 0.5, 0.28),
            self._verdict_dimension("swaps", "Swap safety", swap_coverage, 0.8, 0.5),
            {
                "name": "cost",
                "label": "Cost visibility",
                "score": 1.0 if price_ready else 0.45,
                "status": "pass" if price_ready else "warn",
                "summary": "Per-person estimate present" if price_ready else "Add clearer per-person estimates before broader testing.",
            },
        ]
        weighted_score = self._weighted_verdict_score(dimensions)
        failing_checks = [
            check
            for check in checks
            if check.get("status") == "fail"
        ]
        caution_dimensions = [
            item
            for item in dimensions
            if item.get("status") in {"warn", "fail"}
        ]

        if status == "needs_attention" or failing_checks:
            verdict_status = "needs_attention"
            headline = "Not friend-test ready yet."
        elif (friend_readiness or {}).get("status") == "watch":
            verdict_status = "watch"
            headline = "Testable with friend-fit watchouts."
        elif weighted_score >= 0.76 and not any(item.get("status") == "fail" for item in dimensions):
            verdict_status = "ready"
            headline = "Ready to send to trusted friends."
        elif weighted_score >= 0.58:
            verdict_status = "watch"
            headline = "Testable with a few watchouts."
        else:
            verdict_status = "needs_attention"
            headline = "Route needs more recommendation work first."

        blockers = [
            check.get("message")
            for check in failing_checks
            if check.get("message")
        ][:3]
        next_actions = [
            item.get("summary")
            for item in caution_dimensions
            if item.get("summary")
        ][:3]
        if route_model_confidence.get("next_actions"):
            next_actions.extend(route_model_confidence.get("next_actions")[:2])
        if trip_logistics_readiness.get("next_actions"):
            next_actions.extend(trip_logistics_readiness.get("next_actions")[:2])

        return {
            "status": verdict_status,
            "headline": headline,
            "score": self._rounded_optional(weighted_score),
            "friend_testable": verdict_status == "ready",
            "dimensions": dimensions,
            "blockers": blockers,
            "next_actions": list(dict.fromkeys(next_actions)),
        }

    def _planned_local_authenticity_score(self, stops):
        scores = []
        chain_risks = []
        for stop in stops or []:
            recommendation = stop.get("recommendation") or {}
            components = recommendation.get("components") or {}
            evidence = recommendation.get("authenticity_evidence") or {}
            score = _optional_float(components.get("authenticity"))
            if score is None:
                score = _optional_float(evidence.get("score"))
            if score is None and "local" in str(evidence.get("label") or "").lower():
                score = 0.72
            if score is not None:
                scores.append(score)
            chain_risk = _optional_float(evidence.get("chain_risk"))
            if chain_risk is not None:
                chain_risks.append(chain_risk)
        if not scores:
            return None
        average_score = sum(scores) / len(scores)
        average_chain_risk = sum(chain_risks) / len(chain_risks) if chain_risks else 0
        return max(0, min(1, average_score - average_chain_risk * 0.22))

    def _planned_booking_actionable_score(self, result, route_readiness, booking_score):
        booking_plan = result.get("booking_plan") or {}
        action_links = booking_plan.get("booking_action_links") or []
        timeline_items = (booking_plan.get("booking_timeline") or {}).get("items") or []
        has_actionability_fields = (
            "booking_action_link_count" in route_readiness
            or "booking_saveable_item_count" in route_readiness
            or bool(booking_plan)
        )
        if not has_actionability_fields:
            return booking_score
        action_count = int(route_readiness.get("booking_action_link_count") or len(action_links))
        saveable_count = int(
            route_readiness.get("booking_saveable_item_count")
            or sum(1 for item in timeline_items if item.get("stores_reservation"))
        )
        action_coverage = min(1, action_count / 3)
        saveable_coverage = min(1, saveable_count / 2)
        base_score = booking_score if booking_score is not None else 0.45
        return max(0, min(1, base_score * 0.55 + action_coverage * 0.28 + saveable_coverage * 0.17))

    def _planned_event_pairing_score(self, result, stops, event_score):
        local_events = result.get("local_events") or {}
        summary = local_events.get("summary") or {}
        route_match_count = int(summary.get("route_match_count") or 0)
        if not route_match_count:
            route_match_count = sum(
                len(stop.get("local_event_matches") or [])
                for stop in stops or []
            )
        if route_match_count:
            return min(1, route_match_count / max(1, min(2, len(stops) or 1)))
        return event_score

    def _planned_event_social_score(self, result, route_readiness):
        readiness_score = _optional_float((route_readiness or {}).get("event_social_score"))
        if readiness_score is not None:
            return max(0, min(1, readiness_score))

        local_events = (result or {}).get("local_events") or {}
        summary = local_events.get("summary") or {}
        social_readiness = summary.get("social_readiness") or {}
        social_score = _optional_float(social_readiness.get("score"))
        social_score = social_score if social_score is not None else 0
        event_count = int(summary.get("event_count") or len(local_events.get("events") or []) or 0)
        if not event_count:
            return social_score

        route_social_anchor_count = int(summary.get("route_social_anchor_count") or summary.get("social_anchor_count") or 0)
        route_friend_signal_count = int(summary.get("route_friend_signal_count") or 0)
        if not route_friend_signal_count:
            route_friend_signal_count = (
                int(summary.get("friend_interested_count") or 0)
                + int(summary.get("friend_going_count") or 0)
            )
        route_community_signal_count = int(summary.get("route_community_signal_count") or 0)
        if not route_community_signal_count:
            route_community_signal_count = (
                int(summary.get("interested_count") or 0)
                + int(summary.get("going_count") or 0)
            )
        route_social_signal = max(0, min(1,
            (route_social_anchor_count / max(1, event_count)) * 0.5
            + min(1, route_friend_signal_count / max(1, event_count)) * 0.35
            + min(1, route_community_signal_count / max(1, event_count)) * 0.15
        ))
        return max(0, min(1, social_score * 0.55 + route_social_signal * 0.45))

    def _verdict_dimension(self, name, label, score, pass_min, warn_min):
        status = self._threshold_status(score, pass_min=pass_min, warn_min=warn_min)
        if status == "pass":
            summary = f"{label} is ready."
        elif status == "warn":
            summary = f"{label} is usable, but worth reviewing."
        elif status == "fail":
            summary = f"{label} needs improvement before friend testing."
        else:
            summary = f"{label} has not been measured yet."
        return {
            "name": name,
            "label": label,
            "score": self._rounded_optional(score),
            "status": status,
            "summary": summary,
        }

    def _friend_verdict_dimension(self, score, friend_readiness):
        dimension = self._verdict_dimension("friends", "Friend coverage", score, 0.72, 0.55)
        if (friend_readiness or {}).get("status") == "needs_attention":
            dimension["status"] = "fail"
            dimension["summary"] = (friend_readiness or {}).get("headline") or "At least one traveler needs a stronger route stop."
        elif (friend_readiness or {}).get("status") == "watch" and dimension["status"] == "pass":
            dimension["status"] = "warn"
            dimension["summary"] = (friend_readiness or {}).get("headline") or "Friend coverage is usable, but worth reviewing."
        return dimension

    def _weighted_verdict_score(self, dimensions):
        weights = {
            "route": 0.17,
            "local": 0.15,
            "friends": 0.18,
            "booking": 0.15,
            "model_signal": 0.10,
            "trip_logistics": 0.10,
            "events": 0.10,
            "social_events": 0.08,
            "swaps": 0.10,
            "cost": 0.07,
            "depth": 0.14,
            "first_swipes": 0.13,
            "explanations": 0.10,
        }
        weighted = 0
        total_weight = 0
        for item in dimensions:
            score = _optional_float(item.get("score"))
            if score is None:
                continue
            weight = weights.get(item.get("name"), 0)
            weighted += score * weight
            total_weight += weight
        return weighted / total_weight if total_weight else 0

    def _average_available(self, values):
        available = [
            value
            for value in values
            if value is not None
        ]
        return sum(available) / len(available) if available else None

    def _planned_swap_suggestions_for_member(self, user_id, days):
        suggestions = []
        for day_index, day in enumerate(days or []):
            for stop in day.get("stops") or []:
                recommendation = stop.get("recommendation") or {}
                current_fit = self._member_fit_for_user(recommendation, user_id)
                current_consensus = self._group_consensus_fit(recommendation)
                current_consensus_gap = self._group_consensus_gap(recommendation)
                current_name = recommendation.get("name") or recommendation.get("display", {}).get("name") or stop.get("label") or "current stop"
                for alternative in stop.get("alternatives") or []:
                    alternative_fit = self._member_fit_for_user(alternative, user_id)
                    if alternative_fit is None:
                        continue
                    alternative_consensus = self._group_consensus_fit(alternative)
                    alternative_consensus_gap = self._group_consensus_gap(alternative)
                    swap_impact = alternative.get("swap_impact") or {}
                    member_delta = _optional_float(swap_impact.get("member_fit_delta"))
                    if member_delta is None and current_fit is not None:
                        member_delta = alternative_fit - current_fit
                    rebalance_delta = _optional_float(swap_impact.get("member_rebalance_delta")) or 0
                    consensus_delta = _optional_float(swap_impact.get("group_consensus_delta"))
                    if consensus_delta is None and current_consensus is not None and alternative_consensus is not None:
                        consensus_delta = alternative_consensus - current_consensus
                    consensus_gap_delta = _optional_float(swap_impact.get("group_consensus_gap_delta"))
                    if (
                        consensus_gap_delta is None
                        and current_consensus_gap is not None
                        and alternative_consensus_gap is not None
                    ):
                        consensus_gap_delta = current_consensus_gap - alternative_consensus_gap
                    if (
                        alternative_fit < 0.6
                        and (member_delta or 0) < 0.08
                        and rebalance_delta < 0.05
                        and (consensus_delta or 0) < 0.04
                        and (consensus_gap_delta or 0) < 0.03
                    ):
                        continue
                    suggestion_score = (
                        alternative_fit
                        + max(0, member_delta or 0) * 0.8
                        + max(0, rebalance_delta) * 0.5
                        + max(0, consensus_delta or 0) * 0.7
                        + max(0, consensus_gap_delta or 0) * 0.6
                    )
                    reason = (
                        (swap_impact.get("swap_decision") or {}).get("primary_reason")
                        or (swap_impact.get("reasons") or [None])[0]
                    )
                    if not reason and (consensus_delta or 0) >= 0.04:
                        reason = "Improves group consensus fit"
                    elif not reason and (consensus_gap_delta or 0) >= 0.03:
                        reason = "Narrows the group consensus gap"
                    suggestions.append({
                        "day": day.get("day") or day_index + 1,
                        "slot_id": stop.get("slot_id"),
                        "slot_label": stop.get("label"),
                        "from_stop": current_name,
                        "to_stop": alternative.get("name") or alternative.get("display", {}).get("name") or "swap option",
                        "fit": self._rounded_optional(alternative_fit),
                        "current_fit": self._rounded_optional(current_fit),
                        "member_fit_delta": self._rounded_optional(member_delta),
                        "member_rebalance_delta": self._rounded_optional(rebalance_delta),
                        "current_group_consensus_fit": self._rounded_optional(current_consensus),
                        "group_consensus_fit": self._rounded_optional(alternative_consensus),
                        "group_consensus_delta": self._rounded_optional(consensus_delta),
                        "current_group_consensus_gap": self._rounded_optional(current_consensus_gap),
                        "group_consensus_gap": self._rounded_optional(alternative_consensus_gap),
                        "group_consensus_gap_delta": self._rounded_optional(consensus_gap_delta),
                        "low_friction_score": self._rounded_optional(swap_impact.get("low_friction_score")),
                        "reason": reason,
                        "_score": suggestion_score,
                    })
        suggestions.sort(key=lambda item: item.pop("_score"), reverse=True)
        return suggestions[:3]

    def _member_fit_for_user(self, recommendation, user_id):
        for member in recommendation.get("member_fit") or []:
            if member.get("user_id") == user_id:
                return _optional_float(member.get("fit"))
        return None

    def _planned_friend_readiness_summary(self, member_count, days):
        member_rows = {}
        route_consensus_fits = []
        route_group_average_fits = []
        route_min_fit_weights = []
        for day in days or []:
            for stop_index, stop in enumerate(day.get("stops") or []):
                recommendation = stop.get("recommendation") or {}
                stop_name = recommendation.get("name") or recommendation.get("display", {}).get("name") or stop.get("label") or "Route stop"
                stop_fits = [
                    _optional_float(member.get("fit"))
                    for member in recommendation.get("member_fit") or []
                    if member.get("user_id") is not None
                ]
                stop_fits = [fit for fit in stop_fits if fit is not None]
                if len(stop_fits) > 1:
                    group_average_fit = sum(stop_fits) / len(stop_fits)
                    group_min_fit = min(stop_fits)
                    min_fit_weight = _optional_float(
                        (recommendation.get("components") or {}).get("group_min_fit_weight")
                    )
                    if min_fit_weight is None:
                        min_fit_weight = 0.26
                    consensus_fit = (
                        group_average_fit * (1 - min_fit_weight)
                        + group_min_fit * min_fit_weight
                    )
                    route_group_average_fits.append(group_average_fit)
                    route_consensus_fits.append(consensus_fit)
                    route_min_fit_weights.append(min_fit_weight)

                for member in recommendation.get("member_fit") or []:
                    user_id = member.get("user_id")
                    if user_id is None:
                        continue
                    fit = _optional_float(member.get("fit"))
                    if fit is None:
                        continue
                    row = member_rows.setdefault(user_id, {
                        "user_id": user_id,
                        "display_name": member.get("display_name") or "Traveler",
                        "total_fit": 0.0,
                        "matched_count": 0,
                        "strong_match_count": 0,
                        "best_fit": None,
                        "best_match": None,
                    })
                    row["total_fit"] += fit
                    row["matched_count"] += 1
                    if fit >= 0.6:
                        row["strong_match_count"] += 1
                    if row["best_fit"] is None or fit > row["best_fit"]:
                        row["best_fit"] = fit
                        row["best_match"] = {
                            "name": stop_name,
                            "fit": self._rounded_optional(fit),
                            "rank_position": stop_index + 1,
                            "diversity_groups": recommendation.get("diversity_groups") or [],
                            "authenticity_label": (
                                recommendation.get("authenticity_evidence") or {}
                            ).get("label"),
                        }

        for user_id, row in member_rows.items():
            row["suggested_swaps"] = self._planned_swap_suggestions_for_member(user_id, days)

        coverage_rows = []
        group_members = []
        for row in member_rows.values():
            average_fit = row["total_fit"] / max(1, row["matched_count"])
            coverage_rows.append({
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "strong_match_count": row["strong_match_count"],
                "best_fit": self._rounded_optional(row["best_fit"]),
                "best_match": row["best_match"],
                "suggested_swaps": row.get("suggested_swaps") or [],
            })
            group_members.append({
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "average_fit": self._rounded_optional(average_fit),
                "matched_count": row["strong_match_count"],
            })

        if not group_members:
            return self._friend_readiness_summary(
                member_count=member_count,
                average_group_fit=None,
                member_coverage_share=0,
                group_fit_summary={"members": []},
                slate_summary={"member_coverage": []},
            )

        average_group_fit = sum(member["average_fit"] for member in group_members) / len(group_members)
        route_average_group_fit = self._average_available(route_group_average_fits)
        route_average_consensus_fit = self._average_available(route_consensus_fits)
        route_average_min_fit_weight = self._average_available(route_min_fit_weights)
        route_consensus_gap = None
        if route_average_group_fit is not None and route_average_consensus_fit is not None:
            route_consensus_gap = max(0, route_average_group_fit - route_average_consensus_fit)
        covered_count = sum(1 for row in coverage_rows if row.get("strong_match_count", 0) > 0)
        coverage_share = covered_count / max(1, member_count)
        underserved = [
            row
            for row in coverage_rows
            if row.get("strong_match_count", 0) <= 0
        ]

        return self._friend_readiness_summary(
            member_count=member_count,
            average_group_fit=average_group_fit,
            member_coverage_share=coverage_share,
            consensus_group_fit=route_average_consensus_fit,
            consensus_gap=route_consensus_gap,
            group_fit_summary={
                "average_fit": average_group_fit,
                "average_group_average_fit": self._rounded_optional(route_average_group_fit),
                "average_consensus_fit": self._rounded_optional(route_average_consensus_fit),
                "average_min_fit_weight": self._rounded_optional(route_average_min_fit_weight),
                "consensus_gap": self._rounded_optional(route_consensus_gap),
                "members": group_members,
                "underserved_members": underserved,
            },
            slate_summary={
                "member_coverage": coverage_rows,
                "underserved_members": underserved,
            },
        )

    def _planned_duration_alignment(self, result):
        booking_plan = (result or {}).get("booking_plan") or {}
        trip_packet = (result or {}).get("trip_packet") or {}
        duration_alignment = (
            booking_plan.get("duration_alignment")
            or trip_packet.get("duration_alignment")
            or {}
        )
        if duration_alignment:
            return duration_alignment
        return {
            "status": "aligned",
            "severity": "pass",
            "headline": "Trip duration matches the route.",
            "message": "The selected trip style, itinerary days, and travel dates agree.",
        }

    def _duration_alignment_check_status(self, duration_alignment):
        status = (duration_alignment or {}).get("status")
        if status in {None, "", "aligned"}:
            return "pass"
        if status == "needs_attention":
            return "fail"
        return "warn"

    def _scenario_report(self, mode, status, headline, metrics, checks, strengths=None, warnings=None):
        next_actions = [
            check["message"]
            for check in checks
            if check["status"] in {"fail", "warn"} and check.get("message")
        ]
        return {
            "mode": mode,
            "status": status,
            "ready_for_friend_testing": status == "ready",
            "beta_testable": status in {"ready", "watch"},
            "headline": headline,
            "metrics": metrics,
            "checks": checks,
            "strengths": strengths or [],
            "warnings": list(dict.fromkeys((warnings or []) + [
                check["message"]
                for check in checks
                if check["status"] == "fail" and check.get("message")
            ]))[:5],
            "next_actions": list(dict.fromkeys(next_actions))[:5],
        }

    def _travel_quote_readiness(self, result):
        trip_packet = (result or {}).get("trip_packet") or {}
        price_breakdown = (result or {}).get("price_breakdown") or {}
        cost_confidence = trip_packet.get("cost_confidence") or {}
        quote_plan = (
            price_breakdown.get("quote_plan")
            or trip_packet.get("quote_plan")
            or cost_confidence.get("quote_plan")
            or {}
        )
        required_count = int(quote_plan.get("required_count") or 0)
        ready_count = int(quote_plan.get("ready_count") or 0)
        missing_inputs = quote_plan.get("missing_inputs") or []
        return {
            "status": quote_plan.get("status") or ("local_estimate_only" if required_count == 0 else "needs_inputs"),
            "required_count": required_count,
            "ready_count": ready_count,
            "missing_input_count": len(missing_inputs),
            "ready_coverage": (ready_count / required_count) if required_count else None,
            "missing_inputs": missing_inputs,
            "message": quote_plan.get("message"),
        }

    def _scenario_remediation_plan(
        self,
        checks,
        test_verdict=None,
        friend_readiness=None,
        quote_readiness=None,
        model_confidence=None,
        trip_logistics_readiness=None,
        duration_alignment=None,
    ):
        buckets = {}

        def add(bucket, label, action, severity="watch", priority=50):
            if not action:
                return
            row = buckets.setdefault(bucket, {
                "id": bucket,
                "label": label,
                "severity": severity,
                "priority": priority,
                "actions": [],
            })
            if action not in row["actions"]:
                row["actions"].append(action)
            if severity == "needs_attention":
                row["severity"] = "needs_attention"
            row["priority"] = min(row.get("priority", priority), priority)

        for check in checks or []:
            status = check.get("status")
            if status not in {"fail", "warn", "unknown"}:
                continue
            check_name = check.get("name") or "unknown"
            check_priority = {
                "provider_health": 0,
                "candidate_depth": 1,
                "stop_coverage": 1,
                "travel_quotes": 2,
                "duration_alignment": 2,
                "trip_logistics": 2,
                "booking_readiness": 2,
                "friend_coverage": 3,
                "friend_route_coverage": 3,
                "group_fit": 4,
                "group_consensus": 4,
                "friend_route_fit": 4,
                "route_group_consensus": 4,
                "model_confidence": 5,
                "route_model_confidence": 5,
                "local_events": 6,
                "social_events": 6,
            }.get(check_name, 20)
            add(
                f"check_{check_name}",
                check.get("label") or "Readiness check",
                check.get("message"),
                "needs_attention" if status in {"fail", "unknown"} else "watch",
                check_priority,
            )

        for blocker in (test_verdict or {}).get("blockers") or []:
            add("scenario_blockers", "Friend-test blockers", blocker, "needs_attention", 6)
        for action in (test_verdict or {}).get("next_actions") or []:
            add(
                "verdict_actions",
                "Friend-test next actions",
                action,
                "needs_attention" if (test_verdict or {}).get("status") == "needs_attention" else "watch",
                7,
            )

        if (friend_readiness or {}).get("status") == "needs_attention":
            action = (
                ((friend_readiness or {}).get("next_actions") or [None])[0]
                or (friend_readiness or {}).get("headline")
                or "Rebuild with group-friendly scoring or swap in stops for underserved travelers."
            )
            add("friend_coverage", "Friend coverage", action, "needs_attention", 3)
        elif (friend_readiness or {}).get("status") == "watch":
            action = (
                ((friend_readiness or {}).get("next_actions") or [None])[0]
                or ((friend_readiness or {}).get("watchouts") or [None])[0]
            )
            add("friend_coverage", "Friend coverage", action, "watch", 3)

        if (quote_readiness or {}).get("required_count") and (quote_readiness or {}).get("status") != "ready_to_quote":
            missing = (quote_readiness or {}).get("missing_inputs") or []
            action = (
                f"Add {', '.join(missing[:3])} so flight/stay quote links are ready."
                if missing
                else (quote_readiness or {}).get("message")
                or "Add missing trip basics so flight/stay quote links are ready."
            )
            add("travel_quotes", "Travel quote readiness", action, "needs_attention", 2)

        if (duration_alignment or {}).get("status") in {"watch", "needs_attention"}:
            add(
                "duration_alignment",
                "Trip duration",
                (duration_alignment or {}).get("next_action")
                or (duration_alignment or {}).get("message")
                or "Confirm whether this is a day, weekend, or vacation plan.",
                "needs_attention" if (duration_alignment or {}).get("status") == "needs_attention" else "watch",
                2,
            )

        for source, label in [
            (model_confidence or {}, "Model signal"),
            (trip_logistics_readiness or {}, "Trip logistics"),
        ]:
            for action in source.get("next_actions") or []:
                add(label.lower().replace(" ", "_"), label, action, "watch", 8)
            for warning in source.get("warnings") or []:
                add(label.lower().replace(" ", "_"), label, warning, "needs_attention", 8)

        ordered = sorted(
            buckets.values(),
            key=lambda row: (
                0 if row["severity"] == "needs_attention" else 1,
                row.get("priority", 50),
                row["label"],
            ),
        )
        return [
            {
                **row,
                "adjustment": self._remediation_adjustment(row, friend_readiness, quote_readiness),
                "actions": row["actions"][:3],
            }
            for row in ordered[:8]
        ]

    def _remediation_adjustment(self, row, friend_readiness=None, quote_readiness=None):
        row_id = row.get("id") or ""
        if row_id in {"check_provider_health", "check_candidate_depth", "check_stop_coverage"}:
            return {
                "kind": "rerun_recommendations",
                "scoring_profile": "fresh_discovery",
                "radius_multiplier": 1.5,
                "clear_excluded_tag_groups": True,
                "reason": "Broaden retrieval before judging quality.",
            }
        if row_id in {"check_local_authentic_mix", "check_hidden_gem_presence", "check_generic_risk"}:
            return {
                "kind": "rerun_recommendations",
                "scoring_profile": "authenticity_forward",
                "radius_multiplier": 1.25,
                "reason": "Favor local-authentic and hidden-gem candidates.",
            }
        if row_id in {"check_variety", "check_intent_coverage", "check_first_swipe_variety", "check_route_variety"}:
            return {
                "kind": "rerun_recommendations",
                "scoring_profile": "fresh_discovery",
                "radius_multiplier": 1.25,
                "reason": "Increase category and opening-card variety.",
            }
        if row_id in {
            "check_group_fit",
            "check_group_consensus",
            "check_friend_coverage",
            "check_party_fit",
            "check_friend_route_coverage",
            "check_friend_route_fit",
            "check_route_group_consensus",
            "friend_coverage",
        }:
            underserved = (friend_readiness or {}).get("underserved_members") or []
            boost_tags = []
            for member in underserved:
                for tag in member.get("suggested_query_tags") or []:
                    if tag not in boost_tags:
                        boost_tags.append(tag)
            return {
                "kind": "rerun_recommendations",
                "scoring_profile": "group_friendly",
                "boost_query_tags": boost_tags[:5],
                "radius_multiplier": 1.25,
                "reason": "Rebalance the basket around underserved travelers.",
            }
        if row_id in {"travel_quotes", "check_travel_quotes"}:
            return {
                "kind": "collect_trip_inputs",
                "required_inputs": (quote_readiness or {}).get("missing_inputs") or [],
                "reason": "Finish trip basics before quote links can be trusted.",
            }
        if row_id in {"duration_alignment", "check_duration_alignment"}:
            return {
                "kind": "collect_trip_inputs",
                "required_inputs": ["trip_style", "travel_dates"],
                "reason": "Align trip style, route length, and dates before trusting booking handoff.",
            }
        if row_id in {"check_local_events"}:
            return {
                "kind": "scout_local_events",
                "reason": "Refresh local event sources or add a community event for this destination.",
            }
        if row_id in {"check_social_events"}:
            return {
                "kind": "collect_event_social_signal",
                "reason": "Ask friends to mark Interested/Going or add a social event anchor.",
            }
        if row_id in {"check_model_confidence", "check_route_model_confidence", "model_signal"}:
            return {
                "kind": "collect_feedback",
                "reason": "Collect accepts, rejects, ratings, or keep transparent ranking until the model is trusted.",
            }
        if row_id in {"check_trip_logistics", "trip_logistics"}:
            return {
                "kind": "collect_trip_inputs",
                "required_inputs": ["origin", "dates", "local_transport"],
                "reason": "Complete trip logistics before sharing the plan.",
            }
        if row_id in {"check_booking_readiness"}:
            return {
                "kind": "collect_booking_details",
                "reason": "Save booking links, providers, confirmation numbers, and costs in Adventour.",
            }
        return None

    def _readiness_check(self, name, label, status, value, target, message):
        return {
            "name": name,
            "label": label,
            "status": status,
            "value": self._rounded_optional(value) if isinstance(value, float) else value,
            "target": target,
            "message": "" if status == "pass" else message,
        }

    def _threshold_status(self, value, pass_min, warn_min):
        if value is None:
            return "unknown"
        if value >= pass_min:
            return "pass"
        if value >= warn_min:
            return "warn"
        return "fail"

    def _max_threshold_status(self, value, pass_max, warn_max):
        if value is None:
            return "unknown"
        if value <= pass_max:
            return "pass"
        if value <= warn_max:
            return "warn"
        return "fail"

    def _consensus_status(self, consensus_fit, consensus_gap):
        fit_status = self._threshold_status(consensus_fit, pass_min=0.68, warn_min=0.55)
        gap_status = self._max_threshold_status(consensus_gap, pass_max=0.06, warn_max=0.12)
        statuses = {fit_status, gap_status} - {"unknown"}
        if "fail" in statuses:
            return "fail"
        if "warn" in statuses:
            return "warn"
        if not statuses:
            return "unknown"
        return "pass"

    def _scenario_status(self, checks):
        statuses = {check.get("status") for check in checks}
        if "fail" in statuses:
            return "needs_attention"
        if "warn" in statuses:
            return "watch"
        return "ready"

    def _scenario_headline(self, status, subject):
        if status == "ready":
            return f"{subject} is ready for trusted friend testing."
        if status == "watch":
            return f"{subject} is beta-testable, but has tradeoffs to watch."
        return f"{subject} needs tuning before it should be trusted."

    def _rounded_optional(self, value):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        return _round_metric(value)

    def _explanation_coverage(self, recommendations):
        if not recommendations:
            return 0.0
        explained = 0
        for item in recommendations:
            story = item.get("recommendation_story") or {}
            if story.get("headline") and (story.get("reasons") or story.get("metrics")):
                explained += 1
            elif item.get("explanation") or item.get("explanation_details"):
                explained += 1
        return explained / len(recommendations)

    def _result_variety_groups(self, recommendations):
        groups = set()
        for item in recommendations:
            types = set((item.get("display") or {}).get("types") or item.get("types") or [])
            for group, group_types in SCENARIO_TYPE_GROUPS.items():
                if types.intersection(group_types):
                    groups.add(group)
            if not types:
                groups.add("unknown")
        return groups

    def _swap_coverage(self, stops):
        if not stops:
            return 0.0
        swappable = sum(1 for stop in stops if stop.get("alternatives"))
        return swappable / len(stops)

    def _price_estimate_ready(self, price_breakdown):
        per_person = (price_breakdown or {}).get("per_person") or {}
        return (
            per_person.get("total_known_low") is not None
            and per_person.get("total_known_high") is not None
        )

    def _comparison_delta(self, baseline, learned):
        baseline_metrics = baseline.get("metrics_at_k") or {}
        learned_metrics = learned.get("metrics_at_k") or {}
        all_k = sorted(set(baseline_metrics.keys()) | set(learned_metrics.keys()), key=lambda value: int(value))
        metric_deltas = {}
        for k in all_k:
            baseline_at_k = baseline_metrics.get(k) or {}
            learned_at_k = learned_metrics.get(k) or {}
            metric_deltas[k] = {
                "hit_rate": _round_metric(_safe_float(learned_at_k.get("hit_rate")) - _safe_float(baseline_at_k.get("hit_rate"))),
                "precision": _round_metric(_safe_float(learned_at_k.get("precision")) - _safe_float(baseline_at_k.get("precision"))),
                "average_label": _round_metric(_safe_float(learned_at_k.get("average_label")) - _safe_float(baseline_at_k.get("average_label"))),
                "weighted_average_label": _round_metric(_safe_float(learned_at_k.get("weighted_average_label")) - _safe_float(baseline_at_k.get("weighted_average_label"))),
                "ndcg": _round_metric(_safe_float(learned_at_k.get("ndcg")) - _safe_float(baseline_at_k.get("ndcg"))),
            }

        return {
            "mean_reciprocal_rank": _round_metric(
                _safe_float(learned.get("mean_reciprocal_rank")) - _safe_float(baseline.get("mean_reciprocal_rank"))
            ),
            "metrics_at_k": metric_deltas,
            "exposure_quality_at_k": self._exposure_quality_delta(
                baseline.get("exposure_quality_at_k") or {},
                learned.get("exposure_quality_at_k") or {},
            ),
            "outcome_quality": self._summary_delta(
                baseline.get("outcome_quality") or {},
                learned.get("outcome_quality") or {},
                (
                    "local_quality_score",
                    "average_positive_authenticity",
                    "average_positive_hidden_gem",
                    "average_positive_chain_probability",
                    "average_positive_group_min_fit",
                    "average_positive_group_fairness_penalty",
                ),
            ),
            "event_anchor_quality": self._summary_delta(
                baseline.get("event_anchor_quality") or {},
                learned.get("event_anchor_quality") or {},
                (
                    "event_backed_positive_rate",
                    "average_positive_event_fit",
                    "average_positive_route_anchor_score",
                    "event_anchor_score",
                    "reservation_ready_rate",
                    "source_ready_rate",
                    "friend_signal_positive_rate",
                    "average_positive_social_signal",
                ),
            ),
            "group_balance": self._summary_delta(
                baseline.get("group_balance") or {},
                learned.get("group_balance") or {},
                (
                    "average_lowest_member_fit",
                    "average_group_consensus_fit",
                    "average_group_consensus_gap",
                    "average_member_fit_spread",
                    "average_group_fairness_penalty",
                    "underserved_positive_rate",
                ),
            ),
            "guardrail_status_changed": (baseline.get("guardrails") or {}).get("status") != (learned.get("guardrails") or {}).get("status"),
            "baseline_guardrail_status": (baseline.get("guardrails") or {}).get("status"),
            "learned_guardrail_status": (learned.get("guardrails") or {}).get("status"),
        }

    def _exposure_quality_delta(self, baseline, learned):
        all_k = sorted(set(baseline.keys()) | set(learned.keys()), key=lambda value: int(value))
        return {
            k: self._summary_delta(
                baseline.get(k) or {},
                learned.get(k) or {},
                (
                    "local_quality_score",
                    "average_authenticity",
                    "average_hidden_gem",
                    "average_chain_probability",
                    "average_group_min_fit",
                    "average_group_fairness_penalty",
                ),
            )
            for k in all_k
        }

    def _summary_delta(self, baseline, learned, fields):
        return {
            field: _round_metric(_safe_float(learned.get(field)) - _safe_float(baseline.get(field)))
            for field in fields
        }

    def _promotion_gate(self, baseline, learned, delta, segment_delta=None, baseline_segments=None, learned_segments=None):
        request_count = int(learned.get("request_count") or 0)
        checks = [
            self._gate_check(
                "sample_size",
                "Enough evaluated requests",
                request_count >= MIN_PROMOTION_REQUESTS,
                f"{request_count}/{MIN_PROMOTION_REQUESTS} requests evaluated",
                "Collect more accepted/rejected outcomes before trusting a learned reranker.",
            ),
            self._gate_check(
                "ranking_improved",
                "Ranking quality did not regress",
                self._ranking_improved(delta),
                self._ranking_delta_message(delta),
                "Keep the transparent ranker until the learned model improves MRR or NDCG.",
            ),
            self._gate_check(
                "guardrails_safe",
                "Mission guardrails are safe",
                self._guardrail_status_rank((learned.get("guardrails") or {}).get("status"))
                <= self._guardrail_status_rank((baseline.get("guardrails") or {}).get("status"))
                and (learned.get("guardrails") or {}).get("status") != "fail",
                f"{(baseline.get('guardrails') or {}).get('status')} -> {(learned.get('guardrails') or {}).get('status')}",
                "Do not promote a model that makes authenticity, chain risk, or group fairness guardrails worse.",
            ),
            self._gate_check(
                "local_quality_safe",
                "Local-authentic quality is preserved",
                self._local_quality_safe(delta),
                self._quality_delta_message(delta),
                "Do not promote a model that wins clicks by drifting away from Adventour's local-authentic mission.",
            ),
            self._gate_check(
                "group_balance_safe",
                "Group balance is preserved",
                self._group_balance_safe(baseline, learned, delta),
                self._group_delta_message(delta),
                "Do not promote a model that leaves friends or travel-party members under-served.",
            ),
            self._gate_check(
                "critical_segments_safe",
                "Critical Adventour segments are preserved",
                self._critical_segments_safe(segment_delta or {}, baseline_segments or {}, learned_segments or {}),
                self._critical_segment_delta_message(segment_delta or {}, baseline_segments or {}, learned_segments or {}),
                "Do not promote a model that regresses local-authentic, friend-adjusted, or event-backed recommendations.",
            ),
            self._gate_check(
                "event_anchor_safe",
                "Event and social anchors are preserved",
                self._event_anchor_safe(baseline, learned, delta),
                self._event_anchor_delta_message(delta),
                "Do not promote a model that weakens timely, bookable, friend-aware local-event anchors.",
            ),
        ]

        if checks[0]["status"] == "fail":
            status = "insufficient_data"
        elif any(check["status"] == "fail" for check in checks):
            status = "fail"
        else:
            status = "pass"

        return {
            "status": status,
            "can_promote": status == "pass",
            "checks": checks,
            "summary": self._promotion_summary(status),
        }

    def _gate_check(self, name, label, passed, value, message):
        return {
            "name": name,
            "label": label,
            "status": "pass" if passed else "fail",
            "value": value,
            "message": "" if passed else message,
        }

    def _ranking_improved(self, delta):
        if _safe_float(delta.get("mean_reciprocal_rank")) > 0:
            return True
        for metrics in (delta.get("metrics_at_k") or {}).values():
            if _safe_float(metrics.get("ndcg")) > 0:
                return True
            if _safe_float(metrics.get("weighted_average_label")) > 0:
                return True
        return False

    def _ranking_delta_message(self, delta):
        first_metrics = next(iter((delta.get("metrics_at_k") or {}).values()), {})
        return (
            f"MRR {delta.get('mean_reciprocal_rank', 0):+.4f}, "
            f"NDCG {first_metrics.get('ndcg', 0):+.4f}"
        )

    def _guardrail_status_rank(self, status):
        return {
            "pass": 0,
            "unknown": 1,
            "warn": 2,
            "fail": 3,
        }.get(status, 3)

    def _local_quality_safe(self, delta):
        quality_delta = delta.get("outcome_quality") or {}
        exposure_delta = self._primary_exposure_delta(delta)
        return (
            _safe_float(quality_delta.get("local_quality_score")) >= -0.03
            and _safe_float(quality_delta.get("average_positive_authenticity")) >= -0.05
            and _safe_float(quality_delta.get("average_positive_chain_probability")) <= 0.05
            and _safe_float(exposure_delta.get("local_quality_score")) >= -0.03
            and _safe_float(exposure_delta.get("average_authenticity")) >= -0.05
            and _safe_float(exposure_delta.get("average_chain_probability")) <= 0.05
        )

    def _quality_delta_message(self, delta):
        quality_delta = delta.get("outcome_quality") or {}
        exposure_delta = self._primary_exposure_delta(delta)
        return (
            f"local {quality_delta.get('local_quality_score', 0):+.4f}, "
            f"auth {quality_delta.get('average_positive_authenticity', 0):+.4f}, "
            f"chain {quality_delta.get('average_positive_chain_probability', 0):+.4f}; "
            f"top exposure local {exposure_delta.get('local_quality_score', 0):+.4f}, "
            f"chain {exposure_delta.get('average_chain_probability', 0):+.4f}"
        )

    def _primary_exposure_delta(self, delta):
        exposure_delta = delta.get("exposure_quality_at_k") or {}
        if not exposure_delta:
            return {}
        first_k = sorted(exposure_delta.keys(), key=lambda value: int(value))[0]
        return exposure_delta.get(first_k) or {}

    def _group_balance_safe(self, baseline, learned, delta):
        baseline_group_count = (baseline.get("group_balance") or {}).get("group_positive_count") or 0
        learned_group_count = (learned.get("group_balance") or {}).get("group_positive_count") or 0
        if not baseline_group_count and not learned_group_count:
            return True

        group_delta = delta.get("group_balance") or {}
        return (
            _safe_float(group_delta.get("average_lowest_member_fit")) >= -0.05
            and _safe_float(group_delta.get("average_group_consensus_fit")) >= -0.05
            and _safe_float(group_delta.get("average_group_consensus_gap")) <= 0.05
            and _safe_float(group_delta.get("average_group_fairness_penalty")) <= 0.05
            and _safe_float(group_delta.get("underserved_positive_rate")) <= 0.1
        )

    def _group_delta_message(self, delta):
        group_delta = delta.get("group_balance") or {}
        return (
            f"lowest fit {group_delta.get('average_lowest_member_fit', 0):+.4f}, "
            f"consensus {group_delta.get('average_group_consensus_fit', 0):+.4f}, "
            f"gap {group_delta.get('average_group_consensus_gap', 0):+.4f}, "
            f"fairness penalty {group_delta.get('average_group_fairness_penalty', 0):+.4f}, "
            f"underserved {group_delta.get('underserved_positive_rate', 0):+.4f}"
        )

    def _event_anchor_safe(self, baseline, learned, delta):
        baseline_event_count = (baseline.get("event_anchor_quality") or {}).get("event_backed_positive_count") or 0
        learned_event_count = (learned.get("event_anchor_quality") or {}).get("event_backed_positive_count") or 0
        if not baseline_event_count and not learned_event_count:
            return True

        event_delta = delta.get("event_anchor_quality") or {}
        return (
            _safe_float(event_delta.get("event_backed_positive_rate")) >= -0.05
            and _safe_float(event_delta.get("average_positive_event_fit")) >= -0.08
            and _safe_float(event_delta.get("event_anchor_score")) >= -0.08
            and _safe_float(event_delta.get("reservation_ready_rate")) >= -0.15
            and _safe_float(event_delta.get("friend_signal_positive_rate")) >= -0.15
        )

    def _event_anchor_delta_message(self, delta):
        event_delta = delta.get("event_anchor_quality") or {}
        return (
            f"event rate {event_delta.get('event_backed_positive_rate', 0):+.4f}, "
            f"fit {event_delta.get('average_positive_event_fit', 0):+.4f}, "
            f"anchor {event_delta.get('event_anchor_score', 0):+.4f}, "
            f"reservation {event_delta.get('reservation_ready_rate', 0):+.4f}, "
            f"friend signal {event_delta.get('friend_signal_positive_rate', 0):+.4f}"
        )

    def _critical_segments_safe(self, segment_delta, baseline_segments, learned_segments):
        return not self._critical_segment_failures(segment_delta, baseline_segments, learned_segments)

    def _critical_segment_delta_message(self, segment_delta, baseline_segments, learned_segments):
        failures = self._critical_segment_failures(segment_delta, baseline_segments, learned_segments)
        if not failures:
            return "local_authentic, friend_adjusted, and event_backed segments preserved"
        return "; ".join(
            f"{failure['segment']}: {failure['reason']} ({failure['value']})"
            for failure in failures[:3]
        )

    def _critical_segment_failures(self, segment_delta, baseline_segments, learned_segments):
        critical_segments = ("local_authentic", "friend_adjusted", "event_backed")
        failures = []
        for segment in critical_segments:
            baseline_summary = baseline_segments.get(segment) or {}
            learned_summary = learned_segments.get(segment) or {}
            baseline_count = int(baseline_summary.get("request_count") or 0)
            learned_count = int(learned_summary.get("request_count") or 0)
            if max(baseline_count, learned_count) < 3:
                continue

            delta = segment_delta.get(segment) or {}
            guardrail_status = (learned_summary.get("guardrails") or {}).get("status")
            baseline_guardrail_status = (baseline_summary.get("guardrails") or {}).get("status")
            if (
                guardrail_status == "fail"
                or self._guardrail_status_rank(guardrail_status) > self._guardrail_status_rank(baseline_guardrail_status)
            ):
                failures.append({
                    "segment": segment,
                    "reason": "guardrail regression",
                    "value": f"{baseline_guardrail_status} -> {guardrail_status}",
                })
                continue

            first_metrics = self._first_metric_delta(delta.get("metrics_at_k") or {})
            if _safe_float(delta.get("mean_reciprocal_rank")) < -0.03:
                failures.append({
                    "segment": segment,
                    "reason": "MRR regression",
                    "value": f"{delta.get('mean_reciprocal_rank', 0):+.4f}",
                })
            elif _safe_float(first_metrics.get("hit_rate")) < -0.05:
                failures.append({
                    "segment": segment,
                    "reason": "top hit-rate regression",
                    "value": f"{first_metrics.get('hit_rate', 0):+.4f}",
                })
            elif _safe_float(first_metrics.get("weighted_average_label")) < -0.05:
                failures.append({
                    "segment": segment,
                    "reason": "top outcome-quality regression",
                    "value": f"{first_metrics.get('weighted_average_label', 0):+.4f}",
                })
        return failures

    def _first_metric_delta(self, metrics_at_k):
        if not metrics_at_k:
            return {}
        first_k = sorted(metrics_at_k.keys(), key=lambda value: int(value))[0]
        return metrics_at_k.get(first_k) or {}

    def _promotion_summary(self, status):
        if status == "pass":
            return "Learned reranker passed ranking, local-quality, group-balance, and critical-segment promotion checks."
        if status == "insufficient_data":
            return "Collect more real Adventour outcomes before promoting this learned reranker."
        return "Keep the transparent ranker active; the learned reranker failed at least one promotion check."

    def _request_summary(self, request_id, rows, k_values, positive_threshold):
        ranked_rows = sorted(rows, key=lambda row: row["rank_position"])
        labels = [_safe_float(row.get("label")) for row in ranked_rows]
        weights = [_safe_float(row.get("outcome_weight"), 1.0) for row in ranked_rows]
        first_positive_rank = next(
            (
                row["rank_position"]
                for row in ranked_rows
                if _safe_float(row.get("label")) >= positive_threshold
            ),
            None,
        )
        positive_count = sum(1 for label in labels if label >= positive_threshold)

        metrics_at_k = {}
        for k in k_values:
            top_labels = labels[:k]
            top_weights = weights[:k]
            denominator = min(k, len(top_labels)) or 1
            positive_at_k = sum(1 for label in top_labels if label >= positive_threshold)
            ideal_labels = sorted(labels, reverse=True)[:k]
            ideal_dcg = _dcg(ideal_labels)
            ndcg = _dcg(top_labels) / ideal_dcg if ideal_dcg else 0.0
            weight_sum = sum(top_weights)
            weighted_average_label = (
                sum(label * weight for label, weight in zip(top_labels, top_weights)) / weight_sum
                if weight_sum
                else 0.0
            )
            metrics_at_k[str(k)] = {
                "hit_rate": 1.0 if positive_at_k else 0.0,
                "precision": _round_metric(positive_at_k / denominator),
                "average_label": _round_metric(sum(top_labels) / denominator),
                "weighted_average_label": _round_metric(weighted_average_label),
                "ndcg": _round_metric(ndcg),
            }

        return {
            "request_id": request_id,
            "scoring_profile": self._request_scoring_profile(ranked_rows),
            "segments": self._request_segments(ranked_rows),
            "example_count": len(ranked_rows),
            "positive_count": positive_count,
            "first_positive_rank": first_positive_rank,
            "mrr": _round_metric(1 / first_positive_rank) if first_positive_rank else 0.0,
            "metrics_at_k": metrics_at_k,
            "exposure_quality_at_k": self._exposure_quality_at_k(ranked_rows, k_values),
            "outcome_quality": self._outcome_quality(ranked_rows, positive_threshold),
            "group_balance": self._group_balance(ranked_rows, positive_threshold),
            "event_anchor_quality": self._event_anchor_quality(ranked_rows, positive_threshold),
        }

    def _request_scoring_profile(self, rows):
        profiles = {
            row.get("scoring_profile")
            or (row.get("ranking") or {}).get("scoring_profile")
            or (row.get("components") or {}).get("scoring_profile")
            for row in rows
        }
        profiles = {profile for profile in profiles if profile}
        if not profiles:
            return "unknown"
        if len(profiles) > 1:
            return "mixed"
        return next(iter(profiles))

    def _request_segments(self, rows):
        segments = set()
        is_group = any(self._is_group_row(row) or row.get("context") == "group" for row in rows)
        segments.add("group" if is_group else "solo")

        if any(self._is_local_authentic_row(row) for row in rows):
            segments.add("local_authentic")
        if any(self._is_generic_risk_row(row) for row in rows):
            segments.add("generic_risk")
        if any(self._is_friend_adjusted_row(row) for row in rows):
            segments.add("friend_adjusted")
        if any(self._is_low_signal_row(row) for row in rows):
            segments.add("low_signal")
        if any(_safe_float(row.get("hidden_gem_score")) >= 0.6 for row in rows):
            segments.add("hidden_gem")
        if any(self._is_event_backed_row(row) for row in rows):
            segments.add("event_backed")

        return sorted(segments)

    def _is_local_authentic_row(self, row):
        label = str(row.get("authenticity_label") or "").lower()
        return (
            _safe_float(row.get("authenticity_score")) >= 0.7
            or _safe_float(row.get("hidden_gem_score")) >= 0.45
            or label in {"hidden gem", "local-feeling"}
        )

    def _is_generic_risk_row(self, row):
        label = str(row.get("authenticity_label") or "").lower()
        return _safe_float(row.get("chain_probability")) >= 0.5 or label == "generic risk"

    def _is_friend_adjusted_row(self, row):
        retrieval_context = row.get("retrieval_context") if isinstance(row.get("retrieval_context"), dict) else {}
        return bool(
            row.get("friend_adjusted_retrieval")
            or retrieval_context.get("friend_adjusted")
            or row.get("boost_query_tags")
            or retrieval_context.get("boost_query_tags")
        )

    def _is_low_signal_row(self, row):
        components = row.get("components") if isinstance(row.get("components"), dict) else {}
        preference_confidence = _optional_float(row.get("preference_confidence"))
        if preference_confidence is None:
            preference_confidence = _optional_float(components.get("preference_confidence"))
        signal_count = _optional_float(row.get("average_member_signal_count"))
        if signal_count is None:
            signal_count = _optional_float(components.get("average_member_signal_count"))

        return (
            preference_confidence is not None
            and preference_confidence < 0.35
        ) or (
            signal_count is not None
            and signal_count < 3
        )

    def _is_event_backed_row(self, row):
        components = row.get("components") if isinstance(row.get("components"), dict) else {}
        return bool(
            row.get("local_event_backed")
            or row.get("local_event_match")
            or _safe_float(row.get("local_event_fit")) >= 0.45
            or _safe_float(components.get("local_event_fit")) >= 0.45
        )

    def _outcome_quality(self, rows, positive_threshold):
        positive_rows = [
            row
            for row in rows
            if _safe_float(row.get("label")) >= positive_threshold
        ]

        authenticity_values = self._quality_values(positive_rows, "authenticity_score")
        hidden_gem_values = self._quality_values(positive_rows, "hidden_gem_score")
        chain_values = self._quality_values(positive_rows, "chain_probability")
        group_min_fit_values = self._quality_values(positive_rows, "group_min_fit")
        group_fairness_values = self._quality_values(positive_rows, "group_fairness_penalty")
        local_quality_values = []

        for row in positive_rows:
            authenticity = _optional_float(row.get("authenticity_score"))
            hidden_gem = _optional_float(row.get("hidden_gem_score"))
            chain_probability = _optional_float(row.get("chain_probability"))
            if authenticity is None or hidden_gem is None or chain_probability is None:
                continue
            local_quality_values.append((authenticity + hidden_gem + (1 - chain_probability)) / 3)

        return {
            "positive_quality_count": sum(
                1
                for row in positive_rows
                if any(
                    _optional_float(row.get(field)) is not None
                    for field in ("authenticity_score", "hidden_gem_score", "chain_probability")
                )
            ),
            "authenticity_count": len(authenticity_values),
            "hidden_gem_count": len(hidden_gem_values),
            "chain_probability_count": len(chain_values),
            "group_min_fit_count": len(group_min_fit_values),
            "group_fairness_penalty_count": len(group_fairness_values),
            "local_quality_count": len(local_quality_values),
            "average_positive_authenticity": self._average_or_zero(authenticity_values),
            "average_positive_hidden_gem": self._average_or_zero(hidden_gem_values),
            "average_positive_chain_probability": self._average_or_zero(chain_values),
            "average_positive_group_min_fit": self._average_or_zero(group_min_fit_values),
            "average_positive_group_fairness_penalty": self._average_or_zero(group_fairness_values),
            "local_quality_score": self._average_or_zero(local_quality_values),
        }

    def _quality_values(self, rows, field):
        return [
            value
            for value in (_optional_float(row.get(field)) for row in rows)
            if value is not None
        ]

    def _exposure_quality_at_k(self, ranked_rows, k_values):
        return {
            str(k): self._exposure_quality(ranked_rows[:k])
            for k in k_values
        }

    def _exposure_quality(self, rows):
        authenticity_values = self._quality_values(rows, "authenticity_score")
        hidden_gem_values = self._quality_values(rows, "hidden_gem_score")
        chain_values = self._quality_values(rows, "chain_probability")
        group_min_fit_values = self._quality_values(rows, "group_min_fit")
        group_fairness_values = self._quality_values(rows, "group_fairness_penalty")
        local_quality_values = []

        for row in rows:
            authenticity = _optional_float(row.get("authenticity_score"))
            hidden_gem = _optional_float(row.get("hidden_gem_score"))
            chain_probability = _optional_float(row.get("chain_probability"))
            if authenticity is None or hidden_gem is None or chain_probability is None:
                continue
            local_quality_values.append((authenticity + hidden_gem + (1 - chain_probability)) / 3)

        return {
            "exposed_count": len(rows),
            "local_quality_count": len(local_quality_values),
            "authenticity_count": len(authenticity_values),
            "hidden_gem_count": len(hidden_gem_values),
            "chain_probability_count": len(chain_values),
            "group_min_fit_count": len(group_min_fit_values),
            "group_fairness_penalty_count": len(group_fairness_values),
            "local_quality_score": self._average_or_zero(local_quality_values),
            "average_authenticity": self._average_or_zero(authenticity_values),
            "average_hidden_gem": self._average_or_zero(hidden_gem_values),
            "average_chain_probability": self._average_or_zero(chain_values),
            "average_group_min_fit": self._average_or_zero(group_min_fit_values),
            "average_group_fairness_penalty": self._average_or_zero(group_fairness_values),
        }

    def _average_or_zero(self, values):
        if not values:
            return 0.0
        return _round_metric(sum(values) / len(values))

    def _group_balance(self, rows, positive_threshold):
        positive_rows = [
            row
            for row in rows
            if _safe_float(row.get("label")) >= positive_threshold
        ]
        group_rows = [
            row
            for row in positive_rows
            if self._is_group_row(row)
        ]
        if not group_rows:
            return {
                "group_positive_count": 0,
                "member_fit_count": 0,
                "average_lowest_member_fit": 0.0,
                "average_group_consensus_fit": 0.0,
                "average_group_consensus_gap": 0.0,
                "average_member_fit_spread": 0.0,
                "average_group_fairness_penalty": 0.0,
                "underserved_positive_count": 0,
                "underserved_positive_rate": 0.0,
            }

        lowest_values = [
            self._lowest_member_fit(row)
            for row in group_rows
        ]
        spread_values = [
            self._member_fit_spread(row)
            for row in group_rows
        ]
        consensus_values = [
            self._group_consensus_fit(row)
            for row in group_rows
        ]
        consensus_gap_values = [
            self._group_consensus_gap(row)
            for row in group_rows
        ]
        fairness_values = [
            _optional_float(row.get("group_fairness_penalty"))
            for row in group_rows
        ]
        lowest_values = [value for value in lowest_values if value is not None]
        spread_values = [value for value in spread_values if value is not None]
        consensus_values = [value for value in consensus_values if value is not None]
        consensus_gap_values = [value for value in consensus_gap_values if value is not None]
        fairness_values = [value for value in fairness_values if value is not None]
        underserved_count = sum(
            1
            for row in group_rows
            if self._group_row_is_underserved(row)
        )

        return {
            "group_positive_count": len(group_rows),
            "member_fit_count": sum(int(row.get("member_fit_count") or 0) for row in group_rows),
            "average_lowest_member_fit": self._average_or_zero(lowest_values),
            "group_consensus_fit_count": len(consensus_values),
            "group_consensus_gap_count": len(consensus_gap_values),
            "average_group_consensus_fit": self._average_or_zero(consensus_values),
            "average_group_consensus_gap": self._average_or_zero(consensus_gap_values),
            "average_member_fit_spread": self._average_or_zero(spread_values),
            "average_group_fairness_penalty": self._average_or_zero(fairness_values),
            "underserved_positive_count": underserved_count,
            "underserved_positive_rate": _round_metric(underserved_count / len(group_rows)),
        }

    def _event_anchor_quality(self, rows, positive_threshold):
        positive_rows = [
            row
            for row in rows
            if _safe_float(row.get("label")) >= positive_threshold
        ]
        event_rows = [
            row
            for row in positive_rows
            if self._is_event_backed_row(row)
        ]

        event_fit_values = [
            value
            for value in (self._event_fit_value(row) for row in event_rows)
            if value is not None
        ]
        route_anchor_values = [
            value
            for value in (self._route_anchor_value(row) for row in event_rows)
            if value is not None
        ]
        anchor_score_values = [
            value
            for value in (self._event_anchor_score(row) for row in event_rows)
            if value is not None
        ]
        reservation_flags = [
            value
            for value in (self._event_bool_value(row, "local_event_reservation_ready", "reservation_url") for row in event_rows)
            if value is not None
        ]
        source_flags = [
            value
            for value in (self._event_bool_value(row, "local_event_source_ready", "source_url") for row in event_rows)
            if value is not None
        ]
        friend_signal_values = [
            value
            for value in (self._event_friend_signal_count(row) for row in event_rows)
            if value is not None
        ]
        social_signal_values = [
            value
            for value in (self._event_social_signal(row) for row in event_rows)
            if value is not None
        ]

        event_count = len(event_rows)
        positive_count = len(positive_rows)
        friend_signal_count = sum(1 for value in friend_signal_values if value > 0)

        return {
            "positive_count": positive_count,
            "event_backed_positive_count": event_count,
            "event_backed_positive_rate": _round_metric(event_count / positive_count) if positive_count else 0.0,
            "event_fit_count": len(event_fit_values),
            "average_positive_event_fit": self._average_or_zero(event_fit_values),
            "route_anchor_score_count": len(route_anchor_values),
            "average_positive_route_anchor_score": self._average_or_zero(route_anchor_values),
            "event_anchor_score_count": len(anchor_score_values),
            "event_anchor_score": self._average_or_zero(anchor_score_values),
            "reservation_ready_known_count": len(reservation_flags),
            "reservation_ready_positive_count": sum(1 for value in reservation_flags if value),
            "reservation_ready_rate": _round_metric(
                sum(1 for value in reservation_flags if value) / len(reservation_flags)
            ) if reservation_flags else 0.0,
            "source_ready_known_count": len(source_flags),
            "source_ready_positive_count": sum(1 for value in source_flags if value),
            "source_ready_rate": _round_metric(
                sum(1 for value in source_flags if value) / len(source_flags)
            ) if source_flags else 0.0,
            "friend_signal_known_count": len(friend_signal_values),
            "friend_signal_positive_count": friend_signal_count,
            "friend_signal_positive_rate": _round_metric(
                friend_signal_count / len(friend_signal_values)
            ) if friend_signal_values else 0.0,
            "social_signal_count": len(social_signal_values),
            "average_positive_social_signal": self._average_or_zero(social_signal_values),
        }

    def _event_fit_value(self, row):
        components = row.get("components") if isinstance(row.get("components"), dict) else {}
        match = row.get("local_event_match") if isinstance(row.get("local_event_match"), dict) else {}
        return self._first_optional_float(
            row.get("local_event_fit"),
            components.get("local_event_fit"),
            match.get("score"),
        )

    def _route_anchor_value(self, row):
        components = row.get("components") if isinstance(row.get("components"), dict) else {}
        match = row.get("local_event_match") if isinstance(row.get("local_event_match"), dict) else {}
        route_context = match.get("route_context") if isinstance(match.get("route_context"), dict) else {}
        return self._first_optional_float(
            row.get("route_anchor_score"),
            row.get("local_event_route_anchor_score"),
            components.get("route_anchor_score"),
            match.get("route_anchor_score"),
            route_context.get("route_fit"),
        )

    def _event_anchor_score(self, row):
        components = []
        event_fit = self._event_fit_value(row)
        if event_fit is not None:
            components.append((event_fit, 0.58))

        route_anchor = self._route_anchor_value(row)
        if route_anchor is not None:
            components.append((route_anchor, 0.16))

        reservation_ready = self._event_bool_value(row, "local_event_reservation_ready", "reservation_url")
        if reservation_ready is not None:
            components.append((1.0 if reservation_ready else 0.0, 0.12))

        source_ready = self._event_bool_value(row, "local_event_source_ready", "source_url")
        if source_ready is not None:
            components.append((1.0 if source_ready else 0.0, 0.08))

        friend_signal = self._event_friend_signal_count(row)
        if friend_signal is not None:
            components.append((min(1.0, friend_signal / 2), 0.06))

        total_weight = sum(weight for _, weight in components)
        if not total_weight:
            return None
        return sum(value * weight for value, weight in components) / total_weight

    def _event_bool_value(self, row, top_level_key, match_url_key):
        if top_level_key in row:
            return bool(row.get(top_level_key))
        match = row.get("local_event_match") if isinstance(row.get("local_event_match"), dict) else {}
        if match_url_key in match:
            return bool(match.get(match_url_key))
        return None

    def _event_friend_signal_count(self, row):
        match = row.get("local_event_match") if isinstance(row.get("local_event_match"), dict) else {}
        social = match.get("social") if isinstance(match.get("social"), dict) else {}
        value = self._first_optional_float(
            row.get("local_event_friend_signal_count"),
            row.get("route_friend_signal_count"),
            match.get("friend_signal_count"),
            social.get("friend_signal_count"),
        )
        if value is not None:
            return max(0, value)
        going = _optional_float(social.get("friend_going_count"))
        interested = _optional_float(social.get("friend_interested_count"))
        if going is None and interested is None:
            return None
        return max(0, (going or 0) + (interested or 0))

    def _event_social_signal(self, row):
        match = row.get("local_event_match") if isinstance(row.get("local_event_match"), dict) else {}
        social = match.get("social") if isinstance(match.get("social"), dict) else {}
        components = match.get("components") if isinstance(match.get("components"), dict) else {}
        return self._first_optional_float(
            row.get("local_event_social_signal"),
            row.get("route_social_signal"),
            match.get("social_signal"),
            social.get("signal"),
            components.get("social_signal"),
        )

    def _first_optional_float(self, *values):
        for value in values:
            parsed = _optional_float(value)
            if parsed is not None:
                return parsed
        return None

    def _is_group_row(self, row):
        member_count = _safe_int(row.get("member_fit_count")) or 0
        if member_count > 1:
            return True
        member_fit = row.get("member_fit")
        if isinstance(member_fit, list) and len(member_fit) > 1:
            return True
        return _optional_float(row.get("group_min_fit")) is not None

    def _lowest_member_fit(self, row):
        direct = _optional_float(row.get("lowest_member_fit"))
        if direct is not None:
            return direct
        direct = _optional_float(row.get("group_min_fit"))
        if direct is not None:
            return direct
        member_fit = row.get("member_fit")
        if not isinstance(member_fit, list):
            return None
        values = [
            value
            for value in (_optional_float(item.get("fit")) for item in member_fit if isinstance(item, dict))
            if value is not None
        ]
        return min(values) if values else None

    def _member_fit_spread(self, row):
        direct = _optional_float(row.get("member_fit_spread"))
        if direct is not None:
            return direct
        member_fit = row.get("member_fit")
        if not isinstance(member_fit, list):
            return None
        values = [
            value
            for value in (_optional_float(item.get("fit")) for item in member_fit if isinstance(item, dict))
            if value is not None
        ]
        return max(values) - min(values) if values else None

    def _member_fit_values(self, row):
        member_fit = row.get("member_fit")
        if not isinstance(member_fit, list):
            return []
        return [
            value
            for value in (_optional_float(item.get("fit")) for item in member_fit if isinstance(item, dict))
            if value is not None
        ]

    def _group_average_fit(self, row):
        direct = _optional_float(row.get("group_average_fit"))
        if direct is not None:
            return direct
        values = self._member_fit_values(row)
        return sum(values) / len(values) if values else None

    def _group_consensus_fit(self, row):
        direct = _optional_float(row.get("group_consensus_fit"))
        if direct is not None:
            return direct
        values = self._member_fit_values(row)
        if len(values) <= 1:
            return None
        group_average_fit = sum(values) / len(values)
        group_min_fit = min(values)
        min_fit_weight = _optional_float(row.get("group_min_fit_weight"))
        if min_fit_weight is None:
            min_fit_weight = _optional_float((row.get("components") or {}).get("group_min_fit_weight"))
        if min_fit_weight is None:
            min_fit_weight = 0.14
        return group_average_fit * (1 - min_fit_weight) + group_min_fit * min_fit_weight

    def _group_consensus_gap(self, row):
        direct = _optional_float(row.get("group_consensus_gap"))
        if direct is not None:
            return direct
        group_average_fit = self._group_average_fit(row)
        consensus_fit = self._group_consensus_fit(row)
        if group_average_fit is None or consensus_fit is None:
            return None
        return max(0, group_average_fit - consensus_fit)

    def _group_row_is_underserved(self, row):
        lowest = self._lowest_member_fit(row)
        fairness = _optional_float(row.get("group_fairness_penalty"))
        consensus_fit = self._group_consensus_fit(row)
        consensus_gap = self._group_consensus_gap(row)
        return (
            lowest is not None
            and lowest < GUARDRAIL_THRESHOLDS["group_min_fit_min"]["warn"]
        ) or (
            fairness is not None
            and fairness > GUARDRAIL_THRESHOLDS["group_fairness_penalty_max"]["warn"]
        ) or (
            consensus_fit is not None
            and consensus_fit < GUARDRAIL_THRESHOLDS["group_consensus_fit_min"]["warn"]
        ) or (
            consensus_gap is not None
            and consensus_gap > GUARDRAIL_THRESHOLDS["group_consensus_gap_max"]["warn"]
        )

    def _profile_summaries(self, request_summaries, k_values):
        grouped = defaultdict(list)
        for summary in request_summaries:
            grouped[summary.get("scoring_profile") or "unknown"].append(summary)

        return {
            profile: self._overall_summary(
                summaries,
                labeled_example_count=sum(summary["example_count"] for summary in summaries),
                skipped_without_request=0,
                skipped_without_rank=0,
                k_values=k_values,
            )
            for profile, summaries in sorted(grouped.items())
        }

    def _segment_summaries(self, request_summaries, k_values):
        grouped = defaultdict(list)
        for summary in request_summaries:
            for segment in summary.get("segments") or []:
                grouped[segment].append(summary)

        return {
            segment: self._overall_summary(
                summaries,
                labeled_example_count=sum(summary["example_count"] for summary in summaries),
                skipped_without_request=0,
                skipped_without_rank=0,
                k_values=k_values,
            )
            for segment, summaries in sorted(grouped.items())
        }

    def _segment_comparison_delta(self, baseline_segments, learned_segments):
        segment_names = sorted(set(baseline_segments or {}) | set(learned_segments or {}))
        return {
            segment: {
                "request_count_delta": int((learned_segments.get(segment) or {}).get("request_count") or 0)
                - int((baseline_segments.get(segment) or {}).get("request_count") or 0),
                "mean_reciprocal_rank": _round_metric(
                    _safe_float((learned_segments.get(segment) or {}).get("mean_reciprocal_rank"))
                    - _safe_float((baseline_segments.get(segment) or {}).get("mean_reciprocal_rank"))
                ),
                "metrics_at_k": self._comparison_delta(
                    baseline_segments.get(segment) or {},
                    learned_segments.get(segment) or {},
                ).get("metrics_at_k", {}),
                "guardrail_status_changed": (
                    ((baseline_segments.get(segment) or {}).get("guardrails") or {}).get("status")
                    != ((learned_segments.get(segment) or {}).get("guardrails") or {}).get("status")
                ),
                "baseline_guardrail_status": ((baseline_segments.get(segment) or {}).get("guardrails") or {}).get("status"),
                "learned_guardrail_status": ((learned_segments.get(segment) or {}).get("guardrails") or {}).get("status"),
            }
            for segment in segment_names
        }

    def _overall_summary(
        self,
        request_summaries,
        labeled_example_count,
        skipped_without_request,
        skipped_without_rank,
        k_values,
    ):
        request_count = len(request_summaries)
        grouped_example_count = sum(summary["example_count"] for summary in request_summaries)
        positive_request_count = sum(1 for summary in request_summaries if summary["positive_count"] > 0)

        metrics_at_k = {}
        for k in k_values:
            k_key = str(k)
            if request_count:
                metrics_at_k[k_key] = {
                    "hit_rate": _round_metric(
                        sum(summary["metrics_at_k"][k_key]["hit_rate"] for summary in request_summaries)
                        / request_count
                    ),
                    "precision": _round_metric(
                        sum(summary["metrics_at_k"][k_key]["precision"] for summary in request_summaries)
                        / request_count
                    ),
                    "average_label": _round_metric(
                        sum(summary["metrics_at_k"][k_key]["average_label"] for summary in request_summaries)
                        / request_count
                    ),
                    "weighted_average_label": _round_metric(
                        sum(summary["metrics_at_k"][k_key]["weighted_average_label"] for summary in request_summaries)
                        / request_count
                    ),
                    "ndcg": _round_metric(
                        sum(summary["metrics_at_k"][k_key]["ndcg"] for summary in request_summaries)
                        / request_count
                    ),
                }
            else:
                metrics_at_k[k_key] = {
                    "hit_rate": 0.0,
                    "precision": 0.0,
                    "average_label": 0.0,
                    "weighted_average_label": 0.0,
                    "ndcg": 0.0,
                }

        summary = {
            "request_count": request_count,
            "positive_request_count": positive_request_count,
            "labeled_example_count": labeled_example_count,
            "grouped_example_count": grouped_example_count,
            "skipped_without_request": skipped_without_request,
            "skipped_without_rank": skipped_without_rank,
            "mean_reciprocal_rank": _round_metric(
                sum(summary["mrr"] for summary in request_summaries) / request_count
            ) if request_count else 0.0,
            "metrics_at_k": metrics_at_k,
            "exposure_quality_at_k": self._aggregate_exposure_quality(request_summaries, k_values),
            "outcome_quality": self._aggregate_outcome_quality(request_summaries),
            "group_balance": self._aggregate_group_balance(request_summaries),
            "event_anchor_quality": self._aggregate_event_anchor_quality(request_summaries),
        }
        summary["guardrails"] = self._guardrail_summary(summary)
        return summary

    def _aggregate_exposure_quality(self, request_summaries, k_values):
        def weighted_average(summaries, value_key, count_key):
            total_count = sum(int(summary.get(count_key) or 0) for summary in summaries)
            if not total_count:
                return 0.0
            weighted_total = sum(
                _safe_float(summary.get(value_key)) * int(summary.get(count_key) or 0)
                for summary in summaries
            )
            return _round_metric(weighted_total / total_count)

        aggregated = {}
        for k in k_values:
            k_key = str(k)
            summaries = [
                (summary.get("exposure_quality_at_k") or {}).get(k_key) or {}
                for summary in request_summaries
            ]
            aggregated[k_key] = {
                "exposed_count": sum(int(summary.get("exposed_count") or 0) for summary in summaries),
                "local_quality_count": sum(int(summary.get("local_quality_count") or 0) for summary in summaries),
                "authenticity_count": sum(int(summary.get("authenticity_count") or 0) for summary in summaries),
                "hidden_gem_count": sum(int(summary.get("hidden_gem_count") or 0) for summary in summaries),
                "chain_probability_count": sum(int(summary.get("chain_probability_count") or 0) for summary in summaries),
                "group_min_fit_count": sum(int(summary.get("group_min_fit_count") or 0) for summary in summaries),
                "group_fairness_penalty_count": sum(int(summary.get("group_fairness_penalty_count") or 0) for summary in summaries),
                "local_quality_score": weighted_average(summaries, "local_quality_score", "local_quality_count"),
                "average_authenticity": weighted_average(summaries, "average_authenticity", "authenticity_count"),
                "average_hidden_gem": weighted_average(summaries, "average_hidden_gem", "hidden_gem_count"),
                "average_chain_probability": weighted_average(summaries, "average_chain_probability", "chain_probability_count"),
                "average_group_min_fit": weighted_average(summaries, "average_group_min_fit", "group_min_fit_count"),
                "average_group_fairness_penalty": weighted_average(summaries, "average_group_fairness_penalty", "group_fairness_penalty_count"),
            }
        return aggregated

    def _aggregate_outcome_quality(self, request_summaries):
        quality_summaries = [
            summary.get("outcome_quality") or {}
            for summary in request_summaries
        ]

        def weighted_average(value_key, count_key):
            total_count = sum(int(quality.get(count_key) or 0) for quality in quality_summaries)
            if not total_count:
                return 0.0
            weighted_total = sum(
                _safe_float(quality.get(value_key)) * int(quality.get(count_key) or 0)
                for quality in quality_summaries
            )
            return _round_metric(weighted_total / total_count)

        return {
            "positive_quality_count": sum(
                int(quality.get("positive_quality_count") or 0)
                for quality in quality_summaries
            ),
            "authenticity_count": sum(
                int(quality.get("authenticity_count") or 0)
                for quality in quality_summaries
            ),
            "hidden_gem_count": sum(
                int(quality.get("hidden_gem_count") or 0)
                for quality in quality_summaries
            ),
            "chain_probability_count": sum(
                int(quality.get("chain_probability_count") or 0)
                for quality in quality_summaries
            ),
            "group_min_fit_count": sum(
                int(quality.get("group_min_fit_count") or 0)
                for quality in quality_summaries
            ),
            "group_fairness_penalty_count": sum(
                int(quality.get("group_fairness_penalty_count") or 0)
                for quality in quality_summaries
            ),
            "local_quality_count": sum(
                int(quality.get("local_quality_count") or 0)
                for quality in quality_summaries
            ),
            "average_positive_authenticity": weighted_average(
                "average_positive_authenticity",
                "authenticity_count",
            ),
            "average_positive_hidden_gem": weighted_average(
                "average_positive_hidden_gem",
                "hidden_gem_count",
            ),
            "average_positive_chain_probability": weighted_average(
                "average_positive_chain_probability",
                "chain_probability_count",
            ),
            "average_positive_group_min_fit": weighted_average(
                "average_positive_group_min_fit",
                "group_min_fit_count",
            ),
            "average_positive_group_fairness_penalty": weighted_average(
                "average_positive_group_fairness_penalty",
                "group_fairness_penalty_count",
            ),
            "local_quality_score": weighted_average(
                "local_quality_score",
                "local_quality_count",
            ),
        }

    def _aggregate_group_balance(self, request_summaries):
        group_summaries = [
            summary.get("group_balance") or {}
            for summary in request_summaries
        ]

        def weighted_average(value_key, count_key="group_positive_count"):
            total_count = sum(int(summary.get(count_key) or 0) for summary in group_summaries)
            if not total_count:
                return 0.0
            weighted_total = sum(
                _safe_float(summary.get(value_key)) * int(summary.get(count_key) or 0)
                for summary in group_summaries
            )
            return _round_metric(weighted_total / total_count)

        group_positive_count = sum(
            int(summary.get("group_positive_count") or 0)
            for summary in group_summaries
        )
        underserved_count = sum(
            int(summary.get("underserved_positive_count") or 0)
            for summary in group_summaries
        )

        return {
            "group_positive_count": group_positive_count,
            "member_fit_count": sum(
                int(summary.get("member_fit_count") or 0)
                for summary in group_summaries
            ),
            "average_lowest_member_fit": weighted_average("average_lowest_member_fit"),
            "group_consensus_fit_count": sum(
                int(summary.get("group_consensus_fit_count") or 0)
                for summary in group_summaries
            ),
            "group_consensus_gap_count": sum(
                int(summary.get("group_consensus_gap_count") or 0)
                for summary in group_summaries
            ),
            "average_group_consensus_fit": weighted_average(
                "average_group_consensus_fit",
                "group_consensus_fit_count",
            ),
            "average_group_consensus_gap": weighted_average(
                "average_group_consensus_gap",
                "group_consensus_gap_count",
            ),
            "average_member_fit_spread": weighted_average("average_member_fit_spread"),
            "average_group_fairness_penalty": weighted_average("average_group_fairness_penalty"),
            "underserved_positive_count": underserved_count,
            "underserved_positive_rate": _round_metric(
                underserved_count / group_positive_count
            ) if group_positive_count else 0.0,
        }

    def _aggregate_event_anchor_quality(self, request_summaries):
        event_summaries = [
            summary.get("event_anchor_quality") or {}
            for summary in request_summaries
        ]

        def weighted_average(value_key, count_key):
            total_count = sum(int(summary.get(count_key) or 0) for summary in event_summaries)
            if not total_count:
                return 0.0
            weighted_total = sum(
                _safe_float(summary.get(value_key)) * int(summary.get(count_key) or 0)
                for summary in event_summaries
            )
            return _round_metric(weighted_total / total_count)

        positive_count = sum(int(summary.get("positive_count") or 0) for summary in event_summaries)
        event_count = sum(int(summary.get("event_backed_positive_count") or 0) for summary in event_summaries)
        reservation_known_count = sum(int(summary.get("reservation_ready_known_count") or 0) for summary in event_summaries)
        reservation_ready_count = sum(int(summary.get("reservation_ready_positive_count") or 0) for summary in event_summaries)
        source_known_count = sum(int(summary.get("source_ready_known_count") or 0) for summary in event_summaries)
        source_ready_count = sum(int(summary.get("source_ready_positive_count") or 0) for summary in event_summaries)
        friend_known_count = sum(int(summary.get("friend_signal_known_count") or 0) for summary in event_summaries)
        friend_signal_count = sum(int(summary.get("friend_signal_positive_count") or 0) for summary in event_summaries)

        return {
            "positive_count": positive_count,
            "event_backed_positive_count": event_count,
            "event_backed_positive_rate": _round_metric(event_count / positive_count) if positive_count else 0.0,
            "event_fit_count": sum(int(summary.get("event_fit_count") or 0) for summary in event_summaries),
            "average_positive_event_fit": weighted_average("average_positive_event_fit", "event_fit_count"),
            "route_anchor_score_count": sum(int(summary.get("route_anchor_score_count") or 0) for summary in event_summaries),
            "average_positive_route_anchor_score": weighted_average(
                "average_positive_route_anchor_score",
                "route_anchor_score_count",
            ),
            "event_anchor_score_count": sum(int(summary.get("event_anchor_score_count") or 0) for summary in event_summaries),
            "event_anchor_score": weighted_average("event_anchor_score", "event_anchor_score_count"),
            "reservation_ready_known_count": reservation_known_count,
            "reservation_ready_positive_count": reservation_ready_count,
            "reservation_ready_rate": _round_metric(
                reservation_ready_count / reservation_known_count
            ) if reservation_known_count else 0.0,
            "source_ready_known_count": source_known_count,
            "source_ready_positive_count": source_ready_count,
            "source_ready_rate": _round_metric(
                source_ready_count / source_known_count
            ) if source_known_count else 0.0,
            "friend_signal_known_count": friend_known_count,
            "friend_signal_positive_count": friend_signal_count,
            "friend_signal_positive_rate": _round_metric(
                friend_signal_count / friend_known_count
            ) if friend_known_count else 0.0,
            "social_signal_count": sum(int(summary.get("social_signal_count") or 0) for summary in event_summaries),
            "average_positive_social_signal": weighted_average(
                "average_positive_social_signal",
                "social_signal_count",
            ),
        }

    def _guardrail_summary(self, summary):
        quality = summary.get("outcome_quality") or {}
        event_quality = summary.get("event_anchor_quality") or {}
        checks = [
            self._minimum_guardrail(
                name="local_quality",
                label="Local quality",
                value=quality.get("local_quality_score"),
                count=quality.get("local_quality_count"),
                thresholds=GUARDRAIL_THRESHOLDS["local_quality_min"],
                message="Accepted places should still feel local, authentic, and non-chain.",
            ),
            self._minimum_guardrail(
                name="authenticity",
                label="Authenticity",
                value=quality.get("average_positive_authenticity"),
                count=quality.get("authenticity_count"),
                thresholds=GUARDRAIL_THRESHOLDS["authenticity_min"],
                message="Accepted outcomes are trending generic; review local/authentic boosts.",
            ),
            self._minimum_guardrail(
                name="hidden_gem",
                label="Hidden-gem strength",
                value=quality.get("average_positive_hidden_gem"),
                count=quality.get("hidden_gem_count"),
                thresholds=GUARDRAIL_THRESHOLDS["hidden_gem_min"],
                message="Accepted outcomes are light on hidden-gem signal.",
            ),
            self._maximum_guardrail(
                name="chain_probability",
                label="Chain risk",
                value=quality.get("average_positive_chain_probability"),
                count=quality.get("chain_probability_count"),
                thresholds=GUARDRAIL_THRESHOLDS["chain_probability_max"],
                message="Accepted outcomes are too chain-heavy for Adventour's mission.",
            ),
            self._minimum_guardrail(
                name="group_min_fit",
                label="Group minimum fit",
                value=quality.get("average_positive_group_min_fit"),
                count=quality.get("group_min_fit_count"),
                thresholds=GUARDRAIL_THRESHOLDS["group_min_fit_min"],
                message="Friend/group accepts may be leaving one traveler under-served.",
            ),
            self._maximum_guardrail(
                name="group_fairness_penalty",
                label="Group fairness penalty",
                value=quality.get("average_positive_group_fairness_penalty"),
                count=quality.get("group_fairness_penalty_count"),
                thresholds=GUARDRAIL_THRESHOLDS["group_fairness_penalty_max"],
                message="Accepted group outcomes show too much traveler-fit disagreement.",
            ),
            self._minimum_guardrail(
                name="group_consensus_fit",
                label="Group consensus fit",
                value=(summary.get("group_balance") or {}).get("average_group_consensus_fit"),
                count=(summary.get("group_balance") or {}).get("group_consensus_fit_count"),
                thresholds=GUARDRAIL_THRESHOLDS["group_consensus_fit_min"],
                message="Accepted group outcomes may be hiding a low-fit traveler behind the average.",
            ),
            self._maximum_guardrail(
                name="group_consensus_gap",
                label="Group consensus gap",
                value=(summary.get("group_balance") or {}).get("average_group_consensus_gap"),
                count=(summary.get("group_balance") or {}).get("group_consensus_gap_count"),
                thresholds=GUARDRAIL_THRESHOLDS["group_consensus_gap_max"],
                message="Accepted group outcomes have too much average-to-consensus disagreement.",
            ),
            self._maximum_guardrail(
                name="group_underserved_rate",
                label="Group underserved rate",
                value=(summary.get("group_balance") or {}).get("underserved_positive_rate"),
                count=(summary.get("group_balance") or {}).get("group_positive_count"),
                thresholds=GUARDRAIL_THRESHOLDS["group_underserved_rate_max"],
                message="Too many accepted group outcomes leave at least one traveler under-served.",
            ),
            self._minimum_guardrail(
                name="event_anchor_score",
                label="Event anchor strength",
                value=event_quality.get("event_anchor_score"),
                count=event_quality.get("event_anchor_score_count"),
                thresholds=GUARDRAIL_THRESHOLDS["event_anchor_score_min"],
                message="Accepted event-backed outcomes have weak local-event anchor quality.",
            ),
            self._minimum_guardrail(
                name="event_reservation_ready_rate",
                label="Event reservation readiness",
                value=event_quality.get("reservation_ready_rate"),
                count=event_quality.get("reservation_ready_known_count"),
                thresholds=GUARDRAIL_THRESHOLDS["event_reservation_ready_rate_min"],
                message="Accepted event-backed outcomes need more actionable reservation/source links.",
            ),
        ]

        statuses = {check["status"] for check in checks}
        if "fail" in statuses:
            status = "fail"
        elif "warn" in statuses:
            status = "warn"
        elif statuses == {"unknown"}:
            status = "unknown"
        else:
            status = "pass"

        return {
            "status": status,
            "checks": checks,
            "failures": [check for check in checks if check["status"] == "fail"],
            "warnings": [check for check in checks if check["status"] == "warn"],
            "unknown": [check for check in checks if check["status"] == "unknown"],
        }

    def _minimum_guardrail(self, name, label, value, count, thresholds, message):
        return self._threshold_guardrail(
            name=name,
            label=label,
            value=value,
            count=count,
            direction="min",
            thresholds=thresholds,
            message=message,
        )

    def _maximum_guardrail(self, name, label, value, count, thresholds, message):
        return self._threshold_guardrail(
            name=name,
            label=label,
            value=value,
            count=count,
            direction="max",
            thresholds=thresholds,
            message=message,
        )

    def _threshold_guardrail(self, name, label, value, count, direction, thresholds, message):
        count = int(count or 0)
        rounded_value = _round_metric(value or 0.0)
        if count <= 0:
            status = "unknown"
        elif direction == "min" and rounded_value < thresholds["fail"]:
            status = "fail"
        elif direction == "min" and rounded_value < thresholds["warn"]:
            status = "warn"
        elif direction == "max" and rounded_value > thresholds["fail"]:
            status = "fail"
        elif direction == "max" and rounded_value > thresholds["warn"]:
            status = "warn"
        else:
            status = "pass"

        target = f">= {thresholds['warn']}" if direction == "min" else f"<= {thresholds['warn']}"
        return {
            "name": name,
            "label": label,
            "status": status,
            "value": rounded_value,
            "count": count,
            "target": target,
            "message": message if status in {"fail", "warn"} else "",
        }
