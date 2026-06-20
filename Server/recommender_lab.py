import argparse
import json

from flask import Flask

from adventour_backend.models import db, User
from adventour_backend.services.recommender_service import RecommendationService


class MockProviderRegistry:
    def __init__(self, candidates):
        self.candidates = candidates

    def search(self, tags, location, radius_meters=3200, constraints=None):
        return self.candidates, []


def candidate(name, place_id, types, rating, ratings_total, lat=37.422, lng=-122.084, price_level=2):
    return {
        "provider": "lab",
        "place_id": place_id,
        "name": name,
        "types": types,
        "rating": rating,
        "user_ratings_total": ratings_total,
        "price_level": price_level,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "business_status": "OPERATIONAL",
    }


SCENARIOS = {
    "local_food": {
        "users": [
            {"email": "local@example.com", "preferences": ["restaurant", "cafe"]},
        ],
        "candidates": [
            candidate("Starbucks", "chain-1", ["cafe", "restaurant"], 4.7, 5000),
            candidate("Maya's Corner Cafe", "gem-1", ["cafe", "restaurant"], 4.8, 42),
            candidate("Tourist Pier Grill", "tourist-1", ["restaurant"], 4.4, 9000),
            candidate("Quiet Sculpture Garden", "garden-1", ["park", "tourist_attraction"], 4.8, 40),
        ],
    },
    "group_blend": {
        "users": [
            {"email": "food@example.com", "preferences": ["restaurant", "cafe"]},
            {"email": "art@example.com", "preferences": ["museum", "art_gallery"]},
        ],
        "candidates": [
            candidate("Cafe Gallery", "balanced-1", ["cafe", "art_gallery"], 4.7, 75),
            candidate("Only Burgers", "food-only-1", ["restaurant"], 4.9, 80),
            candidate("Only Museum", "art-only-1", ["museum"], 4.9, 80),
            candidate("Museum Cafe Chain", "chain-2", ["museum", "cafe"], 4.5, 2000),
        ],
    },
    "budget": {
        "users": [
            {"email": "budget@example.com", "preferences": ["restaurant"]},
        ],
        "constraints": {"limit": 10, "avoid_chains": True, "price_max": 2},
        "candidates": [
            candidate("Affordable Noodles", "cheap-1", ["restaurant"], 4.5, 60, price_level=1),
            candidate("Expensive Tasting Room", "expensive-1", ["restaurant"], 4.8, 50, price_level=4),
            candidate("Local Bakery", "bakery-1", ["bakery", "cafe"], 4.7, 30, price_level=1),
        ],
    },
}


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def create_user(email, preferences):
    username = email.split("@")[0]
    user = User(
        firebase_uid=f"lab-{username}",
        email=email,
        username=username,
        display_name=username,
        preferences=",".join(preferences),
    )
    db.session.add(user)
    db.session.commit()
    return user


def run_scenario(name):
    scenario = SCENARIOS[name]
    app = create_app()

    with app.app_context():
        db.create_all()
        users = [create_user(item["email"], item["preferences"]) for item in scenario["users"]]
        service = RecommendationService(MockProviderRegistry(scenario["candidates"]))
        result = service.recommend(
            user=users[0],
            member_ids=[user.id for user in users[1:]],
            location={"latitude": 37.421998333333335, "longitude": -122.084},
            radius_meters=3200,
            constraints=scenario.get("constraints", {"limit": 10, "avoid_chains": True}),
        )
        return result


def print_result(name, result):
    print(f"\nScenario: {name}")
    print(f"Query tags: {', '.join(result['query_tags'])}")
    print(f"Members: {result['member_count']}")
    print("")

    for index, item in enumerate(result["recommendations"], start=1):
        components = item["components"]
        print(f"{index}. {item['name']} | score={item['score']} | distance={item['distance_meters']}m")
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
    parser = argparse.ArgumentParser(description="Run deterministic Adventour recommender scenarios.")
    parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS), default="local_food")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a readable report.")
    args = parser.parse_args()

    result = run_scenario(args.scenario)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(args.scenario, result)


if __name__ == "__main__":
    main()
