import argparse
from datetime import datetime
from pathlib import Path

from flask import Flask

from adventour_backend.models import db
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


def main():
    parser = argparse.ArgumentParser(description="Export Adventour recommendation events as training examples.")
    parser.add_argument(
        "--db-uri",
        default=default_database_uri(),
        help="SQLAlchemy database URI. Defaults to the local dev SQLite database.",
    )
    parser.add_argument("--output", required=True, help="Output path for .jsonl or .csv export.")
    parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since", help="Optional ISO timestamp, e.g. 2026-06-01T00:00:00.")
    args = parser.parse_args()

    app = create_app(args.db_uri)
    with app.app_context():
        service = RecommendationTrainingExportService()
        examples = service.build_examples(limit=args.limit, since=parse_since(args.since))
        if args.format == "csv":
            service.write_csv(args.output, examples)
        else:
            service.write_jsonl(args.output, examples)

    print(f"Exported {len(examples)} training examples to {args.output}")


if __name__ == "__main__":
    main()
