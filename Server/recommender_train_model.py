import argparse
import json
from datetime import datetime
from pathlib import Path

from flask import Flask

from adventour_backend.models import db
from adventour_backend.services.recommender_model_service import (
    LearningToRankBaselineService,
    learned_ranker_artifact_status,
)
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


def load_jsonl(path):
    examples = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                examples.append(json.loads(stripped))
    return examples


def print_report(model, output_path):
    training = model.get("training_summary") or {}
    validation = model.get("validation_summary") or {}
    print("Adventour learned ranker baseline")
    print("---------------------------------")
    print(f"Model artifact: {output_path}")
    print(f"Training examples:   {training.get('example_count', 0)}")
    print(f"Training log loss:   {training.get('log_loss', 0):.4f}")
    print(f"Training pairwise:   {training.get('pairwise_accuracy')}")
    if validation:
        print(f"Validation examples: {validation.get('example_count', 0)}")
        print(f"Validation log loss: {validation.get('log_loss', 0):.4f}")
        print(f"Validation pairwise: {validation.get('pairwise_accuracy')}")
    else:
        print("Validation examples: 0")

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
    readiness = model.get("live_readiness") or learned_ranker_artifact_status(model)
    print("")
    print("Learned beta readiness")
    print("----------------------")
    print(f"Status:       {readiness.get('status')}")
    print(f"Ready in app: {readiness.get('ready')}")
    print(f"Reason:       {readiness.get('reason')}")
    print(f"Message:      {readiness.get('message')}")
    if not readiness.get("ready"):
        print("Next step:    Run recommender_refresh_model.py so offline promotion gates can evaluate this artifact.")


def main():
    parser = argparse.ArgumentParser(description="Train Adventour's dependency-free learned ranker baseline.")
    parser.add_argument(
        "--db-uri",
        default=default_database_uri(),
        help="SQLAlchemy database URI. Defaults to the local dev SQLite database.",
    )
    parser.add_argument("--input", help="Optional JSONL file from recommender_training_export.py.")
    parser.add_argument("--output", required=True, help="Output path for the learned model JSON artifact.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since", help="Optional ISO timestamp, e.g. 2026-06-01T00:00:00.")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--json", action="store_true", help="Print the full model payload as JSON.")
    args = parser.parse_args()

    if args.input:
        examples = load_jsonl(args.input)
    else:
        app = create_app(args.db_uri)
        with app.app_context():
            examples = RecommendationTrainingExportService().build_examples(
                limit=args.limit,
                since=parse_since(args.since),
            )

    service = LearningToRankBaselineService()
    model = service.train(
        examples,
        iterations=args.iterations,
        learning_rate=args.learning_rate,
        l2=args.l2,
        validation_fraction=args.validation_fraction,
    )
    model["live_readiness"] = learned_ranker_artifact_status(model)
    service.write_model(args.output, model)

    if args.json:
        print(json.dumps(model, indent=2, sort_keys=True))
    else:
        print_report(model, args.output)


if __name__ == "__main__":
    main()
