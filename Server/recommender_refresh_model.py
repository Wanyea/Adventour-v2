import argparse
import json
from datetime import datetime
from pathlib import Path

from flask import Flask

from adventour_backend.models import db
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService
from adventour_backend.services.recommender_model_service import (
    LearningToRankBaselineService,
    learned_ranker_artifact_status,
)
from adventour_backend.services.recommender_training_service import RecommendationTrainingExportService


SERVER_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACT_DIR = SERVER_DIR / "instance" / "recommender"


def default_database_uri():
    db_path = SERVER_DIR / "instance" / "adventour_dev.db"
    return f"sqlite:///{db_path.as_posix()}"


def create_app(database_uri):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def parse_since(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def count_labeled_examples(examples):
    return sum(1 for example in examples if example.get("label") is not None)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _health_check(name, label, status, value, target, message):
    return {
        "name": name,
        "label": label,
        "status": status,
        "value": value,
        "target": target,
        "message": "" if status == "pass" else message,
    }


def summarize_training_data_health(examples):
    examples = examples or []
    labeled = [example for example in examples if example.get("label") is not None]
    positives = [example for example in labeled if _safe_float(example.get("label")) >= 0.75]
    negatives = [example for example in labeled if _safe_float(example.get("label")) <= 0.25]
    request_ids = {
        str(example.get("request_id"))
        for example in labeled
        if example.get("request_id")
    }
    group_examples = [
        example
        for example in labeled
        if _safe_float(example.get("member_fit_count")) > 1
        or _safe_float(example.get("group_min_fit"), None) is not None
    ]
    friend_adjusted = [example for example in labeled if example.get("friend_adjusted_retrieval")]
    event_backed = [example for example in labeled if example.get("local_event_backed")]
    event_reservation_ready = [
        example for example in event_backed if example.get("local_event_reservation_ready")
    ]
    event_source_ready = [
        example for example in event_backed if example.get("local_event_source_ready")
    ]
    event_friend_signal = [
        example
        for example in event_backed
        if _safe_float(example.get("local_event_friend_signal_count")) > 0
    ]
    event_social_signal = [
        example
        for example in event_backed
        if _safe_float(example.get("local_event_social_signal")) > 0
    ]

    labeled_count = len(labeled)
    request_count = len(request_ids)
    event_count = len(event_backed)

    checks = [
        _health_check(
            "labeled_outcomes",
            "Enough labeled outcomes",
            "pass" if labeled_count >= 50 else "warn" if labeled_count >= 12 else "fail",
            labeled_count,
            "50+ preferred, 12+ minimum for smoke tests",
            "Collect more accepts, rejects, arrivals, saves, shares, or ratings before trusting learned weights.",
        ),
        _health_check(
            "request_diversity",
            "Enough recommendation requests",
            "pass" if request_count >= 20 else "warn" if request_count >= 5 else "fail",
            request_count,
            "20+ distinct requests preferred, 5+ minimum",
            "Run more searches across launch points, filters, and friend groups so one basket does not dominate training.",
        ),
        _health_check(
            "positive_negative_mix",
            "Both positive and negative outcomes exist",
            "pass" if positives and negatives else "fail",
            {"positive": len(positives), "negative": len(negatives)},
            "At least one positive and one negative outcome",
            "Collect both accepts/ratings and rejects so the model can learn tradeoffs.",
        ),
        _health_check(
            "group_friend_signal",
            "Group/friend examples exist",
            "pass" if group_examples and friend_adjusted else "warn" if group_examples or friend_adjusted else "fail",
            {"group": len(group_examples), "friend_adjusted": len(friend_adjusted)},
            "Group and friend-adjusted examples",
            "Test with selected friends and group-friendly scout style before trusting friend blend weights.",
        ),
        _health_check(
            "event_anchor_signal",
            "Event-backed examples are actionable",
            "pass" if event_count and event_reservation_ready and event_source_ready else "warn" if event_count else "fail",
            {
                "event_backed": event_count,
                "reservation_ready": len(event_reservation_ready),
                "source_ready": len(event_source_ready),
            },
            "Event-backed examples with source and RSVP/reservation links",
            "Add or discover local events with source and RSVP links before trusting event-anchor weights.",
        ),
        _health_check(
            "event_social_signal",
            "Event social/friend signal exists",
            "pass" if event_friend_signal else "warn" if event_social_signal else "fail",
            {
                "friend_signal": len(event_friend_signal),
                "social_signal": len(event_social_signal),
            },
            "At least one event-backed outcome with selected-friend signal",
            "Ask friends to mark Interested/Going on local events before trusting social-event weights.",
        ),
    ]

    statuses = {check["status"] for check in checks}
    if "fail" in statuses:
        status = "needs_data"
    elif "warn" in statuses:
        status = "watch"
    else:
        status = "ready"

    return {
        "status": status,
        "summary": (
            "Training data is ready for learned-ranker evaluation."
            if status == "ready"
            else "Training data can run, but needs more representative friend/event outcomes."
            if status == "watch"
            else "Training data is too thin to trust beyond a smoke test."
        ),
        "counts": {
            "examples": len(examples),
            "labeled": labeled_count,
            "positive": len(positives),
            "negative": len(negatives),
            "requests": request_count,
            "group_examples": len(group_examples),
            "friend_adjusted": len(friend_adjusted),
            "event_backed": event_count,
            "event_reservation_ready": len(event_reservation_ready),
            "event_source_ready": len(event_source_ready),
            "event_friend_signal": len(event_friend_signal),
            "event_social_signal": len(event_social_signal),
        },
        "checks": checks,
    }


def print_training_data_health(health):
    counts = health.get("counts") or {}
    print("")
    print("Training data health")
    print("--------------------")
    print(f"Status:       {health.get('status')}")
    print(f"Summary:      {health.get('summary')}")
    print(
        "Coverage:     "
        f"{counts.get('labeled', 0)} labels, "
        f"{counts.get('requests', 0)} requests, "
        f"{counts.get('group_examples', 0)} group, "
        f"{counts.get('event_backed', 0)} event-backed, "
        f"{counts.get('event_friend_signal', 0)} friend-event"
    )
    for check in health.get("checks") or []:
        if check.get("status") == "pass":
            continue
        print(
            f"{check.get('status')}: {check.get('label')} "
            f"({check.get('value')} target {check.get('target')})"
        )


def print_model_report(model, model_path):
    training = model.get("training_summary") or {}
    validation = model.get("validation_summary") or {}
    print("Adventour learned ranker refreshed")
    print("----------------------------------")
    print(f"Model artifact:     {model_path}")
    print(f"Training examples:  {training.get('example_count', 0)}")
    print(f"Training log loss:  {training.get('log_loss', 0):.4f}")
    print(f"Training pairwise:  {training.get('pairwise_accuracy')}")
    print(f"Validation examples:{validation.get('example_count', 0) if validation else 0}")
    if validation:
        print(f"Validation log loss:{validation.get('log_loss', 0):.4f}")
        print(f"Validation pairwise:{validation.get('pairwise_accuracy')}")

    positives = ", ".join(
        f"{item['feature']}={item['weight']:.3f}"
        for item in model.get("top_positive_weights", [])
    ) or "none"
    negatives = ", ".join(
        f"{item['feature']}={item['weight']:.3f}"
        for item in model.get("top_negative_weights", [])
    ) or "none"
    print(f"Top positive signals: {positives}")
    print(f"Top negative signals: {negatives}")


def print_comparison_summary(comparison):
    baseline = comparison.get("baseline", {}).get("overall", {})
    learned = comparison.get("learned", {}).get("overall", {})
    delta = comparison.get("delta") or {}
    print("")
    print("Offline comparison")
    print("------------------")
    print(f"Baseline MRR: {baseline.get('mean_reciprocal_rank', 0):.4f}")
    print(f"Learned MRR:  {learned.get('mean_reciprocal_rank', 0):.4f}")
    print(f"MRR delta:    {delta.get('mean_reciprocal_rank', 0):+.4f}")
    print(
        "Guardrails:   "
        f"{delta.get('baseline_guardrail_status')} -> {delta.get('learned_guardrail_status')}"
    )
    event_delta = delta.get("event_anchor_quality") or {}
    if event_delta:
        print(
            "Event anchors:"
            f" rate={event_delta.get('event_backed_positive_rate', 0):+.4f}"
            f" fit={event_delta.get('average_positive_event_fit', 0):+.4f}"
            f" anchor={event_delta.get('event_anchor_score', 0):+.4f}"
            f" reservation={event_delta.get('reservation_ready_rate', 0):+.4f}"
            f" friend={event_delta.get('friend_signal_positive_rate', 0):+.4f}"
        )
    for k, metrics in (delta.get("metrics_at_k") or {}).items():
        print(
            f"@{k}: hit={metrics['hit_rate']:+.4f} "
            f"precision={metrics['precision']:+.4f} "
            f"ndcg={metrics['ndcg']:+.4f}"
        )


def print_live_readiness(readiness):
    feature = readiness.get("feature_compatibility") or {}
    gate = readiness.get("promotion_gate") or {}
    print("")
    print("Learned beta readiness")
    print("----------------------")
    print(f"Status:         {readiness.get('status')}")
    print(f"Ready in app:   {readiness.get('ready')}")
    print(f"Reason:         {readiness.get('reason')}")
    print(f"Feature schema: {feature.get('status')} ({feature.get('feature_schema_version')} -> {feature.get('expected_feature_schema_version')})")
    print(f"Promotion gate: {gate.get('status')} (can promote: {gate.get('can_promote')})")
    print(f"Message:        {readiness.get('message')}")
    if readiness.get("ready"):
        print("Next step:      Start the backend with this artifact and choose Learned beta.")
    else:
        print("Next step:      Keep using Auto scout/balanced ranking until this status is ready.")


def refresh_model(args):
    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    export_path = artifact_dir / "recommender-training.latest.jsonl"
    model_path = artifact_dir / "recommender-model.latest.json"
    baseline_eval_path = artifact_dir / "recommender-evaluation-baseline.latest.json"
    comparison_eval_path = artifact_dir / "recommender-evaluation-learned.latest.json"

    app = create_app(args.db_uri)
    with app.app_context():
        examples = RecommendationTrainingExportService().build_examples(
            limit=args.limit,
            since=parse_since(args.since),
        )
        RecommendationTrainingExportService().write_jsonl(export_path, examples)

    labeled_count = count_labeled_examples(examples)
    training_data_health = summarize_training_data_health(examples)
    print(f"Exported {len(examples)} examples to {export_path}")
    print(f"Labeled examples: {labeled_count}")
    print_training_data_health(training_data_health)
    if labeled_count < args.min_labeled:
        raise SystemExit(
            f"Need at least {args.min_labeled} labeled examples to train. "
            "Collect more accepts, rejects, ratings, arrivals, saves, or shares, "
            "or rerun with --min-labeled lowered for a smoke test."
        )

    model_service = LearningToRankBaselineService()
    model = model_service.train(
        examples,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        l2=args.l2,
        validation_fraction=args.validation_fraction,
    )

    evaluation_service = RecommendationEvaluationService()
    baseline_evaluation = evaluation_service.evaluate_examples(
        examples,
        k_values=args.k_values,
        positive_threshold=args.positive_threshold,
    )
    comparison = evaluation_service.compare_with_learned_model(
        examples,
        model,
        k_values=args.k_values,
        positive_threshold=args.positive_threshold,
    )
    model["promotion_gate"] = comparison.get("promotion_gate")
    model["promotion_evaluation"] = {
        "baseline_guardrail_status": (comparison.get("delta") or {}).get("baseline_guardrail_status"),
        "learned_guardrail_status": (comparison.get("delta") or {}).get("learned_guardrail_status"),
        "mean_reciprocal_rank_delta": (comparison.get("delta") or {}).get("mean_reciprocal_rank"),
        "metrics_at_k_delta": (comparison.get("delta") or {}).get("metrics_at_k"),
        "event_anchor_quality_delta": (comparison.get("delta") or {}).get("event_anchor_quality"),
    }
    model["training_data_health"] = training_data_health
    model["live_readiness"] = learned_ranker_artifact_status(model)
    model_service.write_model(model_path, model)
    write_json(baseline_eval_path, baseline_evaluation)
    write_json(comparison_eval_path, comparison)

    print_model_report(model, model_path)
    print_comparison_summary(comparison)
    print_live_readiness(model["live_readiness"])
    print("")
    print("To test in the app:")
    print(f"  powershell -ExecutionPolicy Bypass -File .\\scripts\\dev-backend.ps1 -LearnedRankerPath \"{model_path}\"")
    print("Then choose the Learned beta scout style in Discover.")

    return {
        "export_path": str(export_path),
        "model_path": str(model_path),
        "baseline_evaluation_path": str(baseline_eval_path),
        "comparison_evaluation_path": str(comparison_eval_path),
        "example_count": len(examples),
        "labeled_example_count": labeled_count,
        "training_data_health": training_data_health,
        "comparison": comparison,
        "live_readiness": model["live_readiness"],
    }


def parse_k_values(value):
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def main():
    parser = argparse.ArgumentParser(
        description="Export Adventour swipe data, train the local learned ranker, and write evaluation artifacts.",
    )
    parser.add_argument(
        "--db-uri",
        default=default_database_uri(),
        help="SQLAlchemy database URI. Defaults to the local dev SQLite database.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(DEFAULT_ARTIFACT_DIR),
        help="Where latest training/model/evaluation artifacts are written.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since", help="Optional ISO timestamp, e.g. 2026-06-01T00:00:00.")
    parser.add_argument("--min-labeled", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--positive-threshold", type=float, default=0.75)
    parser.add_argument("--k", default="1,3,5", help="Comma-separated top-k cutoffs. Defaults to 1,3,5.")
    parser.add_argument("--json", action="store_true", help="Print the final artifact summary as JSON.")
    args = parser.parse_args()
    args.k_values = parse_k_values(args.k)

    summary = refresh_model(args)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
