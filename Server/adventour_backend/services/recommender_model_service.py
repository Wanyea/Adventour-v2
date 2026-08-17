import json
import math
from collections import defaultdict


FEATURE_NAMES = [
    "model_score",
    "base_rank_score",
    "personal_fit",
    "group_fit",
    "group_average_fit",
    "group_consensus_fit",
    "group_min_fit",
    "group_min_fit_weight",
    "group_consensus_gap_inverse",
    "group_fairness_inverse",
    "authenticity_score",
    "hidden_gem_score",
    "chain_inverse",
    "tourist_trap_inverse",
    "quality_score",
    "popularity_score",
    "context_fit",
    "time_fit",
    "novelty",
    "exploration",
    "exploration_uncertainty",
    "preference_confidence",
    "profile_signal_density",
    "diversity_bonus",
    "intent_coverage_bonus",
    "covered_intents_density",
    "member_coverage_bonus",
    "served_members_density",
    "friend_adjusted_retrieval",
    "objective_positive_total",
    "objective_penalty_inverse",
    "price_inverse",
    "repeat_freshness",
    "local_event_fit",
    "local_event_backed",
    "local_event_proximity",
    "local_event_reservation_ready",
    "local_event_source_ready",
    "local_event_route_anchor_score",
    "local_event_friend_signal_density",
    "local_event_social_signal",
    "local_event_actionability",
    "session_context_fit",
    "session_momentum",
    "session_mismatch_inverse",
    "friend_history_fit",
    "friend_history_positive",
    "friend_history_conflict_inverse",
]

FEATURE_SCHEMA_VERSION = "phase1_group_friend_event_social_session_objective_v6"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value, minimum=0.0, maximum=1.0):
    return max(minimum, min(maximum, value))


def _sigmoid(value):
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _first_present(*values):
    for value in values:
        if value is not None:
            return value
    return None


def model_feature_compatibility(model):
    """Report whether a learned ranker artifact matches the current feature contract."""
    expected_features = list(FEATURE_NAMES)
    expected_feature_set = set(expected_features)
    feature_names = model.get("feature_names") if isinstance(model, dict) else None
    if isinstance(feature_names, list):
        model_features = [str(name) for name in feature_names]
    else:
        model_features = []
    model_feature_set = set(model_features)
    missing_features = [
        name for name in expected_features
        if name not in model_feature_set
    ]
    extra_features = [
        name for name in model_features
        if name not in expected_feature_set
    ]
    schema_version = model.get("feature_schema_version") if isinstance(model, dict) else None
    version_matches = schema_version == FEATURE_SCHEMA_VERSION

    if not isinstance(model, dict):
        status = "fail"
        reason = "model_invalid"
        message = "Learned ranker artifact is not a valid model object."
    elif not model_features:
        status = "fail"
        reason = "feature_names_missing"
        message = "Learned ranker artifact does not declare its feature schema."
    elif missing_features:
        status = "fail"
        reason = "feature_schema_mismatch"
        message = "Learned ranker artifact is missing current Adventour ranking signals; retrain before live rerank."
    elif not version_matches:
        status = "fail"
        reason = "feature_schema_version_mismatch"
        message = "Learned ranker artifact was trained against an older feature contract; retrain before live rerank."
    else:
        status = "pass"
        reason = "feature_schema_current"
        message = "Learned ranker artifact matches the current Adventour feature schema."

    return {
        "status": status,
        "reason": reason,
        "message": message,
        "feature_schema_version": schema_version,
        "expected_feature_schema_version": FEATURE_SCHEMA_VERSION,
        "model_feature_count": len(model_features),
        "expected_feature_count": len(expected_features),
        "missing_features": missing_features,
        "extra_features": extra_features,
    }


def learned_ranker_artifact_status(model):
    """Return the live-readiness contract for a learned ranker artifact."""
    if not model:
        return {
            "applied": False,
            "available": False,
            "ready": False,
            "status": "not_loaded",
            "reason": "no_model",
            "model_type": None,
            "message": "No learned ranker model is loaded.",
        }

    feature_compatibility = model_feature_compatibility(model)
    promotion_gate = model.get("promotion_gate") or None
    promotion_payload = _promotion_gate_payload(promotion_gate)
    training_data_health = _training_data_health_payload(model.get("training_data_health"))
    model_type = model.get("model_type")

    if feature_compatibility["status"] != "pass":
        return {
            "applied": False,
            "available": True,
            "ready": False,
            "status": "blocked",
            "reason": feature_compatibility["reason"],
            "model_type": model_type,
            "message": feature_compatibility["message"],
            "feature_compatibility": feature_compatibility,
            "promotion_gate": promotion_payload,
            "training_data_health": training_data_health,
        }

    if training_data_health["status"] in {"needs_data", "unknown"}:
        return {
            "applied": False,
            "available": True,
            "ready": False,
            "status": "blocked",
            "reason": f"training_data_{training_data_health['status']}",
            "model_type": model_type,
            "message": (
                training_data_health.get("summary")
                or "Learned beta needs representative training data before live rerank."
            ),
            "feature_compatibility": feature_compatibility,
            "promotion_gate": promotion_payload,
            "training_data_health": training_data_health,
            "override_available": True,
        }

    if promotion_gate and promotion_gate.get("can_promote") is True and promotion_gate.get("status") == "pass":
        return {
            "applied": False,
            "available": True,
            "ready": True,
            "status": "ready",
            "reason": "promotion_gate_passed",
            "model_type": model_type,
            "message": "Learned beta is loaded, current, and passed Adventour promotion gates.",
            "feature_compatibility": feature_compatibility,
            "promotion_gate": promotion_payload,
            "training_data_health": training_data_health,
        }

    if not promotion_gate:
        reason = "promotion_gate_missing"
        message = "Learned beta is trained, but it needs offline evaluation before live rerank."
        status = "needs_evaluation"
    else:
        reason = f"promotion_gate_{promotion_gate.get('status') or 'failed'}"
        message = promotion_payload.get("summary") or "Learned beta is trained, but promotion gates are not passing yet."
        status = "blocked"

    return {
        "applied": False,
        "available": True,
        "ready": False,
        "status": status,
        "reason": reason,
        "model_type": model_type,
        "message": message,
        "feature_compatibility": feature_compatibility,
        "promotion_gate": promotion_payload,
        "training_data_health": training_data_health,
        "override_available": True,
    }


def _training_data_health_payload(training_data_health):
    if not isinstance(training_data_health, dict):
        return {
            "status": "unknown",
            "summary": "This artifact does not include training-data health. Refresh the learned ranker to see friend/event coverage.",
            "counts": {},
            "checks": [],
            "blocking_checks": [],
            "watch_checks": [],
        }

    checks = [
        check for check in training_data_health.get("checks") or []
        if isinstance(check, dict)
    ]
    blocking_checks = [
        check for check in checks
        if check.get("status") == "fail"
    ]
    watch_checks = [
        check for check in checks
        if check.get("status") == "warn"
    ]

    return {
        "status": training_data_health.get("status") or "unknown",
        "summary": training_data_health.get("summary") or "",
        "counts": training_data_health.get("counts") or {},
        "checks": checks,
        "blocking_checks": blocking_checks,
        "watch_checks": watch_checks,
    }


def _promotion_gate_payload(promotion_gate):
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


class LearningToRankBaselineService:
    """Train a tiny dependency-free ranker from Adventour outcome examples.

    This is deliberately simple: it gives Adventour a real learned baseline for
    beta data without adding a heavy ML stack before we know the signal quality.
    """

    def train(
        self,
        examples,
        iterations=500,
        learning_rate=0.08,
        l2=0.01,
        validation_fraction=0.25,
    ):
        labeled = [
            example
            for example in examples
            if example.get("label") is not None
        ]
        if not labeled:
            raise ValueError("At least one labeled example is required")

        training_examples, validation_examples = self._split_examples(
            labeled,
            validation_fraction=validation_fraction,
        )
        stats = self._feature_stats(training_examples)
        weights = {name: 0.0 for name in FEATURE_NAMES}
        intercept = 0.0

        for _ in range(max(1, int(iterations))):
            gradient = {name: 0.0 for name in FEATURE_NAMES}
            intercept_gradient = 0.0
            total_weight = 0.0

            for example in training_examples:
                label = _clamp(_safe_float(example.get("label")))
                outcome_weight = max(0.0, _safe_float(example.get("outcome_weight"), 1.0))
                features = self._standardized_features(example, stats)
                prediction = _sigmoid(intercept + sum(weights[name] * features[name] for name in FEATURE_NAMES))
                error = (prediction - label) * outcome_weight
                total_weight += outcome_weight
                intercept_gradient += error
                for name in FEATURE_NAMES:
                    gradient[name] += error * features[name]

            denominator = total_weight or len(training_examples) or 1
            intercept -= learning_rate * (intercept_gradient / denominator)
            for name in FEATURE_NAMES:
                regularization = l2 * weights[name]
                weights[name] -= learning_rate * ((gradient[name] / denominator) + regularization)

        model = {
            "model_type": "adventour_logistic_ltr_baseline",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_names": FEATURE_NAMES,
            "weights": {name: round(weights[name], 6) for name in FEATURE_NAMES},
            "intercept": round(intercept, 6),
            "feature_stats": stats,
            "training_summary": self._summary(training_examples, weights, intercept, stats),
            "validation_summary": self._summary(validation_examples, weights, intercept, stats)
            if validation_examples
            else None,
        }
        model["top_positive_weights"] = self._top_weights(weights, reverse=True)
        model["top_negative_weights"] = self._top_weights(weights, reverse=False)
        return model

    def predict(self, example, model):
        features = self._standardized_features(example, model.get("feature_stats") or {})
        weights = model.get("weights") or {}
        score = _safe_float(model.get("intercept"))
        for name in model.get("feature_names") or FEATURE_NAMES:
            score += _safe_float(weights.get(name)) * features.get(name, 0.0)
        return round(_sigmoid(score), 6)

    def rerank_examples(self, examples, model):
        grouped = defaultdict(list)
        for example in examples:
            request_id = example.get("request_id")
            if not request_id:
                continue
            enriched = {
                **example,
                "learned_score": self.predict(example, model),
            }
            grouped[str(request_id)].append(enriched)

        reranked = []
        for request_id, rows in grouped.items():
            for rank, row in enumerate(
                sorted(rows, key=lambda item: item["learned_score"], reverse=True),
                start=1,
            ):
                reranked.append({
                    **row,
                    "request_id": request_id,
                    "learned_rank_position": rank,
                })
        return reranked

    def write_model(self, path, model):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(model, handle, indent=2, sort_keys=True)

    def load_model(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _feature_values(self, example):
        components = example.get("components") if isinstance(example.get("components"), dict) else {}
        price_band = _safe_float(example.get("price_band"))
        average_signal_count = _safe_float(
            example.get("average_member_signal_count")
            or components.get("average_member_signal_count")
        )
        group_average_fit = _safe_float(_first_present(
            example.get("group_average_fit"),
            components.get("group_average_fit"),
        ))
        group_consensus_fit = _safe_float(_first_present(
            example.get("group_consensus_fit"),
            components.get("group_consensus_fit"),
        ))
        return {
            "model_score": _safe_float(example.get("model_score")),
            "base_rank_score": _safe_float(example.get("base_rank_score")),
            "personal_fit": _safe_float(components.get("personal_fit")),
            "group_fit": _safe_float(components.get("group_fit")),
            "group_average_fit": group_average_fit,
            "group_consensus_fit": group_consensus_fit,
            "group_min_fit": _safe_float(example.get("group_min_fit") or components.get("group_min_fit")),
            "group_min_fit_weight": _safe_float(_first_present(
                example.get("group_min_fit_weight"),
                components.get("group_min_fit_weight"),
            )),
            "group_consensus_gap_inverse": (
                1 - _clamp(group_average_fit - group_consensus_fit)
                if group_average_fit or group_consensus_fit
                else 0.0
            ),
            "group_fairness_inverse": 1 - _clamp(_safe_float(example.get("group_fairness_penalty") or components.get("group_fairness_penalty"))),
            "authenticity_score": _safe_float(example.get("authenticity_score")),
            "hidden_gem_score": _safe_float(example.get("hidden_gem_score")),
            "chain_inverse": 1 - _clamp(_safe_float(example.get("chain_probability"))),
            "tourist_trap_inverse": 1 - _clamp(_safe_float(example.get("tourist_trap_score"))),
            "quality_score": _safe_float(example.get("quality_score")),
            "popularity_score": _safe_float(example.get("popularity_score")),
            "context_fit": _safe_float(components.get("context_fit")),
            "time_fit": _safe_float(components.get("time_fit")),
            "novelty": _safe_float(components.get("novelty")),
            "exploration": _safe_float(example.get("exploration") or components.get("exploration")),
            "exploration_uncertainty": _safe_float(
                example.get("exploration_uncertainty")
                or components.get("exploration_uncertainty")
            ),
            "preference_confidence": _safe_float(
                example.get("preference_confidence")
                or components.get("preference_confidence")
            ),
            "profile_signal_density": _clamp(average_signal_count / 12 if average_signal_count else 0),
            "diversity_bonus": _safe_float(example.get("diversity_bonus")),
            "intent_coverage_bonus": _safe_float(example.get("intent_coverage_bonus")),
            "covered_intents_density": _clamp(_safe_float(example.get("covered_new_intents_count")) / 4),
            "member_coverage_bonus": _safe_float(example.get("member_coverage_bonus")),
            "served_members_density": _clamp(_safe_float(example.get("served_new_members_count")) / 3),
            "friend_adjusted_retrieval": 1.0 if example.get("friend_adjusted_retrieval") else 0.0,
            "objective_positive_total": _safe_float(example.get("objective_positive_total")),
            "objective_penalty_inverse": 1 - _clamp(_safe_float(example.get("objective_penalty_total"))),
            "price_inverse": 1 - _clamp(price_band / 4 if price_band else 0),
            "repeat_freshness": 0.0 if example.get("repeat_after_exhaustion") else 1.0,
            "local_event_fit": _safe_float(example.get("local_event_fit") or components.get("local_event_fit")),
            "local_event_backed": 1.0 if example.get("local_event_backed") else 0.0,
            "local_event_proximity": self._event_proximity_score(example),
            "local_event_reservation_ready": 1.0 if example.get("local_event_reservation_ready") else 0.0,
            "local_event_source_ready": 1.0 if example.get("local_event_source_ready") else 0.0,
            "local_event_route_anchor_score": _safe_float(example.get("local_event_route_anchor_score")),
            "local_event_friend_signal_density": _clamp(_safe_float(example.get("local_event_friend_signal_count")) / 2),
            "local_event_social_signal": _clamp(_safe_float(example.get("local_event_social_signal"))),
            "local_event_actionability": self._event_actionability_score(example),
            "session_context_fit": _safe_float(
                example.get("session_context_fit")
                if example.get("session_context_fit") is not None
                else components.get("session_context_fit")
            ),
            "session_momentum": _clamp(max(0, _safe_float(
                example.get("session_context_fit")
                if example.get("session_context_fit") is not None
                else components.get("session_context_fit")
            ))),
            "session_mismatch_inverse": 1 - _clamp(abs(min(0, _safe_float(
                example.get("session_context_fit")
                if example.get("session_context_fit") is not None
                else components.get("session_context_fit")
            )))),
            "friend_history_fit": _safe_float(
                example.get("friend_history_fit")
                if example.get("friend_history_fit") is not None
                else components.get("friend_history_fit")
            ),
            "friend_history_positive": _clamp(max(0, _safe_float(
                example.get("friend_history_fit")
                if example.get("friend_history_fit") is not None
                else components.get("friend_history_fit")
            ))),
            "friend_history_conflict_inverse": 1 - _clamp(abs(min(0, _safe_float(
                example.get("friend_history_fit")
                if example.get("friend_history_fit") is not None
                else components.get("friend_history_fit")
            )))),
        }

    def _event_proximity_score(self, example):
        distance = _safe_float(example.get("local_event_distance_to_place_meters"), None)
        if distance is None:
            return 0.0
        return _clamp(1 - (distance / 2500))

    def _event_actionability_score(self, example):
        if not example.get("local_event_backed"):
            return 0.0
        return _clamp(
            _safe_float(example.get("local_event_fit")) * 0.5
            + (1.0 if example.get("local_event_reservation_ready") else 0.0) * 0.16
            + (1.0 if example.get("local_event_source_ready") else 0.0) * 0.12
            + _safe_float(example.get("local_event_route_anchor_score")) * 0.10
            + _clamp(_safe_float(example.get("local_event_friend_signal_count")) / 2) * 0.08
            + _clamp(_safe_float(example.get("local_event_social_signal"))) * 0.04
        )

    def _standardized_features(self, example, stats):
        raw = self._feature_values(example)
        return {
            name: (raw[name] - _safe_float((stats.get(name) or {}).get("mean"))) / (_safe_float((stats.get(name) or {}).get("std"), 1.0) or 1.0)
            for name in FEATURE_NAMES
        }

    def _feature_stats(self, examples):
        stats = {}
        for name in FEATURE_NAMES:
            values = [self._feature_values(example)[name] for example in examples]
            mean = sum(values) / len(values) if values else 0.0
            variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0
            std = math.sqrt(variance) or 1.0
            stats[name] = {
                "mean": round(mean, 6),
                "std": round(std, 6),
            }
        return stats

    def _split_examples(self, examples, validation_fraction):
        if len(examples) < 4 or validation_fraction <= 0:
            return examples, []

        request_ids = sorted({str(example.get("request_id")) for example in examples if example.get("request_id")})
        if len(request_ids) < 4:
            split_index = max(1, int(len(examples) * (1 - validation_fraction)))
            return examples[:split_index], examples[split_index:]

        validation_count = max(1, int(len(request_ids) * validation_fraction))
        validation_ids = set(request_ids[-validation_count:])
        training = [example for example in examples if str(example.get("request_id")) not in validation_ids]
        validation = [example for example in examples if str(example.get("request_id")) in validation_ids]
        return training or examples, validation

    def _summary(self, examples, weights, intercept, stats):
        if not examples:
            return {
                "example_count": 0,
                "log_loss": 0.0,
                "pairwise_accuracy": None,
            }

        weighted_loss = 0.0
        total_weight = 0.0
        for example in examples:
            label = _clamp(_safe_float(example.get("label")))
            outcome_weight = max(0.0, _safe_float(example.get("outcome_weight"), 1.0))
            prediction = self._predict_from_parts(example, weights, intercept, stats)
            prediction = _clamp(prediction, 0.000001, 0.999999)
            weighted_loss += -outcome_weight * (
                label * math.log(prediction) + (1 - label) * math.log(1 - prediction)
            )
            total_weight += outcome_weight

        return {
            "example_count": len(examples),
            "log_loss": round(weighted_loss / (total_weight or len(examples) or 1), 6),
            "pairwise_accuracy": self._pairwise_accuracy(examples, weights, intercept, stats),
        }

    def _predict_from_parts(self, example, weights, intercept, stats):
        features = self._standardized_features(example, stats)
        return _sigmoid(intercept + sum(weights[name] * features[name] for name in FEATURE_NAMES))

    def _pairwise_accuracy(self, examples, weights, intercept, stats):
        grouped = defaultdict(list)
        for example in examples:
            request_id = example.get("request_id")
            if request_id:
                grouped[str(request_id)].append(example)

        correct = 0
        comparable = 0
        for rows in grouped.values():
            scored = [
                (
                    _safe_float(row.get("label")),
                    self._predict_from_parts(row, weights, intercept, stats),
                )
                for row in rows
            ]
            for index, left in enumerate(scored):
                for right in scored[index + 1:]:
                    if left[0] == right[0]:
                        continue
                    comparable += 1
                    if (left[0] > right[0] and left[1] > right[1]) or (right[0] > left[0] and right[1] > left[1]):
                        correct += 1

        if not comparable:
            return None
        return round(correct / comparable, 4)

    def _top_weights(self, weights, reverse):
        sorted_weights = sorted(
            weights.items(),
            key=lambda item: item[1],
            reverse=reverse,
        )
        if reverse:
            selected = [item for item in sorted_weights if item[1] > 0][:5]
        else:
            selected = [item for item in sorted_weights if item[1] < 0][:5]
        return [
            {"feature": name, "weight": round(weight, 6)}
            for name, weight in selected
        ]
