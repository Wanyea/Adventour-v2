import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from adventour_backend.models import User, db
from adventour_backend.providers.place_providers import GooglePlacesProvider, ProviderRegistry
from adventour_backend.services.recommender_service import RecommendationService


SERVER_DIR = Path(__file__).resolve().parent


def load_env(env_file):
    selected = Path(env_file) if env_file else SERVER_DIR / ".env.local"
    load_dotenv(selected, override=True)
    return selected


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def create_user(tags):
    user = User(
        firebase_uid="real-place-lab-user",
        email="real-place-lab@adventour.local",
        username="real_place_lab",
        display_name="Real Place Lab",
        preferences=",".join(tags),
    )
    db.session.add(user)
    db.session.commit()
    return user


def print_result(result):
    print(f"Query tags: {', '.join(result['query_tags'])}")
    if result["provider_errors"]:
        print(f"Provider errors: {json.dumps(result['provider_errors'], indent=2)}")
    if not result["recommendations"]:
        print("No recommendations returned.")
        return

    for index, item in enumerate(result["recommendations"], start=1):
        components = item["components"]
        display = item["display"]
        print(f"\n{index}. {item['name']} | score={item['score']} | distance={item['distance_meters']}m")
        print(f"   rating={display.get('rating')} reviews={display.get('user_ratings_total')} price={display.get('price_level')}")
        print(f"   types={', '.join(display.get('types') or [])}")
        print(f"   explanation: {item['explanation']}")
        print(
            "   components: "
            f"personal={components['personal_fit']} "
            f"group={components['group_fit']} "
            f"auth={components['authenticity']} "
            f"quality={components['quality']} "
            f"context={components['context_fit']} "
            f"chain_penalty={components['chain_penalty']} "
            f"price_penalty={components['price_penalty']}"
        )


def main():
    parser = argparse.ArgumentParser(description="Run Adventour ranking against live Google Places candidates.")
    parser.add_argument("--env-file", default=None, help="Path to the backend env file. Defaults to Server/.env.local.")
    parser.add_argument("--lat", type=float, default=37.421998333333335, help="Search latitude.")
    parser.add_argument("--lng", type=float, default=-122.084, help="Search longitude.")
    parser.add_argument("--radius", type=int, default=1200, help="Search radius in meters.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum recommendations to print.")
    parser.add_argument("--tags", nargs="+", default=["cafe", "restaurant", "park"], help="User taste tags.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON result.")
    args = parser.parse_args()

    env_path = load_env(args.env_file)
    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit(f"GOOGLE_API_KEY is not configured. Checked {env_path}.")

    app = create_app()
    with app.app_context():
        db.create_all()
        user = create_user(args.tags)
        service = RecommendationService(
            ProviderRegistry(providers=[GooglePlacesProvider()])
        )
        result = service.recommend(
            user=user,
            location={"latitude": args.lat, "longitude": args.lng},
            radius_meters=args.radius,
            constraints={"limit": args.limit, "avoid_chains": True},
        )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
