import argparse
import json
from datetime import datetime
from pathlib import Path

from flask import Flask

from adventour_backend.models import db
from adventour_backend.services.recommender_evaluation_service import RecommendationEvaluationService
from adventour_backend.services.recommender_model_service import LearningToRankBaselineService
from adventour_backend.services.recommender_training_service import RecommendationTrainingExportService


def default_database_uri():
    db_path = Path(__file__).resolve().parent / "instance" / "adventour_dev.db"
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


def parse_k_values(value):
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def print_quality(prefix, quality):
    if not quality or not quality.get("positive_quality_count"):
        print(f"{prefix}quality: no positive outcomes with authenticity fields yet")
        return

    print(
        f"{prefix}quality: local={quality['local_quality_score']:.4f} "
        f"authenticity={quality['average_positive_authenticity']:.4f} "
        f"hidden_gem={quality['average_positive_hidden_gem']:.4f} "
        f"chain={quality['average_positive_chain_probability']:.4f} "
        f"n={quality['positive_quality_count']}"
    )


def print_guardrails(prefix, guardrails):
    if not guardrails:
        return

    print(f"{prefix}guardrails: {guardrails['status']}")
    for check in guardrails.get("checks") or []:
        status = check["status"]
        if status == "pass":
            continue
        print(
            f"{prefix}  {status}: {check['label']} "
            f"{check['value']:.4f} target {check['target']} n={check['count']}"
        )


def print_group_balance(prefix, group_balance):
    if not group_balance or not group_balance.get("group_positive_count"):
        print(f"{prefix}group balance: no accepted group outcomes yet")
        return

    print(
        f"{prefix}group balance: lowest_fit={group_balance['average_lowest_member_fit']:.4f} "
        f"spread={group_balance['average_member_fit_spread']:.4f} "
        f"underserved_rate={group_balance['underserved_positive_rate']:.4f} "
        f"n={group_balance['group_positive_count']}"
    )


def print_event_anchor_quality(prefix, event_quality):
    if not event_quality or not event_quality.get("event_backed_positive_count"):
        print(f"{prefix}event anchors: no accepted event-backed outcomes yet")
        return

    print(
        f"{prefix}event anchors: rate={event_quality['event_backed_positive_rate']:.4f} "
        f"fit={event_quality['average_positive_event_fit']:.4f} "
        f"anchor={event_quality['event_anchor_score']:.4f} "
        f"reservation={event_quality['reservation_ready_rate']:.4f} "
        f"friend_signal={event_quality['friend_signal_positive_rate']:.4f} "
        f"n={event_quality['event_backed_positive_count']}"
    )


def print_report(evaluation):
    overall = evaluation["overall"]
    print("Adventour recommender evaluation")
    print("--------------------------------")
    print(f"Requests evaluated: {overall['request_count']}")
    print(f"Labeled examples:   {overall['labeled_example_count']}")
    print(f"Grouped examples:   {overall['grouped_example_count']}")
    print(f"Skipped no request: {overall['skipped_without_request']}")
    print(f"Skipped no rank:    {overall['skipped_without_rank']}")
    print(f"MRR:                {overall['mean_reciprocal_rank']:.4f}")
    print_quality("", overall.get("outcome_quality"))
    print_group_balance("", overall.get("group_balance"))
    print_event_anchor_quality("", overall.get("event_anchor_quality"))
    print_guardrails("", overall.get("guardrails"))
    print("")
    print("Top-k metrics")
    for k, metrics in overall["metrics_at_k"].items():
        print(
            f"@{k}: hit={metrics['hit_rate']:.4f} "
            f"precision={metrics['precision']:.4f} "
            f"avg_label={metrics['average_label']:.4f} "
            f"weighted_avg={metrics['weighted_average_label']:.4f} "
            f"ndcg={metrics['ndcg']:.4f}"
        )

    by_profile = evaluation.get("by_scoring_profile") or {}
    if by_profile:
        print("")
        print("By scoring profile")
        for profile, summary in by_profile.items():
            print(f"{profile}: requests={summary['request_count']} MRR={summary['mean_reciprocal_rank']:.4f}")
            print_quality("  ", summary.get("outcome_quality"))
            print_group_balance("  ", summary.get("group_balance"))
            print_event_anchor_quality("  ", summary.get("event_anchor_quality"))
            print_guardrails("  ", summary.get("guardrails"))
            for k, metrics in summary["metrics_at_k"].items():
                print(
                    f"  @{k}: hit={metrics['hit_rate']:.4f} "
                    f"precision={metrics['precision']:.4f} "
                    f"avg_label={metrics['average_label']:.4f} "
                    f"weighted_avg={metrics['weighted_average_label']:.4f} "
                    f"ndcg={metrics['ndcg']:.4f}"
                )

    by_segment = evaluation.get("by_segment") or {}
    if by_segment:
        print("")
        print("By recommendation segment")
        for segment, summary in by_segment.items():
            print(f"{segment}: requests={summary['request_count']} MRR={summary['mean_reciprocal_rank']:.4f}")
            print_quality("  ", summary.get("outcome_quality"))
            print_group_balance("  ", summary.get("group_balance"))
            print_event_anchor_quality("  ", summary.get("event_anchor_quality"))
            print_guardrails("  ", summary.get("guardrails"))
            for k, metrics in summary["metrics_at_k"].items():
                print(
                    f"  @{k}: hit={metrics['hit_rate']:.4f} "
                    f"precision={metrics['precision']:.4f} "
                    f"weighted_avg={metrics['weighted_average_label']:.4f} "
                    f"ndcg={metrics['ndcg']:.4f}"
                )


def print_comparison_report(comparison):
    print("Baseline shown-order evaluation")
    print("===============================")
    print_report(comparison["baseline"])
    print("")
    print("Learned model rerank evaluation")
    print("===============================")
    print_report(comparison["learned"])
    print("")
    print("Learned-vs-baseline delta")
    print("=========================")
    delta = comparison.get("delta") or {}
    print(f"MRR delta: {delta.get('mean_reciprocal_rank', 0):+.4f}")
    print(
        "Guardrails: "
        f"{delta.get('baseline_guardrail_status')} -> {delta.get('learned_guardrail_status')}"
    )
    exposure = delta.get("exposure_quality_at_k") or {}
    if exposure:
        first_k = sorted(exposure.keys(), key=lambda value: int(value))[0]
        top_exposure = exposure[first_k]
        print(
            f"Top-{first_k} exposure quality delta: "
            f"local={top_exposure.get('local_quality_score', 0):+.4f} "
            f"auth={top_exposure.get('average_authenticity', 0):+.4f} "
            f"chain={top_exposure.get('average_chain_probability', 0):+.4f}"
        )
    gate = comparison.get("promotion_gate") or {}
    if gate:
        print(
            f"Promotion gate: {gate.get('status')} "
            f"({'can promote' if gate.get('can_promote') else 'do not promote'})"
        )
        print(f"Promotion summary: {gate.get('summary')}")
        for check in gate.get("checks") or []:
            print(
                f"- {check['label']}: {check['status']} "
                f"({check.get('value')})"
            )
    for k, metrics in (delta.get("metrics_at_k") or {}).items():
        print(
            f"@{k}: hit={metrics['hit_rate']:+.4f} "
            f"precision={metrics['precision']:+.4f} "
            f"avg_label={metrics['average_label']:+.4f} "
            f"weighted_avg={metrics['weighted_average_label']:+.4f} "
            f"ndcg={metrics['ndcg']:+.4f}"
        )
    segment_delta = comparison.get("segment_delta") or {}
    if segment_delta:
        print("")
        print("Segment deltas")
        for segment, row in segment_delta.items():
            first_metrics = next(iter((row.get("metrics_at_k") or {}).values()), {})
            print(
                f"{segment}: MRR {row.get('mean_reciprocal_rank', 0):+.4f}, "
                f"hit {first_metrics.get('hit_rate', 0):+.4f}, "
                f"NDCG {first_metrics.get('ndcg', 0):+.4f}, "
                f"guardrails {row.get('baseline_guardrail_status')} -> {row.get('learned_guardrail_status')}"
            )


def main():
    parser = argparse.ArgumentParser(description="Evaluate Adventour recommendation ranking quality.")
    parser.add_argument(
        "--db-uri",
        default=default_database_uri(),
        help="SQLAlchemy database URI. Defaults to the local dev SQLite database.",
    )
    parser.add_argument("--input", help="Optional JSONL file from recommender_training_export.py.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since", help="Optional ISO timestamp, e.g. 2026-06-01T00:00:00.")
    parser.add_argument("--k", default="1,3,5", help="Comma-separated top-k cutoffs. Defaults to 1,3,5.")
    parser.add_argument(
        "--positive-threshold",
        type=float,
        default=0.75,
        help="Minimum label counted as a positive hit. Defaults to 0.75 so neutral ratings stay neutral.",
    )
    parser.add_argument("--model", help="Optional learned model JSON from recommender_train_model.py to compare against shown order.")
    parser.add_argument("--json", action="store_true", help="Print the full evaluation payload as JSON.")
    args = parser.parse_args()

    evaluation_service = RecommendationEvaluationService()
    if args.input:
        examples = evaluation_service.load_jsonl(args.input)
    else:
        app = create_app(args.db_uri)
        with app.app_context():
            examples = RecommendationTrainingExportService().build_examples(
                limit=args.limit,
                since=parse_since(args.since),
            )

    k_values = parse_k_values(args.k)
    if args.model:
        model = LearningToRankBaselineService().load_model(args.model)
        evaluation = evaluation_service.compare_with_learned_model(
            examples,
            model,
            k_values=k_values,
            positive_threshold=args.positive_threshold,
        )
    else:
        evaluation = evaluation_service.evaluate_examples(
            examples,
            k_values=k_values,
            positive_threshold=args.positive_threshold,
        )

    if args.json:
        print(json.dumps(evaluation, indent=2, sort_keys=True))
    elif args.model:
        print_comparison_report(evaluation)
    else:
        print_report(evaluation)


if __name__ == "__main__":
    main()
